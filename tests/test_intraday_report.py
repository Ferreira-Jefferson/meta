"""A TABELA PADRAO (`backtest/intraday/report.py`) — regra do dono
2026-08-25: uma base de colunas fixa, conhecida, igual em todo script.

O que estes testes protegem nao e' estetica: e' que a MESMA grandeza apareca
sempre com o mesmo nome, na mesma posicao e no mesmo formato. Duas rodadas
com colunas diferentes nao se comparam de relance, que e' o unico jeito util
de comparar.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.intraday.report import (
    LinhaResultado,
    cabecalho,
    linha,
    linha_de_resultado,
    maxdd_brl,
    num_br,
    tabela,
)


class _ResultadoFake:
    """O minimo que `linha_de_resultado` le de um `IntradayBacktestResult` --
    montar o de verdade exigiria rodar um backtest, que nao e' o que este
    arquivo testa."""

    def __init__(self, trades, equity, max_drawdown=0.0,
                 wiped_out_at=None, sessoes_puladas=()):
        self.trades = trades
        self.equity_curve = equity
        self.metrics = {"max_drawdown": max_drawdown}
        self.wiped_out_at = wiped_out_at
        self.sessoes_puladas_por_capital = list(sessoes_puladas)


class _TradeFake:
    def __init__(self, pnl):
        self.pnl_brl = pnl


def _equity(valores, inicio="2026-03-02 13:00"):
    idx = pd.date_range(inicio, periods=len(valores), freq="min", tz="UTC")
    return pd.Series(valores, index=idx, name="equity")


# ---------- formato de numero ----------------------------------------------

def test_numero_sai_no_formato_br():
    assert num_br(1234.5) == "1.234,50"
    assert num_br(-1234.567, 1) == "-1.234,6"
    assert num_br(0.0) == "0,00"


def test_numero_ausente_vira_travessao_nao_zero():
    """`—` e `0,00` sao coisas diferentes: um e' "nao se aplica", o outro e'
    "mediu e deu zero"."""
    assert num_br(None) == "—"


# ---------- MaxDD em reais --------------------------------------------------

def test_maxdd_em_reais_e_a_pior_queda_pico_a_vale():
    assert maxdd_brl(_equity([100.0, 130.0, 90.0, 120.0])) == pytest.approx(40.0)


def test_curva_sempre_subindo_nao_tem_queda():
    assert maxdd_brl(_equity([100.0, 110.0, 120.0])) == 0.0


def test_curva_vazia_nao_levanta():
    assert maxdd_brl(pd.Series(dtype="float64")) == 0.0


# ---------- montagem da linha ----------------------------------------------

def test_linha_com_capital_real_preenche_as_doze_colunas():
    r = _ResultadoFake(
        trades=[_TradeFake(30.0), _TradeFake(-10.0), _TradeFake(20.0)],
        equity=_equity([1000.0, 1030.0, 1020.0, 1040.0]),
        max_drawdown=-0.02,
    )
    item = linha_de_resultado("baseline", r, initial_capital=1000.0)
    assert item.liquido_brl == pytest.approx(40.0)
    assert item.retorno_pct == pytest.approx(4.0)
    assert item.capital_final == pytest.approx(1040.0)
    assert item.maxdd_pct == pytest.approx(-2.0)
    assert item.maxdd_brl == pytest.approx(10.0)
    assert item.lucro_por_dd == pytest.approx(4.0)
    assert item.trades == 3
    assert item.win_rate_pct == pytest.approx(200.0 / 3)
    assert item.pregoes == 1


def test_capital_nocional_apaga_as_tres_colunas_que_dependem_de_saldo():
    """Futuro em ambiente de margem infinita nao tem saldo: dividir por um
    `initial_capital` inventado produziria "retorno de X%" que ninguem pode
    usar. As colunas em reais continuam valendo."""
    r = _ResultadoFake(trades=[_TradeFake(500.0)],
                       equity=_equity([1e6, 1e6 - 100, 1e6 + 500]), max_drawdown=-0.0001)
    item = linha_de_resultado("copa_win", r, initial_capital=1e6, capital_nocional=True)
    assert item.retorno_pct is None
    assert item.maxdd_pct is None
    assert item.capital_final is None
    assert item.liquido_brl == pytest.approx(500.0)
    texto = linha(item)
    # exatamente 3: `retorno`, `MaxDD %` e `capital final`. As colunas em
    # reais (inclusive `lucro/DD`) continuam com numero.
    assert texto.count("—") == 3


def test_pregoes_conta_dias_distintos_da_curva_nao_barras():
    equity = pd.concat([_equity([1.0] * 3, "2026-03-02 13:00"),
                        _equity([1.0] * 3, "2026-03-03 13:00")])
    item = linha_de_resultado("x", _ResultadoFake([_TradeFake(10.0)], equity),
                              initial_capital=100.0)
    assert item.pregoes == 2
    assert item.liquido_por_pregao == pytest.approx(5.0)
    assert item.trades_por_pregao == pytest.approx(0.5)


def test_sem_queda_nenhuma_o_lucro_por_dd_e_ausente_em_vez_de_infinito():
    """`inf` numa tabela ordenada por esta coluna poria uma run de 1 trade
    (sem drawdown) acima de tudo."""
    item = linha_de_resultado("x", _ResultadoFake([_TradeFake(10.0)], _equity([100.0, 110.0])),
                              initial_capital=100.0)
    assert item.lucro_por_dd is None


def test_conta_zerada_e_pregao_pulado_viram_aviso_automatico():
    """Nenhum script pode esquecer de mostrar isso -- ja aconteceu uma tabela
    com capital final bonito e a conta zerada no meio da janela."""
    r = _ResultadoFake([_TradeFake(-10.0)], _equity([100.0, 0.0]),
                       wiped_out_at=pd.Timestamp("2026-03-02 14:00", tz="UTC"),
                       sessoes_puladas=[1, 2, 3])
    item = linha_de_resultado("x", r, initial_capital=100.0)
    assert "ZERADO" in item.aviso and "pulou 3d" in item.aviso
    assert "ZERADO" in linha(item)


def test_run_sem_trade_nenhum_nao_levanta():
    item = linha_de_resultado("vazia", _ResultadoFake([], pd.Series(dtype="float64")),
                              initial_capital=100.0)
    assert item.trades == 0 and item.win_rate_pct == 0.0
    assert item.liquido_por_pregao is None


# ---------- a base e' fixa --------------------------------------------------

_BASE_ESPERADA = ("variante", "retorno", "liquido R$", "MaxDD %", "MaxDD R$",
                  "lucro/DD", "win%", "trades", "R$/dia", "trd/dia",
                  "capital final", "pregoes")


def test_cabecalho_tem_as_doze_colunas_da_base_nesta_ordem():
    cab = cabecalho().splitlines()[0]
    posicoes = [cab.index(nome) for nome in _BASE_ESPERADA]
    assert posicoes == sorted(posicoes), cab


def test_extras_entram_depois_da_base_nunca_no_lugar_dela():
    item = LinhaResultado(variante="x", liquido_brl=1.0, maxdd_brl=1.0,
                          win_rate_pct=50.0, trades=2, pregoes=1,
                          extras={"recusas%": "0,0"})
    cab = cabecalho(extras=("recusas%",)).splitlines()[0]
    assert cab.index("recusas%") > cab.index("pregoes")
    assert "0,0" in linha(item, extras=("recusas%",))


def test_extra_ausente_numa_linha_vira_travessao_sem_desalinhar():
    """Comparacao entre estrategias pode ter coluna que so' uma delas tem --
    a tabela nao pode quebrar por isso."""
    com = LinhaResultado("com", 1.0, 1.0, 50.0, 2, 1, extras={"giro": "9"})
    sem = LinhaResultado("sem", 1.0, 1.0, 50.0, 2, 1)
    linhas = tabela([com, sem], extras=("giro",)).splitlines()
    assert len(linhas[-1]) == len(linhas[-2])
    assert linhas[-1].rstrip().endswith("—")


def test_tabela_nao_reordena_as_linhas():
    """A ordem e' decisao de quem chama -- a linha baseline costuma vir
    primeiro, fora da ordenacao, para a comparacao ser imediata."""
    a = LinhaResultado("baseline", 1.0, 1.0, 50.0, 2, 1)
    b = LinhaResultado("melhor", 999.0, 1.0, 50.0, 2, 1)
    corpo = tabela([a, b]).splitlines()[2:]
    assert corpo[0].startswith("baseline") and corpo[1].startswith("melhor")
