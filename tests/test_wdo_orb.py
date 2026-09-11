"""`strategy.daytrade.lab.wdo_orb.WdoOrb` -- o ORB do mini-dolar.

A estrategia e' pura (OHLCV entra, decisao sai), entao estes testes chamam
`on_bar` direto, sem motor. O que eles protegem, em ordem de quanto ja'
custou:

 1. o DESENHO DE EXECUCAO (ordem do dono, 2026-09-10): nunca `Enter` a
    mercado, alvo fatiado sem prazo, entrada com prazo. Uma rodada inteira de
    ~50 celulas foi jogada fora por medir um robo que a corretora recusa;
 2. o AVISO DE ORDEM MORTA (`on_order_expired`): sem ele o robo fica cego
    pelo resto do pregao -- 14 dos 72 pregoes do IS, +R$1.236,00 contra
    +R$1.649,00;
 3. a GEOMETRIA sair da faixa de abertura, com o clamp mordendo nas duas
    pontas (13,9% dos pregoes no piso, 31,9% no teto);
 4. o FADE DO ROMPIMENTO OPOSTO (2026-09-11): a 2a operacao do dia que levou
    o veredito do IS de INDEFINIDO a POSITIVO, e que so' pode acontecer UMA
    vez, depois que a 1a ja' fechou.
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.base import (
    AdjustTarget, Bar, Enter, EnterLimit, IntradayOpenPosition,
)
from strategy.daytrade.lab.wdo_orb import EXIT_TTL_BARS_SEM_PRAZO, WdoOrb

ABERTURA = pd.Timestamp("2026-03-02 12:00", tz="UTC")  # 09:00 BRT


def _bar(minuto: float, o, h, low, c, volume: float = 100.0) -> Bar:
    ts = ABERTURA + pd.Timedelta(minutes=minuto)
    return Bar(ts=ts, open=float(o), high=float(h), low=float(low),
               close=float(c), volume=float(volume))


def _posicao(side="long", entry_min=16.0, entry=5_100.0) -> IntradayOpenPosition:
    return IntradayOpenPosition(
        side=side, entry_ts=ABERTURA + pd.Timedelta(minutes=entry_min),
        entry_price=entry, quantity=1, current_stop=None,
        current_target=None, bars_held=1,
    )


def _faixa(robo: WdoOrb, hi: float, lo: float) -> None:
    """Roda a janela de observacao com uma faixa de `lo` a `hi`. Nenhuma
    decisao pode sair daqui: nos primeiros `range_minutos` o robo so' olha."""
    robo.on_session_start(ABERTURA.date())
    for minuto in range(3):
        bar = Bar(ts=ABERTURA + pd.Timedelta(minutes=minuto), open=lo, high=hi,
                  low=lo, close=(hi + lo) / 2, volume=100.0)
        assert robo.on_bar(bar.ts, bar, [], 0.0) == [], (
            "durante a faixa de abertura o robo so' observa"
        )


def _rompe(robo: WdoOrb, preco: float, minuto: float = 16.0, positions=None):
    bar = Bar(ts=ABERTURA + pd.Timedelta(minutes=minuto), open=preco, high=preco,
              low=preco, close=preco, volume=100.0)
    return robo.on_bar(bar.ts, bar, positions or [], 0.0)


# ---------- o desenho de execucao ------------------------------------------

def test_a_entrada_e_ordem_limite_parada_com_prazo_nunca_a_mercado():
    """Ordem do dono, 2026-09-10. `Enter` a mercado nem tem caminho de
    execucao real (`machine._entrar_a_mercado` levanta de proposito), e uma
    limite SEM prazo espera o pregao inteiro -- medido um fill 269,7 min
    depois do sinal num robo irmao, e os atrasados foram os piores."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)

    (acao,) = _rompe(robo, 5_118.5)

    assert isinstance(acao, EnterLimit)
    assert not isinstance(acao, Enter)
    assert acao.ttl_bars == robo.entrada_ttl_bars is not None


def test_o_alvo_e_ordem_limite_real_fatiada_e_sem_prazo():
    """O `tp` nativo e' gatilho varrido a mercado: R$55,00 de deslize contra
    R$95,00 de bruto teorico (n=11, 10 contra 0 a favor). `exit_split_unit=1`
    troca por ordem-limite REAL no livro; `EXIT_TTL_BARS_SEM_PRAZO` (nunca
    `None`, que no motor significa 'comportamento antigo') faz ela esperar o
    mercado pagar em vez de sair a mercado por impaciencia."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)

    (acao,) = _rompe(robo, 5_118.5)

    assert acao.exit_split_unit == 1
    assert acao.exit_ttl_bars == EXIT_TTL_BARS_SEM_PRAZO
    assert acao.exit_ttl_bars is not None


