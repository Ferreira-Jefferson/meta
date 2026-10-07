from __future__ import annotations

import random

import pytest

from social_arbitrage.simulacao import monte_carlo, simular_trajetoria


# ---------------------------------------------------------------------------
# simular_trajetoria
# ---------------------------------------------------------------------------

def test_simular_trajetoria_todas_vitorias_compoe_geometricamente():
    trajetoria = simular_trajetoria(
        n_teses=3, prob_acerto_real=1.0, payoff_real=1.0, fracao_aposta=0.10,
        capital_inicial=1000.0, rng=random.Random(0),
    )
    assert len(trajetoria) == 4
    assert trajetoria[0] == 1000.0
    assert trajetoria[-1] == pytest.approx(1000.0 * (1.1 ** 3))


def test_simular_trajetoria_todas_derrotas_compoe_geometricamente():
    trajetoria = simular_trajetoria(
        n_teses=3, prob_acerto_real=0.0, payoff_real=1.0, fracao_aposta=0.10,
        capital_inicial=1000.0, rng=random.Random(0),
    )
    assert trajetoria[-1] == pytest.approx(1000.0 * (0.9 ** 3))


@pytest.mark.parametrize("fracao", [0.0, -0.1, 1.1])
def test_simular_trajetoria_recusa_fracao_fora_do_dominio(fracao):
    with pytest.raises(ValueError):
        simular_trajetoria(n_teses=1, prob_acerto_real=0.5, payoff_real=1.0, fracao_aposta=fracao, capital_inicial=1000.0, rng=random.Random(0))


# ---------------------------------------------------------------------------
# monte_carlo
# ---------------------------------------------------------------------------

def test_monte_carlo_recusa_parametros_invalidos():
    with pytest.raises(ValueError):
        monte_carlo(n_trajetorias=10, n_teses=10, prob_acerto_real=1.0, payoff_real=1.0)
    with pytest.raises(ValueError):
        monte_carlo(n_trajetorias=10, n_teses=10, prob_acerto_real=0.5, payoff_real=0.0)
    with pytest.raises(ValueError):
        monte_carlo(n_trajetorias=0, n_teses=10, prob_acerto_real=0.5, payoff_real=1.0)
    with pytest.raises(ValueError):
        monte_carlo(n_trajetorias=10, n_teses=10, prob_acerto_real=0.5, payoff_real=1.0, limiar_ruina_pct=1.5)


def test_monte_carlo_sem_edge_assumida_lanca():
    # prob_acerto_assumida=0.3, payoff=1.0 -> kelly cru negativo -> fracao 0
    with pytest.raises(ValueError):
        monte_carlo(
            n_trajetorias=10, n_teses=10, prob_acerto_real=0.6, payoff_real=1.2,
            prob_acerto_assumida=0.3, payoff_assumido=1.0,
        )


def test_monte_carlo_edge_forte_cresce_capital_e_nao_arruina(seed=7):
    r = monte_carlo(
        n_trajetorias=2000, n_teses=50,
        prob_acerto_real=0.90, payoff_real=1.0,
        fracao_kelly=0.25, capital_inicial=100_000.0, seed=seed,
    )
    assert r.mediana_final > r.capital_inicial
    assert r.prob_ruina == 0.0


def test_monte_carlo_e_reprodutivel_com_mesma_seed():
    kwargs = dict(n_trajetorias=500, n_teses=30, prob_acerto_real=0.6, payoff_real=1.2, fracao_kelly=0.5, seed=123)
    r1 = monte_carlo(**kwargs)
    r2 = monte_carlo(**kwargs)
    assert r1 == r2


def test_monte_carlo_kelly_cheio_tem_mais_dispersao_que_quarto_kelly():
    comum = dict(n_trajetorias=2000, n_teses=50, prob_acerto_real=0.6, payoff_real=1.2, seed=99)
    cheio = monte_carlo(fracao_kelly=1.0, **comum)
    quarto = monte_carlo(fracao_kelly=0.25, **comum)
    assert (cheio.p95_final - cheio.p5_final) > (quarto.p95_final - quarto.p5_final)


def test_monte_carlo_excesso_de_confianca_aumenta_prob_ruina():
    comum = dict(n_trajetorias=2000, n_teses=80, prob_acerto_real=0.55, payoff_real=1.0, fracao_kelly=1.0, seed=5)
    estimativa_correta = monte_carlo(**comum)
    excesso_confianca = monte_carlo(prob_acerto_assumida=0.75, payoff_assumido=1.0, **comum)
    assert excesso_confianca.prob_ruina >= estimativa_correta.prob_ruina
