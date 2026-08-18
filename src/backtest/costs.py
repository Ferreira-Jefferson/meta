from __future__ import annotations

from core.config import CostModel


def apply_slippage(price: float, side: str, model: CostModel) -> float:
    """Ajusta o preço pela slippage estimada. Compra sobe, venda desce."""
    factor = 1.0 + model.slippage_pct if side == "buy" else 1.0 - model.slippage_pct
    return price * factor


def fees_for_leg(gross: float, model: CostModel) -> float:
    return gross * model.per_side_pct
