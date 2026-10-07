from __future__ import annotations

from datetime import datetime, timezone

import pytest

from social_arbitrage.calibragem import calibrar
from social_arbitrage.thesis import Fase, Lente, Thesis


def _agora() -> datetime:
    return datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _tese_fechada(
    *,
    lente: Lente = Lente.CONSUMO,
    resultado_brl: float,
    prob_acerto_estimada: float | None = None,
    payoff_estimado: float | None = None,
    fase: Fase = Fase.FECHADA,
) -> Thesis:
    return Thesis(
        id=1,
        marca="X",
        ticker="XXXX4",
        fase=fase,
        lente=lente,
        fonte_deteccao="teste",
        descricao="d",
        criterio_saida="s",
        tamanho_alvo_pct=0.10,
        criado_em=_agora(),
        preco_entrada=10.0,
        quantidade=100,
        preco_saida=10.0 + resultado_brl / 100,
        resultado_brl=resultado_brl,
        prob_acerto_estimada=prob_acerto_estimada,
        payoff_estimado=payoff_estimado,
    )


def test_calibrar_lista_vazia_retorna_so_total_com_n_zero():
    linhas = calibrar([])
    assert len(linhas) == 1
    assert linhas[0].grupo == "TOTAL"
    assert linhas[0].n == 0


def test_calibrar_ignora_teses_nao_fechadas():
    aberta = _tese_fechada(resultado_brl=0.0, fase=Fase.ABERTA)
    linhas = calibrar([aberta])
    assert len(linhas) == 1
    assert linhas[0].grupo == "TOTAL"
    assert linhas[0].n == 0


def test_calibrar_win_pct_e_payoff_realizado():
    teses = [
        _tese_fechada(resultado_brl=2000.0),
        _tese_fechada(resultado_brl=-1000.0),
    ]
    [linha] = [l for l in calibrar(teses) if l.grupo == "consumo"]
    assert linha.n == 2
    assert linha.vitorias == 1
    assert linha.win_pct == pytest.approx(0.5)
    assert linha.ganho_medio_brl == pytest.approx(2000.0)
    assert linha.perda_media_brl == pytest.approx(1000.0)
    assert linha.payoff_realizado == pytest.approx(2.0)
    assert linha.breakeven_empirico == pytest.approx(1000.0 / 3000.0)
    assert linha.resultado_total_brl == pytest.approx(1000.0)


def test_calibrar_sem_derrota_deixa_payoff_e_breakeven_indeterminados():
    teses = [_tese_fechada(resultado_brl=500.0), _tese_fechada(resultado_brl=800.0)]
    [linha] = [l for l in calibrar(teses) if l.grupo == "consumo"]
    assert linha.payoff_realizado is None
    assert linha.breakeven_empirico is None
    assert linha.edge_indeterminada is True
    assert linha.edge_confirmada is False


def test_calibrar_agrupa_por_lente_e_soma_total():
    teses = [
        _tese_fechada(lente=Lente.CONSUMO, resultado_brl=1000.0),
        _tese_fechada(lente=Lente.CONSUMO, resultado_brl=-500.0),
        _tese_fechada(lente=Lente.POSICIONAMENTO, resultado_brl=300.0),
    ]
    linhas = {l.grupo: l for l in calibrar(teses)}
    assert set(linhas) == {"consumo", "posicionamento", "TOTAL"}
    assert linhas["consumo"].n == 2
    assert linhas["posicionamento"].n == 1
    assert linhas["TOTAL"].n == 3
    assert linhas["TOTAL"].resultado_total_brl == pytest.approx(800.0)


def test_calibrar_media_estimativas_so_conta_quem_tem_estimativa():
    teses = [
        _tese_fechada(resultado_brl=100.0, prob_acerto_estimada=0.6, payoff_estimado=1.5),
        _tese_fechada(resultado_brl=-50.0),  # tamanho digitado direto, sem Kelly
    ]
    [linha] = [l for l in calibrar(teses) if l.grupo == "consumo"]
    assert linha.n_com_estimativa == 1
    assert linha.prob_acerto_estimada_media == pytest.approx(0.6)
    assert linha.payoff_estimado_medio == pytest.approx(1.5)


def test_n_baixo_true_abaixo_do_minimo():
    linha = calibrar([_tese_fechada(resultado_brl=100.0)])[0]
    assert linha.n_baixo is True


def test_edge_confirmada_quando_ic_inteiro_acima_do_breakeven():
    # 30 vitorias de 1000, 3 derrotas de 100 -> win% alto, breakeven baixo
    teses = [_tese_fechada(resultado_brl=1000.0) for _ in range(30)] + [_tese_fechada(resultado_brl=-100.0) for _ in range(3)]
    [linha] = [l for l in calibrar(teses) if l.grupo == "consumo"]
    assert linha.n_baixo is False
    assert linha.edge_confirmada is True
