from datetime import date

from core.models import ExitReason, MarketSnapshot, Trade
from journal.enrichment import enrich, market_regime, signal_quality, volatility_bucket


def _snap(**overrides) -> MarketSnapshot:
    base = dict(
        close=100.0, volume=1_000_000, volume_vs_avg20=1.0,
        mm20=99, mm50=95, mm200=90, mm50_over_mm200_pct=0.055,
        days_since_cross=3, ifr14=55.0, atr14=1.5, historical_vol_30d=0.25,
        distance_from_52w_high_pct=-0.05, distance_from_52w_low_pct=0.30,
        ibov_close=120_000, ibov_mm200=110_000, ibov_above_mm200=True,
        ibov_trend_strength=0.09, correlation_with_ibov_60d=0.62,
    )
    base.update(overrides)
    return MarketSnapshot(**base)


def test_signal_quality_textbook():
    assert signal_quality(_snap(days_since_cross=3, mm50_over_mm200_pct=0.01, ibov_trend_strength=0.03)) == "textbook"


def test_signal_quality_late():
    assert signal_quality(_snap(days_since_cross=30)) == "late"


def test_signal_quality_weak_default():
    assert signal_quality(_snap(days_since_cross=10, mm50_over_mm200_pct=0.002, ibov_trend_strength=0.01)) == "weak"


def test_market_regime_bull_bear_lateral():
    assert market_regime(_snap(ibov_trend_strength=0.10)) == "bull"
    assert market_regime(_snap(ibov_trend_strength=-0.10)) == "bear"
    assert market_regime(_snap(ibov_trend_strength=0.0)) == "lateral"


def test_volatility_bucket():
    assert volatility_bucket(_snap(atr14=1.0, close=100)) == "low"
    assert volatility_bucket(_snap(atr14=2.0, close=100)) == "mid"
    assert volatility_bucket(_snap(atr14=5.0, close=100)) == "high"


def test_enrich_full_bundle():
    trade = Trade(
        ticker="PETR4.SA",
        strategy_name="baseline_ma_cross",
        strategy_version="1.0",
        entry_date=date(2024, 1, 3),
        entry_price=30.0, quantity=100, capital_allocated=3_000.0,
        exit_date=date(2024, 3, 15), exit_price=33.0,
        exit_reason=ExitReason.CROSS_DOWN,
        entry_snapshot=_snap(),
    )
    tags = enrich(trade)
    assert set(tags.keys()) == {
        "signal_quality", "market_regime_at_entry", "outcome", "exit_type", "volatility_bucket"
    }
    assert tags["outcome"] == "winner"
    assert tags["exit_type"] == "trend_reversal"
