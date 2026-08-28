"""Teste de permutacao para dependencia de ORDEM (autocorrelacao/Markov) em
serie de retorno ou de sinal -- serve as tres sub-hipoteses de continuidade
(diaria, intradiaria, perna/swing) da rodada `continuidade_*` igualmente:
todas reduzem a "existe uma serie de valores em ORDEM temporal; o valor em
`t` prediz o valor em `t+lag` acima do que a ORDEM embaralhada produziria?".

Por que permutacao e nao so' um coeficiente com p-valor parametrico: retorno
diario/intradiario de futuro nao segue as premissas de um teste parametrico
classico (caudas gordas, heterocedasticidade, autocorrelacao de
volatilidade) -- embaralhar a ORDEM da propria serie MUITAS vezes e comparar
o valor real contra essa distribuicao empirica e' robusto a essas violacoes
por construcao (o nulo usa os MESMOS valores medidos, so' destroi a ordem
entre eles).

Funcao PURA (sem I/O, sem conhecimento de simbolo/instrumento) -- mora em
`backtest/intraday/` e nao em `scripts/` porque nao precisa importar
`strategy` nem tocar disco; quem chama (`scripts/daytrade/continuidade_*.py`)
e' responsavel por carregar os dados e montar `groups`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

StatFn = Callable[[np.ndarray, np.ndarray], float]


def pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    """Correlacao de Pearson entre dois vetores pareados. `0.0` (nunca
    `nan`) quando um dos dois lados tem desvio padrao zero (acontece em
    permutacoes degeneradas com poucos pontos, ou quando `x`/`y` vem
    vazio) -- `nan` quebraria qualquer comparacao de percentil depois."""
    if len(x) < 2 or len(y) < 2:
        return 0.0
    sx, sy = np.std(x), np.std(y)
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def sign_match_rate(x: np.ndarray, y: np.ndarray) -> float:
    """Fracao de pares com o MESMO sinal, MENOS 0,5 -- `0.0` = acaso puro
    (50/50 de continuar o lado), positivo = tende a REPETIR o lado
    (continuidade), negativo = tende a INVERTER (reversao). Pares em que um
    dos dois lados e' exatamente zero sao excluidos (sinal indefinido) --
    nao contam nem como concordancia nem como discordancia."""
    if len(x) == 0:
        return 0.0
    sx, sy = np.sign(x), np.sign(y)
    mask = (sx != 0) & (sy != 0)
    if mask.sum() == 0:
        return 0.0
    return float(np.mean(sx[mask] == sy[mask])) - 0.5


def lag_pairs(groups: Sequence[np.ndarray], lag: int) -> tuple[np.ndarray, np.ndarray]:
    """Pares `(valor_t, valor_{t+lag})` formados DENTRO de cada grupo (nunca
    atravessando a fronteira entre dois grupos -- ex.: nao pareia o ultimo
    retorno de uma sessao com o primeiro da sessao seguinte), empilhados de
    todos os grupos. `lag` tem que ser >= 1."""
    if lag < 1:
        raise ValueError(f"lag tem que ser >= 1, recebeu {lag!r}")
    xs, ys = [], []
    for g in groups:
        g = np.asarray(g, dtype=float)
        if len(g) > lag:
            xs.append(g[:-lag])
            ys.append(g[lag:])
    if not xs:
        return np.array([]), np.array([])
    return np.concatenate(xs), np.concatenate(ys)


@dataclass(frozen=True)
class StatResult:
    real: float
    null_mean: float
    null_std: float
    percentile: float  # 0..100, posicao do valor REAL na distribuicao nula
    p_two_sided: float  # 0..1


@dataclass(frozen=True)
class PermutationResult:
    lag: int
    n_pairs: int
    n_groups: int
    n_perm: int
    seed: int
    stats: dict[str, StatResult] = field(default_factory=dict)


def _flat_with_group_ids(groups: Sequence[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Concatena `groups` num unico array, junto com o ID do grupo de cada
    posicao -- base para embaralhar TODOS os grupos de uma vez (ver
    `_shuffle_within_groups`) em vez de um `rng.permutation` por grupo por
    iteracao (medido: 125 grupos x 3.000 permutacoes assim levava >190s por
    teste -- inviavel para a dezena de horizontes que esta rodada testa)."""
    if not groups:
        return np.array([]), np.array([], dtype=np.int64)
    flat = np.concatenate([np.asarray(g, dtype=float) for g in groups])
    ids = np.concatenate([np.full(len(g), i, dtype=np.int64) for i, g in enumerate(groups)])
    return flat, ids


