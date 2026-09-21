"""As GARANTIAS ESTRUTURAIS do robo evoluido.

Cada teste aqui existe porque uma busca evolutiva encontraria a falha
correspondente e passaria a explora-la. A diferenca entre este arquivo e um
conjunto de testes normal e' essa: nao se trata de proteger contra o erro
distraido de quem edita o codigo depois, e sim contra um otimizador que vai
procurar ativamente qualquer folga que sobre. Um comentario dizendo "nao faca
X" nao protege de nada quando quem busca nao le comentario.

Todos usam dado SINTETICO gerado no proprio teste -- nada de parquet, nada de
caminho compartilhado, nenhuma dependencia de ordem (`pyproject.toml` fixa
`-n auto --dist load`).
"""
from __future__ import annotations

import random

import pandas as pd
import pytest

from strategy.daytrade.base import AdjustTarget, Enter, EnterLimit, Bar
from strategy.daytrade.evo import features as F
from strategy.daytrade.evo.genoma import (
    ALVO_MINIMO_PONTOS, ALVO_MINIMO_TICKS, GEOMETRIA, N_GENES, TICK_EM_PONTOS,
    Genoma, cruzar, genoma_aleatorio, mutar, projeta_em,
)
from strategy.daytrade.lab.wdo_evo import WdoEvo

TICK = 0.5
ABERTURA = pd.Timestamp("2026-03-02 12:00:00", tz="UTC")


def _bars(n: int = 240, semente: int = 1, base: float = 5180.0
          ) -> list[tuple[pd.Timestamp, Bar]]:
    """Uma sessao sintetica na grade de 0,5, com movimento suficiente para o
    robo ter o que decidir."""
    rng = random.Random(semente)
    preco = base
    saida = []
    for i in range(n):
        ts = ABERTURA + pd.Timedelta(minutes=i)
        passo = rng.choice([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0])
        abertura = preco
        preco = round((preco + passo) / TICK) * TICK
        alto = max(abertura, preco) + TICK * rng.randint(0, 4)
        baixo = min(abertura, preco) - TICK * rng.randint(0, 4)
        saida.append((ts, Bar(ts=ts, open=abertura, high=alto, low=baixo,
                              close=preco, volume=1000 + rng.randint(0, 9000))))
    return saida


def _robo(g: Genoma) -> WdoEvo:
    r = WdoEvo(genoma=g, tick_size=TICK)
    r.on_session_start(ABERTURA.date())
    return r


# ---------------------------------------------------------------------------
# 1. O ESPACO E' FECHADO -- genoma ilegal e' irrepresentavel
# ---------------------------------------------------------------------------

def test_todo_genoma_sorteado_decodifica_para_geometria_legal():
    """A defesa principal contra a busca. Validar DEPOIS ("se o alvo for 1
    tick, descarte") seria porta que a evolucao arromba por acidente -- basta
    um individuo cujo alvo so' fica ilegal em alguns dias. Aqui o conjunto
    ilegal simplesmente nao tem imagem no decodificador."""
    rng = random.Random(4242)
    for _ in range(5_000):
        g = genoma_aleatorio(rng)
        geo = g.geometria
        assert geo["alvo_ticks"] >= ALVO_MINIMO_TICKS
        # A ordem do dono (2026-09-18) e' em PONTOS, nao em ticks.
        assert geo["alvo_ticks"] * TICK_EM_PONTOS >= ALVO_MINIMO_PONTOS
        assert geo["stop_ticks"] >= 8
        # offset >= 1 e' o que impede a limite de nascer atravessando o livro,
        # isto e', de ser ordem a mercado disfarcada.
        assert geo["offset_ticks"] >= 1
        assert 1 <= geo["ttl_min"] <= 30
        assert geo["hora_fim"] > geo["hora_ini"]
        assert 1 <= geo["max_ops_dia"] <= 4


def test_extremos_do_cubo_tambem_sao_legais():
    """Os cantos do espaco sao onde a mutacao refletida deposita individuos
    com mais frequencia -- se algum canto decodificasse ilegal, a busca
    encontraria."""
    for valor in (0.0, 1.0):
        geo = Genoma(cru=tuple([valor] * N_GENES)).geometria
        assert geo["alvo_ticks"] >= ALVO_MINIMO_TICKS
        assert geo["offset_ticks"] >= 1
        assert geo["hora_fim"] > geo["hora_ini"]


def test_mutacao_e_cruzamento_nunca_saem_do_cubo():
    rng = random.Random(7)
    a, b = genoma_aleatorio(rng), genoma_aleatorio(rng)
    for _ in range(2_000):
        filho = mutar(cruzar(a, b, rng), rng, taxa=1.0, forca=2.0)
        assert all(0.0 <= v <= 1.0 for v in filho.cru)
        a, b = b, filho


