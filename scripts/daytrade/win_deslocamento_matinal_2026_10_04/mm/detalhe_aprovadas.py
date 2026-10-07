"""Metricas detalhadas BASE x A_e10 x S15 (P2) na IS e na OOS, e o que cada filtro cortou."""
import json, re
import numpy as np

def celula(texto):
    return texto.split()[0]

def carrega(arq):
    out = {}
    for r in json.load(open(arq, encoding="utf-8")):
        if r["premissa"] != "P2":
            continue
        c = celula(r["texto"])
        if c in ("BASE", "A_e10", "S15"):
            out[c] = r["trades"]
    return out

def dd(pnls):
    eq = np.cumsum(pnls); pico = np.maximum.accumulate(np.concatenate([[0], eq]))[1:]
    return float((pico - eq).max())

def seq_perdas(p):
    m = c = 0
    for v in p:
        c = c + 1 if v < 0 else 0; m = max(m, c)
    return m

def metr(t):
    p = np.array([x["pnl"] for x in t]); g = p[p > 0]; l = p[p < 0]
    stops = [x for x in t if x["reason"] == "STOP"]; fl = [x for x in t if x["reason"] != "STOP"]
    md = dd(p)
    return dict(n=len(p), liq=p.sum(), rs_op=p.mean(), win=100 * len(g) / len(p),
                ganho_med=g.mean(), perda_med=l.mean(), payoff=g.mean() / -l.mean(),
                fl_lucro=g.sum() / -l.sum(), stops=len(stops), stop_rs=sum(x["pnl"] for x in stops),
                flat=len(fl), flat_win=100 * sum(x["pnl"] > 0 for x in fl) / max(len(fl), 1),
                flat_rs=sum(x["pnl"] for x in fl), maxdd=md, fr=p.sum() / md, seq=seq_perdas(p))

def cortados(base, filt):
    k = {x["entry_ts"][:10] for x in filt}
    c = [x for x in base if x["entry_ts"][:10] not in k]
    p = np.array([x["pnl"] for x in c])
    return len(c), p.sum(), (100 * (p > 0).mean() if len(p) else 0), sum(x["reason"] == "STOP" for x in c)

for jan, arq in (("IS 2021-24", "saida_IS.json"), ("OOS 2025-26", "saida_OOS.json")):
    d = carrega(arq)
    print(f"\n## {jan}")
    cols = ["n", "liq", "rs_op", "win", "ganho_med", "perda_med", "payoff", "fl_lucro", "stops", "stop_rs", "flat", "flat_win", "flat_rs", "maxdd", "fr", "seq"]
    print("|celula|" + "|".join(cols) + "|cortados n|cortados R$|cortados win%|cortados stops|")
    for c in ("BASE", "A_e10", "S15"):
        if c not in d: continue
        m = metr(d[c]); cn = cortados(d["BASE"], d[c]) if c != "BASE" else (0, 0, 0, 0)
        print(f"|{c}|" + "|".join(f"{m[k]:.2f}" for k in cols) + f"|{cn[0]}|{cn[1]:.1f}|{cn[2]:.1f}|{cn[3]}|")