def test_as_flags_de_custo_do_robo_sao_as_da_producao():
    """`target_fills_as_maker`/`anchor_exits_at_fill` moram na ESTRATEGIA
    justamente para o robo ao vivo e o robo validado nao terem modelo de
    custo diferente (ver `IntradayStrategy`). `feed_kind` idem: foi em TICK
    que este robo foi medido, e todo parametro contado em barras significa
    outra coisa fora dela."""
    robo = WdoOrb()
    assert robo.target_fills_as_maker is True
    assert robo.anchor_exits_at_fill is True
    assert robo.feed_kind == "tick"
    assert robo.is_futuro is True
    assert robo.symbol == "WDO@"


# ---------- a faixa e a geometria ------------------------------------------

def test_a_ordem_fica_offset_ticks_ATRAS_do_rompimento_nos_dois_lados():
    """O offset e' o que faz a ordem esperar um RECUO em vez de perseguir o
    rompimento -- e' por isso que 19,4% dos pregoes passam em branco, e e'
    tambem por isso que o robo nao paga spread. Comprado a limite fica
    ABAIXO; vendido, ACIMA."""
    robo = WdoOrb(offset_ticks=2)
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    (compra,) = _rompe(robo, 5_118.5)
    assert compra.side == "long"
    assert compra.limit_price == pytest.approx(5_118.5 - 2 * 0.5)

    robo = WdoOrb(offset_ticks=2)
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    (venda,) = _rompe(robo, 5_099.0)
    assert venda.side == "short"
    assert venda.limit_price == pytest.approx(5_099.0 + 2 * 0.5)


def test_stop_e_alvo_saem_do_TAMANHO_da_faixa_ancorados_no_limite():
    """Faixa de 17,5 pontos = 35 ticks (a mediana medida do IS) -> stop 35
    ticks, alvo 70. Os niveis contam a partir do LIMITE pedido, nao do preco
    que rompeu: e' esse nivel que a ordem vai ocupar."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)

    (acao,) = _rompe(robo, 5_118.5)

    limite = 5_118.5 - 1.0
    assert acao.initial_stop == pytest.approx(limite - 35 * 0.5)
    assert acao.initial_target == pytest.approx(limite + 70 * 0.5)


@pytest.mark.parametrize("faixa_pontos, stop_esperado", [
    (5.0, 20),    # 10 ticks de faixa: o PISO morde (13,9% dos pregoes do IS)
    (17.5, 35),   # 35 ticks: passa livre (54,2%)
    (46.5, 40),   # 93 ticks, o maximo medido: o TETO morde (31,9%)
])
def test_o_clamp_do_stop_morde_nas_duas_pontas(faixa_pontos, stop_esperado):
    robo = WdoOrb()
    _faixa(robo, hi=5_100.0 + faixa_pontos, lo=5_100.0)

    (acao,) = _rompe(robo, 5_100.0 + faixa_pontos + 1.0)

    distancia_ticks = round((acao.limit_price - acao.initial_stop) / 0.5)
    assert distancia_ticks == stop_esperado


def test_short_espelha_a_geometria_do_long():
    """Sinal trocado nos dois niveis -- um erro de sinal aqui vira um alvo que
    e' stop e um stop que e' alvo, e o motor aceita os dois sem reclamar."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)

    (acao,) = _rompe(robo, 5_099.0)

    limite = 5_099.0 + 1.0
    assert acao.initial_stop == pytest.approx(limite + 35 * 0.5)
    assert acao.initial_target == pytest.approx(limite - 70 * 0.5)


def test_dentro_da_faixa_nao_arma_nada():
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    assert _rompe(robo, 5_110.0) == []


# ---------- uma operacao por pregao NO MESMO LADO (o fade e' a excecao) ----

def test_armou_uma_vez_nao_arma_de_novo_no_mesmo_rompimento():
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    assert len(_rompe(robo, 5_118.5)) == 1
    assert _rompe(robo, 5_119.0, minuto=17.0) == [], "ja' tem ordem no livro"


