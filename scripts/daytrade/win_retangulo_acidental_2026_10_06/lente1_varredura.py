"""Lente 1: horario de entrada e parametros do detector (sem stop/alvo, segura ate' 18:20).
Uso: python lente1_varredura.py um|grade|ctrl|final
Escolha so' por setembro; agosto so' confere. Nulo invertido ao lado de toda linha.
"""
from __future__ import annotations
import itertools, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import numpy as np, pandas as pd
from sim import Cfg, carregar, resumo, simula, PONTO_RS

PER = {"set": ("2026-09-01", "2026-10-01"), "ago": ("2026-08-12", "2026-09-01")}
CUSTO = 2.0
BASE = Cfg(alvo_frac=None, stop_frac=None)
_D = {}

def _ini():
    _D[1] = carregar("WINV26", "2026-08-12", "2026-10-01")
    _D[5] = carregar("WINV26", "2026-08-12", "2026-10-01", tf_min=5)

def _cut(t, a, b):
    return t[(pd.to_datetime(t.dia) >= a) & (pd.to_datetime(t.dia) < b)] if len(t) else t

def _roda(nome, cfg):
    d = _D[cfg.tf_min]
    out = {"nome": nome, "janela": cfg.janela, "tol": cfg.tol, "h": cfg.primeira_entrada // 60 + (cfg.primeira_entrada % 60) / 60,
           "ult": cfg.ultima_entrada, "rearma": cfg.rearma, "tf": cfg.tf_min, "fill": cfg.fill}
    for tag, c in (("", cfg), ("nulo_", replace(cfg, inverte=True))):
        t = simula(d, c)
        for p, (a, b) in PER.items():
            r = resumo(_cut(t, a, b), CUSTO)
            out[f"{tag}{p}_rs"] = r["rs"]
            if not tag:
                out.update({f"{p}_tr": r["trades"], f"{p}_win": r["win"], f"{p}_pf": r["pf"], f"{p}_dd": r["dd"], f"{p}_pior": r["pior_dia"]})
    return out

# ---- controle sem retangulo: 1 entrada/dia no fechamento da barra em hora fixa
def _ctrl(nome, hora_min, lado_modo, W=25):
    d = _D[1]; rows = []
    for dia, g in d.groupby(d.index.date):
        m = (g.index.hour * 60 + g.index.minute).to_numpy()
        idx = np.flatnonzero(m >= hora_min)
        if len(idx) == 0 or idx[0] < W: continue
        i = idx[0]
        z = np.flatnonzero(m >= 18 * 60 + 20)
        if len(z) == 0 or z[0] <= i: continue
        w = g.iloc[i - W + 1:i + 1]
        meio = (np.quantile(w.high, .9) + np.quantile(w.low, .1)) / 2
        c = g.close.iloc[i]
        ent = round(c / 5) * 5
        saida = g.open.iloc[z[0]]
        if lado_modo == "meio": lado = 1 if c > meio else -1      # momentum (preco acima do meio => compra)
        elif lado_modo == "revert": lado = -1 if c > meio else 1  # reversao ao meio (como o EA)
        elif lado_modo == "long": lado = 1
        else: lado = -1
        rows.append(dict(dia=dia, pts=(saida - ent) * lado))
    t = pd.DataFrame(rows)
    out = {"nome": nome}
    for p, (a, b) in PER.items():
        x = _cut(t, a, b); r = resumo(x, CUSTO)
        out[f"{p}_rs"] = r["rs"]; out[f"{p}_tr"] = r["trades"]; out[f"{p}_win"] = r["win"]
        out[f"{p}_pf"] = r["pf"]; out[f"{p}_dd"] = r["dd"]; out[f"{p}_pior"] = r["pior_dia"]
        out[f"nulo_{p}_rs"] = -r["rs"] - 2 * CUSTO * r["trades"]
    return out

def um():
    h = lambda x: x * 60
    for v in [0, 600, 630, 660, 690, 720, 750, 780, 810, 840, 870, 900, 930, 960, 990]:
        yield f"primeira={v//60}:{v%60:02d}", replace(BASE, primeira_entrada=v)
    for v in [660, 720, 780, 840, 900, 960, 1020, 1080]:
        yield f"ultima={v//60}:{v%60:02d}", replace(BASE, ultima_entrada=v)
    for v in [10, 15, 20, 25, 30, 35, 40, 50]:
        yield f"janela={v}", replace(BASE, janela=v)
    for v in [0.10, 0.15, 0.20, 0.24, 0.28, 0.32, 0.36, 0.40]:
        yield f"tol={v}", replace(BASE, tol=v)
    for v in [True, False]:
        yield f"rearma={v}", replace(BASE, rearma=v)
    for v in [1, 3, 10, 30]:
        yield f"ttl={v}", replace(BASE, ttl=v)
    for w in [5, 8, 10, 15]:
        yield f"M5 janela={w}", replace(BASE, tf_min=5, janela=w, ttl=2)
    for w in [5, 8, 10]:
        for h_ in [660, 780, 900]:
            yield f"M5 janela={w} prim={h_//60}", replace(BASE, tf_min=5, janela=w, ttl=2, primeira_entrada=h_)

def grade():
    for h, w, tol, rea in itertools.product([0, 600, 660, 720, 780, 840, 900], [15, 20, 25, 30, 40], [0.15, 0.20, 0.28, 0.35], [True, False]):
        yield f"h{h//60}:{h%60:02d} W{w} tol{tol} rea{int(rea)}", replace(BASE, primeira_entrada=h, janela=w, tol=tol, rearma=rea)

def ctrl():
    for hm in [600, 630, 660, 690, 720, 780, 840, 900, 960]:
        for md in ["meio", "revert", "long", "short"]:
            yield f"ctrl {hm//60}:{hm%60:02d} {md}", hm, md

if __name__ == "__main__":
    st = sys.argv[1]; rows = []
    with ProcessPoolExecutor(max_workers=4, initializer=_ini) as ex:
        if st == "ctrl":
            futs = [ex.submit(_ctrl, n, hm, md) for n, hm, md in ctrl()]
        else:
            gen = {"um": um, "grade": grade}[st]
            futs = [ex.submit(_roda, n, c) for n, c in gen()]
        for f in as_completed(futs):
            r = f.result(); rows.append(r)
            print(f"{r['nome']:34s} SET {r['set_rs']:8.1f} (nulo {r['nulo_set_rs']:8.1f}, {r['set_tr']} op)  AGO {r['ago_rs']:8.1f} (nulo {r['nulo_ago_rs']:8.1f}, {r['ago_tr']} op)", flush=True)
    pd.DataFrame(rows).to_csv(f"lente1_{st}.csv", index=False)
