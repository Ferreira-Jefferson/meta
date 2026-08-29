"""Roda `WdoGridReloadMaker` (WDO F1 maker, TOP-1 do podio) SO' no pregao de
2026-08-28 -- o dia do incidente ao vivo (ver `LICOES_DE_PRODUCAO.md`,
"WDO F1 zerou a conta"). Pergunta direta do dono: "rode o wdo na data de
ontem" (hoje = 2026-08-29).

Usa `get_daytrade_robot("wdo_grid_reload_maker")` (mesma instancia que
`scripts/run_live.py` monta) para nunca digitar parametro a mao -- o
default de classe hoje e' T1 S4 x1 (mudou de S16 em 2026-08-28, ver
`registry.py`). Config nocional (1 contrato, capital ficticio) e' a mesma
convencao de `wdo_grid_reload_f1_lab.py`: mede o SINAL/atrito da estrategia
isolado do teto por caixa, que e' outra pergunta (ver a docstring de
`config_for` sobre `enforce_capital_cap`).

Uso: `python scripts/daytrade/wdof1_dia_2026_08_28.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

SYMBOL = "WDO@"
DIA = "2026-08-28"

#: Mesma leitura de `wdo_grid_reload_f1_lab.py::_ECONOMIA_WDO`.
_ECONOMIA_WDO = (0.01, 0.001)
CAPITAL_NOCIONAL = 1_000_000.0
MAX_OPEN_CONTRATOS = 1


def main() -> None:
    df = load_m1(SYMBOL)
    if df.empty:
        raise SystemExit(f"sem dado M1 salvo para {SYMBOL!r}.")
    df = df.sort_index()
    bars = df[df.index.date == pd_date(DIA)]
    if bars.empty:
        raise SystemExit(f"sem barras M1 para {SYMBOL!r} em {DIA} -- rode "
                          f"backfill_m1.py --symbol {SYMBOL} primeiro.")

    print(f"[wdof1_dia] {SYMBOL} {DIA}: {len(bars)} barras M1 "
          f"({bars.index.min()} -> {bars.index.max()} UTC)")
    if len(bars) < 400:
        print(f"AVISO: pregao incompleto (< 400 barras tipicas) -- resultado "
              f"pode nao refletir o dia inteiro.")

    strat = get_daytrade_robot("wdo_grid_reload_maker")
    print(f"candidato: T{strat.profit_ticks} S{strat.stop_ticks} "
          f"x{strat.level_spacing_ticks} (defaults de producao atuais)")

    profile = profile_for(SYMBOL)
    trade_tick_value, trade_tick_size = _ECONOMIA_WDO
    cfg = config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=CAPITAL_NOCIONAL,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
        max_open_contracts=MAX_OPEN_CONTRATOS,
    )

    result = run_intraday_backtest(bars, strat, cfg)
    item = linha_de_resultado(f"WDO F1 maker ({DIA})", result, CAPITAL_NOCIONAL,
                               capital_nocional=True)
    print()
    print(cabecalho())
    print(linha(item))

    if result.trades:
        print("\ntrades do dia (hora entrada -> saida, lado, R$):")
        for t in result.trades:
            print(f"  {t.entry_ts} -> {t.exit_ts}  {t.side:5s}  R$ {t.pnl_brl:,.2f}")


def pd_date(s: str):
    import datetime
    return datetime.date.fromisoformat(s)


if __name__ == "__main__":
    main()
