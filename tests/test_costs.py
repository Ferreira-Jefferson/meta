"""Testes de `backtest/costs.py::fees_for_leg` — corretagem fixa por perna que
não fecha lote padrão (2026-08-21, ver `core/config.py::CostModel.
fractional_fixed_fee`)."""
from __future__ import annotations

import pytest

from backtest.costs import fees_for_leg
from core.config import CostModel


def test_fees_for_leg_default_fixo_zero_preserva_comportamento_historico():
    """Default `fractional_fixed_fee=0.0` -- só custo percentual, byte-a-byte
    igual a antes desta funcionalidade existir, mesmo para quantidade
    pequena (abaixo do lote padrão)."""
    model = CostModel()
    assert fees_for_leg(1_000.0, model, quantity=3) == pytest.approx(1_000.0 * model.per_side_pct)
    assert fees_for_leg(1_000.0, model, quantity=300) == pytest.approx(1_000.0 * model.per_side_pct)


def test_fees_for_leg_quantidade_abaixo_do_lote_cobra_fixo_alem_do_percentual():
    model = CostModel(fractional_fixed_fee=1.90, fractional_lot_shares=100)
    fees = fees_for_leg(50.0, model, quantity=3)
    assert fees == pytest.approx(50.0 * model.per_side_pct + 1.90)


def test_fees_for_leg_quantidade_no_ou_acima_do_lote_nao_cobra_fixo():
    """>= `fractional_lot_shares` fecha lote padrão (gratuito na Rico) --
    a fronteira exata (== 100) já conta como lote fechado, não como
    fracionário."""
    model = CostModel(fractional_fixed_fee=1.90, fractional_lot_shares=100)
    fees_no_limiar = fees_for_leg(5_000.0, model, quantity=100)
    fees_acima = fees_for_leg(50_000.0, model, quantity=1_000)
    assert fees_no_limiar == pytest.approx(5_000.0 * model.per_side_pct)
    assert fees_acima == pytest.approx(50_000.0 * model.per_side_pct)


def test_fees_for_leg_fixo_domina_quando_posicao_e_pequena():
    """Numa posição de R$20 (ex. R$100 dividido em 5 slots), o fixo de
    R$1,90 é a maior parte do custo -- exatamente o achado que motivou esta
    mudança (backtest antigo subestimava ~300x o custo real nesse regime)."""
    model = CostModel(fractional_fixed_fee=1.90, fractional_lot_shares=100)
    fees = fees_for_leg(20.0, model, quantity=1)
    percentual = 20.0 * model.per_side_pct
    assert fees == pytest.approx(percentual + 1.90)
    assert fees / 20.0 > 0.09  # > 9% da posição, dominado pelo fixo
