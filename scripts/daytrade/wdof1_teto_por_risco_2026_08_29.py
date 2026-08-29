"""Mesma pergunta respondida para o `CopaWin` (item 3.9 de `LICOES_DE_
PRODUCAO.md`), agora para a `WdoGridReloadMaker`: o novo teto por risco
(`strategy.daytrade.base.contracts_from_risk`) muda o resultado quando o
modo de realocacao dinamica por CAPITAL (`margin_per_contract_brl`) esta
ligado?

IMPORTANTE: esse modo dinamico e' OPT-IN -- `get_daytrade_robot(
"wdo_grid_reload_maker")` (o que roda em producao hoje) usa `margin_per_
contract_brl=None`, ou seja, `quantity` FIXA (1 contrato, via `Intraday
BacktestConfig.default_quantity`). Este script LIGA o modo dinamico na mao
(`margin_per_contract_brl=150.0`, a margem real do WDO@) so' para medir o
efeito do teto por risco NESSE cenario hipotetico -- nao reproduz o que a
producao faz hoje.

`hard_cap_contratos=profile.max_open_contracts` (5, teto oficial) e'
OBRIGATORIO aqui: sem ele, a estrategia pede mais contratos do que o motor
(que ja aplica esse teto oficial via `config_for`) deixa abrir, e TODA
ordem e' recusada por teto (medido: 10.536 recusas, 0 trades) -- nao e' o
teto por risco fazendo isso, e' os dois lados (estrategia/motor) pedindo
numeros diferentes por eu ter esquecido de passar o mesmo teto pros dois.

Capital real R$3.000 (folga, mesmo nivel usado no teste do CopaWin), 177
pregoes completos de WDO@ salvos.

Uso: `python -u scripts/daytrade/wdof1_teto_por_risco_2026_08_29.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker  # noqa: E402

CAPITAL_INICIAL = 3_000.0
MIN_BARRAS_POR_PREGAO = 400


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def main() -> None:
    df = load_m1("WDO@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    bars = df[[d in completos for d in df.index.date]]
    profile = profile_for("WDO@")

    cfg = config_for(
        profile, trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_INICIAL, target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
    )

    print(f"=== WdoGridReloadMaker, modo dinamico por capital LIGADO na mao "
          f"(nao e' o default de producao), WDO@, capital R${br(CAPITAL_INICIAL)}, "
          f"{len(set(bars.index.date))} pregoes ===\n")

    variantes = [
        ("SEM teto por risco (so margem dinamica)", dict()),
        ("COM teto por risco (5%/trade)", dict(risco_pct_por_trade=0.05, point_value_brl=10.0)),
    ]
    for rotulo, kwargs_extra in variantes:
        strat = WdoGridReloadMaker(
            margin_per_contract_brl=150.0, tick_size=profile.price_tick_size,
            hard_cap_contratos=profile.max_open_contracts, **kwargs_extra,
        )
        resultado = run_intraday_backtest(bars, strat, cfg)
        liquido = sum(t.pnl_brl for t in resultado.trades)
        equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else CAPITAL_INICIAL
        equity_min = float(resultado.equity_curve.min()) if not resultado.equity_curve.empty else CAPITAL_INICIAL
        qtys = [t.quantity for t in resultado.trades]
        pior = min(resultado.trades, key=lambda t: t.pnl_brl) if resultado.trades else None
        print(f"{rotulo}:")
        print(f"  trades={len(resultado.trades)} | qty maxima={max(qtys) if qtys else 0} "
              f"| liquido=R${br(liquido)} | equity final=R${br(equity_final)} "
              f"| equity MINIMA=R${br(equity_min)}")
        if pior is not None:
            print(f"  pior trade: {pior.entry_ts} qty={pior.quantity} pnl=R${br(pior.pnl_brl)} "
                  f"({pior.pnl_brl / equity_min * 100 if equity_min else 0:.1f}% da equity minima)")
        if resultado.wiped_out_at is not None:
            print(f"  *** ZERADO em {resultado.wiped_out_at} ***")
        else:
            print("  nunca zerou.")
        print()


if __name__ == "__main__":
    main()
