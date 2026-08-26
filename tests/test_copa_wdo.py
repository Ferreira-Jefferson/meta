"""`CopaWdo` — grade maker de alta frequencia no minidolar."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.base import Bar, EnterLimit, IntradayOpenPosition
from strategy.daytrade.lab.copa_wdo import CopaWdo, dividir_em_pecas

TICK = 0.5


def _bar(minuto: int, o, h, low, c, volume=10_000.0) -> Bar:
    ts = pd.Timestamp("2026-03-02 12:00", tz="UTC") + pd.Timedelta(minutes=minuto)
    return Bar(ts=ts, open=float(o), high=float(h), low=float(low),
               close=float(c), volume=volume)


def _robo(**kw) -> CopaWdo:
    base = dict(teto_contratos=4, tick_size=TICK, aquecimento_barras=0,
                ancora_fixa_barras=3, ttl_barras=5, pecas=2)
    base.update(kw)
    r = CopaWdo(**base)
    r.on_session_start(pd.Timestamp("2026-03-02").date())
    return r


def _posicao(qtd=2) -> IntradayOpenPosition:
    return IntradayOpenPosition(
        side="long", entry_ts=pd.Timestamp("2026-03-02 12:05", tz="UTC"),
        entry_price=5150.0, quantity=qtd, current_stop=5147.0,
        current_target=5151.5, bars_held=1,
    )


# ---------- divisao em pecas ------------------------------------------------

@pytest.mark.parametrize("qtd,pecas,esperado", [
    (4, 2, (2, 2)),
    (7, 3, (3, 2, 2)),
    (5, 5, (1, 1, 1, 1, 1)),
    (2, 5, (1, 1)),      # nunca produz peca de zero contrato
    (3, 1, (3,)),
])
def test_pecas_somam_exatamente_a_quantidade(qtd, pecas, esperado):
    """O motor NAO redistribui sozinho (`EnterLimit.split_quantities`): se a
    soma nao bater, a ordem manda quantidade errada para a corretora."""
    assert dividir_em_pecas(qtd, pecas) == esperado
    assert sum(dividir_em_pecas(qtd, pecas)) == qtd


# ---------- o teto e' ENTRADA, nunca constante ------------------------------

@pytest.mark.parametrize("teto,esperado", [(2, 2), (4, 4), (5, 5), (8, 8)])
def test_a_mesma_instancia_escala_com_o_teto_sem_alterar_codigo(teto, esperado):
    assert CopaWdo(teto_contratos=teto, fracao_entrada=1.0).quantidade_por_rodada == esperado


def test_teto_invalido_levanta_em_vez_de_assumir_um_numero():
    with pytest.raises(ValueError):
        CopaWdo(teto_contratos=0)


def test_ordem_dividida_respeita_a_quantidade_derivada_do_teto():
    robo = _robo(teto_contratos=5, fracao_entrada=1.0, pecas=3)
    b = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    ordem = robo.on_bar(b.ts, b, [], 0.0)[0]
    assert ordem.quantity == 5
    assert ordem.split_quantities == (2, 2, 1)


# ---------- a ordem parada --------------------------------------------------

def test_arma_compra_abaixo_da_referencia_com_alvo_e_stop_em_ticks():
    robo = _robo(entrada_ticks=2.0, alvo_ticks=2.0, stop_ticks=6.0)
    b = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    acoes = robo.on_bar(b.ts, b, [], 0.0)

    assert len(acoes) == 1 and isinstance(acoes[0], EnterLimit)
    ordem = acoes[0]
    assert ordem.side == "long"
    assert ordem.limit_price == pytest.approx(5150.0 - 2 * TICK)
    assert ordem.initial_target == pytest.approx(ordem.limit_price + 2 * TICK)
    assert ordem.initial_stop == pytest.approx(ordem.limit_price - 6 * TICK)
    assert ordem.ttl_bars == 5


def test_todo_nivel_cai_na_grade_do_tick():
    """A serie continua `WDO@` reporta tick 0,001; o contrato cheio negocia de
    0,5 em 0,5. Ordem fora da grade e' ordem que a corretora recusa."""
    robo = _robo(entrada_ticks=1.5)
    b = _bar(1, 5150.3, 5150.6, 5150.1, 5150.3)
    ordem = robo.on_bar(b.ts, b, [], 0.0)[0]
    for nivel in (ordem.limit_price, ordem.initial_target, ordem.initial_stop):
        assert round(nivel / TICK, 9) == round(round(nivel / TICK), 9)


