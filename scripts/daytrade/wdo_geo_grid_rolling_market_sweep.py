"""Frente F4-wdo-geometria-sessao, RODADA 2, angulo alternativo do bloco A
(usado quando NENHUMA celula da grade sobrevive a pedagio de fila, nem
estreita nem larga -- ver `scripts/daytrade/wdo_geo_pedagio_largo.py`).

Roda `WdoGeoGridRollingMarket` (entrada A MERCADO, paga slippage, nao
depende de fila -- ver `strategy/daytrade/lab/wdo_geo_grid_rolling_market.
py`) nas mesmas geometrias (T/S/espacamento/reancoragem) que se destacaram
na grade maker desta frente, e reporta LADO A LADO com a versao maker
(sem/com pedagio, ja conhecida): se a versao a mercado tambem morre, o
"edge" medido era so' captura de spread/rebate de maker (exatamente o que
pedagio de fila ja mostrou nao existir de forma capturavel). Se ALGUMA
sobreviver, isso separa um edge de CONTINUIDADE direcional pos-nivel, que
sobrevive a pagar o spread -- so' fica mais caro.

Reusa `_bars_is`/`_config_com_pedagio`/`_monta_robo`/`_fase_metade`/
`_fase_nulo` de `wdo_geo_sweep.py` (so' LE, nao edita).

Uso:
    python scripts/daytrade/wdo_geo_grid_rolling_market_sweep.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import LinhaResultado, linha_de_resultado, num_br, tabela  # noqa: E402
from strategy.daytrade.lab.wdo_geo_grid_rolling_market import WdoGeoGridRollingMarket  # noqa: E402
import wdo_geo_sweep as base  # noqa: E402  (reusa infra da propria frente F4, so' LE)

EXTRAS = ("T", "S", "espac", "reancora")

# Preenchido apos o bloco A (pedagio-largo) terminar -- geometrias que mais
# se destacaram (maior liquido bruto E maiores sobreviventes-candidatas,
# mesmo que nenhuma tenha sobrevivido a pedagio) entram aqui.
CANDIDATOS: list[tuple[int, int, int, int]] = [
    # (T, S, spacing, reanchor_bars) -- top-3 SEM pedagio da rodada 1 (agulha
    # no palheiro), melhor T2/T3/T4 do top-15, e as 3 candidatas LARGAS
    # citadas pelo critico -- nenhuma sobrevive a pedagio (bloco A desta
    # rodada, `wdo_geo_pedagio_largo.py`), entao esta lista cobre toda a
    # faixa de espacamento (1 a 32 ticks) que ja se mostrou promissora
    # zero-atrito, para checar se ALGUMA sobrevive a pagar o spread via
    # entrada a mercado em vez de pedagio de fila.
    (1, 16, 1, 1),   # campea da rodada 1 (o pico agulha-no-palheiro)
    (1, 8, 1, 1),
    (1, 32, 1, 1),
    (2, 16, 2, 1),   # melhor T2 do top-15
    (3, 16, 2, 1),   # melhor T3 do top-15
    (4, 16, 2, 1),   # melhor T4 do top-15
    (4, 16, 4, 1),   # candidatas "largas" citadas pelo critico (bloco A)
    (4, 8, 4, 1),
    (4, 32, 4, 1),
]


def _roda_market(T: int, S: int, spacing: int, reanchor: int) -> LinhaResultado:
    bars = base._bars_is()
    cfg = base._config_com_pedagio(0.0)  # market ja paga slippage sozinho -- sem pedagio artificial aqui
    strat = WdoGeoGridRollingMarket(
        symbol=base.SYMBOL, tick_size=cfg.costs.tick_size, level_spacing_ticks=spacing,
        profit_ticks=T, stop_ticks=S, rolling_reanchor_after_bars=reanchor, quantity=1,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    return linha_de_resultado(
        f"market T{T} S{S} sp{spacing} r{reanchor}", resultado, base.CAPITAL_NOCIONAL,
        capital_nocional=True,
        extras={"T": str(T), "S": str(S), "espac": str(spacing), "reancora": str(reanchor)},
    )


def main() -> None:
    bars = base._bars_is()
    dias = sorted(set(bars.index.date))
    print(f"[wdo_geo_grid_rolling_market_sweep] WDO@ IS: {len(bars)} barras, {len(dias)} pregoes")

    # Numeros maker (sem/com pedagio) ja' medidos no bloco A desta rodada
    # (`wdo_geo_pedagio_largo.py`, log completo) -- reusa em vez de
    # recalcular (economiza 18 dos 27 runs seriais, o gargalo real desta
    # comparacao e' so' rodar a variante MARKET, nova).
    MAKER_CONHECIDO = {
        # (T, S, spacing): (sem_pedagio, com_pedagio) -- rolling, r1
        (1, 16, 1): (62_226.48, -127_843.52),
        (1, 8, 1): (56_350.18, -195_129.82),
        (1, 32, 1): (52_061.19, -77_218.81),
        (2, 16, 2): (50_449.48, -77_770.52),
        (3, 16, 2): (38_269.14, -61_970.86),
        (4, 16, 2): (33_057.59, -50_072.41),
        (4, 16, 4): (21_695.88, -41_054.12),
        (4, 8, 4): (15_700.11, -66_919.89),
        (4, 32, 4): (15_299.76, -26_800.24),
    }

    linhas_market = []
    print(f"\n=== Entrada A MERCADO (taker, paga slippage) -- mesmas geometrias da grade maker ===")
    for T, S, spacing, reanchor in CANDIDATOS:
        linha_market = _roda_market(T, S, spacing, reanchor)
        linhas_market.append(linha_market)

        sem, com = MAKER_CONHECIDO.get((T, S, spacing), (float("nan"), float("nan")))
        print(f"  T{T} S{S} sp{spacing} r{reanchor:<3} "
              f"maker_sem_pedagio={num_br(sem,2):>12}  "
              f"maker_com_pedagio={num_br(com,2):>12}  "
              f"MARKET(taker)={num_br(linha_market.liquido_brl,2):>12}  "
              f"[{'SOBREVIVE' if linha_market.liquido_brl > 0 else 'morre'}]", flush=True)

    print(f"\n=== Tabela padrao -- variantes A MERCADO ===")
    print(tabela(linhas_market, extras=EXTRAS, largura_extra=9))

    sobreviventes = [c for c, l in zip(CANDIDATOS, linhas_market) if l.liquido_brl > 0]
    if sobreviventes:
        melhor_idx = max(range(len(linhas_market)), key=lambda i: linhas_market[i].liquido_brl)
        T, S, spacing, reanchor = CANDIDATOS[melhor_idx]
        print(f"\n[wdo_geo_grid_rolling_market_sweep] candidata MARKET sobrevivente: "
              f"T{T} S{S} sp{spacing} r{reanchor} = {num_br(linhas_market[melhor_idx].liquido_brl,2)} "
              f"-- rodando metade + nulo...")

        cfg = base._config_com_pedagio(0.0)

        def _roda_em(bars_sub, T=T, S=S, spacing=spacing, reanchor=reanchor):
            strat = WdoGeoGridRollingMarket(symbol=base.SYMBOL, tick_size=cfg.costs.tick_size,
                                             level_spacing_ticks=spacing, profit_ticks=T, stop_ticks=S,
                                             rolling_reanchor_after_bars=reanchor, quantity=1)
            resultado = run_intraday_backtest(bars_sub, strat, cfg)
            return sum(t.pnl_brl for t in resultado.trades)

        primeira, segunda = base._metade(bars)
        liq1, liq2 = _roda_em(primeira), _roda_em(segunda)
        print(f"\n=== Teste de metade -- market T{T} S{S} sp{spacing} r{reanchor} ===")
        print(f"  1a metade: {num_br(liq1,2)}   2a metade: {num_br(liq2,2)}   "
              f"({'positivo' if liq2 > 0 else 'negativo'} na 2a)")

        # nulo sign-flip (formula correta) reaproveitando o mesmo padrao de
        # `wdo_geo_sweep._fase_nulo`, adaptado para a estrategia MARKET.
        import random
        from backtest.intraday.costs import IntradayCostModel
        from backtest.intraday.machine import IntradayBacktestConfig

        cfg_sem_custo = IntradayCostModel(point_value_brl=cfg.costs.point_value_brl,
                                           tick_size=cfg.costs.tick_size, fee_round_trip_brl=0.0,
                                           slippage_ticks=0.0, exchange_fee_pct_per_leg=0.0)
        cfg_bruto = IntradayBacktestConfig(
            costs=cfg_sem_custo, initial_capital=cfg.initial_capital,
            default_quantity=cfg.default_quantity, session_end_time=cfg.session_end_time,
            session_end_policy=cfg.session_end_policy, target_fills_as_maker=True,
            limit_fill_capped_by_volume=cfg.limit_fill_capped_by_volume,
            enforce_capital_minimo=cfg.enforce_capital_minimo, max_open_contracts=cfg.max_open_contracts,
        )
        strat_liq = WdoGeoGridRollingMarket(symbol=base.SYMBOL, tick_size=cfg.costs.tick_size,
                                             level_spacing_ticks=spacing, profit_ticks=T, stop_ticks=S,
                                             rolling_reanchor_after_bars=reanchor, quantity=1)
        res_liq = run_intraday_backtest(bars, strat_liq, cfg)
        strat_bruto = WdoGeoGridRollingMarket(symbol=base.SYMBOL, tick_size=cfg.costs.tick_size,
                                               level_spacing_ticks=spacing, profit_ticks=T, stop_ticks=S,
                                               rolling_reanchor_after_bars=reanchor, quantity=1)
        res_bruto = run_intraday_backtest(bars, strat_bruto, cfg_bruto)

        def _por_dia(trades):
            acc = {}
            for t in trades:
                d = t.entry_ts.date()
                acc[d] = acc.get(d, 0.0) + t.pnl_brl
            return acc

        liquido_por_dia = _por_dia(res_liq.trades)
        bruto_por_dia = _por_dia(res_bruto.trades)
        dias_n = sorted(set(liquido_por_dia) | set(bruto_por_dia))
        bruto_d = [bruto_por_dia.get(d, 0.0) for d in dias_n]
        delta_custo_d = [liquido_por_dia.get(d, 0.0) - bruto_por_dia.get(d, 0.0) for d in dias_n]
        liquido_real = sum(liquido_por_dia.values())

        nulos = []
        for seed in range(20):
            rng = random.Random(seed)
            s = [rng.choice((-1.0, 1.0)) for _ in dias_n]
            nulos.append(sum(sd * b + c for sd, b, c in zip(s, bruto_d, delta_custo_d)))
        nulos.sort()
        abaixo = sum(1 for v in nulos if v < liquido_real)
        print(f"\n=== Nulo sign-flip -- market T{T} S{S} sp{spacing} r{reanchor} (20 sementes) ===")
        print(f"  liquido REAL: {num_br(liquido_real,2)}")
        print(f"  nulo: media={num_br(statistics.mean(nulos),2)}  desvio={num_br(statistics.pstdev(nulos),2)}  "
              f"min={num_br(nulos[0],2)}  max={num_br(nulos[-1],2)}")
        print(f"  percentil do real: {100.0*abaixo/len(nulos):.1f}% ({abaixo}/{len(nulos)} sementes abaixo)")
    else:
        print(f"\n[wdo_geo_grid_rolling_market_sweep] NENHUMA variante MARKET sobrevive -- "
              f"o edge maker inteiro era spread/rebate de fila, nao continuidade direcional.")


if __name__ == "__main__":
    main()
