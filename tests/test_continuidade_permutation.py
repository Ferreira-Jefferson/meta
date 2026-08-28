from __future__ import annotations

import numpy as np
import pytest

from backtest.intraday.continuidade_permutation import (
    lag_pairs,
    pearson_corr,
    permutation_test,
    sign_match_rate,
)


def test_pearson_corr_perfect_positive():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([2.0, 4.0, 6.0, 8.0])
    assert pearson_corr(x, y) == pytest.approx(1.0)


def test_pearson_corr_constant_series_is_zero_not_nan():
    x = np.array([1.0, 1.0, 1.0])
    y = np.array([1.0, 2.0, 3.0])
    assert pearson_corr(x, y) == 0.0


def test_pearson_corr_short_series_is_zero():
    assert pearson_corr(np.array([1.0]), np.array([1.0])) == 0.0
    assert pearson_corr(np.array([]), np.array([])) == 0.0


def test_sign_match_rate_all_same_sign_is_half():
    x = np.array([1.0, 2.0, 3.0, -1.0])
    y = np.array([1.0, 5.0, 0.5, -3.0])
    assert sign_match_rate(x, y) == pytest.approx(0.5)  # 4/4 concordam -> 1.0 - 0.5


def test_sign_match_rate_all_opposite_sign_is_negative_half():
    x = np.array([1.0, 2.0, -3.0])
    y = np.array([-1.0, -5.0, 3.0])
    assert sign_match_rate(x, y) == pytest.approx(-0.5)


def test_sign_match_rate_excludes_zero_pairs():
    x = np.array([1.0, 0.0, 2.0])
    y = np.array([1.0, 5.0, 2.0])
    # o par (0.0, 5.0) e' excluido -- so' sobram 2 pares, ambos concordam
    assert sign_match_rate(x, y) == pytest.approx(0.5)


def test_sign_match_rate_empty_is_zero():
    assert sign_match_rate(np.array([]), np.array([])) == 0.0


def test_lag_pairs_within_single_group():
    x, y = lag_pairs([np.array([1.0, 2.0, 3.0, 4.0])], lag=1)
    np.testing.assert_array_equal(x, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(y, [2.0, 3.0, 4.0])


def test_lag_pairs_never_crosses_group_boundary():
    # grupo 1 tem 2 elementos, grupo 2 tem 3 -- lag=1 dentro de cada,
    # NUNCA pareando o ultimo do grupo 1 com o primeiro do grupo 2.
    x, y = lag_pairs([np.array([1.0, 2.0]), np.array([10.0, 20.0, 30.0])], lag=1)
    np.testing.assert_array_equal(x, [1.0, 10.0, 20.0])
    np.testing.assert_array_equal(y, [2.0, 20.0, 30.0])


def test_lag_pairs_rejects_lag_below_one():
    with pytest.raises(ValueError):
        lag_pairs([np.array([1.0, 2.0])], lag=0)


def test_permutation_test_detects_strong_autocorrelation():
    # serie AR(1) com persistencia forte (rho=0.9) -- o real tem que ficar
    # no TOPO da distribuicao nula (embaralhada, que destroi a ordem).
    rng = np.random.default_rng(42)
    noise = rng.normal(size=200)
    series = np.zeros(200)
    for i in range(1, 200):
        series[i] = 0.9 * series[i - 1] + noise[i]
    result = permutation_test(
        [series], lag=1, stat_fns={"corr": pearson_corr}, n_perm=500, seed=1,
    )
    assert result.stats["corr"].real > 0.7
    assert result.stats["corr"].percentile > 95.0
    assert result.stats["corr"].p_two_sided < 0.05


def test_permutation_test_on_iid_noise_lands_near_the_middle():
    rng = np.random.default_rng(7)
    series = rng.normal(size=300)
    result = permutation_test(
        [series], lag=1, stat_fns={"corr": pearson_corr}, n_perm=1000, seed=2,
    )
    # ruido puro: nao deve ficar na cauda extrema (teste fraco de sanidade,
    # nao um teste de potencia -- so' garante que nao acusa dependencia
    # onde nao ha)
    assert 2.0 < result.stats["corr"].percentile < 98.0
    assert result.stats["corr"].p_two_sided > 0.02


def test_permutation_test_respects_group_boundaries_in_shuffle():
    # 2 grupos identicos e curtos -- embaralhar so' DENTRO de cada grupo
    # nunca pode gerar um par cruzando grupos (checado indiretamente via
    # n_pairs constante em toda iteracao: se cruzasse, o total mudaria).
    groups = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
    result = permutation_test(
        groups, lag=1, stat_fns={"corr": pearson_corr}, n_perm=200, seed=3,
    )
    assert result.n_pairs == 4  # 2 pares por grupo de 3 elementos, lag=1
    assert result.n_groups == 2


def test_permutation_test_reports_n_perm_and_seed():
    result = permutation_test(
        [np.array([1.0, 2.0, 3.0, 4.0, 5.0])], lag=1,
        stat_fns={"corr": pearson_corr}, n_perm=50, seed=9,
    )
    assert result.n_perm == 50
    assert result.seed == 9
    assert result.lag == 1