# ---------------------------------------------------------------------------
# 2. O DESENHO DE EXECUCAO E' FECHADO -- nunca a mercado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("semente", [1, 2, 3, 4, 5])
def test_robo_nunca_emite_ordem_a_mercado(semente):
    """`Enter` (a mercado) nao tem caminho de execucao real -- o motor levanta
    `EntradaAMercadoNaoSuportada` de proposito. Depender desse `raise` seria
    deixar a regra num canto do motor; o robo nao pode nem formular a acao."""
    rng = random.Random(semente)
    for _ in range(40):
        robo = _robo(genoma_aleatorio(rng))
        for ts, bar in _bars(semente=semente):
            for acao in robo.on_bar(ts, bar, [], 0.0):
                assert not isinstance(acao, Enter)
                assert isinstance(acao, (EnterLimit, AdjustTarget))


@pytest.mark.parametrize("semente", [11, 12, 13])
def test_limite_de_entrada_nasce_do_lado_favoravel(semente):
    """Compra ABAIXO do preco corrente, venda ACIMA. Uma limite do lado
    errado preencheria na hora e seria uma ordem a mercado com outro nome --
    e o backtest a precificaria como maker, de graca."""
    rng = random.Random(semente)
    vistas = 0
    for _ in range(60):
        robo = _robo(genoma_aleatorio(rng))
        for ts, bar in _bars(semente=semente):
            for acao in robo.on_bar(ts, bar, [], 0.0):
                if isinstance(acao, EnterLimit):
                    vistas += 1
                    if acao.side == "long":
                        assert acao.limit_price < bar.close
                        assert acao.initial_stop < acao.limit_price
                        assert acao.initial_target > acao.limit_price
                    else:
                        assert acao.limit_price > bar.close
                        assert acao.initial_stop > acao.limit_price
                        assert acao.initial_target < acao.limit_price
    assert vistas > 0, "nenhuma ordem gerada -- o teste nao testou nada"


@pytest.mark.parametrize("semente", [21, 22])
def test_ordem_de_entrada_sempre_tem_prazo(semente):
    """Sem prazo a limite espera ate' o fim do pregao: ja' foi medido um
    preenchimento 269,7 minutos depois do sinal, que nao e' a operacao que a
    estrategia pediu."""
    rng = random.Random(semente)
    for _ in range(40):
        robo = _robo(genoma_aleatorio(rng))
        for ts, bar in _bars(semente=semente):
            for acao in robo.on_bar(ts, bar, [], 0.0):
                if isinstance(acao, EnterLimit):
                    assert acao.ttl_bars is not None and acao.ttl_bars >= 1


def test_niveis_caem_na_grade_do_instrumento():
    """Nivel fora da grade de 0,5 nao existe no book: a corretora recusa, e um
    backtest que o preenche esta' medindo um trade impossivel."""
    rng = random.Random(99)
    conferidas = 0
    for _ in range(40):
        robo = _robo(genoma_aleatorio(rng))
        for ts, bar in _bars(semente=5):
            for acao in robo.on_bar(ts, bar, [], 0.0):
                if isinstance(acao, EnterLimit):
                    conferidas += 1
                    for nivel in (acao.limit_price, acao.initial_stop,
                                  acao.initial_target):
                        assert abs(nivel / TICK - round(nivel / TICK)) < 1e-9
    assert conferidas > 0


# ---------------------------------------------------------------------------
# 3. A ORDEM DOS 3 PONTOS -- inclusive pela porta dos fundos
# ---------------------------------------------------------------------------

def test_corte_do_relogio_nunca_pousa_dentro_dos_3_pontos():
    """O corte do relogio move o alvo para o preco corrente. Sem piso, um
    genoma com `corte_min` curto faturaria 1 ponto por operacao e a tabela
    mostraria win% alto -- mas aquele ganho e' do tamanho do escorregao que o
    produziu, que e' exatamente o que a ordem do dono proibe."""
    from strategy.daytrade.base import IntradayOpenPosition

    robo = _robo(Genoma(cru=tuple([0.5] * N_GENES)))
    entrada = 5180.0
    for lado, sinal in (("long", 1.0), ("short", -1.0)):
        for desvio in (-5.0, -1.0, 0.0, 1.0, 2.0, 5.0, 40.0):
            pos = IntradayOpenPosition(
                side=lado, entry_ts=ABERTURA, entry_price=entrada,
                quantity=1, current_stop=None, current_target=None,
                bars_held=1)
            bar = Bar(ts=ABERTURA, open=entrada, high=entrada + abs(desvio),
                      low=entrada - abs(desvio), close=entrada + desvio,
                      volume=1000)
            alvo = robo._alvo_do_corte(pos, bar)
            lucro = (alvo - entrada) * sinal
            assert lucro >= ALVO_MINIMO_PONTOS - 1e-9, (
                f"{lado} com desvio {desvio}: alvo do corte a {lucro} pontos")


