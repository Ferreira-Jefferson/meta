# -*- coding: utf-8 -*-
"""SIMULACAO DO PREGAO DE HOJE (2026-09-15) ate 17:20 BRT -- `wdo_grid_reload_maker`
contra o robo novo `win_retangulo`.

Pedido do dono (2026-09-15). O que este script NAO e': uma comparacao de qual
robo e' melhor. Sao instrumentos diferentes (WDO@ e WIN@), granularidades
diferentes (tick e M1), pisos de caixa diferentes (R$375 e R$1.100) e UM
pregao de amostra. Um pregao nao decide nada -- e dizer isso aqui e' mais
barato do que alguem ler a tabela daqui a um mes achando que decidiu.

O que ele E': ver os dois rodando sobre o MESMO dia, com o desenho de
execucao de producao, para saber o que cada um teria feito.

## O corte das 17:20

Aplicado como `session_end_time` do motor, que e' o instante a partir do qual
a posicao e' ACHATADA. Nao e' o corte de producao (18:20 BRT = 21:20 UTC,
derivado de `FOLGA_ACHATAMENTO_MINUTOS`): e' o pedido do dono para esta
simulacao, entao vai explicito e declarado na tabela. 17:20 BRT = 20:20 UTC.

## O dado

`WIN@` e `WDO@` em M1 foram atualizados ate 20:23 UTC de hoje pelo coletor
incremental (`collect_m1_daily.py`), ou seja, o pregao de hoje esta coberto
ate 17:23 BRT -- passa do corte pedido, que era o necessario.

`wdo_grid_reload_maker` roda em TICK (`feed_kind="tick"`), nao em M1. A base
canonica de tick do WDO@ para em 2026-09-04, entao os ticks de HOJE sao
puxados do terminal so' para esta simulacao, em memoria, **sem merge na base
canonica** -- reescrever um parquet de 170MB para um dia de teste e' risco
sem retorno, e a base canonica tem historico proprio de furo de coleta.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/simulacao_hoje_dois_robos_2026_09_15.py`
"""
from __future__ import annotations

import dataclasses
import sys
from datetime import datetime, time, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

HOJE = pd.Timestamp("2026-09-15").date()
CORTE_BRT = time(17, 20)
CORTE_UTC = time(20, 20)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ticks_de_hoje(symbol_real: str) -> pd.DataFrame:
    """Ticks do pregao de hoje, direto do terminal. Nao toca a base canonica."""
    from core.b3_session import utc_to_server_wall_clock
    from market_data_intraday.mt5_ticks_source import fetch_ticks_range

    ini = datetime.combine(HOJE, time(11, 0), tzinfo=timezone.utc)   # 08:00 BRT
    fim = datetime.combine(HOJE, time(21, 40), tzinfo=timezone.utc)  # 18:40 BRT
    # o terminal le' o limite como RELOGIO DE PAREDE dele rotulado de UTC --
    # mesma armadilha de `collect_m1_daily._limite_servidor`, que ja custou
    # 19,3% dos minutos do parquet canonico do WDO@.
    erros: list = []
    df = fetch_ticks_range(
        symbol_real,
        utc_to_server_wall_clock(ini).replace(tzinfo=timezone.utc),
        utc_to_server_wall_clock(fim).replace(tzinfo=timezone.utc),
        on_error=lambda k, e: erros.append((k, e)),
    )
    if erros:
        print(f"  [ticks] erros: {erros}", flush=True)
    return df


