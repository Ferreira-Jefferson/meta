"""A PREMISSA de cada especie tem de ser estrutural, nao sugerida.

Este arquivo existe por causa de uma medicao, nao de uma suspeita. Na rodada
longa de 2026-09-18 (10 especies x 60 individuos x 65 geracoes) a premissa de
7 das 10 ilhas entrava somente como um individuo SEMEADO. Ao fim, das 28
features semeadas nessas 7 especies, os campeoes ainda usavam **1**. As 2
ilhas cuja premissa era estrutural (`permitidas`) ficaram **100% dentro**
dela.

Duas ilhas foram piores ainda: a semente do `retangulo` e a do `vwap` fizeram
zero operacoes na sonda de triagem e foram DESCARTADAS antes da geracao 1 --
essas especies rodaram 65 geracoes como populacao sorteada com um rotulo.

Dez ilhas sem premissa nao sao dez buscas: sao a MESMA busca dez vezes, com o
custo estatistico de dez tentativas independentes e nada da diversidade que
justificava paga-lo. Os testes abaixo fecham as duas portas.

Dado sintetico, sem parquet e sem caminho compartilhado (`-n auto`).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "daytrade"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from evo import ga                                          # noqa: E402
from evo.especies import ENCAIXES_DE_NUCLEO, ESPECIES       # noqa: E402
from strategy.daytrade.evo import features as F             # noqa: E402
from strategy.daytrade.evo.genoma import (                  # noqa: E402
    N_ENCAIXES, N_GENES, PESO_MINIMO_NUCLEO, Genoma, cruzar,
    genoma_aleatorio, mutar,
)

COM_NUCLEO = [e for e in ESPECIES if e.nucleo]
TODAS = list(ESPECIES)


def _indices(g: Genoma) -> list[int]:
    return [e.idx for e in g.encaixes]


def _no_nucleo(g: Genoma, nucleo) -> int:
    return sum(1 for i in _indices(g) if i in nucleo)


@pytest.mark.parametrize("esp", COM_NUCLEO, ids=lambda e: e.nome)
def test_nucleo_garantido_no_sorteio(esp):
    rng = random.Random(7)
    for _ in range(300):
        g = esp.aleatorio(rng)
        assert _no_nucleo(g, esp.nucleo) >= esp.min_nucleo


@pytest.mark.parametrize("esp", COM_NUCLEO, ids=lambda e: e.nome)
def test_nucleo_sobrevive_a_500_rodadas_de_evolucao(esp):
    """O ponto todo: cruzamento e mutacao nao podem dissolver a premissa.

    Foi exatamente isso que aconteceu na rodada de 65 geracoes -- so' que la'
    nao havia nada para impedir."""
    rng = random.Random(11)
    pop = [esp.aleatorio(rng) for _ in range(12)]
    for _ in range(500):
        a, b = rng.choice(pop), rng.choice(pop)
        filho = esp.projeta(mutar(cruzar(a, b, rng), rng, taxa=0.9, forca=0.9))
        assert _no_nucleo(filho, esp.nucleo) >= esp.min_nucleo
        pop[rng.randrange(len(pop))] = filho


@pytest.mark.parametrize("esp", TODAS, ids=lambda e: e.nome)
def test_nunca_enxerga_fora_das_permitidas(esp):
    rng = random.Random(3)
    permitidas = set(esp.permitidas)
    for _ in range(200):
        g = esp.projeta(mutar(esp.aleatorio(rng), rng, taxa=0.9, forca=0.9))
        assert set(_indices(g)) <= permitidas


@pytest.mark.parametrize("esp", COM_NUCLEO, ids=lambda e: e.nome)
def test_nucleo_deixa_encaixes_livres_para_descobrir(esp):
    """A premissa nao pode virar camisa de forca: com 6 encaixes e 2
    reservados, sobram 4 para a ilha achar o que ninguem pediu. Sem isto o
    conserto do desvio de premissa mataria o objetivo da busca."""
    rng = random.Random(5)
    fora = set()
    for _ in range(400):
        fora |= {i for i in _indices(esp.aleatorio(rng)) if i not in esp.nucleo}
    assert len(fora) > ENCAIXES_DE_NUCLEO
    assert N_ENCAIXES - esp.min_nucleo >= 4


def test_semente_e_imune_a_triagem_de_atividade():
    """A semente MUDA na sonda nao pode ser apagada: foi o que deletou o
    `retangulo` e o `vwap` antes da geracao 1."""
    rng = random.Random(1)
    pop = [genoma_aleatorio(rng) for _ in range(10)]
    atividade = [0, 0] + [5] * 8          # as duas primeiras sao mudas
    sel = ga._triagem_de_atividade(pop, atividade, tamanho=4, imunes=2)
    assert sel[0] is pop[0] and sel[1] is pop[1]
    # e sem imunidade elas somem -- prova que o teste acima nao e' vacuo
    sem = ga._triagem_de_atividade(pop, atividade, tamanho=4)
    assert pop[0] not in sem and pop[1] not in sem


def test_toda_especie_semeada_planta_a_semente_na_populacao():
    rng = random.Random(2)
    for esp in ESPECIES:
        if not esp.sementes:
            continue
        pop = ga._populacao_inicial(esp, 30, rng)
        assert len(pop) == 30
        for s in esp.sementes:
            assert _no_nucleo(esp.projeta(s), esp.nucleo) >= esp.min_nucleo


def test_cada_ilha_tem_premissa_estrutural_ou_e_declarada_sem_premissa():
    """Guarda-corpo contra a proxima especie: ou ela restringe features, ou
    tem nucleo, ou e' explicitamente uma ilha sem vies. O que nao pode
    acontecer de novo e' uma especie ACHAR que tem premissa por causa de uma
    semente."""
    sem_vies = {"cega"}
    for esp in ESPECIES:
        estrutural = len(esp.permitidas) < F.N_FEATURES or bool(esp.nucleo)
        assert estrutural or esp.nome in sem_vies, (
            f"{esp.nome} so' tem semente -- premissa nao se sustenta assim")
        if esp.nome in sem_vies:
            assert not esp.sementes, "ilha sem vies nao pode ter semente"


# --------------------------------------------------------------------------
# O nucleo tem de exigir PARTICIPACAO, nao so' presenca.
#
# MEDIDO em 2026-09-19: a ilha `vwap` satisfez o nucleo com um encaixe em
# `dist_vwap` de peso |a|,|b| < 0,05 -- a feature estava no genoma e nao fazia
# nada. Restringir a FORMA sem restringir o EFEITO nao restringe nada, e uma
# busca acha a saida barata por construcao.
# --------------------------------------------------------------------------

def _nucleo_ativo(g, esp) -> int:
    return sum(1 for e in g.encaixes if e.idx in esp.nucleo
               and (e.porta or max(abs(e.a), abs(e.b)) >= PESO_MINIMO_NUCLEO))


@pytest.mark.parametrize("esp", COM_NUCLEO, ids=lambda e: e.nome)
def test_encaixe_de_nucleo_tem_peso_que_muda_decisao(esp):
    rng = random.Random(21)
    for _ in range(300):
        assert _nucleo_ativo(esp.aleatorio(rng), esp) >= esp.min_nucleo


@pytest.mark.parametrize("esp", COM_NUCLEO, ids=lambda e: e.nome)
def test_peso_do_nucleo_sobrevive_a_evolucao(esp):
    rng = random.Random(22)
    pop = [esp.aleatorio(rng) for _ in range(10)]
    for _ in range(400):
        f = esp.projeta(mutar(cruzar(rng.choice(pop), rng.choice(pop), rng),
                              rng, taxa=0.9, forca=0.9))
        assert _nucleo_ativo(f, esp) >= esp.min_nucleo
        pop[rng.randrange(len(pop))] = f


@pytest.mark.parametrize("esp", COM_NUCLEO, ids=lambda e: e.nome)
def test_zerar_o_peso_do_nucleo_a_mao_e_desfeito(esp):
    """Anti-vacuidade: prova que a garantia AGE, e nao que o sorteio nunca
    produz o caso ruim."""
    rng = random.Random(23)
    g = esp.aleatorio(rng)
    cru = list(g.cru)
    for k in range(N_ENCAIXES):          # zera TODO peso e desliga as portas
        cru[k * 4 + 1] = cru[k * 4 + 2] = 0.5      # a = b = 0
        cru[k * 4 + 3] = 0.0                       # nao e' porta
    morto = Genoma(cru=tuple(cru))
    assert _nucleo_ativo(morto, esp) == 0, "o caso ruim nao foi construido"
    assert _nucleo_ativo(esp.projeta(morto), esp) >= esp.min_nucleo


def test_o_peso_minimo_sobrevive_a_ida_e_volta_pelo_gene():
    """O gene guarda (peso+1)/2 e o decodificador faz cru*2-1. Gravar
    exatamente o limiar devolve 0,14999999999999991 -- abaixo dele. A
    restricao tem de mirar DENTRO da regiao legal, nunca na fronteira."""
    for alvo in (PESO_MINIMO_NUCLEO, -PESO_MINIMO_NUCLEO):
        cru = [0.5] * N_GENES
        cru[0] = 0.5
        cru[1] = ((alvo + 1e-6 if alvo > 0 else alvo - 1e-6) + 1.0) / 2.0
        assert abs(Genoma(cru=tuple(cru)).encaixes[0].a) >= PESO_MINIMO_NUCLEO