# ---------------------------------------------------------------------------
# 4. CAUSALIDADE -- a feature nao pode depender do futuro
# ---------------------------------------------------------------------------

def test_wdo_evo_nao_sobrescreve_initialize():
    """`initialize` recebe o historico INTEIRO do backtest. Qualquer robo pode
    usa-lo; este nao pode, e a ausencia do metodo e' a garantia. Uma busca
    evolutiva nao COMETE o erro de olhar o futuro -- ela converge para ele,
    porque olhar o futuro e' a melhor estrategia que existe."""
    from strategy.daytrade.base import IntradayStrategy

    assert "initialize" not in vars(WdoEvo), (
        "WdoEvo passou a implementar `initialize` -- ela ve o DataFrame "
        "completo, incluindo barras futuras. Ver a docstring do modulo.")
    assert WdoEvo.initialize is IntradayStrategy.initialize


def test_feature_do_instante_k_nao_muda_com_o_que_vem_depois():
    """O teste direto da anti-look-ahead: duas sessoes IDENTICAS ate' a barra
    k e divergentes depois tem de produzir o MESMO vetor em k.

    Se alguma feature passasse a ser calculada com `df.rolling(...)` sobre a
    sessao inteira -- que e' a forma natural de escrever e a forma errada --
    este teste quebra."""
    a = _bars(120, semente=1)
    b = list(a[:60]) + _bars(120, semente=999)[60:]

    def vetor_em(barras, k):
        banco = F.BancoDeFeatures(range_minutos=15.0)
        banco.iniciar_sessao(fim_ts=ABERTURA + pd.Timedelta(minutes=570))
        banco.range_diario_mediano = 40.0
        banco.fechamento_vespera = 5175.0
        for i, (ts, bar) in enumerate(barras):
            banco.registrar(ts, bar)
            if i == k:
                return banco.vetor(ts, bar, 0, 2, 0.0, 150.0)
        raise AssertionError("k fora da sessao")

    for k in (30, 45, 59):
        assert vetor_em(a, k) == vetor_em(b, k), f"vazamento de futuro em k={k}"


def test_todas_as_features_ficam_normalizadas():
    """Feature de escala livre faz o peso do genoma significar coisas
    diferentes em dias diferentes, e a busca 'corrige' isso decorando a escala
    tipica da janela de treino."""
    banco = F.BancoDeFeatures(range_minutos=15.0)
    banco.iniciar_sessao(fim_ts=ABERTURA + pd.Timedelta(minutes=570))
    banco.range_diario_mediano = 40.0
    banco.fechamento_vespera = 5175.0
    for ts, bar in _bars(200, semente=3):
        banco.registrar(ts, bar)
        v = banco.vetor(ts, bar, 1, 2, -80.0, 150.0)
        assert len(v) == F.N_FEATURES
        for nome, valor in zip(F.NOMES, v):
            assert valor == valor, f"{nome} devolveu NaN"
            assert -1.0 <= valor <= 1.0, f"{nome} fora de [-1,1]: {valor}"


def test_banco_sobrevive_a_ausencia_de_escala():
    """No PRIMEIRO pregao do historico nao ha' range diario mediano (nenhum
    dia anterior foi registrado). O banco tem de devolver um vetor valido em
    vez de explodir -- e' o mesmo caso de `JanelaVolatilidadeDiaria` vazia."""
    banco = F.BancoDeFeatures(range_minutos=15.0)
    banco.iniciar_sessao(fim_ts=ABERTURA + pd.Timedelta(minutes=570))
    for ts, bar in _bars(40, semente=8):
        banco.registrar(ts, bar)
        v = banco.vetor(ts, bar, 0, 1, 0.0, 0.0)
        assert all(-1.0 <= x <= 1.0 and x == x for x in v)


# ---------------------------------------------------------------------------
# 5. AS ESPECIES -- a restricao nao pode vazar na reproducao
# ---------------------------------------------------------------------------

