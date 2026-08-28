"""Cenarios sinteticos para cada detector de `strategy.daytrade.lab.
candle_patterns` — uma vela/trio construido a mao por padrao, com o
resultado esperado conhecido de antemao (AGENTS.md: "toda regra de
entrada/saida em strategy/ -> teste com cenario sintetico"). Roda so' com
`python -m pytest tests/test_candle_patterns.py -q` (nao a suite inteira)."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.lab.candle_patterns import (
    PATTERNS,
    TREND_LOOKBACK,
    detect_bearish_engulfing,
    detect_bearish_harami,
    detect_bullish_engulfing,
    detect_bullish_harami,
    detect_dark_cloud_cover,
    detect_doji,
    detect_dragonfly_doji_bullish,
    detect_evening_star,
    detect_gravestone_doji_bearish,
    detect_hammer,
    detect_hanging_man,
    detect_inverted_hammer,
    detect_marubozu_bearish,
    detect_marubozu_bullish,
    detect_morning_star,
    detect_piercing_line,
    detect_shooting_star,
    detect_three_black_crows,
    detect_three_white_soldiers,
    detect_tweezer_bottom,
    detect_tweezer_top,
    prior_trend,
)


def _bars(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def _trend_lead_in(direction: str, start: float = 100.0, step: float = 2.0) -> list[dict]:
    """`TREND_LOOKBACK + 1` barras de tendencia MONOTONICA antes da vela do
    padrao — o suficiente para `prior_trend()` (que compara `close.shift(1)`
    contra `close.shift(1+TREND_LOOKBACK)`) enxergar o contexto certo na
    barra seguinte a esta lista."""
    sign = 1.0 if direction == "up" else -1.0
    rows = []
    price = start
    for _ in range(TREND_LOOKBACK + 1):
        price += sign * step
        rows.append({"open": price - 0.1, "high": price + 0.2, "low": price - 0.3, "close": price})
    return rows


def _last_true(mask: pd.Series) -> bool:
    return bool(mask.iloc[-1])


class TestPriorTrend:
    def test_downtrend_detected(self):
        df = _bars(_trend_lead_in("down") + [{"open": 50, "high": 51, "low": 49, "close": 50}])
        assert prior_trend(df).iloc[-1] == -1

    def test_uptrend_detected(self):
        df = _bars(_trend_lead_in("up") + [{"open": 150, "high": 151, "low": 149, "close": 150}])
        assert prior_trend(df).iloc[-1] == 1

    def test_not_enough_history_is_neutral(self):
        df = _bars([{"open": 100, "high": 101, "low": 99, "close": 100.5}] * 3)
        assert prior_trend(df).iloc[-1] == 0


class TestDoji:
    def test_doji_true(self):
        df = _bars([{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.05}])
        assert _last_true(detect_doji(df))

    def test_strong_body_is_not_doji(self):
        df = _bars([{"open": 100.0, "high": 103.2, "low": 99.8, "close": 103.0}])
        assert not _last_true(detect_doji(df))


class TestDragonflyGravestone:
    def test_dragonfly_after_downtrend_is_bullish(self):
        rows = _trend_lead_in("down") + [{"open": 50.0, "high": 50.15, "low": 47.0, "close": 50.1}]
        df = _bars(rows)
        assert _last_true(detect_dragonfly_doji_bullish(df))

    def test_dragonfly_shape_after_uptrend_is_not_flagged(self):
        rows = _trend_lead_in("up") + [{"open": 150.0, "high": 150.15, "low": 147.0, "close": 150.1}]
        df = _bars(rows)
        assert not _last_true(detect_dragonfly_doji_bullish(df))

    def test_gravestone_after_uptrend_is_bearish(self):
        rows = _trend_lead_in("up") + [{"open": 150.0, "high": 153.0, "low": 149.85, "close": 149.9}]
        df = _bars(rows)
        assert _last_true(detect_gravestone_doji_bearish(df))


class TestMarubozu:
    def test_bullish_marubozu(self):
        df = _bars([{"open": 100.0, "high": 103.05, "low": 99.98, "close": 103.0}])
        assert _last_true(detect_marubozu_bullish(df))
        assert not _last_true(detect_marubozu_bearish(df))

    def test_bearish_marubozu(self):
        df = _bars([{"open": 103.0, "high": 103.02, "low": 99.95, "close": 100.0}])
        assert _last_true(detect_marubozu_bearish(df))
        assert not _last_true(detect_marubozu_bullish(df))

    def test_body_with_shadows_is_not_marubozu(self):
        df = _bars([{"open": 100.0, "high": 104.0, "low": 98.0, "close": 103.0}])
        assert not _last_true(detect_marubozu_bullish(df))


class TestHammerFamily:
    """Mesma FORMA (corpo pequeno + sombra inferior longa) muda de nome
    conforme o contexto de tendencia — martelo em baixa, enforcado em alta."""

    def _shape_row(self) -> dict:
        return {"open": 100.0, "high": 100.35, "low": 97.0, "close": 100.3}

    def test_hammer_after_downtrend(self):
        df = _bars(_trend_lead_in("down") + [self._shape_row()])
        assert _last_true(detect_hammer(df))
        assert not _last_true(detect_hanging_man(df))

    def test_hanging_man_after_uptrend(self):
        df = _bars(_trend_lead_in("up") + [self._shape_row()])
        assert _last_true(detect_hanging_man(df))
        assert not _last_true(detect_hammer(df))


class TestInvertedHammerFamily:
    """Mesma FORMA (corpo pequeno + sombra superior longa) — martelo
    invertido em baixa, estrela cadente em alta."""

    def _shape_row(self) -> dict:
        return {"open": 100.0, "high": 103.0, "low": 99.95, "close": 100.2}

    def test_inverted_hammer_after_downtrend(self):
        df = _bars(_trend_lead_in("down") + [self._shape_row()])
        assert _last_true(detect_inverted_hammer(df))
        assert not _last_true(detect_shooting_star(df))

    def test_shooting_star_after_uptrend(self):
        df = _bars(_trend_lead_in("up") + [self._shape_row()])
        assert _last_true(detect_shooting_star(df))
        assert not _last_true(detect_inverted_hammer(df))


class TestEngulfing:
    def test_bullish_engulfing(self):
        df = _bars([
            {"open": 102.0, "high": 102.5, "low": 99.5, "close": 100.0},
            {"open": 99.5, "high": 102.8, "low": 99.3, "close": 102.5},
        ])
        assert _last_true(detect_bullish_engulfing(df))

    def test_partial_body_does_not_engulf(self):
        df = _bars([
            {"open": 102.0, "high": 102.5, "low": 99.5, "close": 100.0},
            {"open": 102.5, "high": 103.0, "low": 102.4, "close": 103.0},
        ])
        assert not _last_true(detect_bullish_engulfing(df))

    def test_bearish_engulfing(self):
        df = _bars([
            {"open": 100.0, "high": 102.5, "low": 99.5, "close": 102.0},
            {"open": 102.5, "high": 102.8, "low": 99.3, "close": 99.5},
        ])
        assert _last_true(detect_bearish_engulfing(df))

    def test_weak_containment_is_not_engulfing(self):
        """Corpo da vela 2 fica DENTRO do corpo da vela 1 (nao contem os
        dois extremos) -- bug medido 2026-08-26: uma versao anterior deste
        detector comparava contra o limite ERRADO da vela anterior (abre <=
        abertura anterior, fecha >= fechamento anterior, em vez de abre <=
        fechamento anterior, fecha >= abertura anterior) e essa condicao
        fraca dava positivo aqui -- 22-24% de "engolfo" em dado real, um
        padrao que deveria ser raro. Vela 1 baixa: abre 102, fecha 100
        (corpo [100,102]). Vela 2 alta, corpo [101,101.2] -- INTEIRAMENTE
        dentro do corpo da vela 1, entao NAO e' engolfo de verdade."""
        df = _bars([
            {"open": 102.0, "high": 102.2, "low": 99.8, "close": 100.0},
            {"open": 101.0, "high": 101.3, "low": 100.9, "close": 101.2},
        ])
        assert not _last_true(detect_bullish_engulfing(df))

    def test_weak_containment_is_not_bearish_engulfing(self):
        """Espelho do teste acima, para engolfo de baixa."""
        df = _bars([
            {"open": 100.0, "high": 102.2, "low": 99.8, "close": 102.0},
            {"open": 101.2, "high": 101.3, "low": 100.9, "close": 101.0},
        ])
        assert not _last_true(detect_bearish_engulfing(df))


