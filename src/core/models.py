from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class ExitReason(str, Enum):
    CROSS_DOWN = "cross_down"
    STOP = "stop"
    IBOV_DEFENSIVE = "ibov_defensive"
    MANUAL = "manual"
    OPEN = "open"
    MEAN_REVERSION_DONE = "mean_reversion_done"
    TARGET_MID_BAND = "target_mid_band"
    ROTATION_OUT = "rotation_out"
    DEFENSIVE_ABSOLUTE_MOM = "defensive_absolute_mom"
    TRAIL_STOP = "trail_stop"
    WITHDRAWAL = "withdrawal"  # posicao zerada para levantar caixa de saque programado


@dataclass(frozen=True)
class Signal:
    ticker: str
    on_date: date
    type: SignalType
    reason: str


@dataclass
class MarketSnapshot:
    """Snapshot de features de mercado em um ponto do tempo.

    Preenchido pelo engine no momento da entrada e da saída de cada trade,
    persistido em `signal_snapshots` para análise posterior.
    """

    close: float
    volume: float
    volume_vs_avg20: float
    mm20: float
    mm50: float
    mm200: float
    mm50_over_mm200_pct: float
    days_since_cross: int
    ifr14: float
    atr14: float
    historical_vol_30d: float
    distance_from_52w_high_pct: float
    distance_from_52w_low_pct: float
    ibov_close: float
    ibov_mm200: float
    ibov_above_mm200: bool
    ibov_trend_strength: float
    correlation_with_ibov_60d: float


@dataclass
class Trade:
    ticker: str
    strategy_name: str
    strategy_version: str
    entry_date: date
    entry_price: float
    quantity: int
    capital_allocated: float
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_reason: ExitReason = ExitReason.OPEN
    fees_total: float = 0.0
    slippage_total: float = 0.0
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    entry_snapshot: Optional[MarketSnapshot] = None
    exit_snapshot: Optional[MarketSnapshot] = None
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.exit_date is None

    @property
    def pnl_brl(self) -> float:
        if self.exit_price is None:
            return 0.0
        gross = (self.exit_price - self.entry_price) * self.quantity
        return gross - self.fees_total

    @property
    def pnl_pct(self) -> float:
        if self.exit_price is None or self.capital_allocated == 0:
            return 0.0
        return self.pnl_brl / self.capital_allocated

    @property
    def holding_days(self) -> int:
        if self.exit_date is None:
            return 0
        return (self.exit_date - self.entry_date).days

    @property
    def r_multiple(self) -> float:
        if self.exit_price is None:
            return 0.0
        risk_per_share = self.entry_price * 0.15
        if risk_per_share == 0:
            return 0.0
        return (self.exit_price - self.entry_price) / risk_per_share
