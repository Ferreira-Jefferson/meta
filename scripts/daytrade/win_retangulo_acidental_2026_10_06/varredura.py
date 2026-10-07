"""Varredura da logica acidental (retangulo M1 -> limite no meio -> segura ate' 18:20), WINV26.

Escolha SO' por setembro/2026 (refino); agosto (12-31) so' confere. Cada celula vem com o
nulo invertido (mesmo gatilho, lado oposto) ao lado.
Uso: python varredura.py etapa1|etapa2
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace

import pandas as pd

from sim import Cfg, carregar, resumo, simula

PER = {"set": ("2026-09-01", "2026-10-01"), "ago": ("2026-08-12", "2026-09-01")}
CUSTO = 2.0  # R$ por operacao (corretagem/emolumentos + 1 tick de deslize na zeragem), 1 contrato
_D = None


def _ini():
    global _D
    _D = carregar("WINV26", "2026-08-12", "2026-10-01")


def _roda(nome, cfg):
    out = {"nome": nome}
    for tag, c in (("", cfg), ("nulo_", replace(cfg, inverte=True))):
        t = simula(_D, c)
        for p, (a, b) in PER.items():
            x = t[(pd.to_datetime(t.dia) >= a) & (pd.to_datetime(t.dia) < b)] if len(t) else t
            r = resumo(x, CUSTO)
            out[f"{tag}{p}_rs"] = r["rs"]
            if not tag:
                out[f"{p}_tr"] = r["trades"]; out[f"{p}_win"] = r["win"]
                out[f"{p}_pf"] = r["pf"]; out[f"{p}_dd"] = r["dd"]; out[f"{p}_pior"] = r["pior_dia"]
    return out


def etapa1():
    base = Cfg(alvo_frac=None, stop_frac=None)
    for h, w, tol in itertools.product([0, 11, 12, 13, 14, 15, 16], [15, 20, 25, 30, 40], [0.15, 0.20, 0.28, 0.35]):
        yield f"h{h:02d} W{w} tol{tol}", replace(base, primeira_entrada=h * 60, janela=w, tol=tol)


def etapa2():
    h = int(sys.argv[2]) if len(sys.argv) > 2 else 13
    base = Cfg(primeira_entrada=h * 60)
    stops = [("sem", dict(stop_frac=None)), ("1L", dict(stop_frac=1.0)), ("2L", dict(stop_frac=2.0)),
             ("3L", dict(stop_frac=3.0)), ("4,5L", dict(stop_frac=4.5)), ("300p", dict(stop_frac=None, stop_pts=300)),
             ("500p", dict(stop_frac=None, stop_pts=500)), ("800p", dict(stop_frac=None, stop_pts=800)),
             ("1200p", dict(stop_frac=None, stop_pts=1200))]
    alvos = [("sem", dict(alvo_frac=None)), ("1L", dict(alvo_frac=1.0)), ("2L", dict(alvo_frac=2.0)),
             ("3L", dict(alvo_frac=3.0)), ("4,5L", dict(alvo_frac=4.5)), ("6L", dict(alvo_frac=6.0))]
    for (sn, s), (an, a), w in itertools.product(stops, alvos, [20, 25, 30]):
        yield f"h{h} W{w} stop {sn} alvo {an}", replace(base, janela=w, **s, **a)


if __name__ == "__main__":
    gen = {"etapa1": etapa1, "etapa2": etapa2}[sys.argv[1]]
    rows = []
    with ProcessPoolExecutor(max_workers=10, initializer=_ini) as ex:
        futs = [ex.submit(_roda, n, c) for n, c in gen()]
        for f in as_completed(futs):
            r = f.result(); rows.append(r)
            print(f"{r['nome']:32s} SET {r['set_rs']:8.1f} (nulo {r['nulo_set_rs']:8.1f}, {r['set_tr']} op)"
                  f"  AGO {r['ago_rs']:8.1f} (nulo {r['nulo_ago_rs']:8.1f}, {r['ago_tr']} op)", flush=True)
    df = pd.DataFrame(rows)
    nome_arq = "_".join(sys.argv[1:])
    df.to_csv(f"{nome_arq}.csv", index=False)