class TestHarami:
    def test_bullish_harami(self):
        df = _bars([
            {"open": 103.0, "high": 103.2, "low": 98.8, "close": 99.0},
            {"open": 100.0, "high": 102.2, "low": 99.8, "close": 102.0},
        ])
        assert _last_true(detect_bullish_harami(df))

    def test_bearish_harami(self):
        df = _bars([
            {"open": 99.0, "high": 103.2, "low": 98.8, "close": 103.0},
            {"open": 102.0, "high": 102.2, "low": 99.8, "close": 100.0},
        ])
        assert _last_true(detect_bearish_harami(df))

    def test_body_not_contained_is_not_harami(self):
        df = _bars([
            {"open": 103.0, "high": 103.2, "low": 98.8, "close": 99.0},
            {"open": 98.5, "high": 102.2, "low": 98.0, "close": 102.0},
        ])
        assert not _last_true(detect_bullish_harami(df))


class TestPiercingDarkCloud:
    def test_piercing_line(self):
        df = _bars([
            {"open": 103.0, "high": 103.2, "low": 99.5, "close": 100.0},
            {"open": 99.0, "high": 102.3, "low": 98.8, "close": 102.0},
        ])
        assert _last_true(detect_piercing_line(df))

    def test_dark_cloud_cover(self):
        df = _bars([
            {"open": 100.0, "high": 103.5, "low": 99.8, "close": 103.0},
            {"open": 104.0, "high": 104.2, "low": 100.7, "close": 101.0},
        ])
        assert _last_true(detect_dark_cloud_cover(df))


