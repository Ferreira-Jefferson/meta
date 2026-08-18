"""Gera tags automáticas a partir de trades e snapshots.

Estas tags ficam em `notes` e alimentam agregações do dashboard.
Objetivo: transformar cada trade em dado analisável ("por que ganhamos, por que perdemos").
"""
from __future__ import annotations

from core.models import ExitReason, MarketSnapshot, Trade


def signal_quality(entry: MarketSnapshot) -> str:
    """textbook | weak | late

    - textbook: cruzamento recente (≤ 5 dias), MM50 sobe > 0.5% acima da MM200, IBOV forte
    - late: cruzamento antigo (> 20 dias)
    - weak: caso geral (média intermediária)
    """
    if entry.days_since_cross > 20:
        return "late"
    if entry.days_since_cross <= 5 and entry.mm50_over_mm200_pct >= 0.005 and entry.ibov_trend_strength > 0.02:
        return "textbook"
    return "weak"


def market_regime(entry: MarketSnapshot) -> str:
    if entry.ibov_trend_strength > 0.05:
        return "bull"
    if entry.ibov_trend_strength < -0.05:
        return "bear"
    return "lateral"


def outcome(trade: Trade) -> str:
    if trade.exit_price is None:
        return "open"
    if trade.pnl_pct > 0.005:
        return "winner"
    if trade.pnl_pct < -0.005:
        return "loser"
    return "breakeven"


def exit_type(trade: Trade) -> str:
    mapping = {
        ExitReason.CROSS_DOWN: "trend_reversal",
        ExitReason.STOP: "stop_hit",
        ExitReason.TRAIL_STOP: "trail_stop",
        ExitReason.IBOV_DEFENSIVE: "defensive",
        ExitReason.DEFENSIVE_ABSOLUTE_MOM: "defensive",
        ExitReason.MEAN_REVERSION_DONE: "target",
        ExitReason.TARGET_MID_BAND: "target",
        ExitReason.ROTATION_OUT: "rotation",
        ExitReason.MANUAL: "time",
        ExitReason.OPEN: "open",
    }
    return mapping.get(trade.exit_reason, "other")


def volatility_bucket(entry: MarketSnapshot) -> str:
    ratio = entry.atr14 / entry.close if entry.close else 0.0
    if ratio < 0.015:
        return "low"
    if ratio < 0.03:
        return "mid"
    return "high"


def enrich(trade: Trade) -> dict[str, str]:
    if trade.entry_snapshot is None:
        return {}
    return {
        "signal_quality": signal_quality(trade.entry_snapshot),
        "market_regime_at_entry": market_regime(trade.entry_snapshot),
        "outcome": outcome(trade),
        "exit_type": exit_type(trade),
        "volatility_bucket": volatility_bucket(trade.entry_snapshot),
    }
