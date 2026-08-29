"""Mesma pergunta que `wdof1_stress_capital_real_historico_completo.py` fez
para a WDO F1 ("em algum dia o capital fica negativo, rodando o historico
INTEIRO numa unica passada continua, com caixa REAL?") -- agora para os
OUTROS 3 robos do podio, depois do fix de `on_order_rejected` (2026-08-29,
`LICOES_DE_PRODUCAO.md` item 1.14) ter sido aplicado tambem em `Gremah` e
`GremahTick`, e da recalibracao de `stop_vol` do `CopaWin` (2026-08-28) ter
mudado o stop dela sem confirmacao equivalente a esta.

Roda cada robo com os defaults de PRODUCAO (`get_daytrade_robot`, sem digitar
parametro a mao) numa passada CONTINUA sobre TODO o historico salvo do
simbolo PRINCIPAL dele (o unico, no caso do CopaWin; o flagship PMAM3, mais
medido e com mais historico, no caso de Gremah/GremahTick -- os dois tambem
operam KLBN3/CSAN3/etc, fora do escopo desta rodada) -- rodar dia a dia
reiniciaria o caixa e esconderia uma sequencia de perda ATRAVESSANDO dias,
exatamente como no script da WDO F1.

Niveis de capital, cada um justificado (nenhum arbitrario, ver CLAUDE.md
"Capital inicial: sempre o minimo real do instrumento"):
  - CopaWin (WIN@, futuro): R$200 = minimo de tabela (margem R$100 x2 lotes);
    R$250 = limiar EXATO pra abrir 1 contrato JA com a reserva de seguranca
    (`RESERVA_CAIXA_SEGURANCA=1.25` sobre o buffer de 2x -- mesma conta do
    WDO, margem diferente); R$3.000 = folga, pra separar "trava por caixa"
    de "trava por perda de verdade".
  - Gremah/GremahTick (PMAM3, acao): capital_minimo_brl(preco) muda com o
    preco -- o papel foi de R$4,53 a R$0,09 nesta janela
    (`pmam3_colapso_de_preco_2026_08_26`), entao um unico numero fixo cobre
    janelas MUITO diferentes da mesma serie. R$30 = minimo real de HOJE
    (preco de referencia ~R$0,15); R$1.000 = folga suficiente pra operar
    tambem nos pregoes mais caros do inicio da serie (2023), pra nao confundir
    "sessao pulada por preco antigo mais caro" com "capital ficou negativo".

Uso: `python -u scripts/daytrade/podio_stress_capital_real_historico_completo.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

MIN_BARRAS_M1_FUTURO = 400
MIN_EVENTOS_POR_PREGAO_ACAO = 20  # PMAM3 tem giro bem mais baixo que WIN@/WDO@


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _completos(df: pd.DataFrame, min_por_dia: int) -> pd.DataFrame:
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= min_por_dia}
    return df[[d in completos for d in df.index.date]]


def rodar(robo_key: str, symbol: str, bars: pd.DataFrame, niveis: list[float],
          trade_tick_value: float, trade_tick_size: float) -> None:
    dias = sorted(set(bars.index.date))
    profile = profile_for(symbol)
    print(f"\n### {robo_key} @ {symbol}: {len(bars):,} barras/eventos, "
          f"{len(dias)} pregoes, {dias[0]} -> {dias[-1]} ###")
    for capital in niveis:
        strat = get_daytrade_robot(robo_key, symbol=symbol)
        cfg = config_for(
            profile,
            trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
            initial_capital=capital,
            target_fills_as_maker=strat.target_fills_as_maker,
            limit_fill_capped_by_volume=True,
        )
        resultado = run_intraday_backtest(bars, strat, cfg)
        liquido = sum(t.pnl_brl for t in resultado.trades)
        equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else capital
        equity_min = float(resultado.equity_curve.min()) if not resultado.equity_curve.empty else capital
        pulou = len(resultado.sessoes_puladas_por_capital)
        print(f"  capital inicial R${br(capital)}: trades={len(resultado.trades)} "
              f"| recusadas_capital={resultado.ordens_recusadas_por_capital} "
              f"| recusadas_teto={resultado.ordens_recusadas_por_teto} "
              f"| liquido=R${br(liquido)} | equity final=R${br(equity_final)} "
              f"| equity MINIMA=R${br(equity_min)} | pregoes pulados p/ capital={pulou}")
        if resultado.wiped_out_at is not None:
            print(f"  *** ZERADO em {resultado.wiped_out_at} *** "
                  f"(equity <= 0 -- passada interrompida ai, resto do historico NAO rodado)")
        else:
            print("  nunca zerou no historico inteiro.")


def main() -> None:
    # --- CopaWin @ WIN@ (futuro, teto dinamico por caixa ATIVO) ---
    win = load_m1("WIN@").sort_index()
    win = _completos(win, MIN_BARRAS_M1_FUTURO)
    rodar("copa_win", "WIN@", win, [200.0, 250.0, 3_000.0],
          trade_tick_value=0.20, trade_tick_size=1.0)

    # --- GremahTick @ PMAM3 (acao, tick-a-tick) ---
    ticks = load_ticks("PMAM3").sort_index()
    bars_tick = ticks_to_degenerate_bars(ticks)
    bars_tick = _completos(bars_tick, MIN_EVENTOS_POR_PREGAO_ACAO)
    rodar("gremah_tick", "PMAM3", bars_tick, [30.0, 1_000.0],
          trade_tick_value=0.01, trade_tick_size=0.01)

    # --- Gremah @ PMAM3 (acao, M1) ---
    pmam3_m1 = load_m1("PMAM3").sort_index()
    pmam3_m1 = _completos(pmam3_m1, MIN_EVENTOS_POR_PREGAO_ACAO)
    rodar("gremah", "PMAM3", pmam3_m1, [30.0, 1_000.0],
          trade_tick_value=0.01, trade_tick_size=0.01)


if __name__ == "__main__":
    main()
