"""Testes do Quantum — os invariantes que, se quebrarem, fazem o backtest mentir.

Rodar:  .\\.venv\\Scripts\\python.exe -m pytest quantum/tests
Cada teste monta o próprio SQLite em `tmp_path` (a suíte roda em paralelo).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantum import armazem, metricas
from quantum.backtest import rodar
from quantum.base import Base
from quantum.estrategias import Estrategia, Fator
from quantum.estudos import benjamini_hochberg
from quantum.fontes import cvm


# ── LTM ────────────────────────────────────────────────────────────────────
def _doc(cnpj, dt, tipo, receb, meses, ytd, pen=None, acoes=1e6, lpa=None):
    return {"CNPJ_CIA": cnpj, "DT_REFER": dt, "tipo": tipo, "VERSAO": 1, "DT_RECEB": receb, "consolidado": 1,
            "meses": meses, "receita": ytd, "lucro_bruto": ytd, "ebit": ytd, "lucro": ytd, "lucro_contr": ytd,
            "fco": ytd, "receita_pen": pen, "lucro_bruto_pen": pen, "ebit_pen": pen, "lucro_pen": pen,
            "lucro_contr_pen": pen, "fco_pen": pen, "ativo": 10.0, "caixa": 1.0, "divida": 2.0, "pl": 5.0,
            "pl_contr": 5.0, "acoes": acoes, "lpa_on": lpa, "lucro_contr_ytd": ytd}


def test_ltm_soma_trimestre_atual_com_anual_anterior():
    docs = pd.DataFrame([
        _doc("A", "2020-12-31", "DFP", "2021-03-01", 12, 100.0),
        _doc("A", "2021-06-30", "ITR", "2021-08-10", 6, 60.0, pen=40.0),
    ])
    out = cvm.montar_ltm(docs).set_index("dt_refer")
    assert out.loc["2020-12-31", "lucro"] == 100.0
    assert out.loc["2021-06-30", "lucro"] == pytest.approx(60 + 100 - 40)


def test_ltm_disponivel_so_quando_a_dfp_usada_chegou():
    # DFP reapresentada DEPOIS do ITR: o LTM do ITR só vale a partir da DFP.
    docs = pd.DataFrame([
        _doc("A", "2020-12-31", "DFP", "2021-09-01", 12, 100.0),
        _doc("A", "2021-06-30", "ITR", "2021-08-10", 6, 60.0, pen=40.0),
    ])
    out = cvm.montar_ltm(docs).set_index("dt_refer")
    assert out.loc["2021-06-30", "dt_receb"] == "2021-09-01"


def test_composicao_em_milhar_e_corrigida_pelo_lpa():
    d = _doc("A", "2021-03-31", "ITR", "2021-05-01", 3, 1e9, pen=1e9, acoes=9_719.0, lpa=1e9 / 9_719_000)
    out = cvm.montar_ltm(pd.DataFrame([d]))
    assert out.acoes.iloc[0] == pytest.approx(9_719_000)


# ── Base sintética ─────────────────────────────────────────────────────────
def _banco(tmp_path, dem_receb="2020-02-10", split_em=None):
    con = armazem.conectar(tmp_path / "q.sqlite")
    armazem.upsert(con, "empresas", pd.DataFrame([
        {"cnpj": c, "nome": c, "nome_comercial": c, "cd_cvm": "1", "setor": "Indústria", "situacao": "ATIVO",
         "site_ri": None, "financeira": 0} for c in ("A", "B", "C")]))
    armazem.upsert(con, "tickers", pd.DataFrame([
        {"ticker": t, "cnpj": c, "classe": "ON", "segmento": "NM", "inicio_negociacao": None, "fim_negociacao": None}
        for t, c in (("AAAA3", "A"), ("BBBB3", "B"), ("CCCC3", "C"))]))
    dem = []
    for c, lucro in (("A", 300.0), ("B", 200.0), ("C", 100.0)):
        dem.append({"cnpj": c, "dt_refer": "2019-12-31", "tipo": "DFP", "versao": 1, "dt_receb": dem_receb,
                    "consolidado": 1, "receita": 1000.0, "lucro_bruto": 500.0, "ebit": lucro, "lucro": lucro,
                    "lucro_contr": lucro, "fco": lucro, "ativo": 2000.0, "caixa": 100.0, "divida": 100.0,
                    "pl": 1000.0, "pl_contr": 1000.0, "acoes": 100.0})
    armazem.upsert(con, "demonstracoes", pd.DataFrame(dem))
    datas = pd.bdate_range("2019-01-01", "2021-12-31")
    rows = []
    rng = np.random.default_rng(7)   # ruído pequeno e fixo: sem ele o desvio-padrão é ~0 e o Sharpe vira ruído numérico
    for t, drift in (("AAAA3", 0.001), ("BBBB3", 0.0), ("CCCC3", -0.0005), ("^BVSP", 0.0003)):
        px = 10 * np.cumprod(1 + drift + rng.normal(0, 0.002, len(datas)))
        for d, p in zip(datas, px):
            sp = 2.0 if (split_em and t == "AAAA3" and d == pd.Timestamp(split_em)) else 0.0
            rows.append({"ticker": t, "data": d.strftime("%Y-%m-%d"), "close": p, "adj_close": p,
                         "volume": 1e6, "dividendo": 0.0, "split": sp})
    armazem.upsert(con, "precos", pd.DataFrame(rows))
    cdi = (1 + pd.Series(0.0004, index=datas)).cumprod()
    armazem.upsert(con, "indices", pd.DataFrame({"serie": "CDI", "data": datas.strftime("%Y-%m-%d"), "valor": cdi.values}))
    con.commit()
    return con


def test_balanco_so_aparece_depois_da_data_de_entrega(tmp_path):
    con = _banco(tmp_path, dem_receb="2020-02-10")
    b = Base(con)
    assert b.painel("2020-02-10").empty          # entregue NO dia: ainda não conta
    assert len(b.painel("2020-02-11")) == 3


def test_valor_de_mercado_usa_preco_sem_ajuste_de_desdobramento(tmp_path):
    con = _banco(tmp_path, split_em="2020-06-01")
    b = Base(con)
    antes = b.painel("2020-05-29").set_index("ticker")
    depois = b.painel("2020-06-02").set_index("ticker")
    # desdobramento 2:1 → preço cai à metade, ações dobram, valor de mercado ~igual
    assert depois.loc["AAAA3", "acoes_d"] == pytest.approx(2 * antes.loc["AAAA3", "acoes_d"])
    assert depois.loc["AAAA3", "mcap"] == pytest.approx(antes.loc["AAAA3", "mcap"], rel=0.01)


def test_backtest_executa_no_pregao_seguinte_e_escolhe_pelo_ranking(tmp_path):
    con = _banco(tmp_path)
    b = Base(con)
    est = Estrategia("t", "t", "", (Fator("roe", True),))
    r = rodar(b, est, 1, 3, "2020-03-01", "2020-12-31", liquidez_min=0, custo_lado=0)
    assert set(r.carteiras.ticker) == {"AAAA3"}                  # maior ROE
    primeira = r.carteiras.iloc[0]
    assert primeira.data_execucao > primeira.data_decisao        # nunca no preço do sinal


def test_custo_reduz_o_resultado(tmp_path):
    con = _banco(tmp_path)
    b = Base(con)
    est = Estrategia("t", "t", "", (Fator("roe", True),))
    sem = rodar(b, est, 2, 3, "2020-03-01", "2021-06-30", liquidez_min=0, custo_lado=0).serie.iloc[-1]
    com = rodar(b, est, 2, 3, "2020-03-01", "2021-06-30", liquidez_min=0, custo_lado=0.01).serie.iloc[-1]
    assert com < sem


def test_metricas_basicas(tmp_path):
    con = _banco(tmp_path)
    b = Base(con)
    est = Estrategia("t", "t", "", (Fator("roe", True),))
    r = rodar(b, est, 1, 3, "2020-03-01", "2021-12-31", liquidez_min=0, custo_lado=0)
    m = metricas.calcular(r.serie, b.ibov, b.cdi, r.operacoes, r.giro)
    assert m["rentabilidade"]["cagr"] > m["rentabilidade"]["cagr_ibov"]
    assert m["tecnicos"]["taxa_acerto"] == 1.0
    assert m["risco"]["max_drawdown"] <= 0


def test_benjamini_hochberg():
    r = benjamini_hochberg({"a": 0.001, "b": 0.02, "c": 0.5, "d": 0.9}, q=0.10)
    assert r == {"a": True, "b": True, "c": False, "d": False}
    assert benjamini_hochberg({"a": 0.2, "b": 0.3}, q=0.10) == {"a": False, "b": False}


# ── Units e documentos ─────────────────────────────────────────────────────
@pytest.mark.parametrize("texto,esperado", [
    ("1 ON / 2 PN", 3), ("1 KLBN3 + 4 KLBN4", 5), ("2 ações preferenciais e 1 ação ordinária", 3),
    ("1 PN + 3 Recibos de Subscrição", 1), ("1 ON+ 2PN", 3),
])
def test_acoes_por_unit(texto, esperado):
    assert cvm.acoes_por_unit(texto) == esperado


def test_acoes_por_unit_ilegivel_fica_em_branco():
    assert np.isnan(cvm.acoes_por_unit(None))


def test_regras_proventos():
    from quantum import documentos
    txt = ("O Conselho aprovou o pagamento de juros sobre capital próprio no valor de R$ 0,4512 por ação, "
           "com base na posição acionária de 22/09/2026. As ações serão negociadas ex-direito a partir de "
           "23 de setembro de 2026. O pagamento será realizado em 15/10/2026.")
    c, ev, ok = documentos.regras_proventos(txt)
    assert ok and c["tipo"] == "JCP" and c["valor_por_acao"] == pytest.approx(0.4512)
    assert (c["data_com"], c["data_ex"], c["data_pagamento"]) == ("2026-09-22", "2026-09-23", "2026-10-15")


def test_regras_release():
    from quantum import documentos
    txt = "Destaques (R$ milhões)\nReceita Líquida 1.234,5 1.100,0 12,2%\nEBITDA Ajustado 300,1 280,0\nLucro Líquido (12,3) 50,0\n"
    c, ev, ok = documentos.regras_release(txt)
    assert ok and c["unidade"] == "R$ milhões"
    assert (c["receita_liquida"], c["ebitda"], c["lucro_liquido"]) == (1234.5, 300.1, -12.3)


def test_tipo_do_documento():
    from quantum.documentos import tipo_do_documento as t
    assert t("Aviso aos Acionistas", "Outros avisos", None, "Pagamento de dividendos") == "proventos"
    assert t("Dados Econômico-Financeiros", "Press-release", None, "Resultado 2T26") == "release"
    assert t("Fato Relevante", None, None, "Aquisição de controle") == "fato_relevante"
    assert t("Comunicado ao Mercado", "Outros", None, "Mudança de endereço") is None


def test_sharpe_do_nulo_igual_ao_das_metricas(tmp_path):
    """O p-valor compara o Sharpe da estratégia (metricas.calcular) com o dos sorteios
    (conta rápida em estudos._nulo): as duas contas precisam ser a MESMA."""
    from quantum import estudos
    from quantum.backtest import _Precos
    con = _banco(tmp_path)
    b = Base(con)
    est = Estrategia("t", "t", "", (Fator("roe", True),))
    r = rodar(b, est, 3, 3, "2020-03-01", "2020-12-31")   # premissas padrão, as mesmas do nulo
    alvo = metricas.calcular(r.serie, b.ibov, b.cdi)["risco"]["sharpe"]
    # com N = universo inteiro, o sorteio escolhe as mesmas 3 ações → mesmo Sharpe
    nulo = estudos._nulo(b, est, 3, 3, "2020-03-01", "2020-12-31", alvo, _Precos(b), 3, seed=1)
    assert nulo["sharpe_nulo_mediana"] == pytest.approx(alvo, rel=1e-9)
