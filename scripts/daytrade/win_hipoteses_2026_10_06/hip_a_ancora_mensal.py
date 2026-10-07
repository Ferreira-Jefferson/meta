"""Hipotese A: media/VWAP/abertura ancorada no 1o pregao do mes como regime de lado."""
import importlib.util as u, sys, json, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
KIT = AQUI.parent / "win_melhor_kit.py"

def _kit():
    s = u.spec_from_file_location("kit", KIT); k = u.module_from_spec(s); s.loader.exec_module(k); return k

def ancora(seg, tipo):
    """Serie ancorada no 1o pregao do mes DENTRO do contrato (max(inicio mes, inicio seg)).
    Usa so' dados ate o fechamento da barra t (acumulados)."""
    mes = seg.index.to_period("M")
    c = seg.c; g = c.groupby(mes)
    if tipo == "media":
        return g.cumsum() / (g.cumcount() + 1)
    if tipo == "vwap":
        tp = (seg.h + seg.l + seg.c) / 3; v = seg.vol.astype(float).clip(lower=1)
        return (tp * v).groupby(mes).cumsum() / v.groupby(mes).cumsum()
    if tipo == "abertura":
        return seg.o.groupby(mes).transform("first")

def atr14(seg):
    pc = seg.c.shift(1)
    tr = pd.concat([seg.h - seg.l, (seg.h - pc).abs(), (seg.l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(14, min_periods=1).mean()

def regime(seg, v):
    """+1 compras, -1 vendas, 0 ambos."""
    a = ancora(seg, v["anc"]); mes = seg.index.to_period("M")
    if v["regra"] == "pos":
        dist = seg.c - a; band = v["k"] * atr14(seg)
        r = np.where(dist > band, 1, np.where(dist < -band, -1, 0)) if v["k"] > 0 else np.sign(dist).astype(int).values
        r = pd.Series(r, index=seg.index)
    else:  # inclinacao: N barras, nao cruza o mes (a ancora reinicia) -> exige N barras no mes
        d = a - a.shift(v["N"])
        ok = (seg.groupby(mes).cumcount() >= v["N"])
        r = pd.Series(np.where(ok, np.sign(d), 0).astype(int), index=seg.index)
    D = v["D"]
    if D > 0 or v.get("prev"):
        dia = pd.Series(seg.index.normalize(), index=seg.index)
        rank = dia.groupby(mes).transform(lambda s: s.rank(method="dense")).values
        young = rank <= D
        if v.get("prev"):
            ult = r.groupby(mes).last()           # regime na ultima barra de cada mes
            prev = pd.Series(mes, index=seg.index).map(lambda p: ult.get(p - 1, 0)).astype(int)
            r = pd.Series(np.where(young, prev.values, r.values), index=seg.index)
        else:
            r = pd.Series(np.where(young, 0, r.values), index=seg.index)
    return r.values

def hooks(v):
    if v["nome"] == "baseline":
        return {}
    if v["nome"] == "ORACULO":
        def dirmes(seg):
            mes = seg.index.to_period("M")
            fim = seg.c.groupby(mes).transform("last"); ini = seg.o.groupby(mes).transform("first")
            return np.sign(fim - ini).values
        return dict(permite_long=lambda s: dirmes(s) >= 0, permite_short=lambda s: dirmes(s) <= 0)
    return dict(permite_long=lambda s: regime(s, v) >= 0, permite_short=lambda s: regime(s, v) <= 0)

def rodar(v):
    kit = _kit(); m5 = kit.carregar_m5()
    res = kit.rodar_meses(m5, **hooks(v))
    liq = [float(r["eq"].iloc[-1] - kit.b.CAP0) for r in res]
    return v["nome"], v, kit.resumo(res), liq, [r["janela"] for r in res], \
        (kit.tabela_meses(res) if v.get("tabela") else None)

def variantes():
    V = [dict(nome="baseline")]
    for anc in ("media", "vwap", "abertura"):
        for k in (0, .5, 1, 2):
            for D in (0, 2, 5):
                V.append(dict(nome=f"{anc}|pos|k{k}|D{D}", anc=anc, regra="pos", k=k, D=D))
    for anc in ("media", "vwap"):
        for N in (12, 48, 96):
            for D in (0, 2, 5):
                V.append(dict(nome=f"{anc}|incl|N{N}|D{D}", anc=anc, regra="incl", N=N, D=D, k=0))
    for anc in ("media", "vwap", "abertura"):
        for k in (0, 1):
            V.append(dict(nome=f"{anc}|pos|k{k}|D5|mesant", anc=anc, regra="pos", k=k, D=5, prev=True))
    V.append(dict(nome="ORACULO"))
    return V

if __name__ == "__main__":
    V = variantes(); print(f"variantes: {len(V)}", flush=True)
    out = {}; t0 = time.time()
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(rodar, v) for v in V]
        for f in as_completed(fs):
            nome, v, r, liq, jan, _ = f.result(); out[nome] = dict(v=v, r=r, liq=liq, jan=jan)
            print(f"{nome:32s} liq={r['liquido_total']:9.2f} jan+={r['janelas_pos']} pior={r['pior_janela']:8.2f} "
                  f"PF={r['PF']} tr={r['trades']} ({time.time()-t0:.0f}s)", flush=True)
    json.dump(out, open(AQUI / "hip_a_resultados.json", "w"))