def test_especie_restrita_nao_enxerga_fora_do_conjunto_permitido():
    """A especie `crua` e' PROIBIDA de olhar o bloco destilado -- e' o que
    torna qualquer achado dela necessariamente coisa nova. Sem a projecao
    depois da mutacao, a restricao vazaria na primeira geracao: um gene de
    indice mutado sairia do conjunto e a especie passaria a enxergar."""
    permitidas = tuple(range(17, F.N_FEATURES))
    rng = random.Random(5)
    a = genoma_aleatorio(rng, permitidas)
    b = genoma_aleatorio(rng, permitidas)
    assert all(e.idx in permitidas for e in a.encaixes)

    for _ in range(500):
        filho = projeta_em(mutar(cruzar(a, b, rng), rng, taxa=1.0, forca=1.0),
                           permitidas)
        assert all(e.idx in permitidas for e in filho.encaixes)
        a, b = b, filho


# ---------------------------------------------------------------------------
# 6. A POLITICA -- as portas de fato vetam
# ---------------------------------------------------------------------------

def test_porta_fechada_impede_qualquer_ordem():
    """Uma porta impossivel (exige `hora >= 1,0` estritamente maior que o
    maximo alcancavel) tem de calar o robo o pregao inteiro. Se ela nao
    calasse, o modo porta seria decorativo e a busca estaria escolhendo entre
    dois modos que fazem a mesma coisa."""
    cru = [0.5] * N_GENES
    # encaixe 0 vira porta: feature `hora` (indice 5), limiar no teto, lado
    # ">=" -- `hora` nunca chega la' porque a sessao sintetica e' curta.
    cru[0] = (5 + 0.5) / F.N_FEATURES
    cru[1] = 1.0     # a = +1,0 depois de escalar
    cru[2] = 1.0     # b >= 0 -> compara com ">="
    cru[3] = 0.9     # modo porta
    # encaixe 1 e' um somador forte, para garantir que SEM a porta haveria
    # ordem -- senao o teste passaria por falta de sinal, nao por causa dela.
    cru[4] = (0 + 0.5) / F.N_FEATURES
    cru[5], cru[6], cru[7] = 1.0, 0.0, 0.1
    cru[N_GENES - len(GEOMETRIA) - 1] = 0.0   # theta no minimo

    com_porta = _robo(Genoma(cru=tuple(cru)))
    ordens = [a for ts, bar in _bars(200, semente=2)
              for a in com_porta.on_bar(ts, bar, [], 0.0)
              if isinstance(a, EnterLimit)]
    assert ordens == []

    sem_porta = list(cru)
    sem_porta[3] = 0.1   # o MESMO individuo, so' que somador
    robo2 = _robo(Genoma(cru=tuple(sem_porta)))
    ordens2 = [a for ts, bar in _bars(200, semente=2)
               for a in robo2.on_bar(ts, bar, [], 0.0)
               if isinstance(a, EnterLimit)]
    assert ordens2, ("sem a porta tambem nao houve ordem -- o teste acima "
                     "nao provou nada sobre a porta")


def test_teto_de_operacoes_do_dia_e_respeitado():
    """`max_ops_dia` e' do genoma, e o robo conta os fills sozinho. Sem isto a
    busca poderia pedir uma operacao por barra e o teto seria decorativo."""
    from strategy.daytrade.base import IntradayOpenPosition

    cru = [0.5] * N_GENES
    cru[0] = (0 + 0.5) / F.N_FEATURES
    cru[1], cru[2], cru[3] = 1.0, 0.0, 0.1
    base = N_GENES - len(GEOMETRIA)
    cru[base - 1] = 0.0                       # theta minimo: age sempre
    cru[base + 4] = 0.0                       # max_ops_dia = 1
    robo = _robo(Genoma(cru=tuple(cru)))
    assert robo.genoma.geometria["max_ops_dia"] == 1

    barras = _bars(200, semente=6)
    aberta = None
    ordens = 0
    for i, (ts, bar) in enumerate(barras):
        posicoes = [aberta] if aberta else []
        for acao in robo.on_bar(ts, bar, posicoes, 0.0):
            if isinstance(acao, EnterLimit):
                ordens += 1
                # simula o preenchimento na barra seguinte e o fechamento
                # duas barras depois
                aberta = IntradayOpenPosition(
                    side=acao.side, entry_ts=ts, entry_price=acao.limit_price,
                    quantity=1, current_stop=acao.initial_stop,
                    current_target=acao.initial_target, bars_held=0)
        if aberta and i % 7 == 0:
            aberta = None
    # EXATAMENTE 1, nao "<= 1": com `<=` o teste passaria a vazio no dia em
    # que uma mudanca calasse o robo por outro motivo, e estaria verde sem
    # provar nada sobre o teto.
    assert ordens == 1, (
        f"{ordens} ordens com `max_ops_dia=1` -- se for 0, o robo ficou mudo "
        f"e o teste nao provou nada sobre o teto; se for >1, o teto nao vale")
