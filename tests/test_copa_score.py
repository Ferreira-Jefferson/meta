"""A regua da Copa BTG (`backtest/intraday/copa_score.py`) com valores
conhecidos, escrita ANTES de qualquer estrategia da familia `copa` existir --
e' esse o ponto dela: definir como o resultado sera' julgado antes de haver
resultado para julgar.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.intraday.copa_score import (
    PREGOES_POR_FASE,
    blocos_de_fase,
    janelas_sprint,
    resultados_diarios,
    resumir_blocos,
    resumo_sprint,
)
from backtest.intraday.machine import IntradayTrade
from core.models import IntradayExitReason


def _trade(dia: str, pnl: float, hora_entrada: str = "10:00", minutos: int = 10) -> IntradayTrade:
    """Trade sintetico com P&L EXATO: `point_value_brl=1`, `quantity=1` e
    `fees_total=0` fazem `pnl_brl` ser literalmente `exit_price - entry_price`.
    Nada aqui testa custo -- isso e' `tests/test_intraday_cost_model.py`."""
    entrada = pd.Timestamp(f"{dia} {hora_entrada}", tz="UTC")
    return IntradayTrade(
        symbol="WIN@", strategy_name="teste", strategy_version="0",
        side="long",
        entry_ts=entrada, entry_price=0.0,
        exit_ts=entrada + pd.Timedelta(minutes=minutos), exit_price=pnl,
        quantity=1, exit_reason=IntradayExitReason.TARGET,
        point_value_brl=1.0, capital_base=1000.0, fees_total=0.0,
    )


# ---------- resultados_diarios ---------------------------------------------

def test_resultados_diarios_soma_por_pregao_e_ordena():
    trades = [
        _trade("2026-03-03", 5.0), _trade("2026-03-03", -2.0),
        _trade("2026-03-02", 7.0),
    ]
    serie = resultados_diarios(trades)
    assert list(serie.index) == [pd.Timestamp("2026-03-02"), pd.Timestamp("2026-03-03")]
    assert serie.tolist() == [7.0, 3.0]


def test_pregao_sem_trade_nao_vira_zero_na_serie():
    """Um dia sem trade NAO aparece -- a serie descreve os dias em que o robo
    operou. Virar zero silenciosamente inflaria o denominador de qualquer
    media por pregao."""
    serie = resultados_diarios([_trade("2026-03-02", 4.0), _trade("2026-03-05", 1.0)])
    assert len(serie) == 2
    assert pd.Timestamp("2026-03-03") not in serie.index


def test_sem_trade_nenhum_devolve_serie_vazia_em_vez_de_levantar():
    serie = resultados_diarios([])
    assert serie.empty
    assert blocos_de_fase(serie) == []


# ---------- blocos_de_fase --------------------------------------------------

def _diarios(valores: list[float]) -> pd.Series:
    datas = pd.bdate_range("2026-03-02", periods=len(valores))
    return pd.Series(valores, index=datas, name="liquido_brl")


def test_bloco_de_4_pregoes_e_a_unidade_padrao():
    assert PREGOES_POR_FASE == 4
    blocos = blocos_de_fase(_diarios([10.0, -3.0, 5.0, 2.0]))
    assert len(blocos) == 1
    b = blocos[0]
    assert b.pregoes == 4
    assert b.liquido_brl == pytest.approx(14.0)
    assert b.pior_dia_brl == pytest.approx(-3.0)
    assert b.melhor_dia_brl == pytest.approx(10.0)
    assert b.dias_positivos == 3
    assert b.positivo is True


def test_sobra_que_nao_completa_um_bloco_e_descartada():
    """6 pregoes com blocos de 4 = 1 bloco, nao 1 bloco + 1 pela metade: um
    bloco de 2 dias nao e' comparavel a um de 4."""
    blocos = blocos_de_fase(_diarios([1.0] * 6))
    assert len(blocos) == 1
    assert blocos[0].pregoes == 4


def test_bloco_inteiro_negativo_e_reconhecido_como_negativo():
    b = blocos_de_fase(_diarios([-1.0, -2.0, -3.0, -4.0]))[0]
    assert b.positivo is False
    assert b.liquido_brl == pytest.approx(-10.0)
    assert b.pior_dia_brl == pytest.approx(-4.0)
    # o "melhor" dia de um bloco todo negativo continua sendo negativo
    assert b.melhor_dia_brl == pytest.approx(-1.0)


def test_bloco_de_um_pregao_so_e_valido_quando_pedido():
    blocos = blocos_de_fase(_diarios([3.0, -1.0]), pregoes=1)
    assert [b.liquido_brl for b in blocos] == [3.0, -1.0]
    assert blocos[0].pior_dia_brl == blocos[0].melhor_dia_brl == 3.0


def test_repescagem_usa_bloco_de_3():
    blocos = blocos_de_fase(_diarios([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]), pregoes=3)
    assert [b.liquido_brl for b in blocos] == [6.0, 15.0]


