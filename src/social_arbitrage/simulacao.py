"""Monte Carlo do DIMENSIONAMENTO (Kelly fracionario), nao da deteccao.

Isto NAO e' um backtest da estrategia -- nao existe historico real de
observacao de consumo (Camilo) nem de posicionamento (Williams) neste repo
para rodar contra ele, e fabricar um seria exatamente o tipo de "resultado
de backtest nunca aferido contra o extrato" que `LICOES_DE_PRODUCAO.md`
existe para impedir. O que este modulo testa e' outra pergunta, honesta e
respondivel sem dado historico: DADO um edge hipotetico (prob_acerto/payoff
que o dono escolhe), a MATEMATICA de aposta fracionaria de Kelly segura o
capital, ou apanha da mesma fragilidade que quase quebrou Larry Williams em
1987?

Modelo: aposta fracao `f` (de `sizing.tamanho_meio_kelly`, FIXA ao longo da
trajetoria -- nao ha reestimativa dinamica aqui) do capital ATUAL a cada
tese. Vitoria: capital *= (1 + f*payoff_real). Derrota: capital *= (1 - f).
E' o modelo classico de aposta fracionaria composta (Kelly), nao uma soma de
resultados em reais fixos -- por isso o resultado e' MULTIPLICATIVO: uma
sequencia de derrotas reduz o capital que a proxima aposta ve, e o dono do
projeto ja documentou (`CLAUDE.md`, WDO F1) que censura silenciosa desse
tipo e' o jeito mais comum de uma medicao mentir.

`prob_acerto_assumida`/`payoff_assumido` sao SEPARADOS de `prob_acerto_real`/
`payoff_real` de proposito: o dono decide o TAMANHO da aposta com base no
que ACHA que e' o edge (assumida), mas o resultado de cada tese sai do edge
REAL. Iguais os dois = "estimativa perfeita". Assumida MELHOR que real =
excesso de confianca -- e' o cenario que expõe a fragilidade do Kelly cheio
que a docstring de `sizing.py` ja descreve.
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from social_arbitrage.sizing import tamanho_meio_kelly


def simular_trajetoria(
    *,
    n_teses: int,
    prob_acerto_real: float,
    payoff_real: float,
    fracao_aposta: float,
    capital_inicial: float,
    rng: random.Random,
) -> list[float]:
    """Uma trajetoria de capital, `n_teses` sorteios (Bernoulli, `prob_acerto_real`)
    depois do inicial -- `len(retorno) == n_teses + 1`. `fracao_aposta` e' a
    fracao do capital ATUAL apostada em CADA tese (ja resolvida por
    `tamanho_meio_kelly` fora daqui -- esta funcao so' aplica o numero, nao o
    calcula, para poder simular tambem `fracao_aposta=1.0` (Kelly cru) sem
    duplicar logica)."""
    if not 0.0 < fracao_aposta <= 1.0:
        raise ValueError(f"simular_trajetoria: `fracao_aposta` tem de estar em (0, 1], recebeu {fracao_aposta!r}.")
    capital = capital_inicial
    trajetoria = [capital]
    for _ in range(n_teses):
        if rng.random() < prob_acerto_real:
            capital *= 1.0 + fracao_aposta * payoff_real
        else:
            capital *= 1.0 - fracao_aposta
        trajetoria.append(capital)
    return trajetoria


@dataclass(frozen=True)
class ResultadoMonteCarlo:
    """Resumo de `n_trajetorias` simulacoes independentes -- nunca guarda so'
    a media (mesma exigencia de `metodo_numero_sem_dispersao` da memoria do
    projeto: dispersao SEMPRE junto do centro)."""

    fracao_kelly: float
    fracao_aposta_usada: float
    capital_inicial: float
    n_teses: int
    n_trajetorias: int
    mediana_final: float
    p5_final: float
    p10_final: float
    p90_final: float
    p95_final: float
    media_final: float
    prob_ruina: float
    limiar_ruina_pct: float


def monte_carlo(
    *,
    n_trajetorias: int,
    n_teses: int,
    prob_acerto_real: float,
    payoff_real: float,
    prob_acerto_assumida: float | None = None,
    payoff_assumido: float | None = None,
    fracao_kelly: float = 0.5,
    teto_pct: float = 0.40,
    capital_inicial: float = 100_000.0,
    limiar_ruina_pct: float = 0.10,
    seed: int | None = None,
) -> ResultadoMonteCarlo:
    """`n_trajetorias` simulacoes de `simular_trajetoria`, resumidas.

    `prob_acerto_assumida`/`payoff_assumido` default para os valores REAIS
    (estimativa perfeita) quando omitidos -- passe-os explicitamente para
    simular excesso de confianca (assumida mais otimista que a real).

    "Ruina" e' definida como capital final abaixo de `limiar_ruina_pct` do
    capital inicial (default 10%) -- o modelo multiplicativo nunca chega a
    ZERO exato com `fracao_aposta < 1.0`, entao um limiar e' a unica forma de
    falar em "quebrou" de um jeito que faz sentido aqui."""
    if not 0.0 < prob_acerto_real < 1.0:
        raise ValueError(f"monte_carlo: `prob_acerto_real` tem de estar em (0, 1), recebeu {prob_acerto_real!r}.")
    if payoff_real <= 0:
        raise ValueError(f"monte_carlo: `payoff_real` tem de ser > 0, recebeu {payoff_real!r}.")
    if n_trajetorias <= 0 or n_teses <= 0:
        raise ValueError(f"monte_carlo: `n_trajetorias` e `n_teses` tem de ser > 0, recebeu {n_trajetorias!r}/{n_teses!r}.")
    if not 0.0 < limiar_ruina_pct < 1.0:
        raise ValueError(f"monte_carlo: `limiar_ruina_pct` tem de estar em (0, 1), recebeu {limiar_ruina_pct!r}.")

    prob_assumida = prob_acerto_real if prob_acerto_assumida is None else prob_acerto_assumida
    payoff_assum = payoff_real if payoff_assumido is None else payoff_assumido

    fracao_aposta = tamanho_meio_kelly(prob_assumida, payoff_assum, fracao_kelly=fracao_kelly, teto_pct=teto_pct)
    if fracao_aposta <= 0.0:
        raise ValueError(
            f"monte_carlo: prob_acerto_assumida={prob_assumida!r}/payoff_assumido={payoff_assum!r} nao indicam "
            f"edge positiva (fracao de aposta <= 0) -- simular uma aposta de tamanho zero nao informa nada."
        )

    rng = random.Random(seed)
    finais = [
        simular_trajetoria(
            n_teses=n_teses, prob_acerto_real=prob_acerto_real, payoff_real=payoff_real,
            fracao_aposta=fracao_aposta, capital_inicial=capital_inicial, rng=rng,
        )[-1]
        for _ in range(n_trajetorias)
    ]
    finais.sort()
    limiar_ruina = capital_inicial * limiar_ruina_pct
    prob_ruina = sum(1 for f in finais if f < limiar_ruina) / n_trajetorias

    def _percentil(p: float) -> float:
        # `statistics.quantiles` com n=100 da os 99 pontos de corte percentual;
        # indexar direto e' mais simples e sem dependencia nova (numpy nao e'
        # importado so' para isso).
        pontos = statistics.quantiles(finais, n=100, method="inclusive")
        idx = max(0, min(98, int(p * 100) - 1))
        return pontos[idx]

    return ResultadoMonteCarlo(
        fracao_kelly=fracao_kelly,
        fracao_aposta_usada=fracao_aposta,
        capital_inicial=capital_inicial,
        n_teses=n_teses,
        n_trajetorias=n_trajetorias,
        mediana_final=statistics.median(finais),
        p5_final=_percentil(0.05),
        p10_final=_percentil(0.10),
        p90_final=_percentil(0.90),
        p95_final=_percentil(0.95),
        media_final=statistics.mean(finais),
        prob_ruina=prob_ruina,
        limiar_ruina_pct=limiar_ruina_pct,
    )