def test_nao_re_arma_antes_do_prazo_da_ordem_anterior():
    """Re-armar a cada barra SUBSTITUI a ordem no motor (`LimitCancelled`
    reason="superseded") -- ela nunca completaria o prazo de espera e o
    `ttl_bars` viraria letra morta."""
    robo = _robo(ttl_barras=5)
    primeira = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    assert len(robo.on_bar(primeira.ts, primeira, [], 0.0)) == 1
    for i in range(2, 6):
        b = _bar(i, 5150.0, 5151.0, 5149.0, 5150.0)
        assert robo.on_bar(b.ts, b, [], 0.0) == [], f"re-armou na barra {i}"


def test_re_arma_depois_do_prazo():
    robo = _robo(ttl_barras=3)
    for i in range(1, 4):
        b = _bar(i, 5150.0, 5151.0, 5149.0, 5150.0)
        robo.on_bar(b.ts, b, [], 0.0)
    b = _bar(4, 5150.0, 5151.0, 5149.0, 5150.0)
    assert len(robo.on_bar(b.ts, b, [], 0.0)) == 1


def test_com_posicao_aberta_nao_arma_ordem_nova():
    robo = _robo()
    b = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    assert robo.on_bar(b.ts, b, [_posicao()], 0.0) == []


def test_alterna_o_lado_depois_de_zerar():
    """Alternar (em vez de insistir no mesmo lado) impede a grade de virar
    aposta direcional disfarcada depois de uma sequencia."""
    robo = _robo(ttl_barras=1)
    b1 = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    assert robo.on_bar(b1.ts, b1, [], 0.0)[0].side == "long"
    b2 = _bar(2, 5150.0, 5151.0, 5149.0, 5150.0)
    robo.on_bar(b2.ts, b2, [_posicao()], 0.0)          # preencheu
    b3 = _bar(3, 5150.0, 5151.0, 5149.0, 5150.0)
    assert robo.on_bar(b3.ts, b3, [], 0.0)[0].side == "short"


# ---------- ancora hibrida --------------------------------------------------

def test_ancora_e_a_abertura_do_pregao_e_depois_o_preco_corrente():
    robo = _robo(ancora_fixa_barras=2, ttl_barras=1, entrada_ticks=2.0)
    b1 = _bar(1, 5150.0, 5151.0, 5149.0, 5155.0)
    ordem1 = robo.on_bar(b1.ts, b1, [], 0.0)[0]
    assert ordem1.metadata["referencia"] == pytest.approx(5150.0)   # abertura

    b2 = _bar(2, 5155.0, 5156.0, 5154.0, 5160.0)
    ordem2 = robo.on_bar(b2.ts, b2, [], 0.0)[0]
    assert ordem2.metadata["referencia"] == pytest.approx(5150.0)   # ainda fixa

    b3 = _bar(3, 5160.0, 5161.0, 5159.0, 5165.0)
    ordem3 = robo.on_bar(b3.ts, b3, [], 0.0)[0]
    assert ordem3.metadata["referencia"] == pytest.approx(5165.0)   # rolante


# ---------- nenhum nivel de preco atravessa a virada do pregao --------------

def test_on_session_start_apaga_a_abertura_e_os_contadores():
    """`WDO@` rola de vencimento TODO MES -- ~9 emendas na janela salva."""
    robo = _robo()
    b = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    robo.on_bar(b.ts, b, [], 0.0)
    assert robo._abertura == 5150.0
    robo.on_session_start(pd.Timestamp("2026-03-03").date())
    assert robo._abertura is None
    assert robo._rodadas_hoje == 0 and robo._espera is None


# ---------- freios ----------------------------------------------------------

def test_teto_de_rodadas_do_dia_e_respeitado():
    robo = _robo(max_rodadas_dia=1, ttl_barras=1)
    b1 = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    assert len(robo.on_bar(b1.ts, b1, [], 0.0)) == 1
    b2 = _bar(2, 5150.0, 5151.0, 5149.0, 5150.0)
    assert robo.on_bar(b2.ts, b2, [], 0.0) == []


def test_perda_max_dia_e_fracao_do_teto_e_para_de_armar():
    robo = _robo(perda_max_dia_pontos=2.0, point_value_brl=10.0, teto_contratos=4)
    assert robo.perda_max_dia_brl == pytest.approx(2.0 * 10.0 * 4)
    b = _bar(1, 5150.0, 5151.0, 5149.0, 5150.0)
    assert robo.on_bar(b.ts, b, [], -100.0) == []


def test_freio_diario_desligado_por_padrao():
    assert CopaWdo(teto_contratos=4).perda_max_dia_brl is None


def test_aquecimento_segura_as_primeiras_barras():
    robo = _robo(aquecimento_barras=3)
    for i in range(1, 4):
        b = _bar(i, 5150.0, 5151.0, 5149.0, 5150.0)
        assert robo.on_bar(b.ts, b, [], 0.0) == []
    b = _bar(4, 5150.0, 5151.0, 5149.0, 5150.0)
    assert len(robo.on_bar(b.ts, b, [], 0.0)) == 1
