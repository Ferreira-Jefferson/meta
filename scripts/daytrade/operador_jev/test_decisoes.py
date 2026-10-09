"""Testes do modo decisoes SEM REDE: parser com respostas gravadas, perguntas e conversao resposta -> ordem."""
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev_api import parse_resposta  # noqa: E402
from perguntas_jev import QUESTOES_MERCADO, QUESTOES_GESTAO, MERCADO, GESTAO  # noqa: E402
from decisoes import Ctx, decisao_entrada, decisao_gestao, decide_vela, pivo_recente, nivel_trailing  # noqa: E402

# resposta REAL gravada da API (versao fixa), 3 tipos
GRAVADA = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
        "tendencia": {"type": "noul", "noul": 0.85},
        "acao": {"type": "choice", "choice": "comprar", "probabilities": {"comprar": 0.83, "vender": 0.13, "fora": 0.04}, "confidence": 0.74},
        "forca": {"type": "score", "score": 2.81, "legend": {"0": "a", "1": "b"}, "probabilities": {"0": 0.2, "1": 0.8}, "confidence": 0.68},
    },
    "usage": {"input_tokens": 489, "output_tokens": 75, "cost": 0.000020538},
}


def test_parse_tres_tipos():
    r = parse_resposta(GRAVADA)
    assert r["tendencia"] == 0.85
    assert r["acao"]["c"] == "comprar" and r["acao"]["p"]["comprar"] == 0.83 and r["acao"]["k"] == 0.74
    assert r["forca"]["s"] == 2.81 and r["forca"]["p"]["1"] == 0.8


def test_parse_descarta_malformadas_e_vazio():
    j = {"answers": {"a": {"type": "noul"}, "b": {"type": "choice", "probabilities": {}}, "c": {"type": "zzz", "x": 1},
                     "d": {"type": "noul", "noul": 0.1}}}
    assert parse_resposta(j) == {"d": 0.1}
    assert parse_resposta({}) == {} and parse_resposta(None) == {}


def test_perguntas_bem_formadas():
    ids = [q[0] for q in MERCADO + GESTAO]
    assert len(ids) == len(set(ids))
    for qid, q in {**QUESTOES_MERCADO, **QUESTOES_GESTAO}.items():
        assert q["type"] in ("noul", "choice", "score") and q["instructions"]
        if q["type"] == "choice":
            assert isinstance(q["criteria"], dict) and len(q["criteria"]) >= 2
        if q["type"] == "score":
            assert isinstance(q["criteria"], list) and len(q["criteria"]) >= 2
        if q["type"] == "noul":
            assert "criteria" not in q
    for qid in ("acao", "stop", "alvo", "mao"):
        assert qid in QUESTOES_MERCADO
    assert set(QUESTOES_MERCADO["acao"]["criteria"]) == {"comprar", "vender", "fora"}
    assert "g_acao" in QUESTOES_GESTAO


# ---- conversao: mercado sintetico, sobe devagar; ATR 100
def ctx_dia(n=40):
    T = (np.datetime64("2026-03-10T09:00") + np.arange(n) * np.timedelta64(15, "m"))
    c = ctx = Ctx.__new__(Ctx)
    c.T = T
    base = 100000 + np.arange(n) * 10.0
    c.C = base.copy()
    c.H = base + 50
    c.L = base - 50
    c.ATR = np.full(n, 100.0)
    dia = SimpleNamespace(m15_t=T)
    return ctx, dia


def resp(esc="comprar", p=0.6, stop="1atr", alvo="2atr", mao="2"):
    return {"acao": {"c": esc, "p": {"comprar": p if esc == "comprar" else 0.1, "vender": p if esc == "vender" else 0.1,
                                     "fora": p if esc == "fora" else 0.1}, "k": 0.5},
            "stop": {"c": stop, "p": {}, "k": 0}, "alvo": {"c": alvo, "p": {}, "k": 0}, "mao": {"c": mao, "p": {}, "k": 0}}


def test_entrada_compra_limite_no_fechamento_stop_alvo_mao():
    ctx, dia = ctx_dia()
    dec, info = decisao_entrada(resp(), ctx, dia, 20, 0.5)
    assert dec["acao"] == "comprar_limite" and dec["preco"] == 100200.0 and dec["preco"] <= ctx.C[20]
    assert dec["stop"] == 100100.0 and dec["alvo"] == 100400.0 and dec["contratos"] == 2
    assert dec["validade_velas"] == 3 and dec["trail"] is False


