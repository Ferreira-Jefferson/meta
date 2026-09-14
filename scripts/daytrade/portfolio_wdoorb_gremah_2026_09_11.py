"""HIPOTESE: portfolio wdo_orb (WDO@) + gremah/PMAM3 combinados por peso de
minima-variancia (MaxDD), caixa fisicamente SEPARADO (sem capital
compartilhado), pesos FIXOS recalibrados so' periodicamente.

Nao mexe em sinal/execucao de nenhum robo -- os dois rodam com a config de
PRODUCAO (`strategy.daytrade.registry.get_daytrade_robot`), no desenho de
execucao FECHADO (entrada/alvo por ordem-limite, so' o stop a mercado) que
ja e' o default de cada classe.

## Janela

`wdo_orb`: janela CONGELADA IS+OOS do WDO@ (`data/raw_ticks/WDO_A_f1.parquet`,
coluna `janela` ja rotulada -- IS 72 pregoes 2026-02-27..2026-06-12, OOS 51
pregoes 2026-06-15..2026-08-25). Mesmo split usado em toda a familia WDO F1
(ver `scripts/daytrade/wdof1_deslize_alvo_is_oos_2026_09_08.py`).

`gremah`/PMAM3: `market_data_intraday.storage.load_m1("PMAM3")`, filtrado ao
REGIME de preco atual (>= 2025-12-16, mesmo corte de
`scripts/daytrade/gremah_defesa_corte_sweep_2026_09_03.py` -- e' o corte onde
a calibracao de producao em TICKS (1,1,16) foi medida; rodar contra o regime
antigo, R$4,53, misturaria duas geometrias de mercado diferentes numa serie
so').

## Capital

`wdo_orb`: R$375,00, o piso REAL de 1 contrato de WDO@ (margem R$150 x
buffer 2,0 x reserva 1,25 -- CLAUDE.md).

`gremah`/PMAM3: `capital_minimo_brl(preco_abertura_do_1o_pregao_da_janela)`
-- o minimo REAL do simbolo NO PRECO DE HOJE, nao um valor nocional. Isto e'
BEM menor que os ~R$1.000 assumidos na hipotese original: a PMAM3 colapsou
para ~R$0,13-0,15 (ver a memoria do projeto `pmam3_colapso_de_preco`), entao
`capital_minimo_brl` fica na casa de R$26-30, nao R$1.000. Reportado como
CORRECAO ao racional da hipotese -- nao inventado aqui, e' o numero que o
proprio metodo do projeto manda usar.

## O que este script mede

1. Series de P&L DIARIO de cada robo, na janela de CADA UM (nao cruzadas).
2. Correlacao de Pearson dos retornos diarios NORMALIZADOS (P&L / capital
   proprio) no INTERSECT calendarico das duas janelas (os mesmos ~123
   pregoes do wdo_orb, que cabem dentro da janela mais longa da gremah).
3. Varredura de peso w em [0,1] (passo 0,05) sobre os retornos normalizados,
   MINIMIZANDO o MaxDD da serie combinada `w*r_wdo + (1-w)*r_gremah` -- nunca
   maximizando retorno. Comparado contra w=0,5 (ingenuo) e os dois extremos
   (robo isolado).
4. Combinado em R$ NATURAL (caixa realmente separado, cada robo com o
   PROPRIO capital minimo) -- o numero que de fato descreve "rodar os dois
   ao mesmo tempo, dinheiro de bolsos diferentes".

## Paralelismo

`ProcessPoolExecutor`, UMA tarefa por (robo, janela) -- 3 tarefas (wdo_orb
IS, wdo_orb OOS, gremah janela unica). O peso w e' varrido DEPOIS, em
memoria, sobre series ja' prontas (nao e' backtest por peso -- nao precisa
de pool).

## Teste pequeno primeiro

`--smoke` roda so' os 10 primeiros pregoes de cada janela antes da rodada
cheia -- convencao do projeto ("o minimo que refuta primeiro").
"""
from __future__ import annotations

import argparse
import io
import contextlib
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
# Precisa estar no sys.path do processo PAI tambem (nao so' dos filhos): o
# resultado que volta pela fila do ProcessPoolExecutor carrega objetos de
# `backtest.intraday.machine.IntradayTrade` dentro de `dict`, e o pai precisa
# do modulo importavel para DESSERIALIZAR a resposta, mesmo sem chamar
# nenhuma funcao de `backtest` diretamente.
sys.path.insert(0, str(RAIZ / "src"))
WDO_CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

REGIME_START_PMAM3 = "2025-12-16"
CAPITAL_WDO_BRL = 375.0


