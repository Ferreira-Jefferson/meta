"""Calcula respostas (n x 2 lados) por pergunta e o alvo +-1 ATR por vela. Salva npz por periodo."""
import sys, time, numpy as np, pandas as pd
from bq_core import *
import catalogo as K

def alvo(b):
    """y_compra por vela: +1 ATR M15 antes de -1 ATR (barreiras a partir do fechamento), ate o fim do pregao; empate/fim = 0,5."""
    n = len(b); y = np.full(n, np.nan)
    H, L, C, A = b.high.to_numpy(), b.low.to_numpy(), b.close.to_numpy(), b.atr.to_numpy()
    d = b.dia.to_numpy(); starts = np.r_[0, np.where(d[1:] != d[:-1])[0] + 1, n]
    for s, e in zip(starts[:-1], starts[1:]):
        m = e - s
        for k in range(m - 1):
            i = s + k
            if not np.isfinite(A[i]) or A[i] <= 0: continue
            hu = np.where(H[i+1:e] >= C[i] + A[i])[0]; hd = np.where(L[i+1:e] <= C[i] - A[i])[0]
            u = hu[0] if len(hu) else 10**6; dn = hd[0] if len(hd) else 10**6
            y[i] = 1.0 if u < dn else (0.0 if dn < u else 0.5)
    return y

def run(per):
    t = time.time()
    b, V = vistas(per)
    Fs = {l: derive(V[l]) for l in (1, -1)}
    print(per, "features", round(time.time() - t), "s", flush=True)
    P = bancoC.preparar(per)
    ans = {}
    for r in K.R:
        cols = []
        for l in (1, -1):
            if r["id"] in K.EXTERNAS:
                g = P["gat"][r["id"]][l]; cols.append(np.asarray(g).astype(np.int8))
            else:
                x = r["fn"](Fs[l], dict(v=V[l])); cols.append(np.asarray(x, np.int8))
        ans[r["id"]] = np.stack(cols, 1)
    y = alvo(b)
    mins = b.index.hour * 60 + b.index.minute
    elig = (mins >= 570) & (mins <= 1005) & np.isfinite(y)
    np.savez_compressed(f"calc_{per}.npz", y=y, elig=elig, **{k: v for k, v in ans.items()},
                        _dia=b.dia.to_numpy().astype("datetime64[D]").astype(np.int64), _mins=mins.to_numpy(), _ad=V[1].ad.to_numpy(),
                        _close=b.close.to_numpy(), _high=b.high.to_numpy(), _low=b.low.to_numpy(), _atr=b.atr.to_numpy(), _open=b.open.to_numpy())
    print(per, "pronto", len(b), int(elig.sum()), round(time.time() - t), "s", flush=True)

if __name__ == "__main__":
    run(sys.argv[1])