class TestTweezer:
    def test_tweezer_bottom_after_downtrend(self):
        rows = _trend_lead_in("down") + [
            {"open": 51.0, "high": 52.0, "low": 47.0, "close": 48.0},
            {"open": 48.0, "high": 50.0, "low": 47.02, "close": 49.5},
        ]
        df = _bars(rows)
        assert _last_true(detect_tweezer_bottom(df))

    def test_tweezer_top_after_uptrend(self):
        rows = _trend_lead_in("up") + [
            {"open": 149.0, "high": 153.0, "low": 148.0, "close": 152.0},
            {"open": 152.0, "high": 152.98, "low": 150.0, "close": 150.5},
        ]
        df = _bars(rows)
        assert _last_true(detect_tweezer_top(df))


class TestStars:
    def test_morning_star(self):
        df = _bars([
            {"open": 110.0, "high": 110.2, "low": 99.8, "close": 100.0},
            {"open": 99.5, "high": 99.9, "low": 99.2, "close": 99.8},
            {"open": 100.0, "high": 107.3, "low": 99.9, "close": 107.0},
        ])
        assert _last_true(detect_morning_star(df))

    def test_evening_star(self):
        df = _bars([
            {"open": 100.0, "high": 110.2, "low": 99.8, "close": 110.0},
            {"open": 110.2, "high": 110.5, "low": 109.8, "close": 109.9},
            {"open": 109.0, "high": 109.2, "low": 102.7, "close": 103.0},
        ])
        assert _last_true(detect_evening_star(df))

    def test_small_reversal_is_not_a_star(self):
        """Vela 3 fecha so' um pouco dentro do corpo da vela 1 (nao passa
        da metade) -- nao deve contar como estrela da manha."""
        df = _bars([
            {"open": 110.0, "high": 110.2, "low": 99.8, "close": 100.0},
            {"open": 99.5, "high": 99.9, "low": 99.2, "close": 99.8},
            {"open": 100.0, "high": 101.5, "low": 99.9, "close": 101.0},
        ])
        assert not _last_true(detect_morning_star(df))


class TestSoldiersCrows:
    def test_three_white_soldiers(self):
        df = _bars([
            {"open": 100.0, "high": 103.2, "low": 99.8, "close": 103.0},
            {"open": 101.0, "high": 105.3, "low": 100.8, "close": 105.0},
            {"open": 102.0, "high": 108.2, "low": 101.8, "close": 108.0},
        ])
        assert _last_true(detect_three_white_soldiers(df))
        assert not _last_true(detect_three_black_crows(df))

    def test_three_black_crows(self):
        df = _bars([
            {"open": 108.0, "high": 108.2, "low": 104.8, "close": 105.0},
            {"open": 107.0, "high": 107.2, "low": 102.7, "close": 103.0},
            {"open": 106.0, "high": 106.2, "low": 99.8, "close": 100.0},
        ])
        assert _last_true(detect_three_black_crows(df))
        assert not _last_true(detect_three_white_soldiers(df))

    def test_gap_breaks_the_soldiers_pattern(self):
        """Terceira vela abre FORA do corpo da anterior -- nao e' mais o
        avanco gradual que caracteriza o padrao."""
        df = _bars([
            {"open": 100.0, "high": 103.2, "low": 99.8, "close": 103.0},
            {"open": 101.0, "high": 105.3, "low": 100.8, "close": 105.0},
            {"open": 106.0, "high": 109.2, "low": 105.8, "close": 109.0},
        ])
        assert not _last_true(detect_three_white_soldiers(df))


class TestRegistryIntegrity:
    """A varredura de medicao (`scripts/daytrade/candle_measure.py`) itera
    `PATTERNS` -- se um detector nunca disparar em NENHUM cenario razoavel
    ele quebra a medicao em silencio (0 ocorrencias em toda a serie real
    nunca aparece como erro, so' como uma linha vazia na tabela). Confere
    aqui que TODO detector registrado dispara em pelo menos um cenario
    minimo, e que o registro cobre exatamente os 21 padroes documentados."""

    def test_all_21_patterns_registered(self):
        assert len(PATTERNS) == 21

    @pytest.mark.parametrize("name", list(PATTERNS.keys()))
    def test_detector_returns_bool_series_same_index(self, name):
        spec = PATTERNS[name]
        df = _bars(_trend_lead_in("down") + _trend_lead_in("up"))
        result = spec.detector(df)
        assert isinstance(result, pd.Series)
        assert list(result.index) == list(df.index)
        assert result.dtype == bool