def test_entrada_venda_e_sem_alvo_deixa_correr():
    ctx, dia = ctx_dia()
    dec, _ = decisao_entrada(resp("vender", 0.7, "1.5atr", "sem_alvo", "1"), ctx, dia, 20, 0.5)
    assert dec["acao"] == "vender_limite" and dec["preco"] >= ctx.C[20]
    assert dec["stop"] == 100350.0 and dec["alvo"] is None and dec["trail"] is True and dec["contratos"] == 1


def test_limiar_e_fora_nao_entram():
    ctx, dia = ctx_dia()
    assert decisao_entrada(resp("comprar", 0.45), ctx, dia, 20, 0.5)[0]["acao"] == "ficar_fora"
    assert decisao_entrada(resp("fora", 0.9), ctx, dia, 20, 0.5)[0]["acao"] == "ficar_fora"
    assert decisao_entrada(resp("comprar", 0.45), ctx, dia, 20, 0.4)[0]["acao"] == "comprar_limite"
    assert decisao_entrada({}, ctx, dia, 20, 0.5)[0]["acao"] == "ficar_fora"


def test_pivo_so_usa_velas_confirmadas():
    ctx, dia = ctx_dia()
    g = 20
    ctx.L[g - 1] = 99000.0           # fundo na vela anterior a ultima: ainda NAO confirmado (precisa de 2 velas depois)
    assert pivo_recente(ctx, g, 1) is None
    ctx.L[g - 2] = 99000.0           # com 2 velas depois ja confirma... mas g-1 e g-2 iguais nao e estrito
    ctx.L[g - 1] = ctx.L[g - 1] + 500
    p = pivo_recente(ctx, g, 1)
    assert p is not None and p[0] == g - 2 and p[1] == 99000.0
    ctx.L[g + 1:] = 0.0              # futuro nao pode influenciar
    assert pivo_recente(ctx, g, 1) == p


def test_stop_no_pivo_e_fallback():
    ctx, dia = ctx_dia()
    g = 20
    ctx.L[g - 5] = ctx.C[g] - 150.0          # fundo a 1,5 ATR abaixo do fechamento
    dec, info = decisao_entrada(resp(stop="pivo"), ctx, dia, g, 0.5)
    assert dec["stop"] == ctx.L[g - 5] - 5.0 and info["modo_stop"] == "pivo"
    ctx.L[g - 5] = ctx.C[g] - 5.0           # pivo colado (< 0,3 ATR): inviavel -> 1,5 ATR
    ctx.L[g - 6:g - 5] = ctx.L[g - 6:g - 5]
    dec, info = decisao_entrada(resp(stop="pivo"), ctx, dia, g, 0.5)
    assert info["modo_stop"] in ("pivo", "pivo->1.5atr")
    assert dec["stop"] < dec["preco"]


def test_gestao_trailing_so_a_favor_e_zerar():
    ctx, dia = ctx_dia()
    g = 25
    pos = dict(dir=1, stop=100000.0, trail=True, k_ent=15, n=1, preco=100150.0)
    dec, info = decisao_gestao({"g_acao": {"c": "manter", "p": {"manter": 0.9}, "k": 1}}, ctx, dia, g, pos)
    # minima das ultimas 8 velas = L[18] = 100180-50 = 100130 > stop 100000 e < fechamento 100250
    assert dec["acao"] == "mover_stop" and dec["novo_stop"] == 100130.0
    pos["stop"] = 100200.0                    # stop ja acima do trailing: nunca recua
    assert decisao_gestao(None, ctx, dia, g, pos)[0]["acao"] == "manter"
    z, _ = decisao_gestao({"g_acao": {"c": "zerar", "p": {"zerar": 0.8}, "k": 1}}, ctx, dia, g, pos)
    assert z["acao"] == "zerar"


def test_decide_vela_fases():
    ctx, dia = ctx_dia()
    s = SimpleNamespace(pos=None, pend=dict(x=1))
    assert decide_vela(ctx, dia, 20, s, resp(), None, 0.5)[0]["acao"] == "manter"          # ordem pendente: aguarda
    s = SimpleNamespace(pos=None, pend=None)
    assert decide_vela(ctx, dia, 20, s, None, None, 0.5)[0]["acao"] == "ficar_fora"        # falha de API: fora
    assert decide_vela(ctx, dia, 20, s, resp(), None, 0.5)[0]["acao"] == "comprar_limite"
