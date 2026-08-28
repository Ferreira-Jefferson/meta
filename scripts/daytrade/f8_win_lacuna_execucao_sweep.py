"""Frente F8-win-lacuna-execucao -- pergunta 1: existe T (alvo) maior que 2
ticks ou espacamento muito maior que o testado (0/60 celulas, T=1 e T=2)
capaz de mudar o veredito do grid-maker em WIN@?

Reusa `strategy.daytrade.lab.grid_reload_maker.GridReloadMaker` (mecanica de
reload no mesmo nivel + stop largo por posicao a mercado + alvo maker) e o
motor real (`backtest.intraday.engine.run_intraday_backtest`), NAO uma
aproximacao por primeira passagem em barra de fechamento -- essa aproximacao
foi tentada primeiro e descartada por vies de discretizacao (toda barra M1 do
WIN@ tem range >= 2 ticks, mediana 21,6 ticks: um stop menor que isso e
irresolvivel so com fechamentos, o motor real resolve via
`ambiguous_bar_resolution="stop_first"`, que ja e o padrao conservador do
projeto).

So' IS (< OOS_CUTOFF), via LockedBars, `.in_sample()` apenas. NAO chama
`.unlock(...)`.
"""
from __future__ import annotations

import sys
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.costs import IntradayCostModel  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig  # noqa: E402
from backtest.intraday.profiles import FUTURES_PROFILES, config_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.grid_reload_maker import GridReloadMaker  # noqa: E402

SYMBOL = "WIN@"
CAPITAL_NOCIONAL = 1_000_000.0
# economia real (nao a da serie continua) -- mesma tabela de fallback do
# copa_lab.py, para rodar sem MT5 aberto.
_ECONOMIA_CONHECIDA = {"WIN@": (0.2, 1.0), "WDO@": (0.01, 0.001)}


def carregar_is():
    profile = FUTURES_PROFILES[SYMBOL]
    df = load_m1(SYMBOL)
    if df.empty:
        raise SystemExit(f"sem dado M1 salvo para {SYMBOL!r}")
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note="F8 sweep T>2 / spacing maior")
    locked = LockedBars(df.sort_index(), split)
    return locked.in_sample(), profile


def montar_config(profile, pedagio_ticks: float = 0.0, pernas_maker: int = 2) -> IntradayBacktestConfig:
    trade_tick_value, trade_tick_size = _ECONOMIA_CONHECIDA[SYMBOL]
    cfg = config_for(
        profile,
        trade_tick_value=trade_tick_value,
        trade_tick_size=trade_tick_size,
        initial_capital=CAPITAL_NOCIONAL,
        target_fills_as_maker=True,
        max_open_contracts=1,  # a estrategia so abre 1 por vez de qualquer jeito
    )
    custos = cfg.costs
    if pedagio_ticks:
        extra = pedagio_ticks * custos.tick_size * custos.point_value_brl * pernas_maker
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=custos.fee_round_trip_brl + extra,
            slippage_ticks=custos.slippage_ticks,
            exchange_fee_pct_per_leg=custos.exchange_fee_pct_per_leg,
        )
        cfg = IntradayBacktestConfig(
            costs=custos, initial_capital=cfg.initial_capital,
            default_quantity=cfg.default_quantity, session_end_time=cfg.session_end_time,
            session_end_policy=cfg.session_end_policy, target_fills_as_maker=cfg.target_fills_as_maker,
            limit_fill_capped_by_volume=cfg.limit_fill_capped_by_volume,
            enforce_capital_minimo=cfg.enforce_capital_minimo, max_open_contracts=cfg.max_open_contracts,
        )
    return cfg


def rodar(bars, profile, T: int, S: int, spacing: int, pedagio_ticks: float):
    tick = profile.price_tick_size  # 5.0 pontos reais
    cfg = montar_config(profile, pedagio_ticks=pedagio_ticks)
    robo = GridReloadMaker(
        symbol=SYMBOL,
        tick_size=tick,
        level_spacing_ticks=spacing,
        profit_ticks=T,
        stop_ticks=S,
        max_trades_per_side=30,          # folga generosa -- nao queremos o teto mordendo
        session_stop_brl=1_000_000.0,     # capital nocional: sem stop agregado artificial
        quantity=1,                       # 1 CONTRATO fixo, conforme a missao
    )
    return run_intraday_backtest(bars, robo, cfg)


def main():
    bars, profile = carregar_is()
    print(f"[{SYMBOL}] barras IS: {len(bars)}, sessoes: {bars.index.normalize().nunique()}")

    import os
    T_LIST = [int(x) for x in os.environ.get("F8_T_LIST", "3,5,8,13,20").split(",")]
    S_LIST = [int(x) for x in os.environ.get("F8_S_LIST", "8,16,32,64").split(",")]
    SPACING_LIST = [int(x) for x in os.environ.get("F8_SPACING_LIST", "2").split(",")]
    PEDAGIO_CENARIOS = [float(x) for x in os.environ.get("F8_PEDAGIO_LIST", "0.0").split(",")]

    linhas = []
    t0 = _time.time()
    total = len(T_LIST) * len(S_LIST) * len(SPACING_LIST) * len(PEDAGIO_CENARIOS)
    done = 0
    resumo_rows = []
    for pedagio in PEDAGIO_CENARIOS:
        for T in T_LIST:
            for S in S_LIST:
                for spacing in SPACING_LIST:
                    res = rodar(bars, profile, T, S, spacing, pedagio)
                    liquido = sum(t.pnl_brl for t in res.trades)
                    n_trades = len(res.trades)
                    rotulo = f"T{T} S{S} x{spacing} ped{pedagio:.0f}"
                    linha = linha_de_resultado(rotulo, res, CAPITAL_NOCIONAL, capital_nocional=True)
                    linhas.append(linha)
                    resumo_rows.append((pedagio, T, S, spacing, liquido, n_trades))
                    done += 1
                    print(f"[{done}/{total}] {rotulo}: liquido=R${liquido:,.2f} trades={n_trades}", flush=True)
    dt = _time.time() - t0
    print(f"\ntempo total: {dt:.1f}s ({dt/total:.2f}s/celula)")

    print("\n" + tabela(linhas))

    print("\n=== resumo por cenario de pedagio ===")
    for pedagio in PEDAGIO_CENARIOS:
        subset = [r for r in resumo_rows if r[0] == pedagio]
        positivos = sum(1 for r in subset if r[4] > 0)
        mediana = sorted(r[4] for r in subset)[len(subset) // 2]
        melhor = max(subset, key=lambda r: r[4])
        print(f"pedagio={pedagio:.0f} tick: {positivos}/{len(subset)} positivas, "
              f"mediana=R${mediana:,.2f}, melhor=T{melhor[1]} S{melhor[2]} x{melhor[3]} "
              f"-> R${melhor[4]:,.2f} ({melhor[5]} trades)")


if __name__ == "__main__":
    main()
