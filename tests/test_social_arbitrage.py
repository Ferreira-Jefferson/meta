from __future__ import annotations

from datetime import datetime, timezone

import pytest

from social_arbitrage.brand_map import buscar_por_marca, buscar_por_ticker
from social_arbitrage.sizing import kelly_fraction, max_unidades_pelo_pior_caso, tamanho_meio_kelly
from social_arbitrage.store import SocialArbitrageStore
from social_arbitrage.thesis import Evidencia, Fase, Lente, Thesis


def _agora() -> datetime:
    return datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# brand_map
# ---------------------------------------------------------------------------

def test_buscar_por_marca_encontra_entrada_conhecida():
    vinculos = buscar_por_marca("Havaianas")
    assert len(vinculos) == 1
    assert vinculos[0].ticker == "ALPA4"


def test_buscar_por_marca_case_insensitive():
    assert buscar_por_marca("havaianas") == buscar_por_marca("HAVAIANAS")


def test_buscar_por_marca_desconhecida_retorna_vazio():
    assert buscar_por_marca("marca-que-nao-existe-no-catalogo") == ()


def test_buscar_por_ticker_holding_multimarca():
    vinculos = buscar_por_ticker("ABEV3")
    marcas = {v.marca for v in vinculos}
    assert {"Skol", "Brahma", "Guarana Antarctica"} <= marcas


# ---------------------------------------------------------------------------
# Thesis: validacao e maquina de estados
# ---------------------------------------------------------------------------

def _tese_valida(**overrides) -> Thesis:
    campos = dict(
        id=None,
        marca="Havaianas",
        ticker="ALPA4",
        fase=Fase.DETECTADA,
        lente=Lente.CONSUMO,
        fonte_deteccao="campo",
        descricao="prateleira vazia em 3 lojas",
        criterio_saida="quando a imprensa noticiar",
        tamanho_alvo_pct=0.10,
        criado_em=_agora(),
    )
    campos.update(overrides)
    return Thesis(**campos)


@pytest.mark.parametrize("campo,valor", [
    ("marca", ""),
    ("ticker", ""),
    ("descricao", "  "),
    ("criterio_saida", ""),
])
def test_thesis_recusa_campo_texto_vazio(campo, valor):
    with pytest.raises(ValueError):
        _tese_valida(**{campo: valor})


@pytest.mark.parametrize("tamanho", [0.0, -0.1, 1.1])
def test_thesis_recusa_tamanho_alvo_fora_do_intervalo(tamanho):
    with pytest.raises(ValueError):
        _tese_valida(tamanho_alvo_pct=tamanho)


def test_thesis_transicao_valida_avanca_fase():
    tese = _tese_valida()
    tese.transicionar(Fase.EM_VERIFICACAO, quando=_agora())
    assert tese.fase == Fase.EM_VERIFICACAO


def test_thesis_transicao_invalida_lanca_e_nao_muda_fase():
    tese = _tese_valida()
    with pytest.raises(ValueError):
        tese.transicionar(Fase.ABERTA, quando=_agora())
    assert tese.fase == Fase.DETECTADA


def test_thesis_fase_terminal_nao_transiciona():
    tese = _tese_valida(fase=Fase.FECHADA)
    with pytest.raises(ValueError):
        tese.transicionar(Fase.ABERTA, quando=_agora())


def test_thesis_adicionar_evidencia_fora_de_fase_valida_lanca():
    tese = _tese_valida(fase=Fase.APROVADA)
    with pytest.raises(ValueError):
        tese.adicionar_evidencia(Evidencia(texto="x", fonte="y", registrado_em=_agora()))


def test_evidencia_recusa_texto_ou_fonte_vazios():
    with pytest.raises(ValueError):
        Evidencia(texto="", fonte="y", registrado_em=_agora())
    with pytest.raises(ValueError):
        Evidencia(texto="x", fonte="", registrado_em=_agora())


# ---------------------------------------------------------------------------
# SocialArbitrageStore: ciclo de vida completo
# ---------------------------------------------------------------------------

def _store(tmp_path) -> SocialArbitrageStore:
    return SocialArbitrageStore(db_path=tmp_path / "social_arbitrage.sqlite")


def test_criar_tese_persiste_em_detectada(tmp_path):
    store = _store(tmp_path)
    tese = store.criar_tese(
        marca="Havaianas", ticker="ALPA4", lente=Lente.CONSUMO,
        fonte_deteccao="campo", descricao="prateleira vazia",
        criterio_saida="quando a imprensa noticiar", tamanho_alvo_pct=0.10,
        quando=_agora(),
    )
    assert tese.id is not None
    recarregada = store.obter(tese.id)
    assert recarregada.fase == Fase.DETECTADA
    assert recarregada.lente == Lente.CONSUMO


