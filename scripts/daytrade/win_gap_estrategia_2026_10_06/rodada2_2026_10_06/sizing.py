# -*- coding: utf-8 -*-
"""Dimensionamento de PRODUCAO (mesma conta de `IntradaySessionMachine._cap_capital_atual`), chamado com as
funcoes reais de `strategy.daytrade.base`; `hard_cap` = `max_open_contracts` que `config_for` devolve a R$1.000."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from strategy.daytrade.base import contracts_from_capital_escada, contracts_from_capital_operacional  # noqa: E402

MARGEM = 100.0
BUFFER = 2.0
HARD_CAP = 5          # config_for(cash_brl=1000, margin_per_contract_brl=100).max_open_contracts
CAPITAL = 1000.0


def n_contratos(cash: float) -> int:
    teto = contracts_from_capital_operacional(cash, MARGEM, BUFFER, hard_cap=HARD_CAP)
    esc = contracts_from_capital_escada(cash, MARGEM, hard_cap=HARD_CAP)
    return min(teto, esc) if esc >= 1 else min(teto, 1)
