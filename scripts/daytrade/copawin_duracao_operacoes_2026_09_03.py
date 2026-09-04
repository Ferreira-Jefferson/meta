"""Pesquisa pedida pelo dono em 2026-09-03 ("estudar a media de tempo que leva
cada operacao") aplicada ao `CopaWin` (WIN@, M1) -- baseline de PRODUCAO (sem
a defesa de recuo nova, ver `strategy.daytrade.lab.copa_win.CopaWin.defesa_
ativa`), nos DOIS niveis de capital ja usados no sweep irmao
(`copawin_defesa_recuo_sweep_2026_09_03.py`): R$434,00 (capital REAL atual do
slot `dt-copa_win-win@-shadow`) e R$3.000,00 (folga, livre do teto de
capital).

## O que este script faz

1. Roda o baseline (config de PRODUCAO, `get_daytrade_robot("copa_win",
   symbol="WIN@")`, defesa desligada) nos dois niveis de capital.
2. Para cada `IntradayTrade`, calcula a DURACAO (`exit_ts - entry_ts`, em
   MINUTOS -- faz mais sentido aqui que segundos, dado que a granularidade e'
   M1) e agrupa por `exit_reason` (STOP/TARGET/FORCED_FLATTEN -- os 3 unicos
   valores possiveis no baseline, ja que a defesa esta' desligada e nunca
   produz `SIGNAL`).
3. `describe()` completo por grupo (N, media, mediana, desvio, p25/p75,
   min/max) -- em MINUTOS e em BARRAS M1 (identico a minutos aqui: a
   granularidade e' M1, 1 barra = 1 minuto, entao "quantas barras a operacao
   durou" e' o MESMO numero que "quantos minutos", sem precisar de um campo
   separado no `IntradayTrade` -- ver a docstring do modulo `IntradayTrade`
   em `backtest.intraday.machine`, que nao guarda `bars_held` do trade
   fechado, so' da posicao ABERTA em `IntradayOpenPosition`).

## Bonus (2026-09-03, so' se sobrar tempo -- feito): fracao de tempo do lado
## ADVERSO vs desfecho

Mesma pergunta que `wdof1_padrao_tempo_adverso_2026_09_03.py` fez para a WDO
F1 ("nos primeiros X% do tempo do trade, o preco ficou do lado adverso ou
favoravel -- isso prediz STOP ou TARGET no final?"), adaptada para
granularidade de BARRA M1 em vez de TICK -- mais leve (104 mil barras contra
milhoes de ticks), o metodo e' o MESMO: fatiar `entry_ts..exit_ts` no array
de barras, achar o checkpoint em fracao de tempo decorrido, olhar o lado
(favoravel/adverso/neutro) e a fracao adversa ACUMULADA ate ali.

## Ressalva de look-ahead (repetida da WDO F1 -- vale aqui tambem)

"Fracao do tempo TOTAL do trade" so' e' conhecida DEPOIS que o trade fecha.
Este script e' analise RETROSPECTIVA sobre trades ja fechados, NAO uma regra
de execucao ao vivo -- nenhuma regra de saida e' proposta ou implementada
aqui.

Uso: `python scripts/daytrade/copawin_duracao_operacoes_2026_09_03.py`
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import num_br  # noqa: E402
from core.models import IntradayExitReason  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

SYMBOL = "WIN@"
MIN_BARRAS_M1_FUTURO = 400
TRADE_TICK_VALUE = 0.20
TRADE_TICK_SIZE = 1.0

#: Mesmos dois niveis do sweep irmao -- ver a docstring do modulo.
CAPITAL_REAL_BRL = 434.0
CAPITAL_FOLGA_BRL = 3_000.0
NIVEIS_CAPITAL = (CAPITAL_REAL_BRL, CAPITAL_FOLGA_BRL)

#: Checkpoints de fracao de tempo decorrido -- mesma grade da WDO F1.
CHECKPOINTS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)

FAIXAS_ACUMULADA = [
    (0.0, 0.2, "0-20%"),
    (0.2, 0.4, "20-40%"),
    (0.4, 0.6, "40-60%"),
    (0.6, 0.8, "60-80%"),
    (0.8, 1.0 + 1e-9, "80-100%"),
]

_EXIT_RESOLVIDOS = (IntradayExitReason.STOP, IntradayExitReason.TARGET)


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def carregar_bars() -> pd.DataFrame:
    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_M1_FUTURO}
    return df[[d in completos for d in df.index.date]]


def rodar_baseline(bars: pd.DataFrame, capital: float):
    """Config de PRODUCAO (`get_daytrade_robot`), SEM defesa (a classe nunca
    recebe `defesa_ativa`, fica no default `False`)."""
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    return run_intraday_backtest(bars, strat, cfg)


# ---------- Parte 3: duracao media por tipo de saida -------------------------

def tabela_duracao(trades: list) -> pd.DataFrame:
    """1 linha por `exit_reason`, `describe()` completo da duracao em
    MINUTOS (== barras M1, ver a docstring do modulo)."""
    linhas = []
    por_motivo: dict[str, list[float]] = {}
    for t in trades:
        dur_min = (t.exit_ts - t.entry_ts).total_seconds() / 60.0
        por_motivo.setdefault(t.exit_reason.value, []).append(dur_min)

    for motivo, duracoes in sorted(por_motivo.items()):
        s = pd.Series(duracoes)
        linhas.append(dict(
            exit_reason=motivo,
            N=len(s),
            media_min=s.mean(),
            mediana_min=s.median(),
            desvio_min=s.std(ddof=1) if len(s) > 1 else 0.0,
            p25_min=s.quantile(0.25),
            p75_min=s.quantile(0.75),
            min_min=s.min(),
            max_min=s.max(),
        ))
    return pd.DataFrame(linhas)


def _fmt_duracao(tab: pd.DataFrame) -> str:
    out = tab.copy()
    for col in out.columns:
        if col == "exit_reason":
            continue
        if col == "N":
            out[col] = out[col].astype(int)
        else:
            out[col] = out[col].map(lambda v: num_br(v, 1))
    return out.to_string(index=False)


# ---------- Bonus: fracao de tempo do lado adverso vs desfecho ---------------

def extrair_checkpoints(trades: list, times_ns: np.ndarray, closes: np.ndarray) -> pd.DataFrame:
    """Mesmo metodo de `wdof1_padrao_tempo_adverso_2026_09_03.py`, adaptado
    para BARRA M1 em vez de TICK -- ver a ressalva de look-ahead na docstring
    do modulo. `times_ns` tem que estar em nanosegundos verdadeiros
    (`DatetimeIndex.as_unit("ns").asi8`, NUNCA so' `.asi8` cru): o parquet do
    WIN@ guarda o indice em microssegundo (`datetime64[us, UTC]`), e
    `pd.Timestamp.value` sempre devolve nanosegundos -- as duas escalas
    divergem por 1e3x sem a conversao explicita (mesmo bug, escala diferente,
    ja encontrado e documentado na WDO F1)."""
    linhas: list[dict] = []
    pulados_duracao_zero = 0
    pulados_sem_barra_na_janela = 0
    for trade_id, t in enumerate(trades):
        entry_ns = t.entry_ts.value
        exit_ns = t.exit_ts.value
        if exit_ns <= entry_ns:
            pulados_duracao_zero += 1
            continue

        start = int(np.searchsorted(times_ns, entry_ns, side="left"))
        end = int(np.searchsorted(times_ns, exit_ns, side="right"))
        if end <= start:
            pulados_sem_barra_na_janela += 1
            continue

        tt = times_ns[start:end].astype(np.float64)
        cc = closes[start:end]
        frac_tempo = (tt - entry_ns) / (exit_ns - entry_ns)
        np.clip(frac_tempo, 0.0, 1.0, out=frac_tempo)

        if t.side == "long":
            lado = np.where(cc > t.entry_price, "favoravel",
                             np.where(cc < t.entry_price, "adverso", "neutro"))
        else:
            lado = np.where(cc < t.entry_price, "favoravel",
                             np.where(cc > t.entry_price, "adverso", "neutro"))

        adverso_bin = (lado == "adverso").astype(np.float64)
        cum_adverso = np.cumsum(adverso_bin)
        n_visto = np.arange(1, len(lado) + 1, dtype=np.float64)
        frac_acumulada = cum_adverso / n_visto

        exit_reason_txt = t.exit_reason.value
        for chk in CHECKPOINTS:
            idx = int(np.searchsorted(frac_tempo, chk, side="right")) - 1
            if idx < 0:
                idx = 0
            linhas.append(dict(
                trade_id=trade_id, checkpoint=chk, lado_no_checkpoint=lado[idx],
                frac_tempo_adverso_acumulada_ate_checkpoint=float(frac_acumulada[idx]),
                exit_reason=exit_reason_txt,
            ))

    if pulados_duracao_zero:
        print(f"[copawin_duracao] {pulados_duracao_zero} trade(s) com duracao 0 "
              f"(fecham na mesma barra da entrada) pulado(s).")
    if pulados_sem_barra_na_janela:
        print(f"[copawin_duracao] {pulados_sem_barra_na_janela} trade(s) sem barra "
              f"localizavel na janela entry_ts..exit_ts (inesperado -- investigar se > 0).")
    colunas = ["trade_id", "checkpoint", "lado_no_checkpoint",
               "frac_tempo_adverso_acumulada_ate_checkpoint", "exit_reason"]
    if not linhas:
        return pd.DataFrame(columns=colunas)
    return pd.DataFrame(linhas)


def tabela_pontual(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for chk in CHECKPOINTS:
        sub = df[df["checkpoint"] == chk]
        row: dict = {"checkpoint_%": chk * 100.0}
        for lado in ("adverso", "favoravel"):
            cel = sub[sub["lado_no_checkpoint"] == lado]
            n = len(cel)
            pct_stop = 100.0 * (cel["exit_reason"] == "stop").mean() if n else float("nan")
            pct_target = 100.0 * (cel["exit_reason"] == "target").mean() if n else float("nan")
            row[f"N_{lado}"] = n
            row[f"%STOP|{lado}"] = pct_stop
            row[f"%TARGET|{lado}"] = pct_target
        row["N_neutro"] = int((sub["lado_no_checkpoint"] == "neutro").sum())
        linhas.append(row)
    return pd.DataFrame(linhas)


def tabela_acumulada(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for chk in CHECKPOINTS:
        sub = df[df["checkpoint"] == chk]
        row: dict = {"checkpoint_%": chk * 100.0}
        for lo, hi, rotulo in FAIXAS_ACUMULADA:
            frac = sub["frac_tempo_adverso_acumulada_ate_checkpoint"]
            cel = sub[(frac >= lo) & (frac < hi)]
            n = len(cel)
            pct_stop = 100.0 * (cel["exit_reason"] == "stop").mean() if n else float("nan")
            pct_target = 100.0 * (cel["exit_reason"] == "target").mean() if n else float("nan")
            row[f"N_{rotulo}"] = n
            row[f"%STOP|{rotulo}"] = pct_stop
            row[f"%TARGET|{rotulo}"] = pct_target
        linhas.append(row)
    return pd.DataFrame(linhas)


def _fmt_tabela(tab: pd.DataFrame) -> str:
    out = tab.copy()
    for col in out.columns:
        if col.startswith("checkpoint"):
            out[col] = out[col].map(lambda v: f"{num_br(v, 0)}%")
        elif col.startswith("N_"):
            out[col] = out[col].astype(int)
        elif col.startswith("%"):
            out[col] = out[col].map(lambda v: "-" if pd.isna(v) else f"{num_br(v, 1)}%")
    return out.to_string(index=False)


def main() -> None:
    t0 = time.perf_counter()
    bars = carregar_bars()
    n_dias = len(set(bars.index.date))
    print(f"[copawin_duracao] {len(bars):,} barras M1, {n_dias} pregoes "
          f"({bars.index.min()} -> {bars.index.max()})".replace(",", "."))

    times_ns = bars.index.as_unit("ns").asi8
    closes = bars["close"].to_numpy()

    for capital in NIVEIS_CAPITAL:
        print(f"\n{'='*78}\ncapital inicial R${br(capital, 2)}\n{'='*78}")
        resultado = rodar_baseline(bars, capital)
        trades = list(resultado.trades)
        liquido = sum(t.pnl_brl for t in trades)
        print(f"[copawin_duracao] baseline: {len(trades)} trades, liquido=R${br(liquido)}, "
              f"recusadas_capital={resultado.ordens_recusadas_por_capital}")

        contagem_motivos = pd.Series([t.exit_reason.value for t in trades]).value_counts()
        print(f"\ndistribuicao de exit_reason ({len(trades)} trades totais):")
        print(contagem_motivos.to_string())

        print("\n=== Parte 3: duracao (minutos == barras M1) por exit_reason ===")
        tab_dur = tabela_duracao(trades)
        print(_fmt_duracao(tab_dur))

        trades_resolvidos = [t for t in trades if t.exit_reason in _EXIT_RESOLVIDOS]
        print(f"\n{len(trades_resolvidos)} trades resolvidos por STOP ou TARGET "
              f"({len(trades) - len(trades_resolvidos)} descartados -- FORCED_FLATTEN, "
              f"nao e' resolucao de stop/alvo) -- bonus abaixo so' usa estes.")

        df_chk = extrair_checkpoints(trades_resolvidos, times_ns, closes)
        n_trades_dataset = df_chk["trade_id"].nunique() if not df_chk.empty else 0
        print(f"[copawin_duracao] {n_trades_dataset} trades no dataset de checkpoints "
              f"({len(df_chk)} linhas trade x checkpoint)")

        if not df_chk.empty:
            print("\n--- Bonus, Tabela 1: estado PONTUAL no checkpoint ---")
            print(_fmt_tabela(tabela_pontual(df_chk)))
            print("\n--- Bonus, Tabela 2: por FAIXA de frac_tempo_adverso_acumulada ---")
            print(_fmt_tabela(tabela_acumulada(df_chk)))

    dt_total = time.perf_counter() - t0
    print(f"\n[copawin_duracao] total: {dt_total:.1f}s")
    print("\nNOTA: fracao de tempo e' conhecida so' DEPOIS que o trade fecha -- "
          "isto e' analise RETROSPECTIVA, nao regra de execucao ao vivo. Nenhuma "
          "regra foi implementada aqui.")


if __name__ == "__main__":
    main()
