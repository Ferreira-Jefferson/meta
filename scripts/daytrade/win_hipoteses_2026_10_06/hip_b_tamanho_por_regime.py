"""Hipotese B: tamanho de posicao conforme o regime do mes (WIN, MELHOR ATUAL).
Detectores (tempo real, so' ate c[t]): 'vwap' = c > VWAP ancorada no 1o pregao do mes
(preco tipico (h+l+c)/3 x vol, ancora = max(inicio do mes, inicio do seg)); 'abert' = c > abertura
do mes (1a o do mes no seg). 'oraculo' = sinal de (c final - o inicial) do mes: TETO, usa futuro.
Variante = (detector, a_favor, contra). Hook de qtd; o motor reduz pelo caixa."""
import sys, importlib.util as u
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
_s = u.spec_from_file_location("kit", AQUI.parent / "win_melhor_kit.py")
kit = u.module_from_spec(_s); _s.loader.exec_module(kit)


def regime(seg, det):
    mes = seg.index.to_period("M")
    out = np.zeros(len(seg), int)
    for m in pd.unique(mes):
        ix = np.where(mes == m)[0]
        g = seg.iloc[ix]
        if det == "vwap":
            tp = (g.h + g.l + g.c) / 3
            v = g.vol.replace(0, np.nan).fillna(1.0)
            ref = ((tp * v).cumsum() / v.cumsum()).values
        elif det == "abert":
            ref = np.full(len(g), g.o.iloc[0])
        else:  # oraculo
            ref = np.full(len(g), g.o.iloc[0]); 
            out[ix] = 1 if g.c.iloc[-1] > g.o.iloc[0] else -1
            continue
        out[ix] = np.where(g.c.values > ref, 1, -1)
    return out


def rodar(spec):
    det, fav, con = spec
    m5 = kit.carregar_m5()
    if det == "base":
        res = kit.rodar_meses(m5)
    else:
        ql = lambda s: np.where(regime(s, det) == 1, fav, con)
        qs = lambda s: np.where(regime(s, det) == -1, fav, con)
        res = kit.rodar_meses(m5, qtd_long=ql, qtd_short=qs)
    return spec, metricas(res), [(r["janela"], r["eq"].iloc[-1] - kit.b.CAP0, r["mercado_pts"],
            r["trades"].pnl[r["trades"].lado == 1].sum(), r["trades"].pnl[r["trades"].lado == -1].sum(),
            len(r["trades"]), float(r["eq"].min())) for r in res]


def seq_perdas(res):
    pior = 0.0
    for r in res:
        cur = 0.0
        for p in r["trades"].pnl:
            cur = cur + p if p < 0 else 0.0
            pior = min(pior, cur)
    return pior


def metricas(res):
    m = kit.resumo(res)
    mc = [float(r["eq"].min()) for r in res]
    m["jan_cx<250"] = sum(x < 250 for x in mc)
    m["jan_cx<100"] = sum(x < 100 for x in mc)
    m["seq_perdas_R$"] = round(seq_perdas(res), 2)
    return m


if __name__ == "__main__":
    specs = [("base", 1, 1)]
    for det in ("vwap", "abert", "oraculo"):
        for fav in (1, 2, 3, 4):
            for con in (0, 1):
                if fav == 1 and con == 1:
                    continue  # = baseline
                specs.append((det, fav, con))
    print(f"variantes (incl. baseline): {len(specs)}", flush=True)
    R = {}
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(rodar, s) for s in specs]
        for f in as_completed(fs):
            s, m, jan = f.result(); R[s] = (m, jan)
            print(s, m, flush=True)
    import pickle; pickle.dump(R, open(AQUI / "hip_b_res.pkl", "wb"))
