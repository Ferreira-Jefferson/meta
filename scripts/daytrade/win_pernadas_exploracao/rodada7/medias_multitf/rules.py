"""As 10 regras (familias) escolhidas pelo PLATO da descoberta jan-jun (grade x2), congeladas antes de abrir jul-ago."""
import grid

# (id, par, breach, trend, var, stop)  -- a celula central da familia: x=0.5, K=5, entrada no fechamento, ttl 10 min, conservador
FAMS = [
    ("R1", (10, 30), "f", "strict", "c", "x15"),
    ("R2", (10, 30), "fm", "strict", "c", "x5"),
    ("R3", (10, 30), "f", "strict", "c", "x5"),
    ("R4", (10, 30), "fm", "loose", "c", "x5"),
    ("R5", (5, 30), "fm", "strict", "c", "x15"),
    ("R6", (5, 30), "f", "strict", "c", "x15"),
    ("R7", (15, 60), "f", "loose", "c", "x15"),
    ("R8", (10, 30), "fm", "strict", "c", "x15"),
    ("R9", (5, 30), "f", "loose", "c", "e50h"),
    ("R10", (5, 15), "fms", "strict", "c", "x15"),   # controle: definicao literal do dono (M5 rompe as 3 medias, M15 alinhado)
]
STOPS = {"x5": dict(stop="x", N=5), "x15": dict(stop="x", N=15), "atr1.0": dict(stop="atr", Katr=1.0), "e50h": dict(stop="e50h")}
XS = (0.1, 0.25, 0.5, 1.0)
KS = (3, 5, 7.5)


def cell(fam, x=0.5, K=5, P=(9, 21, 50, "ema"), ttl=10, otim=False, tag=None):
    rid, (l, h), b, tr, v, sn = fam
    cfg = {**grid.REF_CFG, **dict(ltf=l, htf=h, breach=b, x=x, trend=tr, var=v, P=P)}
    geom = {**grid.REF_GEOM, **STOPS[sn], **dict(K=K, ttl=ttl, otim=otim)}
    return dict(axis=rid, value=tag or f"x{x}|K{K}|{P[0]}/{P[1]}/{P[2]}{P[3]}|ttl{ttl}", cfg=cfg, geom=geom)


def centre(fam, **kw):
    return cell(fam, 0.5, 5, **kw)


def family_cells(fam, **kw):
    return [cell(fam, x, K, **kw) for x in XS for K in KS]


def period_cells(fam):
    out = []
    for f in (7, 9, 11):
        for m in (19, 21, 24):
            for s in (40, 50, 60):
                out.append(cell(fam, P=(f, m, s, "ema"), tag=f"P{f}/{m}/{s}"))
    for f in (5, 6, 7, 8, 9, 10, 11, 12, 13, 15): out.append(cell(fam, P=(f, 21, 50, "ema"), tag=f"fast{f}"))
    for m in (15, 17, 19, 21, 24, 28, 30, 34, 40): out.append(cell(fam, P=(9, m, 50, "ema"), tag=f"mid{m}"))
    for s in (34, 40, 45, 50, 60, 72, 89, 100, 120): out.append(cell(fam, P=(9, 21, s, "ema"), tag=f"slow{s}"))
    out.append(cell(fam, P=(9, 21, 50, "sma"), tag="sma"))
    return out