def _wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """IC95% de Wilson para uma proporcao k/n. `(nan, nan)` se n=0."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centro = p + z * z / (2 * n)
    margem = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = (centro - margem) / denom
    hi = (centro + margem) / denom
    return (max(0.0, lo), min(1.0, hi))


def _max_drawdown_pct(equity_relativo: pd.Series) -> float:
    """MaxDD %, sobre uma serie que comeca em 1.0 (retornos acumulados)."""
    if equity_relativo.empty:
        return float("nan")
    pico = equity_relativo.cummax()
    dd = (equity_relativo - pico) / pico
    return float(dd.min()) * 100.0


def _bars_wdo(janela: str, smoke: bool) -> pd.DataFrame:
    """Le' a fatia tick da janela. `smoke=True` filtra pelos 10 primeiros
    `dia` NO PROPRIO LEITOR do parquet (coluna `dia` ja rotulada) -- ler o
    OHLCV inteiro da janela (14,4M/6,2M linhas) so' para descartar 92% dele
    depois seria o mesmo erro de memoria/tempo que a docstring de
    `wdof1_deslize_alvo_is_oos_2026_09_08.py` ja documentou."""
    if smoke:
        dias_df = pd.read_parquet(WDO_CACHE, columns=["dia"],
                                   filters=[("janela", "==", janela)])
        dias = sorted(dias_df["dia"].unique())[:10]
        df = pd.read_parquet(
            WDO_CACHE,
            columns=["open", "high", "low", "close", "volume"],
            filters=[("janela", "==", janela), ("dia", "in", dias)],
        )
        return df.sort_index()
    df = pd.read_parquet(
        WDO_CACHE,
        columns=["open", "high", "low", "close", "volume"],
        filters=[("janela", "==", janela)],
    )
    return df.sort_index()


def _roda_wdo_orb(janela: str, smoke: bool) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars_wdo(janela, smoke)

    robo = get_daytrade_robot("wdo_orb")
    profile = profile_for("WDO@")
    cfg = config_for(
        profile, trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_WDO_BRL,
        target_fills_as_maker=robo.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, robo, cfg)
    dt = time.perf_counter() - t0

    equity = resultado.equity_curve
    daily = equity.groupby(equity.index.date).last()
    # `groupby(...date)` devolve indice de OBJETOS `datetime.date` -- hash
    # diferente de `pd.Timestamp` mesmo quando `==` da' True. Sem esta
    # conversao, `reindex(overlap)` mais abaixo (overlap e' `DatetimeIndex`)
    # casa NADA por hash e devolve tudo NaN, em silencio.
    daily.index = pd.to_datetime(daily.index)
    daily_pnl = daily.diff()
    if len(daily) > 0:
        daily_pnl.iloc[0] = daily.iloc[0] - CAPITAL_WDO_BRL
    dias_janela = sorted(set(bars.index.date))
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in resultado.trades}
    dias_sem_trade = [d for d in dias_janela if d not in dias_com_trade]

    return dict(
        leg="wdo_orb", janela=janela, capital=CAPITAL_WDO_BRL,
        daily_pnl=daily_pnl, trades=resultado.trades,
        equity_curve=equity, dias_janela=dias_janela,
        dias_sem_trade=dias_sem_trade,
        fila_calibrada=resultado.fila_entrada_qty, dt=dt,
        wiped_out_at=resultado.wiped_out_at,
    )


def _roda_gremah(smoke: bool) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.registry import get_daytrade_robot

    df = load_m1("PMAM3").sort_index()
    regime_start = pd.Timestamp(REGIME_START_PMAM3, tz=df.index.tz)
    df = df.loc[df.index >= regime_start]
    if smoke:
        dias = sorted(set(df.index.date))[:10]
        df = df[[d in set(dias) for d in df.index.date]]

    preco_ref = float(df.iloc[0]["open"])
    capital = capital_minimo_brl(preco_ref)

    robo = get_daytrade_robot("gremah")  # symbol default = PMAM3
    profile = profile_for("PMAM3")
    cfg = config_for(
        profile, trade_tick_value=0.01, trade_tick_size=0.01,
        initial_capital=capital,
        target_fills_as_maker=robo.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    t0 = time.perf_counter()
    resultado = run_intraday_backtest(df, robo, cfg)
    dt = time.perf_counter() - t0

    equity = resultado.equity_curve
    daily = equity.groupby(equity.index.date).last()
    daily.index = pd.to_datetime(daily.index)
    daily_pnl = daily.diff()
    if len(daily) > 0:
        daily_pnl.iloc[0] = daily.iloc[0] - capital
    dias_janela = sorted(set(df.index.date))
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in resultado.trades}
    dias_sem_trade = [d for d in dias_janela if d not in dias_com_trade]

    return dict(
        leg="gremah", janela="full", capital=capital,
        preco_ref=preco_ref,
        daily_pnl=daily_pnl, trades=resultado.trades,
        equity_curve=equity, dias_janela=dias_janela,
        dias_sem_trade=dias_sem_trade,
        fila_calibrada=resultado.fila_entrada_qty, dt=dt,
        wiped_out_at=resultado.wiped_out_at,
    )


def _stats_leg(trades: list, capital: float, daily_pnl: pd.Series,
               dias_janela: list, dias_sem_trade: list,
               equity_curve_barra: pd.Series | None = None) -> dict:
    liquido = float(sum(t.pnl_brl for t in trades))
    n = len(trades)
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    k_win = len(ganhos)
    win_pct = 100.0 * k_win / n if n else float("nan")
    ci_lo, ci_hi = _wilson_ci(k_win, n)
    ganho_medio = float(np.mean(ganhos)) if ganhos else 0.0
    perda_media_abs = float(np.mean([abs(p) for p in perdas])) if perdas else 0.0
    breakeven_emp = (100.0 * perda_media_abs / (ganho_medio + perda_media_abs)
                     if (ganho_medio + perda_media_abs) > 0 else float("nan"))
    n_stops = sum(1 for t in trades if t.exit_reason.value == "stop")

    # MaxDD sobre a curva de patrimonio POR BARRA (a mesma que
    # `backtest.intraday.report.maxdd_brl` usa) quando disponivel -- mede a
    # queda INTRADIARIA de verdade, nao so' o fecha-a-fecha diario (que
    # esconde uma queda e recuperacao dentro do mesmo pregao). A serie diaria
    # (`daily_pnl`) so' entra como fallback para a analise COMBINADA, onde
    # nao ha' curva por barra comum aos dois instrumentos.
    if equity_curve_barra is not None and len(equity_curve_barra):
        pico = equity_curve_barra.cummax()
        maxdd_brl = float((pico - equity_curve_barra).max())
        maxdd_pct = float((((pico - equity_curve_barra) / pico).max()) * 100.0)
    else:
        equity_rel = 1.0 + daily_pnl.cumsum() / capital
        maxdd_pct = -_max_drawdown_pct(equity_rel)
        maxdd_brl = float((capital + daily_pnl.cumsum()).cummax().sub(
            capital + daily_pnl.cumsum()).max()) if len(daily_pnl) else float("nan")

    dias_positivos = int((daily_pnl > 0).sum())
    dias_negativos = int((daily_pnl < 0).sum())
    dias_zero = int((daily_pnl == 0).sum())
    frac_positivos = 100.0 * dias_positivos / len(daily_pnl) if len(daily_pnl) else float("nan")

    return dict(
        liquido_brl=liquido, trades=n, n_stops=n_stops,
        win_pct=win_pct, ci95=(ci_lo * 100, ci_hi * 100),
        breakeven_emp_pct=breakeven_emp,
        maxdd_pct=maxdd_pct, maxdd_brl=maxdd_brl,
        pregoes=len(dias_janela), pregoes_sem_trade=len(dias_sem_trade),
        frac_dias_positivos=frac_positivos,
        dias_positivos=dias_positivos, dias_negativos=dias_negativos,
        dias_zero=dias_zero,
        capital=capital,
    )


def _fmt_pct(x: float) -> str:
    return "n/d" if (x is None or (isinstance(x, float) and math.isnan(x))) else f"{x:.2f}%"


def _imprime_stats(rotulo: str, s: dict) -> None:
    print(f"\n=== {rotulo} ===")
    print(f"  capital usado        R${s['capital']:.2f}")
    print(f"  liquido R$           {s['liquido_brl']:.2f}")
    print(f"  trades               {s['trades']}  (stops: {s['n_stops']})")
    print(f"  win%                 {_fmt_pct(s['win_pct'])}  IC95 [{_fmt_pct(s['ci95'][0])} ; {_fmt_pct(s['ci95'][1])}]")
    print(f"  breakeven empirico   {_fmt_pct(s['breakeven_emp_pct'])}")
    print(f"  MaxDD                {_fmt_pct(s['maxdd_pct'])}  (R${s['maxdd_brl']:.2f})")
    print(f"  pregoes              {s['pregoes']}  (sem trade: {s['pregoes_sem_trade']})")
    print(f"  dias +/-/0           {s['dias_positivos']}/{s['dias_negativos']}/{s['dias_zero']}"
          f"  ({_fmt_pct(s['frac_dias_positivos'])} positivos)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                     help="so' os 10 primeiros pregoes de cada janela (teste pequeno)")
    args = ap.parse_args()

    if not WDO_CACHE.exists():
        raise SystemExit(f"cache ausente: {WDO_CACHE}")

    print(f"[portfolio] modo {'SMOKE (10 pregoes/janela)' if args.smoke else 'CHEIO'}\n", flush=True)

    tarefas = [("wdo_orb", "IS"), ("wdo_orb", "OOS"), ("gremah", None)]
    resultados: dict = {}
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures = {}
        for leg, janela in tarefas:
            if leg == "wdo_orb":
                fut = pool.submit(_roda_wdo_orb, janela, args.smoke)
            else:
                fut = pool.submit(_roda_gremah, args.smoke)
            futures[fut] = (leg, janela)
        for fut in as_completed(futures):
            leg, janela = futures[fut]
            r = fut.result()
            resultados[(leg, janela)] = r
            print(f"[ok] {leg} {janela or ''} -- {r['dt']:.1f}s, "
                  f"{len(r['trades'])} trades, {len(r['dias_janela'])} pregoes, "
                  f"fila_entrada_qty={r['fila_calibrada']}, "
                  f"wiped_out={r['wiped_out_at']}", flush=True)

    # ---- concatena as duas pernas do wdo_orb (IS + OOS) numa serie so' ----
    wdo_is = resultados[("wdo_orb", "IS")]
    wdo_oos = resultados[("wdo_orb", "OOS")]
    wdo_trades = list(wdo_is["trades"]) + list(wdo_oos["trades"])
    wdo_daily = pd.concat([wdo_is["daily_pnl"], wdo_oos["daily_pnl"]]).sort_index()
    wdo_dias_janela = wdo_is["dias_janela"] + wdo_oos["dias_janela"]
    wdo_dias_sem_trade = wdo_is["dias_sem_trade"] + wdo_oos["dias_sem_trade"]

    gremah = resultados[("gremah", None)]

    # MaxDD por leg reportado SEPARADO por janela (IS/OOS nunca se misturam
    # numa curva de patrimonio so' -- cada janela comeca do MESMO capital
    # inicial, concatenar as duas faria parecer que o capital dobrou entre
    # elas). O agregado IS+OOS (`stats_wdo`) usa a serie DIARIA (retorno,
    # nao patrimonio por barra) so' para trades/win%/liquido -- o MaxDD dele
    # cai para o fallback diario (fecha-a-fecha), que e' informativo mas nao
    # substitui o MaxDD intradiario de cada janela isolada.
    stats_wdo_is = _stats_leg(wdo_is["trades"], CAPITAL_WDO_BRL, wdo_is["daily_pnl"],
                               wdo_is["dias_janela"], wdo_is["dias_sem_trade"],
                               equity_curve_barra=wdo_is["equity_curve"])
    stats_wdo_oos = _stats_leg(wdo_oos["trades"], CAPITAL_WDO_BRL, wdo_oos["daily_pnl"],
                                wdo_oos["dias_janela"], wdo_oos["dias_sem_trade"],
                                equity_curve_barra=wdo_oos["equity_curve"])
    stats_wdo = _stats_leg(wdo_trades, CAPITAL_WDO_BRL, wdo_daily,
                            wdo_dias_janela, wdo_dias_sem_trade)
    stats_gremah = _stats_leg(gremah["trades"], gremah["capital"], gremah["daily_pnl"],
                               gremah["dias_janela"], gremah["dias_sem_trade"],
                               equity_curve_barra=gremah["equity_curve"])

    _imprime_stats("wdo_orb (WDO@, IS, R$375) -- MaxDD intradiario (por barra)", stats_wdo_is)
    _imprime_stats("wdo_orb (WDO@, OOS, R$375) -- MaxDD intradiario (por barra)", stats_wdo_oos)
    _imprime_stats("wdo_orb (WDO@, IS+OOS agregado) -- MaxDD FECHA-A-FECHA diario (fallback)", stats_wdo)
    _imprime_stats(f"gremah/PMAM3 (regime >= {REGIME_START_PMAM3}, "
                    f"preco ref R${gremah['preco_ref']:.2f}, R${gremah['capital']:.2f}) "
                    f"-- MaxDD intradiario (por barra)",
                    stats_gremah)

    # ---- overlap calendarico para correlacao + peso -----------------------
    idx_wdo = pd.DatetimeIndex(wdo_daily.index)
    idx_gre = pd.DatetimeIndex(gremah["daily_pnl"].index)
    overlap = idx_wdo.intersection(idx_gre)
    print(f"\n[overlap] {len(overlap)} pregoes em comum de {len(idx_wdo)} (wdo_orb) "
          f"e {len(idx_gre)} (gremah)")

    if len(overlap) < 10:
        print("[overlap] MENOS DE 10 PREGOES EM COMUM -- correlacao/peso NAO confiaveis, "
              "reportando mesmo assim por transparencia.")

    r_wdo = (wdo_daily.reindex(overlap) / CAPITAL_WDO_BRL).astype(float)
    r_gre = (gremah["daily_pnl"].reindex(overlap) / gremah["capital"]).astype(float)
    r_wdo = r_wdo.fillna(0.0)
    r_gre = r_gre.fillna(0.0)

    corr = float(np.corrcoef(r_wdo.values, r_gre.values)[0, 1]) if len(overlap) > 1 else float("nan")
    print(f"[overlap] correlacao de Pearson (retornos diarios normalizados): {corr:.4f}")

    # ---- varredura de peso w minimizando MaxDD -----------------------------
    melhores = []
    for w in np.linspace(0.0, 1.0, 21):
        combinado = w * r_wdo + (1 - w) * r_gre
        equity_rel = 1.0 + combinado.cumsum()
        dd = _max_drawdown_pct(equity_rel)
        liquido_norm = float(combinado.sum())
        melhores.append((round(float(w), 2), dd, liquido_norm))

    melhores.sort(key=lambda t: t[1], reverse=True)  # dd e' negativo; maior (menos negativo) = melhor
    print("\n=== varredura de peso w (fracao alocada ao wdo_orb) -- retornos NORMALIZADOS ===")
    print(f"{'w':>6}  {'MaxDD%':>10}  {'retorno_norm_acum':>18}")
    for w, dd, liq in sorted(melhores, key=lambda t: t[0]):
        marca = "  <- MENOR |MaxDD|" if (w, dd, liq) == melhores[0] else ""
        print(f"{w:6.2f}  {dd:10.2f}  {liq:18.4f}{marca}")

    w_wdo_only = next(t for t in melhores if t[0] == 1.0)
    w_gre_only = next(t for t in melhores if t[0] == 0.0)
    w_5050 = next(t for t in melhores if t[0] == 0.5)
    w_star = melhores[0]

    print(f"\n[resumo pesos] wdo_orb sozinho (w=1,0): MaxDD {w_wdo_only[1]:.2f}%")
    print(f"[resumo pesos] gremah sozinho  (w=0,0): MaxDD {w_gre_only[1]:.2f}%")
    print(f"[resumo pesos] 50/50 ingenuo   (w=0,5): MaxDD {w_5050[1]:.2f}%")
    print(f"[resumo pesos] otimo (min |MaxDD|) w={w_star[0]:.2f}: MaxDD {w_star[1]:.2f}%")

    # ---- combinado em R$ NATURAL (caixa realmente separado) --------------
    capital_total = CAPITAL_WDO_BRL + gremah["capital"]
    pnl_wdo_overlap = wdo_daily.reindex(overlap).fillna(0.0)
    pnl_gre_overlap = gremah["daily_pnl"].reindex(overlap).fillna(0.0)
    pnl_combinado_brl = pnl_wdo_overlap + pnl_gre_overlap
    equity_combinada = capital_total + pnl_combinado_brl.cumsum()
    maxdd_natural_brl = float(equity_combinada.cummax().sub(equity_combinada).max())
    maxdd_natural_pct = 100.0 * maxdd_natural_brl / capital_total
    liquido_combinado = float(pnl_combinado_brl.sum())
    dias_pos_comb = int((pnl_combinado_brl > 0).sum())

    print(f"\n=== combinado NATURAL (caixa separado: R${CAPITAL_WDO_BRL:.2f} wdo_orb "
          f"+ R${gremah['capital']:.2f} gremah = R${capital_total:.2f}), so' no overlap ===")
    print(f"  liquido R$ combinado   {liquido_combinado:.2f}")
    print(f"  MaxDD combinado        R${maxdd_natural_brl:.2f}  ({maxdd_natural_pct:.2f}% do capital total)")
    print(f"  dias positivos         {dias_pos_comb}/{len(overlap)} "
          f"({100.0*dias_pos_comb/len(overlap) if len(overlap) else float('nan'):.2f}%)")
    print(f"  peso natural (capital) w_wdo={CAPITAL_WDO_BRL/capital_total:.3f} "
          f"w_gremah={gremah['capital']/capital_total:.3f}")

    print("\n[fim] ver o corpo do script para a leitura completa dos resultados.")


if __name__ == "__main__":
    main()