def test_depois_de_uma_OPERACAO_o_MESMO_LADO_nao_reentra_com_a_ordem_morta():
    """`_preencheu_hoje` e' o que separa "devolver a visao" de "operar de
    novo NO MESMO LADO". O aviso de ordem morta nao pode virar um segundo
    trade igual ao primeiro -- so' o fade (rompimento CONTRARIO, testado
    abaixo) tem licenca para operar duas vezes no dia."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)
    _rompe(robo, 5_118.0, minuto=17.0, positions=[_posicao()])   # preencheu
    # 5_119.0/5_119.5 continuam do lado da COMPRA -- nao e' o rompimento
    # contrario que o fade escuta (esse so' dispara abaixo de range_lo).
    assert _rompe(robo, 5_119.0, minuto=30.0) == [], "posicao fechou, mesmo lado nao reentra"

    robo.on_order_expired(ABERTURA + pd.Timedelta(minutes=31))
    assert _rompe(robo, 5_119.5, minuto=32.0) == [], (
        "o aviso de ordem morta devolve a visao, nao uma segunda operacao IGUAL"
    )


# ---------- o robo cego -----------------------------------------------------

def test_sem_aviso_de_ordem_morta_o_robo_fica_MUDO_pelo_resto_do_pregao():
    """Este teste descreve o BUG, para deixar registrado o que se perdia: o
    motor cancelava a ordem por prazo e o robo nunca ficava sabendo, entao
    `_armou_hoje` seguia ligado achando que havia ordem no livro. 14 dos 72
    pregoes do IS terminaram assim."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)
    # a ordem morreu por prazo na corretora, mas ninguem avisou o robo:
    assert _rompe(robo, 5_119.0, minuto=40.0) == []


def test_com_o_aviso_o_robo_rearma_no_rompimento_seguinte():
    """Os 14 pregoes recuperados nao eram lixo: win 57,1% e +R$29,50/op,
    acima da media do proprio robo. Nao havia selecao adversa escondida no
    silencio -- havia so' silencio."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)

    robo.on_order_expired(ABERTURA + pd.Timedelta(minutes=39))
    (acao,) = _rompe(robo, 5_119.0, minuto=40.0)

    assert isinstance(acao, EnterLimit)
    assert acao.limit_price == pytest.approx(5_119.0 - 1.0)


def test_recusa_por_teto_tambem_devolve_a_visao():
    """O irmao mais velho do hook acima -- recusa por capital/teto ja' era
    avisada desde 2026-08-29 (incidente WDO F1). Os dois caminhos matam a
    ordem, os dois tem de desarmar."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)

    robo.on_order_rejected(ABERTURA + pd.Timedelta(minutes=17))
    assert len(_rompe(robo, 5_119.0, minuto=18.0)) == 1


# ---------- o fade do rompimento oposto (2026-09-11) -----------------------
#
# Medido no IS: sozinho adiciona 31 operacoes (win 67,74%, R$/op +38,53) e
# leva o robo inteiro de INDEFINIDO a POSITIVO (IC95% [50,5;69,1] contra
# breakeven 48,58%). Confirmado no OOS (28 operacoes novas, win 67,86%,
# R$/op +34,50) -- por isso entrou como DEFAULT da classe, nao como opt-in.

def test_fade_dispara_no_rompimento_CONTRARIO_apos_a_operacao_fechar():
    """A operacao original (compra, rompeu pra cima) fecha; o preco depois
    rompe a MESMA faixa para baixo -- o fade entra comprado de novo,
    apostando que esse segundo rompimento (o contrario) tambem falha e o
    preco volta pra dentro/alem da faixa."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)                                          # 1a entrada, lado long
    _rompe(robo, 5_118.0, minuto=17.0, positions=[_posicao()])     # preencheu
    _rompe(robo, 5_110.0, minuto=30.0)                             # fechou (positions=[])

    (acao,) = _rompe(robo, 5_099.0, minuto=45.0)                   # rompe a faixa pra baixo

    assert acao.side == "long"
    # mesma convencao da entrada normal: comprado, a limite fica ABAIXO do
    # preco corrente (espera o recuo), so' que agora do lado de baixo da faixa.
    assert acao.limit_price == pytest.approx(5_099.0 - 2 * 0.5)
    assert acao.reason == "orb_fade_volta_a_faixa"


def test_fade_espelha_quando_o_primeiro_rompimento_foi_vendido():
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_099.0)                                           # 1a entrada, lado short
    _rompe(robo, 5_099.5, minuto=17.0,
           positions=[_posicao(side="short", entry=5_099.0)])       # preencheu
    _rompe(robo, 5_105.0, minuto=30.0)                               # fechou

    (acao,) = _rompe(robo, 5_118.5, minuto=45.0)                    # rompe a faixa pra cima

    assert acao.side == "short"
    # vendido, a limite fica ACIMA do preco corrente.
    assert acao.limit_price == pytest.approx(5_118.5 + 2 * 0.5)


def test_fade_dispara_ate_3_vezes_por_pregao_e_para_na_4a():
    """O teto subiu de 1 para 3 em 2026-09-11 (ver `max_fades_por_dia`): teto
    3 ficou em 1o lugar nas DUAS janelas (IS +3.055,50 / OOS +839,00, contra
    +2.843,50 / +385,50 do teto 1). A 4a chamada e' o que o teto existe para
    cortar -- ela deu -496,00 no IS."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)
    _rompe(robo, 5_118.0, minuto=17.0, positions=[_posicao()])
    _rompe(robo, 5_110.0, minuto=30.0)

    minuto = 45.0
    for n in (1, 2, 3):
        assert len(_rompe(robo, 5_099.0, minuto=minuto)) == 1, f"fade #{n}"
        robo.on_order_expired(ABERTURA + pd.Timedelta(minutes=minuto + 1))
        minuto += 2.0

    assert _rompe(robo, 5_098.0, minuto=minuto) == [], (
        "3 fades ja' dispararam -- a 4a e' exatamente a que o teto corta"
    )