def test_pregoes_zero_ou_negativo_levanta():
    with pytest.raises(ValueError):
        blocos_de_fase(_diarios([1.0]), pregoes=0)


# ---------- score_copa (RELATORIO, nunca criterio) --------------------------

def test_score_copa_descarta_o_pior_pregao_do_bloco():
    b = blocos_de_fase(_diarios([10.0, -30.0, 5.0, 2.0]))[0]
    assert b.liquido_brl == pytest.approx(-13.0)
    # a regra da Copa descarta o pior dia: -13 - (-30) = +17
    assert b.score_copa_brl == pytest.approx(17.0)


def test_score_copa_descarta_o_pior_dia_mesmo_quando_todos_sao_positivos():
    """A regra e' "descarta o PIOR", nao "descarta se for negativo" -- num
    bloco todo positivo o score fica ABAIXO do liquido, e e' assim mesmo."""
    b = blocos_de_fase(_diarios([10.0, 4.0, 6.0, 8.0]))[0]
    assert b.score_copa_brl == pytest.approx(28.0 - 4.0)


# ---------- resumir_blocos (insumo do portao G1-G4) -------------------------

def test_resumo_conta_positivos_e_medianas():
    diarios = _diarios([10.0, -3.0, 5.0, 2.0, -1.0, -2.0, -3.0, -4.0])
    blocos = blocos_de_fase(diarios)
    r = resumir_blocos(blocos, diarios)
    assert r.n_blocos == 2
    assert r.positivos == 1
    assert r.fracao_positiva == pytest.approx(0.5)
    assert r.pior_bloco_brl == pytest.approx(-10.0)
    assert r.melhor_bloco_brl == pytest.approx(14.0)
    assert r.mediana_dos_vencedores_brl == pytest.approx(14.0)
    assert r.pior_pregao_brl == pytest.approx(-4.0)
    # pregoes positivos: 10, 5, 2 -> mediana 5
    assert r.mediana_dos_pregoes_positivos_brl == pytest.approx(5.0)


def test_resumo_de_lista_vazia_e_zerado_em_vez_de_levantar():
    r = resumir_blocos([], pd.Series(dtype="float64"))
    assert r.n_blocos == 0
    assert r.fracao_positiva == 0.0


# ---------- janelas_sprint (a bateria da final) -----------------------------

def test_trade_so_conta_na_janela_se_abriu_E_fechou_dentro_dela():
    """O competidor chega zerado na bateria e e' achatado no fim -- um trade
    montado antes do apito inicial nao e' resultado dele."""
    trades = [
        _trade("2026-03-02", 100.0, hora_entrada="10:00", minutos=5),   # dentro de 10:00-10:40
        _trade("2026-03-02", 500.0, hora_entrada="09:50", minutos=20),  # abriu antes das 10:00
        _trade("2026-03-02", 700.0, hora_entrada="10:30", minutos=30),  # fecha 11:00, depois do fim
    ]
    janelas = janelas_sprint(trades, minutos=40, passo_minutos=10)
    j = janelas[janelas["inicio"] == pd.Timestamp("2026-03-02 10:00")].iloc[0]
    assert j["liquido_brl"] == pytest.approx(100.0)
    assert j["trades"] == 1


def test_janela_mais_longa_nunca_captura_menos_que_a_curta_no_mesmo_inicio():
    """Invariante do desenho e a razao de 40 e 45 serem sempre reportados
    juntos: se 45 min rende MENOS que 40 no mesmo inicio, o robo devolve
    ganho depois do minuto 40 -- e isso e' defeito, nao conservadorismo."""
    trades = [
        _trade("2026-03-02", 10.0, hora_entrada="10:00", minutos=5),
        _trade("2026-03-02", 90.0, hora_entrada="10:35", minutos=8),  # fecha 10:43
    ]
    j40 = janelas_sprint(trades, minutos=40, passo_minutos=60)
    j45 = janelas_sprint(trades, minutos=45, passo_minutos=60)
    assert j40.iloc[0]["liquido_brl"] == pytest.approx(10.0)
    assert j45.iloc[0]["liquido_brl"] == pytest.approx(100.0)


def test_sprint_sem_trade_devolve_dataframe_vazio_com_as_colunas():
    vazio = janelas_sprint([], minutos=40)
    assert vazio.empty
    assert list(vazio.columns) == ["data", "inicio", "fim", "liquido_brl", "trades"]
    assert resumo_sprint(vazio)["janelas"] == 0


def test_resumo_sprint_reporta_pior_e_percentual_positivo():
    trades = [
        _trade("2026-03-02", -50.0, hora_entrada="10:00", minutos=5),
        _trade("2026-03-03", 150.0, hora_entrada="10:00", minutos=5),
    ]
    r = resumo_sprint(janelas_sprint(trades, minutos=40, passo_minutos=60))
    assert r["janelas"] == 2
    assert r["pior"] == pytest.approx(-50.0)
    assert r["melhor"] == pytest.approx(150.0)
    assert r["positivas_pct"] == pytest.approx(50.0)