def _roda(nome: str, bars: pd.DataFrame, strat, capital: float):
    profile = profile_for(strat.symbol)
    # a MESMA formula do caminho de producao (`dashboard.live_service`):
    # valor por 0,01 de preco = 0,01 x point_value_brl. Digitar 0,20/1,0 aqui
    # daria certo so' para o WIN@ e erraria o WDO@ por um fator de 50.
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    # o corte pedido pelo dono, no lugar do corte de achatamento de producao
    cfg = dataclasses.replace(cfg, session_end_time=CORTE_UTC)
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    liq = sum(t.pnl_brl for t in trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    return dict(
        nome=nome, simbolo=strat.symbol, capital=capital, trades=trades,
        liquido=liq, n=len(trades),
        win=(len(g) / len(trades)) if trades else float("nan"),
        be=(pm / (gm + pm)) if (gm + pm) > 0 else float("nan"),
        ganho_medio=gm, perda_media=pm,
        fila=(cfg.queue_ahead_qty, cfg.exit_queue_ahead_qty),
    )


def main():
    print("=" * 118)
    print(f"SIMULACAO do pregao de {HOJE} ate {CORTE_BRT.strftime('%H:%M')} BRT "
          f"({CORTE_UTC.strftime('%H:%M')} UTC)")
    print("=" * 118)
    print("  NAO e' comparacao entre os dois: instrumentos, granularidades e pisos de")
    print("  caixa diferentes, e UM pregao de amostra. E' so' o que cada um teria feito.\n")

    resultados = []

    # ---------------------------------------------------------- win_retangulo
    win = get_daytrade_robot("win_retangulo")
    m1 = load_m1("WIN@").sort_index()
    bars_win = m1[(m1.index.date == HOJE) & (m1.index.time <= CORTE_UTC)]
    print(f"  WIN@  M1 : {len(bars_win)} barras hoje ate o corte "
          f"({bars_win.index.min()} -> {bars_win.index.max()})" if len(bars_win)
          else "  WIN@  M1 : SEM barras hoje", flush=True)
    if len(bars_win):
        resultados.append(_roda("win_retangulo", bars_win, win, 1_100.0))

    # ------------------------------------------------- wdo_grid_reload_maker
    wdo = get_daytrade_robot("wdo_grid_reload_maker")
    print(f"\n  {wdo.name}: feed_kind={wdo.feed_kind}, simbolo {wdo.symbol}", flush=True)
    if wdo.feed_kind == "tick":
        from market_data_intraday.tick_bars import ticks_to_degenerate_bars

        print("  puxando ticks de hoje do terminal (sem merge na base canonica)...",
              flush=True)
        ticks = _ticks_de_hoje("WDOV26")
        print(f"  WDO@ tick: {len(ticks)} ticks hoje", flush=True)
        if len(ticks):
            bars_wdo = ticks_to_degenerate_bars(ticks)
            bars_wdo = bars_wdo[(bars_wdo.index.date == HOJE)
                                & (bars_wdo.index.time <= CORTE_UTC)]
            print(f"  WDO@ barras degeneradas ate o corte: {len(bars_wdo)} "
                  f"({bars_wdo.index.min()} -> {bars_wdo.index.max()})", flush=True)
            resultados.append(_roda("wdo_grid_reload_maker", bars_wdo, wdo, 375.0))
    else:
        m1w = load_m1("WDO@").sort_index()
        bars_wdo = m1w[(m1w.index.date == HOJE) & (m1w.index.time <= CORTE_UTC)]
        resultados.append(_roda("wdo_grid_reload_maker", bars_wdo, wdo, 375.0))

    # ------------------------------------------------------------------ saida
    print("\n" + "=" * 118)
    print("RESULTADO DO DIA")
    print("=" * 118)
    hdr = (f"  {'robo':<26}{'simb':<7}{'capital':>9}{'liquido R$':>12}{'trades':>8}"
           f"{'win%':>7}{'BEemp%':>9}{'ganho med':>11}{'perda med':>11}{'fila':>10}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in resultados:
        pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
        fila = "0/0" if r["fila"] == (0.0, 0.0) else f"{br(r['fila'][0],0)}/{br(r['fila'][1],0)}"
        print(f"  {r['nome']:<26}{r['simbolo']:<7}{br(r['capital'],0):>9}"
              f"{br(r['liquido']):>12}{r['n']:>8}{pc(r['win']):>7}{pc(r['be']):>9}"
              f"{br(r['ganho_medio']):>11}{br(r['perda_media']):>11}{fila:>10}")

    for r in resultados:
        print(f"\n  --- {r['nome']} ({r['simbolo']}): as {r['n']} operacoes ---")
        if not r["trades"]:
            print("    nenhuma operacao hoje ate o corte.")
            continue
        print(f"    {'entrada (BRT)':<17}{'saida (BRT)':<17}{'lado':<7}{'qtd':>5}"
              f"{'entrada':>12}{'saida':>12}{'R$':>10}  motivo")
        for t in sorted(r["trades"], key=lambda x: x.entry_ts):
            ent = (t.entry_ts.tz_convert("America/Sao_Paulo")).strftime("%H:%M:%S")
            sai = (t.exit_ts.tz_convert("America/Sao_Paulo")).strftime("%H:%M:%S")
            print(f"    {ent:<17}{sai:<17}{t.side:<7}{t.quantity:>5}"
                  f"{br(t.entry_price):>12}{br(t.exit_price):>12}"
                  f"{br(t.pnl_brl):>10}  {t.exit_reason.value}")

    print("\n" + "=" * 118)
    print("COMO LER")
    print("=" * 118)
    print("  * UM pregao. Nao ha veredito possivel aqui -- o acerto de um dia nao")
    print("    distingue estrategia de sorteio, e os dois robos tem breakeven empirico")
    print("    proprio que so' faz sentido sobre centenas de operacoes.")
    print("  * O corte das 17:20 e' o pedido do dono, NAO o de producao (18:20 BRT).")
    print("  * WIN@ nao tem fila calibrada (`fidelidade.py` so' tem WDO@): a coluna")
    print("    `fila` mostra a premissa de cada linha. Onde ela e' 0/0, toda ordem-limite")
    print("    preenche no TOQUE -- otimista.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
