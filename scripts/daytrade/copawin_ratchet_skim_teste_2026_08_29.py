"""Testa a ideia do dono (2026-08-29, resposta ao achado do item 3.9 de
`LICOES_DE_PRODUCAO.md`): em vez do dimensionamento por caixa ser LINEAR
(`contracts_from_capital_com_reserva` direto sobre o caixa inteiro -- o que
fez o CopaWin ir de 12 pra 15 contratos num unico dia bom, e quase zerar no
trade seguinte), separar uma FATIA do caixa a cada marco de crescimento e
parar de contar essa fatia como "caixa pra operar":

    a cada vez que o caixa total cresce `limiar` (60% default) acima do
    ultimo marco, separa `percentual` (10% default) do caixa TOTAL naquele
    instante -- e so' o que sobra depois de separar (nunca o caixa cheio)
    alimenta `contracts_from_capital_com_reserva`.

Exemplo do proprio dono: caixa 100 -> chega em 160 (+60%) -> separa 10% de
160 = 16 -> opera dai em diante com 144 (nao 152 -- a conta do dono nao bate
com "10% do caixa", fica registrado aqui pra ele confirmar se quis dizer
outro percentual/base; o script usa a leitura literal "10% do caixa total no
marco").

NAO mexe em `copa_win.py` -- e' um teste isolado, subclasse local, pra medir
o EFEITO antes de decidir se vira o dimensionamento de producao. Roda o
MESMO histórico completo de WIN@ (182 pregoes) e o MESMO capital real
(R$3.000) do item 3.9, pra comparar linha a linha contra o baseline ja
medido (5 trades, R$3.000,00 -> R$68,50, um trade so' perdendo R$3.457,50).

Uso: `python -u scripts/daytrade/copawin_ratchet_skim_teste_2026_08_29.py`
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
from strategy.daytrade.base import contracts_from_capital_com_reserva  # noqa: E402
from strategy.daytrade.registry import _KWARGS_PADRAO  # noqa: E402
from strategy.daytrade.lab.copa_win import CopaWin  # noqa: E402

CAPITAL_INICIAL = 3_000.0
LIMIAR_CRESCIMENTO = 1.60
PERCENTUAL_SEPARADO = 0.10


class CopaWinRatchetSkim(CopaWin):
    """`CopaWin` com o mesmo dimensionamento, exceto que `quantidade_por_
    entrada` ve' o caixa DEPOIS de separar a fatia -- nunca o caixa cheio."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._capital_marco = CAPITAL_INICIAL
        self._capital_separado_acumulado = 0.0
        self.historico_skim: list[tuple[pd.Timestamp | None, float, float]] = []

    def on_capital_update(self, cash_brl: float) -> None:
        # `cash_brl` = caixa TOTAL real (initial_capital + realized_pnl) --
        # o separado e' so' uma LEITURA diferente pra `quantidade_por_
        # entrada`, nunca some da conta de verdade (mesmo espirito do
        # withdrawal overlay `FloorSkim` do lado diario: reserva, nao saque
        # fisico dentro do backtest).
        while cash_brl >= self._capital_marco * LIMIAR_CRESCIMENTO:
            self._capital_marco = cash_brl
            separado_agora = PERCENTUAL_SEPARADO * cash_brl
            self._capital_separado_acumulado += separado_agora
            self.historico_skim.append((None, cash_brl, self._capital_separado_acumulado))
        operacional = max(0.0, cash_brl - self._capital_separado_acumulado)
        super().on_capital_update(operacional)


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def main() -> None:
    df = load_m1("WIN@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= 400}
    bars = df[[d in completos for d in df.index.date]]
    profile = profile_for("WIN@")

    kwargs = dict(_KWARGS_PADRAO["copa_win"])
    strat = CopaWinRatchetSkim(**kwargs)
    cfg = config_for(
        profile, trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL_INICIAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)

    print(f"=== CopaWin RATCHET-SKIM (a cada +{int((LIMIAR_CRESCIMENTO-1)*100)}% do caixa, "
          f"separa {int(PERCENTUAL_SEPARADO*100)}% do total) -- WIN@, capital R${br(CAPITAL_INICIAL)} ===\n")
    for t in resultado.trades:
        print(f"{t.entry_ts} -> {t.exit_ts}  {t.side:5s} qty={t.quantity:3d}  "
              f"motivo={t.exit_reason}  pnl=R${br(t.pnl_brl)}")

    liquido = sum(t.pnl_brl for t in resultado.trades)
    equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else CAPITAL_INICIAL
    equity_min = float(resultado.equity_curve.min()) if not resultado.equity_curve.empty else CAPITAL_INICIAL

    print(f"\ntrades={len(resultado.trades)} | liquido=R${br(liquido)} | "
          f"equity final=R${br(equity_final)} | equity MINIMA=R${br(equity_min)}")
    print(f"caixa separado acumulado no fim: R${br(strat._capital_separado_acumulado)}")
    if resultado.wiped_out_at is not None:
        print(f"*** ZERADO em {resultado.wiped_out_at} ***")
    else:
        print("nunca zerou.")

    if strat.historico_skim:
        print("\nmarcos de separacao (caixa total no marco -> separado acumulado):")
        for _, total, acumulado in strat.historico_skim:
            print(f"  caixa=R${br(total)} -> separado acumulado=R${br(acumulado)} "
                  f"(operacional=R${br(total - acumulado)})")
    else:
        print("\nnenhum marco de +60% atingido no periodo.")

    print(f"\n--- baseline ja medido (item 3.9, sem skim) ---")
    print("trades=5 | liquido=R$-2.931,50 | equity final=R$68,50 | equity MINIMA=R$68,50 | nunca zerou.")


if __name__ == "__main__":
    main()