def test_o_teto_do_fade_e_parametro_nao_numero_cravado():
    """`max_fades_por_dia` existe para que mexer no teto seja uma DECISAO
    explicita, com a medicao ao lado (ver a nota do campo), e nao uma edicao
    de logica. Com teto 1 o robo reproduz o comportamento anterior a
    2026-09-11."""
    robo = WdoOrb(max_fades_por_dia=1)
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)
    _rompe(robo, 5_118.0, minuto=17.0, positions=[_posicao()])
    _rompe(robo, 5_110.0, minuto=30.0)

    assert len(_rompe(robo, 5_099.0, minuto=45.0)) == 1
    robo.on_order_expired(ABERTURA + pd.Timedelta(minutes=46))
    assert _rompe(robo, 5_098.0, minuto=47.0) == []


def test_fade_nao_dispara_antes_da_1a_operacao_fechar():
    """Enquanto a posicao original ainda esta aberta, o motor nunca chega no
    bloco do fade (secao 2 do `on_bar` intercepta antes) -- mas o teste
    confere isso tambem no limbo entre armar e preencher."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)                       # armou, ainda nao preencheu
    assert _rompe(robo, 5_099.0, minuto=17.0) == [], (
        "ordem original ainda pendente -- fade nao e' opcao ainda"
    )


def test_fade_desligado_reproduz_o_comportamento_antigo():
    """`fade_rompimento_oposto=False` devolve o robo a uma operacao por
    pregao, ponto -- para quem quiser reproduzir a medicao anterior a
    2026-09-11."""
    robo = WdoOrb(fade_rompimento_oposto=False)
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)
    _rompe(robo, 5_118.0, minuto=17.0, positions=[_posicao()])
    _rompe(robo, 5_110.0, minuto=30.0)

    assert _rompe(robo, 5_099.0, minuto=45.0) == []


def test_sem_fill_da_1a_ORDEM_o_rompimento_oposto_e_ENTRADA_NORMAL_nao_fade():
    """Pergunta do dono, 2026-09-11: "se o preco nao rompeu [i.e., a 1a
    ordem nunca ENCHEU], nem ativa a segunda fase do robo?" -- confirmado
    aqui, empiricamente, sem mudar nada em producao.

    A 1a ordem (rompimento pra cima) morre por prazo SEM preencher --
    `_preencheu_hoje` continua False. Um rompimento no lado oposto, depois
    disso, cai no mesmo rearme ja medido em `test_com_o_aviso_o_robo_
    rearma_no_rompimento_seguinte` (uma ENTRADA NORMAL nova, lado short) --
    nao no bloco do fade, que exige um FILL de verdade da 1a operacao
    (`_preencheu_hoje=True`) antes de poder disparar."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    _rompe(robo, 5_118.5)                                          # arma, lado long
    robo.on_order_expired(ABERTURA + pd.Timedelta(minutes=17))     # morre sem encher

    (acao,) = _rompe(robo, 5_099.0, minuto=18.0)                   # rompe o lado OPOSTO

    assert acao.side == "short"
    assert acao.reason == "orb_rompimento_baixa", (
        "e' entrada NORMAL nova, nao 'orb_fade_volta_a_faixa' -- sem fill "
        "real da 1a operacao, o fade nao e' opcao"
    )