def _shuffle_within_groups(flat: np.ndarray, group_ids: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Uma permutacao ALEATORIA INDEPENDENTE do conteudo de cada grupo,
    preservando a ordem/posicao dos GRUPOS -- vetorizado via o truque
    "ordenar por (id_do_grupo + chave aleatoria em [0,1))": como os ids sao
    inteiros e a chave e' sempre < 1, a ordenacao NUNCA mistura elementos de
    grupos diferentes (cada grupo ocupa um intervalo `[id, id+1)` disjunto
    dos vizinhos), e DENTRO do intervalo a ordem sai uniformemente aleatoria
    (chaves iid). Um unico `argsort` faz o trabalho de N `rng.permutation`
    independentes."""
    keys = group_ids.astype(np.float64) + rng.random(len(flat))
    return flat[np.argsort(keys, kind="quicksort")]


def permutation_test(
    groups: Sequence[np.ndarray],
    lag: int,
    stat_fns: dict[str, StatFn],
    n_perm: int = 5000,
    seed: int = 0,
) -> PermutationResult:
    """Testa CADA estatistica em `stat_fns` contra `n_perm` embaralhamentos
    INDEPENDENTES DENTRO de cada grupo (a ORDEM embaralha; o CONJUNTO de
    valores de cada grupo nao muda -- preserva a distribuicao marginal de
    cada dia/sessao/serie, destroi so' a dependencia temporal).

    `percentile`: posicao do valor real na distribuicao nula, 0..100 (`0` =
    menor que TODOS os embaralhamentos, `100` = maior que todos, `50` =
    exatamente no meio -- e' o "onde o valor real cai na distribuicao"
    pedido pela disciplina de teste do projeto).

    `p_two_sided`: chance de um resultado tao extremo quanto o real, pra
    QUALQUER lado, ter saido do puro acaso -- `(min(#null>=real, #null<=real)
    + 1) / (n_perm + 1)`, multiplicado por 2 e limitado a 1.0. O `+1` no
    numerador e denominador (correcao padrao de teste de permutacao) evita
    reportar p=0,0 exato, que nenhuma quantidade finita de embaralhamentos
    pode provar."""
    groups_arr = [np.asarray(g, dtype=float) for g in groups]
    rng = np.random.default_rng(seed)

    x_real, y_real = lag_pairs(groups_arr, lag)
    real_vals = {name: fn(x_real, y_real) for name, fn in stat_fns.items()}

    flat, group_ids = _flat_with_group_ids(groups_arr)
    # posicoes (x,y) validas sao as MESMAS em toda permutacao (dependem so'
    # do TAMANHO/fronteira de cada grupo, que o embaralhamento preserva) --
    # calculadas UMA vez aqui, reaproveitadas nas `n_perm` iteracoes.
    lengths = np.array([len(g) for g in groups_arr], dtype=np.int64)
    ends = np.cumsum(lengths)
    starts = ends - lengths
    x_idx = np.concatenate([np.arange(s, e - lag) for s, e in zip(starts, ends) if e - s > lag]) \
        if len(lengths) else np.array([], dtype=np.int64)
    y_idx = x_idx + lag

    null_vals: dict[str, np.ndarray] = {name: np.empty(n_perm) for name in stat_fns}
    for p in range(n_perm):
        shuffled = _shuffle_within_groups(flat, group_ids, rng)
        xs, ys = shuffled[x_idx], shuffled[y_idx]
        for name, fn in stat_fns.items():
            null_vals[name][p] = fn(xs, ys)

    stats_out: dict[str, StatResult] = {}
    for name in stat_fns:
        real = real_vals[name]
        null = np.asarray(null_vals[name])
        n_ge = int(np.sum(null >= real))
        n_le = int(np.sum(null <= real))
        p_upper = (n_ge + 1) / (n_perm + 1)
        p_lower = (n_le + 1) / (n_perm + 1)
        p_two = min(2.0 * min(p_upper, p_lower), 1.0)
        percentile = 100.0 * float(np.mean(null <= real))
        stats_out[name] = StatResult(
            real=real,
            null_mean=float(null.mean()) if len(null) else 0.0,
            null_std=float(null.std()) if len(null) else 0.0,
            percentile=percentile,
            p_two_sided=p_two,
        )
    return PermutationResult(
        lag=lag, n_pairs=len(x_real), n_groups=len(groups_arr),
        n_perm=n_perm, seed=seed, stats=stats_out,
    )
