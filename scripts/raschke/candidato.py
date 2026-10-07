"""Robustez do candidato: bootstrap do expR por periodo, sensibilidade a deslize e capital.

Uso: python -m scripts.raschke.candidato WDO H1 ANTI "modo=stoch;recuo=1" "eod alvo=None trail=0"
"""
from __future__ import annotations
import sys
import numpy as np
from . import dados, nucleo, varredura as v
from .nucleo import Saida, Custo


def trades_do(ativo, tf, setup, params, saida, slip_ticks=1.0):
    b, idx, custo, _ = v._carregar(ativo, tf)
    fn, _, _ = v.GRADES[setup]
    kw = {}
    for kv in params.split(";"):
        k, val = kv.split("=")
        kw[k] = val if val.isalpha() or k == "modo" else (float(val) if "." in val else int(val))
    tick_real = custo.tick
    ordens = fn(b, tick_real, **kw)
    sd = dict(v.grade_saidas(b.intraday, setup))[saida]
    c2 = Custo(tick=custo.tick * slip_ticks, valor_ponto=custo.valor_ponto, qty=custo.qty, fee_brl=custo.fee_brl,
               pct_lado=custo.pct_lado, risco_min_ticks=custo.risco_min_ticks / slip_ticks)
    tr = nucleo.simular(b, ordens, sd, c2 if slip_ticks != 1.0 else custo, um_por_dia=setup in ("PIN", "8020"))
    return tr, idx


def boot(r, n=5000, seed=0):
    rng = np.random.default_rng(seed)
    m = np.array([rng.choice(r, len(r)).mean() for _ in range(n)])
    return np.percentile(m, [2.5, 97.5])


if __name__ == "__main__":
    ativo, tf, setup, params, saida = sys.argv[1:6]
    for slip in (1.0, 2.0):
        tr, idx = trades_do(ativo, tf, setup, params, saida, slip)
        corte = np.datetime64(dados.CORTE_OOS)
        for nome, sel in (("IS", lambda t: np.datetime64(idx[t.i_entrada]) < corte), ("OOS", lambda t: np.datetime64(idx[t.i_entrada]) >= corte)):
            ts = [t for t in tr if sel(t)]
            r = np.array([t.r for t in ts]); pnl = np.array([t.pnl_brl for t in ts])
            lo, hi = boot(r)
            eq = np.cumsum(pnl); dd = (np.maximum.accumulate(np.concatenate([[0], eq])) - np.concatenate([[0], eq])).max()
            print(f"slip={slip:.0f}t {nome:3s} n={len(ts):4d} expR={r.mean():+.3f} IC95[{lo:+.3f};{hi:+.3f}] win={(pnl>0).mean():.1%} "
                  f"liq=R${pnl.sum():,.0f} maxDD=R${dd:,.0f} pior_trade=R${pnl.min():,.0f}")