def test_ciclo_completo_ate_fechamento_calcula_resultado(tmp_path):
    store = _store(tmp_path)
    tese = store.criar_tese(
        marca="Havaianas", ticker="ALPA4", lente=Lente.CONSUMO,
        fonte_deteccao="campo", descricao="prateleira vazia",
        criterio_saida="quando a imprensa noticiar", tamanho_alvo_pct=0.10,
        quando=_agora(),
    )
    store.adicionar_evidencia(tese.id, Evidencia(texto="loja Y confirmou falta de estoque", fonte="ligacao", registrado_em=_agora()))
    store.transicionar(tese.id, Fase.EM_VERIFICACAO, quando=_agora())
    store.transicionar(tese.id, Fase.APROVADA, quando=_agora())
    store.registrar_abertura(tese.id, preco_entrada=4.20, quantidade=1000, quando=_agora())
    fechada = store.registrar_fechamento(tese.id, preco_saida=6.30, quando=_agora())
    assert fechada.fase == Fase.FECHADA
    assert fechada.resultado_brl == pytest.approx(2100.0)
    assert len(store.obter(tese.id).evidencias) == 1


def test_rejeitar_sem_motivo_lanca(tmp_path):
    store = _store(tmp_path)
    tese = store.criar_tese(
        marca="Havaianas", ticker="ALPA4", lente=Lente.CONSUMO,
        fonte_deteccao="campo", descricao="x", criterio_saida="y",
        tamanho_alvo_pct=0.10, quando=_agora(),
    )
    with pytest.raises(ValueError):
        store.transicionar(tese.id, Fase.REJEITADA, quando=_agora())


def test_rejeitar_com_motivo_grava_e_e_terminal(tmp_path):
    store = _store(tmp_path)
    tese = store.criar_tese(
        marca="Havaianas", ticker="ALPA4", lente=Lente.CONSUMO,
        fonte_deteccao="campo", descricao="x", criterio_saida="y",
        tamanho_alvo_pct=0.10, quando=_agora(),
    )
    rejeitada = store.transicionar(tese.id, Fase.REJEITADA, quando=_agora(), motivo_rejeicao="evidencia insuficiente")
    assert rejeitada.motivo_rejeicao == "evidencia insuficiente"
    with pytest.raises(ValueError):
        store.transicionar(tese.id, Fase.EM_VERIFICACAO, quando=_agora())


def test_listar_filtra_por_fase(tmp_path):
    store = _store(tmp_path)
    t1 = store.criar_tese(marca="A", ticker="AAAA4", lente=Lente.CONSUMO, fonte_deteccao="f", descricao="d", criterio_saida="s", tamanho_alvo_pct=0.1, quando=_agora())
    store.criar_tese(marca="B", ticker="BBBB4", lente=Lente.POSICIONAMENTO, fonte_deteccao="f", descricao="d", criterio_saida="s", tamanho_alvo_pct=0.1, quando=_agora())
    store.transicionar(t1.id, Fase.EM_VERIFICACAO, quando=_agora())
    detectadas = store.listar(Fase.DETECTADA)
    assert len(detectadas) == 1
    assert detectadas[0].marca == "B"


# ---------------------------------------------------------------------------
# sizing: Kelly e teto de pior caso (Larry Williams)
# ---------------------------------------------------------------------------

def test_kelly_fraction_valores_conhecidos():
    # p=0.6, b=1.0 -> f* = 0.6 - 0.4/1.0 = 0.2
    assert kelly_fraction(0.6, 1.0) == pytest.approx(0.2)


def test_kelly_fraction_edge_negativa_retorna_zero():
    # p=0.4, b=1.0 -> f* = 0.4 - 0.6/1.0 = -0.2 -> clipa em 0
    assert kelly_fraction(0.4, 1.0) == 0.0


@pytest.mark.parametrize("prob,payoff", [(0.0, 1.0), (1.0, 1.0), (-0.1, 1.0), (0.5, 0.0), (0.5, -1.0)])
def test_kelly_fraction_recusa_parametros_fora_do_dominio(prob, payoff):
    with pytest.raises(ValueError):
        kelly_fraction(prob, payoff)


def test_tamanho_meio_kelly_aplica_fracao_e_teto():
    # kelly cru 0.2, meio-kelly = 0.1, abaixo do teto default (0.4)
    assert tamanho_meio_kelly(0.6, 1.0) == pytest.approx(0.1)
    # teto baixo corta o resultado
    assert tamanho_meio_kelly(0.6, 1.0, teto_pct=0.05) == pytest.approx(0.05)


def test_tamanho_meio_kelly_sem_edge_retorna_zero():
    assert tamanho_meio_kelly(0.4, 1.0) == 0.0


def test_max_unidades_pelo_pior_caso_regra_williams():
    # capital 10_000, pior perda por unidade 1_000, multiplicador 1.5
    # exigencia por unidade = 1_500 -> 10_000 // 1_500 = 6
    assert max_unidades_pelo_pior_caso(10_000.0, 1_000.0, multiplicador=1.5) == 6


def test_max_unidades_pelo_pior_caso_capital_insuficiente_retorna_zero():
    assert max_unidades_pelo_pior_caso(1_000.0, 1_000.0, multiplicador=1.5) == 0


def test_max_unidades_pelo_pior_caso_recusa_multiplicador_baixo():
    with pytest.raises(ValueError):
        max_unidades_pelo_pior_caso(10_000.0, 1_000.0, multiplicador=1.0)
