"""Testes SEM REDE do pacote DERIVADO (mercado.derivados_calc / montar_estado(derivados=True)) e das perguntas v2."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "experimento_dia_positivo"))
from mercado import derivados_calc, formata_derivados, montar_pacote, montar_estado  # noqa: E402
from test_motor import m1_dia, monta  # noqa: E402
import perguntas_v2 as pv  # noqa: E402


def _arr(o, h, l, c, v):
    return [np.array(x, float) for x in (o, h, l, c, v)]


def test_derivados_valores_calculados_a_mao():
    # 4 velas: abertura 100; maxima do dia 130 na vela 2; minima 90 na vela 0; fecha 110
    o, h, l, c, v = _arr([100, 105, 120, 118], [110, 120, 130, 120], [90, 100, 115, 105], [105, 118, 119, 110], [10, 10, 10, 40])
    d = derivados_calc(o, h, l, c, v, np.array([10.0] * 20), (125.0, 95.0, 98.0), atrd=100.0, atr15=10.0)
    assert d["desl"] == 10.0 and d["desl_atrd"] == 0.1
    assert abs(d["er"] - 10 / (20 + 20 + 15 + 15)) < 1e-12                   # |10| / soma das amplitudes
    assert abs(d["desl_amp"] - 10 / 40) < 1e-12 and d["amp"] == 40.0
    assert d["pct_acima_ab"] == 100.0 and d["hi"] == 130 and d["lo"] == 90
    assert d["vel_hi"] == 1 and d["vel_lo"] == 3                              # max foi na vela 2 (1 vela atras); min na vela 0 (3 atras)
    assert d["vol_r10"] == 4.0 and d["vol_r20"] == 4.0                       # 40 / media(10)
    assert d["rompeu_dia"] == "nenhum"
    assert d["dev_lado"] == "alta" and abs(d["dev"] - (130 - 110) / 30) < 1e-12   # devolveu 20 dos 30 pts
    assert d["pos_ont"] == "dentro" and d["gap"] == 2.0 and abs(d["gap_preenchido"] - (100 - 110) / 2) < 1e-12
    assert d["swing_topo"] is None and d["swing_fundo"] is None               # so 4 velas: nenhum fractal confirmado


def test_derivados_rompeu_dia_e_swing_confirmado():
    n = 9
    h = np.array([10, 11, 12, 20, 12, 11, 10, 11, 25], float)
    l = h - 5
    c = h - 1
    o = h - 2
    d = derivados_calc(o, h, l, c, np.full(n, 10.0), np.array([]), None, atrd=50.0, atr15=5.0)
    assert d["swing_topo"] == (3, 20.0)                                       # fractal confirmado na vela 3 (indice <= k-2)
    assert d["rompeu_dia"] == "alta"                                          # ultimo fechamento 24 > maxima anterior 20
    assert d["ont_h"] is None
    txt = "\n".join(formata_derivados(d))
    assert "DERIVADOS" in txt and "Ultimo topo de swing" in txt


def test_swing_nao_usa_vela_nao_confirmada():
    h = np.array([10, 11, 12, 11, 10, 20], float)   # pico na ultima vela nao e fractal (sem 2 velas depois)
    l = h - 3
    d = derivados_calc(h - 1, h, l, h - 1, np.full(6, 5.0), np.array([]), None, 50.0, 5.0)
    assert d["swing_topo"] == (2, 12.0)


def test_pacote_derivado_sem_look_ahead_e_opcional():
    d1, d2, d3 = m1_dia("2026-03-09", seed=1), m1_dia("2026-03-10", seed=2), m1_dia("2026-03-11", seed=3)
    mk = monta([d1, d2, d3])
    K = 10
    corte = pd.Timestamp("2026-03-10 09:00") + pd.Timedelta(minutes=15 * (K + 1))
    d2b, d3b = d2.copy(), d3.copy()
    d2b.loc[d2b.index >= corte, ["open", "high", "low", "close"]] = 55555.0
    d2b.loc[d2b.index >= corte, "real_volume"] = 9e9
    d3b.loc[:, ["open", "high", "low", "close"]] = 77777.0
    mk2 = monta([d1, d2b, d3b])
    e1 = montar_estado(mk, mk.dia("2026-03-10"), K, derivados=True)
    e2 = montar_estado(mk2, mk2.dia("2026-03-10"), K, derivados=True)
    assert e1 == e2 and "DERIVADOS" in e1
    assert "55555" not in e1 and "77777" not in e1 and "2026" not in e1
    assert montar_estado(mk, mk.dia("2026-03-10"), K + 1, derivados=True) != e1
    # opcao desligada (padrao): pacote identico ao anterior, sem a secao
    est = dict(pos=None, pend=None, pts=0, brl=0, ntrades=0)
    p0 = montar_pacote(mk, mk.dia("2026-03-10"), K, est, [], [])
    assert "DERIVADOS" not in p0 and "DERIVADOS" not in montar_estado(mk, mk.dia("2026-03-10"), K)
    # com derivados so ACRESCENTA linhas
    p1 = montar_pacote(mk, mk.dia("2026-03-10"), K, est, [], [], derivados=True)
    assert set(p0.split("\n")) <= set(p1.split("\n"))
    # derivados na vela 0 (uma vela so) nao quebra
    assert "DERIVADOS" in montar_estado(mk, mk.dia("2026-03-10"), 0, derivados=True)


def test_perguntas_v2_bem_formadas():
    ids = [d["id"] for d in pv.M + pv.G + pv.FINAIS]
    assert len(ids) == len(set(ids)) and len(pv.M) == 17
    for qid, q in {**pv.QUESTOES_B, **pv.QUESTOES_GESTAO_A, **pv.QUESTOES_FINAIS_A}.items():
        assert q["type"] in ("noul", "choice", "score") and q["instructions"]
        if q["type"] == "choice":
            assert isinstance(q["criteria"], dict) and len(q["criteria"]) >= 2
        if q["type"] == "score":
            assert isinstance(q["criteria"], list) and len(q["criteria"]) >= 2
        if q["type"] == "noul":
            assert "criteria" not in q
    assert set(pv.QUESTOES_B["acao"]["criteria"]) == {"comprar", "vender", "fora"}
    assert set(pv.QUESTOES_GESTAO_A["v2_g_acao"]["criteria"]) == {"manter", "stop_pivo", "zerar"}
    # as categorias do veto existem de verdade nas perguntas
    for qid, cats in pv.VOTOS.items():
        assert set(cats) <= set(pv.QUESTOES_MERCADO_V2[qid]["criteria"])
    assert pv.gera_md().startswith("# Perguntas v2")


def test_vetos_e_texto_respostas():
    rm = {"v2_dia_tipo": {"c": "baixa_dirigida", "p": {"baixa_dirigida": 0.7, "alta_dirigida": 0.1}, "k": 0.5},
          "v2_h1": {"c": "alta", "p": {"alta": 0.4, "baixa": 0.3, "misto": 0.3}, "k": 0.5},
          "v2_lateral_morta": 0.2, "v2_eficiencia": {"s": 1.4, "p": {"0": 0.1, "1": 0.5, "2": 0.4}, "k": 0.6}}
    v = pv.vetos(rm)
    assert len(v["comprar"]) == 1 and v["vender"] == [] and v["fora"] == []   # so dia_tipo (P 0,7) conta; h1 alta P 0,4 < 0,5
    assert pv.vetos({**rm, "v2_lateral_morta": 0.6})["fora"]
    assert pv.vetos(None) == {"comprar": [], "vender": [], "fora": []}
    t = pv.texto_respostas(rm)
    assert "baixa_dirigida" in t and "P(sim) = 0.20" in t and "nível esperado 1.40" in t and "sem resposta" in t