def test_sem_NENHUM_rompimento_no_pregao_nada_acontece_nunca():
    """O outro lado da mesma pergunta: se o preco nunca sai da faixa o dia
    inteiro, nem a 1a entrada arma -- e sem `_lado_primeiro` definido, o
    bloco do fade nem tem o que espelhar. Confirma que a 2a fase depende
    estritamente da 1a ter acontecido."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    for minuto in (16.0, 60.0, 120.0, 200.0, 300.0):
        assert _rompe(robo, 5_110.0, minuto=minuto) == [], (
            "preco dentro da faixa o pregao inteiro -- nada arma, nunca"
        )


# ---------- o corte do relogio, por ordem parada ---------------------------

def test_uma_hora_depois_da_entrada_o_alvo_vira_o_preco_corrente():
    """A troca que levou o deslize pago de R$265,00 para R$70,00 nos 72
    pregoes e o R$/op de +15,71 para +21,31. A limite fica NO preco, nao
    alem dele: e' ordem parada de verdade, nao ordem a mercado disfarcada."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    pos = _posicao(entry_min=16.0)

    assert _rompe(robo, 5_105.0, minuto=75.0, positions=[pos]) == [], "ainda nao deu 1h"

    (acao,) = _rompe(robo, 5_104.0, minuto=76.0, positions=[pos])

    assert isinstance(acao, AdjustTarget)
    assert acao.new_target == pytest.approx(5_104.0)


def test_o_corte_do_relogio_so_dispara_UMA_vez_por_posicao():
    """Repetir `AdjustTarget` a cada barra faria o motor cancelar e remandar
    a ordem-limite de saida sem parar -- cada remessa entra no FIM da fila
    daquele nivel, entao um robo que 'ajusta sempre' nunca preenche nada."""
    robo = WdoOrb()
    _faixa(robo, hi=5_117.5, lo=5_100.0)
    pos = _posicao(entry_min=16.0)

    assert len(_rompe(robo, 5_104.0, minuto=76.0, positions=[pos])) == 1
    assert _rompe(robo, 5_103.5, minuto=77.0, positions=[pos]) == []
    assert _rompe(robo, 5_103.0, minuto=78.0, positions=[pos]) == []


def test_o_corte_a_MERCADO_vem_desligado():
    """`exit_minutos` e' o desenho ANTIGO, mantido so' para reproduzir a
    linha de base (+R$911,00 contra +R$1.649,00). Ligado por engano, ele
    volta a pagar 1 tick de deslize em 67% das saidas do robo."""
    assert WdoOrb().exit_minutos is None
    assert WdoOrb().saida_limite_minutos == 60.0


# ---------- catalogo --------------------------------------------------------

def test_o_robo_esta_no_podio_com_os_defaults_da_classe():
    """O registry nao passa kwargs para este robo de proposito: os defaults
    da CLASSE ja' sao a producao. Se um dia precisarem divergir, este teste
    e' o lugar onde a divergencia aparece."""
    from strategy.daytrade.registry import _KWARGS_PADRAO, get_daytrade_robot

    assert "wdo_orb" not in _KWARGS_PADRAO
    robo = get_daytrade_robot("wdo_orb")
    assert isinstance(robo, WdoOrb)
    assert robo.symbol == "WDO@"
    assert robo.fade_rompimento_oposto is True, (
        "o fade e' o que levou o IS a POSITIVO -- tem de vir ligado por default"
    )
    assert robo.max_fades_por_dia == 3, (
        "teto 3 ficou em 1o lugar nas DUAS janelas (IS +3.055,50 / OOS "
        "+839,00); teto 1 da' +2.843,50 / +385,50 e soltar de vez da' "
        "+2.399,50 no IS -- ver a nota do campo"
    )
    assert robo.quantity == 1, (
        "1 contrato ate' o risco de capital achado no OOS (R$375 trava, "
        "R$500 sobrevive raspando) ser endereçado"
    )


def test_a_ficha_do_painel_explica_o_robo_em_portugues_simples():
    """A ficha e' montada por `getattr` (ver `dashboard/robot_view.py`), entao
    um robo que nao declara os blocos NAO quebra a pagina -- ele aparece vazio,
    que e' pior: o dono liga dinheiro real num robo que a tela nao explica.

    Este teste existe porque o silencio e' o modo de falha aqui."""
    from dashboard import robot_view

    ficha = robot_view.detail("wdo_orb")

    assert ficha is not None
    assert ficha.summary and ficha.example
    # `_blocks` omite bloco vazio em vez de renderizar caixa sem conteudo --
    # entao "os quatro apareceram" e' a prova de que os quatro foram escritos.
    assert [titulo for titulo, _ in ficha.blocks] == [
        "O que ele olha", "Quando compra", "Quando vende",
        "Quanto compra, e o que custa",
    ]
    (ativo,) = ficha.assets
    assert ativo.symbol == "WDO@"
    assert ativo.is_futuro is True
    assert ativo.min_capital == pytest.approx(375.0), (
        "piso de PARTIDA do WDO@: margem 150 x buffer 2,0 x reserva 1,25"
    )
