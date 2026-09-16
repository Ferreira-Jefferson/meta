"""Invariantes do robô `win_retangulo`.

Cada teste aqui guarda uma coisa que, se quebrar em silêncio, faz o robô que
opera deixar de ser o robô que foi medido. Não há teste de "o líquido dá
R$2.980" de propósito — isso é `scripts/daytrade/win_retangulo_conferencia_
arranque_2026_09_15.py`, que roda o motor inteiro; aqui ficam só as
propriedades que valem para QUALQUER janela de dado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.daytrade.base import EnterLimit
from strategy.daytrade.lab.win_retangulo import (
    CONTRACAO_MAXIMA, WinRetangulo, detecta_retangulo,
)


def _bar(i: int, o: float, h: float, lo: float, c: float, vol: float = 1_000.0):
    from strategy.daytrade.base import Bar

    return Bar(ts=pd.Timestamp("2026-09-15 13:00", tz="UTC") + pd.Timedelta(minutes=i),
               open=o, high=h, low=lo, close=c, volume=vol)


def _retangulo_sintetico(n: int, centro: float, meia_largura: float):
    """Uma onda que sobe e desce dentro de uma faixa: visita as duas bordas
    várias vezes, espalhada no tempo, cruzando o meio.

    O pavio é PROPOSITALMENTE maior que a oscilação dos fechamentos: num
    retângulo de verdade o preço fura a linha e volta (é o que as imagens do
    dono mostram), então quem toca a borda é a máxima/mínima, e os
    fechamentos ficam DENTRO da banda — que é exatamente o que o critério de
    contenção ≥95% exige."""
    barras = []
    pavio = 0.25 * meia_largura
    for i in range(n):
        fase = np.sin(2 * np.pi * i / (n / 3.0))
        c = centro + 0.85 * meia_largura * fase
        barras.append(_bar(i, c, c + pavio, c - pavio, c))
    return barras


def _tendencia(n: int, inicio: float, passo: float):
    barras = []
    for i in range(n):
        c = inicio + passo * i
        barras.append(_bar(i, c, c + 5.0, c - 5.0, c))
    return barras


def _arrays(barras):
    return (np.array([b.high for b in barras], dtype=float),
            np.array([b.low for b in barras], dtype=float),
            np.array([b.close for b in barras], dtype=float))


# -- o detector --------------------------------------------------------------

def test_detector_recusa_uma_tendencia():
    """Uma perna direcional não é retângulo: ela não cruza o meio nem visita
    as bordas duas vezes. Sem esta recusa, "retângulo" vira qualquer pedaço
    de mercado visto de perto — foi exatamente o que aconteceu com a primeira
    versão do detector, que achava 8.830 achados (15 por pregão)."""
    high, low, close = _arrays(_tendencia(20, 100_000.0, 60.0))
    assert detecta_retangulo(high, low, close, amplitude_anterior=5_000.0) is None


def test_detector_aceita_a_faixa_que_o_dono_desenhou():
    ret = detecta_retangulo(*_arrays(_retangulo_sintetico(20, 100_000.0, 200.0)),
                            amplitude_anterior=5_000.0)
    assert ret is not None
    assert ret["cruzamentos"] >= 3
    assert ret["visitas_topo"] >= 2 and ret["visitas_piso"] >= 2
    assert ret["piso"] < ret["meio"] < ret["topo"]
    assert ret["largura"] == pytest.approx(ret["topo"] - ret["piso"])


def test_contracao_recusa_faixa_larga_perto_do_que_veio_antes():
    """O retângulo é ESTREITO comparado ao movimento anterior. Com a mesma
    janela, só muda a amplitude de referência: o teste tem de virar."""
    barras = _retangulo_sintetico(20, 100_000.0, 200.0)
    largura = detecta_retangulo(*_arrays(barras), amplitude_anterior=None)["largura"]

    # contração = largura / amplitude_anterior, então amplitude MAIOR = mais
    # contraído. Invertê-los aqui faria o teste passar sem testar nada.
    folgado = largura / (CONTRACAO_MAXIMA / 2)      # contração 0,275 — passa
    apertado = largura / (CONTRACAO_MAXIMA * 1.1)   # contração 0,605 — recusa
    assert detecta_retangulo(*_arrays(barras), amplitude_anterior=folgado) is not None
    assert detecta_retangulo(*_arrays(barras), amplitude_anterior=apertado) is None


def test_sem_amplitude_anterior_a_contracao_fica_marcada_e_nao_escondida():
    """Começo de pregão não tem 2W barras anteriores. O teste é PULADO, e isso
    aparece como NaN — nunca atrás de um default que o faria passar calado."""
    ret = detecta_retangulo(*_arrays(_retangulo_sintetico(20, 100_000.0, 200.0)),
                            amplitude_anterior=None)
    assert ret is not None
    assert np.isnan(ret["contracao"])


# -- o robô ------------------------------------------------------------------

def _roda_ate_armar(robo: WinRetangulo, barras):
    acoes = []
    for i, b in enumerate(barras):
        acoes = robo.on_bar(b.ts, b, positions=[], session_pnl_brl=0.0)
        if acoes:
            return i, acoes
    return None, []


def _historico_que_arma(largura_minima: float = 0.0):
    """2W barras de perna larga (para a contração passar) + W de retângulo."""
    antes = _tendencia(40, 100_000.0, 75.0)
    dentro = _retangulo_sintetico(20, antes[-1].close, 200.0)
    for i, b in enumerate(dentro):
        b.ts = antes[-1].ts + pd.Timedelta(minutes=i + 1)
    return antes + dentro


def test_a_entrada_e_sempre_ordem_limite_com_prazo():
    """Desenho de execução FECHADO: entrada só por `EnterLimit` e sempre com
    `ttl_bars`. Ordem a mercado não tem caminho de execução real, e limite sem
    prazo vira ordem esquecida no livro (medido: fill 269,7 min depois)."""
    robo = WinRetangulo()
    _i, acoes = _roda_ate_armar(robo, _historico_que_arma())
    assert acoes, "o robô não armou nada sobre um retângulo sintético"
    assert all(isinstance(a, EnterLimit) for a in acoes)
    assert all(a.ttl_bars is not None and a.ttl_bars > 0 for a in acoes)


def test_a_limite_descansa_do_lado_certo_do_preco():
    """Venda-limite só ACIMA do preço, compra-limite só ABAIXO. Uma limite do
    lado errado é ordem a mercado disfarçada."""
    barras = _historico_que_arma()
    robo = WinRetangulo()
    i, acoes = _roda_ate_armar(robo, barras)
    assert acoes
    ordem = acoes[0]
    fechamento = barras[i].close
    if ordem.side == "short":
        assert ordem.limit_price > fechamento
    else:
        assert ordem.limit_price < fechamento


def test_alvo_fica_alem_da_borda_oposta_e_stop_na_borda_de_tras():
    """A geometria que a matriz de trajetória achou: alvo 0,80×L do meio (ou
    seja, 0,30×L ALÉM da borda) e stop 0,50×L (na borda de trás). O desenho
    original do dono — alvo a 90% do meio até a borda — foi medido e deu 14 de
    15 células negativas."""
    robo = WinRetangulo()
    _i, acoes = _roda_ate_armar(robo, _historico_que_arma())
    assert acoes
    ordem = acoes[0]
    ret = robo._retangulo
    meio, largura = ret["meio"], ret["largura"]
    sentido = 1 if ordem.side == "long" else -1

    assert ordem.initial_target == pytest.approx(
        meio + sentido * robo.alvo_fracao_largura * largura, abs=robo.tick_size)
    assert ordem.initial_stop == pytest.approx(
        meio - sentido * robo.stop_fracao_largura * largura, abs=robo.tick_size)
    # o alvo passa da borda oposta; o stop não passa da borda de trás
    borda_alvo = ret["topo"] if sentido > 0 else ret["piso"]
    assert sentido * (ordem.initial_target - borda_alvo) > 0


def test_o_piso_de_largura_cala_o_robo_em_retangulo_estreito():
    """O filtro de largura foi o único que manteve sinal E magnitude nas duas
    janelas. Um retângulo abaixo do piso não pode virar ordem."""
    barras = _historico_que_arma()
    largo = WinRetangulo(largura_minima_pontos=0.0)
    estreito = WinRetangulo(largura_minima_pontos=100_000.0)
    assert _roda_ate_armar(largo, barras)[1]
    assert not _roda_ate_armar(estreito, barras)[1]


def test_nenhum_nivel_de_preco_atravessa_o_pregao():
    """`WIN@` é série contínua com emenda de rolagem — o salto dela (+742,
    +786, +630, +510 pontos) se esconde dentro do ruído overnight normal e é
    indetectável por outlier. A única defesa é estrutural."""
    robo = WinRetangulo()
    _roda_ate_armar(robo, _historico_que_arma())
    assert robo._retangulo is not None

    robo.on_session_start(pd.Timestamp("2026-09-16").date())
    assert robo._retangulo is None
    assert robo._barras_esperando is None
    assert len(robo._hist) == 0


@pytest.mark.parametrize("hook", ["on_order_rejected", "on_order_expired"])
def test_ordem_morta_libera_o_robo_para_armar_de_novo(hook):
    """Uma limite de entrada morre por cinco caminhos. O robô que só trata um
    deles trava pelo resto da sessão — confirmado 20/20 no `WdoGridReloadMaker`
    antes de `on_order_rejected` existir, e de novo em 2026-09-10 com o prazo
    (item 4.25 de `LICOES_DE_PRODUCAO.md`)."""
    robo = WinRetangulo()
    _i, acoes = _roda_ate_armar(robo, _historico_que_arma())
    assert acoes and robo._barras_esperando is not None

    getattr(robo, hook)(pd.Timestamp("2026-09-15 14:00", tz="UTC"))
    assert robo._barras_esperando is None


def test_limite_de_entrada_sem_prazo_e_recusado_na_construcao():
    with pytest.raises(ValueError, match="prazo"):
        WinRetangulo(ttl_barras=0)


def test_o_piso_de_caixa_declarado_e_o_medido():
    """R$3.400 = pior rebaixamento POR OPERAÇÃO com `escala_por_caixa` ligada
    (R$3.229,00 no IS) + margem crua do WIN@ (R$100), arredondado.

    Com 1 contrato fixo o piso era R$1.100 (R$989,50 + R$100). A escala não
    muda quais operações acontecem — muda o TAMANHO delas —, então o
    rebaixamento sobe junto com o lucro e o piso acompanha. Os números que o
    piso NÃO é, cada um com o motivo:

      R$250   — piso de tabela do instrumento, não diz nada sobre a estratégia
      R$290   — piso exato daquela sequência de operações (a R$275 o robô cala
                para sempre); sorteio sobre quais operações vieram primeiro
      R$650   — derivado do rebaixamento da SÉRIE DIÁRIA (R$525,60), que o
                portão de capital não vê: o caixa anda POR OPERAÇÃO
      R$1.100 — o piso de `escala_por_caixa=False`, que continua correto para
                quem roda assim
    """
    assert WinRetangulo.capital_minimo_recomendado_brl == 3_400.0


def test_a_escala_por_caixa_nasce_ligada():
    """Pedido do dono (2026-09-15): o robô tem de saber aumentar E diminuir
    contrato conforme o capital disponível. Antes disso ele pedia
    `quantidade=1` fixo e o motor só sabia reduzir."""
    assert WinRetangulo().escala_por_caixa is True


def test_contrato_novo_so_entra_em_retangulo_mais_apertado():
    """"Sempre diminuindo o risco a cada novo contrato" vira uma regra exata:
    o contrato `k` recebe orçamento `risco_maximo_brl / k`, então `n`
    contratos custam `risco × H(n)` (harmônico). Como o risco por contrato é
    proporcional à LARGURA, quantidade alta só cabe em retângulo apertado — a
    quantidade tem de ser NÃO-CRESCENTE na largura."""
    robo = WinRetangulo()
    robo.on_capital_update(10_000.0)
    larguras = [328.0, 400.0, 500.0, 600.0, 800.0]
    quantidades = [robo._dimensiona(L) for L in larguras]
    assert quantidades == sorted(quantidades, reverse=True)
    assert quantidades[0] > quantidades[-1], "largura não está mexendo em nada"


def test_o_risco_por_contrato_cai_a_cada_contrato_novo():
    """O invariante que o dono pediu, escrito como desigualdade: o orçamento
    do contrato `k` é estritamente menor que o do contrato `k-1`. Sem isso o
    risco total cresceria LINEAR com a quantidade, que é exatamente o caminho
    do item 3.9 (a conta do CopaWin foi de R$3.000,00 a R$68,50 num trade, com
    margem e reserva funcionando como desenhadas)."""
    robo = WinRetangulo()
    robo.on_capital_update(10_000.0)
    orcamentos = [robo.risco_maximo_brl / k for k in range(1, 6)]
    assert all(b < a for a, b in zip(orcamentos, orcamentos[1:]))
    # E o total cresce MENOS que linear: 5 contratos custam menos que 5x um.
    total_5 = sum(orcamentos)
    assert total_5 < 5 * orcamentos[0]


def test_a_quantidade_encolhe_quando_o_caixa_cai():
    """"Aumentar E diminuir" — a metade de diminuir é a que protege. O caixa
    entra pelo `on_capital_update` que o motor chama a cada barra com
    `capital inicial + P&L realizado`, então a quantidade acompanha a conta de
    verdade em vez de ser uma foto tirada no início."""
    robo = WinRetangulo()
    robo.on_capital_update(10_000.0)
    muitos = robo._dimensiona(400.0)
    robo.on_capital_update(300.0)
    poucos = robo._dimensiona(400.0)
    assert poucos < muitos
    assert poucos >= 1, "nunca pede menos de 1: quem recusa abaixo da margem é o motor"


def test_sem_escala_o_robo_e_exatamente_o_de_antes():
    """`escala_por_caixa=False` tem de reproduzir o desenho congelado (1
    contrato fixo, piso R$1.100), porque é ele que a tabela do topo do módulo
    descreve e é ele que atravessou o OOS."""
    robo = WinRetangulo(escala_por_caixa=False)
    robo.on_capital_update(10_000.0)
    assert all(robo._dimensiona(L) == 1 for L in (328.0, 400.0, 600.0, 800.0))


def test_o_robo_nao_gere_posicao_aberta():
    """24 regras de gestão (trailing, zero-a-zero, corte por tempo) foram
    medidas no `copa_win` e TODAS saíram negativas. Com posição aberta quem
    manda é o stop e o alvo já registrados."""
    from strategy.daytrade.base import IntradayOpenPosition

    robo = WinRetangulo()
    barras = _historico_que_arma()
    _roda_ate_armar(robo, barras)
    aberta = IntradayOpenPosition(
        side="long", entry_ts=barras[-1].ts, entry_price=100_000.0, quantity=1,
        current_stop=99_000.0, current_target=101_000.0, bars_held=1)
    assert robo.on_bar(barras[-1].ts, barras[-1], [aberta], 0.0) == []


def test_a_tolerancia_do_robo_chega_no_detector():
    """`tolerancia_borda` é parâmetro de INSTÂNCIA; a constante do módulo é só
    o fallback da função pura. Se o robô não repassar o valor dele, ele opera
    um detector diferente do que foi medido — e em silêncio, porque o número
    da classe continuaria certo na tela."""
    barras = _historico_que_arma()
    W = 20
    recente = barras[-W:]
    anterior = barras[-3 * W:-W]
    amplitude = max(b.high for b in anterior) - min(b.low for b in anterior)

    apertado = WinRetangulo(tolerancia_borda=0.02)
    _roda_ate_armar(apertado, barras)
    largo = WinRetangulo(tolerancia_borda=0.30)
    _roda_ate_armar(largo, barras)

    # o detector chamado com cada tolerância tem de dar o MESMO veredito que o
    # robô correspondente chegou a guardar
    for robo in (apertado, largo):
        direto = detecta_retangulo(*_arrays(recente), amplitude,
                                   tolerancia=robo.tolerancia_borda)
        assert (direto is None) == (robo._retangulo is None), (
            f"tolerancia {robo.tolerancia_borda} não chegou ao detector"
        )


def test_o_teto_de_risco_nasce_ligado_em_80():
    """Decisão do dono (2026-09-15): LIGADO, e explicitamente por controle de
    CAUDA, não por resultado. A pior operação cai de −R$110,50 para −R$80,50
    (IS), −R$85,50 para −R$74,30 (OOS) e −R$85,50 para −R$72,50 (2 semanas) —
    o único efeito que replica nas três janelas.

    O preço está documentado e não pode se perder: no IS o teto CUSTA
    R$792,00 movendo 32 das 615 operações, e o retorno por real arriscado
    CRESCE com a largura nas duas janelas (ρ +0,338 e +0,306), ou seja, ele
    corta parte do que melhor paga. Quem mexer neste número por líquido está
    garimpando."""
    assert WinRetangulo().risco_maximo_brl == 80.0


def test_o_teto_de_risco_recusa_retangulo_largo_demais():
    """Desligado por padrão, mas funcionando quando ligado — quem quiser
    cortar a cauda (pior operação vai de −R$110,50 para −R$80,50) tem o
    parâmetro. O que ele NÃO faz é melhorar resultado: no IS R$80 é o pior
    valor da vizinhança R$70-120 e no OOS é um pico de uma célula, decidido
    por 2 operações em 133."""
    barras = _historico_que_arma()
    sem_teto = WinRetangulo(risco_maximo_brl=float("inf"))
    _i, acoes = _roda_ate_armar(sem_teto, barras)
    assert acoes

    ret = sem_teto._retangulo
    risco = (sem_teto.stop_fracao_largura * ret["largura"]
             * sem_teto.valor_do_ponto_brl * sem_teto.quantidade)
    justo_abaixo = WinRetangulo(risco_maximo_brl=risco * 0.9)
    justo_acima = WinRetangulo(risco_maximo_brl=risco * 1.1)
    assert not _roda_ate_armar(justo_abaixo, barras)[1]
    assert _roda_ate_armar(justo_acima, barras)[1]


def test_tolerancia_absurda_e_recusada_na_construcao():
    """Acima de 0,5 as duas zonas de borda se encontram no meio e todo preço
    'toca' as duas ao mesmo tempo — o detector deixaria de testar forma."""
    with pytest.raises(ValueError, match="tolerancia_borda"):
        WinRetangulo(tolerancia_borda=0.6)
    with pytest.raises(ValueError, match="tolerancia_borda"):
        WinRetangulo(tolerancia_borda=0.0)


def test_teto_de_risco_nao_positivo_e_recusado():
    with pytest.raises(ValueError, match="risco_maximo_brl"):
        WinRetangulo(risco_maximo_brl=0.0)
