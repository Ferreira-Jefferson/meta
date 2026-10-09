"""Avaliacao em paralelo (ProcessPoolExecutor, submit/as_completed) com cache em disco. Chave = (ids ordenados, dia)."""
import sys, json, pickle, os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd

C3 = Path(__file__).resolve().parent
sys.path.insert(0, str(C3))
import cfg3, base, robo

CACHE = C3 / "cache.pkl"


def _um(args):
    ids, dia = args
    c = cfg3.monta(list(ids))
    return ids, dia, cfg3.resultado_dia(dia, c)


def carrega_cache():
    if CACHE.exists():
        return pickle.load(open(CACHE, "rb"))
    return {}


def avalia(configs, dias, workers=11, verbose=True):
    """configs: lista de listas de ids. Devolve {tuple(ids): {dia: resultado}}."""
    cache = carrega_cache()
    chaves = [tuple(sorted(c, key=cfg3.ORDEM.index)) for c in configs]
    falta = [(k, d) for k in dict.fromkeys(chaves) for d in dias if (k, d) not in cache]
    if falta:
        with ProcessPoolExecutor(workers) as ex:
            fut = [ex.submit(_um, a) for a in falta]
            for i, f in enumerate(as_completed(fut)):
                k, d, r = f.result(); cache[(k, d)] = r
                if verbose and i % 200 == 0: print(f"  {i}/{len(falta)}", flush=True)
        pickle.dump(cache, open(CACHE, "wb"))
    return {k: {d: cache[(k, d)] for d in dias} for k in dict.fromkeys(chaves)}


def eficiencia_todos(ini="2022-01-01", fim="2025-09-30"):
    m1 = base.m1_tudo()
    dias = pd.Series(m1.index.normalize().unique())
    dias = dias[(dias >= ini) & (dias <= fim)]
    f = C3 / "ef_todos.json"
    if f.exists():
        return json.load(open(f))
    out = {}
    g = m1.groupby(m1.index.normalize())
    for d, mm in g:
        if d < pd.Timestamp(ini) or d > pd.Timestamp(fim) or len(mm) < 300: continue
        b = base._m15(mm)
        rng = float((b.high - b.low).sum())
        out[str(d.date())] = abs(b.close.iloc[-1] - b.open.iloc[0]) / rng if rng > 0 else 0.0
    json.dump(out, open(f, "w"))
    return out


def estrato(ef, lim_bom=0.25, lim_ruim=0.15):
    return "bom" if ef >= lim_bom else ("ruim" if ef < lim_ruim else "int")
