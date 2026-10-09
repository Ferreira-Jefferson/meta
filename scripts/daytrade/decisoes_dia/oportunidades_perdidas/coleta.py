"""Coleta nos 50 dias: trades do v2, TODAS as candidatas bloqueadas (com causa, estado e simulacao isolada) e o teto de hindsight."""
import json, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd
sys.path.insert(0, ".")
import motor, robo_v2, robo
from base import CUSTO, RS_PT, FURA, VALIDADE

STOP_MAX = 600.0   # R$120 / 0,20


def teto_dia(m1d, fim, tempos):
    """Hindsight: para cada instante de decisao (fecho de M15) e lado, ordem limitada no fechamento, stop <= 600 pts,
    saida no melhor extremo antes do stop. Devolve lista de ops (t_sinal, t_ent, t_sai, pts) e o DP de ate 3 ops / ilimitado."""
    idx = m1d.index; hi = m1d.high.values; lo = m1d.low.values; cl = m1d.close.values
    ops = []
    for t in tempos:
        i0 = idx.searchsorted(t)
        if i0 >= len(idx) or t > fim: continue
        p = float(m1d.close.values[idx.searchsorted(t) - 1]) if i0 > 0 else float(cl[0])
        for lado in ("compra", "venda"):
            c = lado == "compra"
            ent = None
            for k in range(i0, len(idx)):
                if idx[k] >= t + VALIDADE or idx[k] > fim: break
                if (lo[k] <= p - FURA) if c else (hi[k] >= p + FURA): ent = k; break
            if ent is None: continue
            best, bk = -1e9, None
            for k in range(ent + 1, len(idx)):
                if idx[k] > fim: break
                if (lo[k] <= p - STOP_MAX) if c else (hi[k] >= p + STOP_MAX): break
                g = ((hi[k] - FURA - p) if c else (p - (lo[k] + FURA))) - CUSTO
                if g > best: best, bk = g, k
            if bk is not None and best > 0:
                ops.append((t, idx[ent], idx[bk], best, lado))
    ops.sort(key=lambda x: x[2])
    return ops


def dp(ops, kmax):
    # max soma de ate kmax ops sem sobreposicao (proxima ordem so depois da saida anterior)
    n = len(ops)
    ops = sorted(ops, key=lambda x: x[2])
    ends = [o[2] for o in ops]
    import bisect
    prev = []
    for o in ops:
        prev.append(bisect.bisect_right(ends, o[0]) - 1)   # ultima op cuja saida <= t_sinal
    kmax = min(kmax, n)
    F = [[0.0] * (kmax + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for k in range(1, kmax + 1):
            a = F[i - 1][k]
            b = ops[i - 1][3] + F[prev[i - 1] + 1][k - 1]
            F[i][k] = max(a, b)
    return F[n][kmax] * RS_PT if n else 0.0


def um(args):
    dia, tipo, ciclo = args
    fz, nf = robo_v2.monta_v2()
    tr, cands, m1d, fim = motor.roda(dia, fz, nf, log_cand=True)
    feitos = [x for x in tr if x.t_ent is not None]
    out_c = []
    for c in cands:
        if c["causa"] == "outra_mesma_vela": continue
        r = motor.sim_cand(dia, c, m1d, fim)
        out_c.append(dict(dia=dia, t=str(c["t"]), regra=c["regra"], lado=c["lado"], causa=c["causa"], vetos=c["vetos"],
                          est=c["est"], n_ops=c["n_ops"], pos_lado=c["pos_lado"], pos_enchida=c["pos_enchida"], **r))
    tempos = [t for t in pd.date_range(m1d.index[0].normalize() + pd.Timedelta(hours=9, minutes=15), fim, freq="15min")]
    ops = teto_dia(m1d, fim, tempos)
    h = m1d
    return dict(dia=dia, tipo=tipo, ciclo=ciclo, brl=motor.brl(tr), ops=len(feitos),
                trades=[dict(fonte=x.fonte, lado=x.lado, t_sinal=str(x.t_sinal), ent=str(x.t_ent), brl=round(x.brl, 2), motivo=x.motivo, t_sai=str(x.t_sai)) for x in feitos],
                cands=out_c,
                teto1=round(dp(ops, 1), 2), teto3=round(dp(ops, 3), 2), teto_inf=round(dp(ops, 99), 2),
                n_oracle=len(ops), ef=float(robo.eficiencia(dia)),
                rng_pts=float(h.high.max() - h.low.min()),
                melhor=[(str(o[0].time()), str(o[1].time()), str(o[2].time()), round(o[3], 0)) for o in sorted(ops, key=lambda x: -x[3])[:2]])


def main():
    res = []
    with ProcessPoolExecutor(10) as ex:
        fut = [ex.submit(um, a) for a in motor.dias50()]
        for f in as_completed(fut):
            r = f.result(); res.append(r)
            print(r["dia"], r["tipo"], r["brl"], r["ops"], len(r["cands"]), r["teto3"], flush=True)
    res.sort(key=lambda r: r["dia"])
    json.dump(res, open("coleta.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
