"""Coleta: entradas do robo_v2 (enchidas) nos 50 dias + estado na entrada + grade de gestoes (1 contrato).
Cada entrada e simulada ISOLADA (mesma entrada e mesmo instante de fill; so a saida muda)."""
import json, sys, itertools
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd
AQ = Path(__file__).resolve().parent; PAI = AQ.parent
sys.path.insert(0, str(PAI))
import base, robo, robo_v2
from base import FURA, CUSTO, RS_PT

STOPS = [0.75, 1, 1.5, 2]; ALVOS = [0.75, 1, 1.5, 2, 3, None]
TRAILS = ["nenhum", "be1", "t2", "t4", "t8"]
RISCO_MAX_PTS = 120 / RS_PT   # R$120/contrato = 600 pts
GRADE = [(s, a, t) for s in STOPS for a in ALVOS for t in TRAILS]


def sim(m1d, m15all, fim, lado, preco, t_ent, atr, sk, ak, tr):
    c = lado == "compra"; sg = 1 if c else -1
    dist = min(sk * atr, RISCO_MAX_PTS)
    stop = preco - sg * dist
    alvo = None if ak is None else preco + sg * ak * atr
    idx = m1d.index; i0 = idx.get_loc(t_ent) + 1
    H = m1d.high.values; L = m1d.low.values; O = m1d.open.values; C = m1d.close.values
    best = preco
    for i in range(i0, len(idx)):
        ts = idx[i]
        if ts.minute % 15 == 0 and i > i0 - 0:
            # gerir no fechamento da M15 que terminou em ts (barras fechadas ate ts)
            if tr == "be1":
                if (best - preco) * sg >= atr:
                    if c and preco > stop: stop = preco
                    if (not c) and preco < stop: stop = preco
            elif tr != "nenhum":
                n = int(tr[1:])
                bars = m15all[m15all.index < ts].iloc[-n:]
                ns = bars.low.min() if c else bars.high.max()
                if c and ns > stop: stop = ns
                if (not c) and ns < stop: stop = ns
        bs = (L[i] <= stop) if c else (H[i] >= stop)
        ba = alvo is not None and ((H[i] >= alvo + FURA) if c else (L[i] <= alvo - FURA))
        if bs:
            px = min(O[i], stop) if c else max(O[i], stop); return (px - preco) * sg - CUSTO
        if ba:
            return (alvo - preco) * sg - CUSTO
        if c: best = max(best, H[i])
        else: best = min(best, L[i])
        if ts >= fim:
            return (C[i] - preco) * sg - CUSTO
    return (C[-1] - preco) * sg - CUSTO


def estado(ctx, lado, atr):
    h = ctx.hoje; n = len(h)
    op = float(h.open.iloc[0]); cl = float(h.close.iloc[-1])
    rng = float((h.high - h.low).sum())
    ef = abs(cl - op) / rng if rng > 0 else 0.0
    r4 = float((h.high - h.low).iloc[-4:].mean()) / atr
    # volume relativo por horario (hist) e ultimas 4 vs media do historico do mesmo horario
    m15 = ctx.m15; hist = m15[m15.dia < h.dia.iloc[0]]
    tod = hist.groupby([hist.index.hour, hist.index.minute]).vol.mean()
    def rel(k):
        ix = h.index[-k:]; v = h.vol.iloc[-k:].values
        ref = np.array([tod.get((a.hour, a.minute), np.nan) for a in ix])
        return float(np.nansum(v) / np.nansum(ref)) if np.nansum(ref) > 0 else np.nan
    m1h = ctx.m1[ctx.m1.index.normalize() == h.dia.iloc[0]]
    tp = (m1h.high + m1h.low + m1h.close) / 3
    vw = float((tp * m1h.real_volume).sum() / m1h.real_volume.sum()) if m1h.real_volume.sum() > 0 else cl
    ih = int(np.argmax(h.high.values)); il = int(np.argmin(h.low.values))
    leg = (cl - float(h.low.min())) / atr if ih >= il else -(float(h.high.max()) - cl) / atr
    sg = 1 if lado == "compra" else -1
    return dict(ef=ef, vol4=r4, volrel1=rel(1), volrel4=rel(4), hora=ctx.t.hour + ctx.t.minute / 60,
                d_vwap=(cl - vw) / atr * sg, d_open=(cl - op) / atr * sg, perna=leg * sg,
                a_favor=int(np.sign(cl - op) == sg), ef_bars=n)


def natureza(nome):
    s = nome.lower()
    if any(k in s for k in ("rompimento", "expansao", "breakout", "inversao")): return "rompimento"
    if any(k in s for k in ("fade", "falha", "spring", "faixa", "gap", "retorno", "esticada")): return "reversao"
    if any(k in s for k in ("recuo", "tendencia", "pullback")): return "continuacao"
    return "outra"


def um(dia):
    fz, nf = robo_v2.monta_v2()
    tr, log, _ = robo_v2.roda_v2(dia, fz, nf)
    ok = [x for x in tr if x.t_ent is not None]
    if not ok: return dia, []
    ctxs = {t: c for t, c in base.contextos(dia) if t in {x.t_sinal for x in ok}}
    m1 = base.carrega(dia, 0); d = pd.Timestamp(dia); m1d = m1[m1.index.normalize() == d]
    fim = m1d.index[m1d["ultima_continua"]].max() if m1d["ultima_continua"].any() else m1d.index.max()
    m15all = base._m15(base.carrega(dia, 40))
    out = []
    for x in ok:
        ctx = ctxs[x.t_sinal]; atr = ctx.atr15
        st = estado(ctx, x.lado, atr)
        grade = [sim(m1d, m15all, fim, x.lado, x.preco, x.t_ent, atr, *g) for g in GRADE]
        out.append(dict(dia=dia, fonte=x.fonte, nat=natureza(x.fonte), lado=x.lado, contratos=x.contratos,
                        sinal=str(x.t_sinal.time()), atr=atr, atual=x.pts, motivo=x.motivo, estado=st,
                        grade=grade))
    return dia, out


def main():
    du = json.load(open(PAI / "dias_usados.json"))
    ciclo = {}
    for d in du["ciclo0"]["dias"]: ciclo[d] = 0
    for x in du["ciclo1"]["dias"]: ciclo[x["dia"]] = 1
    for x in du["ciclo2"]["dias"]: ciclo[x["dia"]] = 2
    assert len(ciclo) == 50
    res = []
    with ProcessPoolExecutor(6) as ex:
        fut = [ex.submit(um, d) for d in ciclo]
        for f in as_completed(fut):
            d, o = f.result()
            for r in o: r["ciclo"] = ciclo[d]
            res += o; print(d, len(o), flush=True)
    res.sort(key=lambda r: (r["dia"], r["sinal"]))
    json.dump(dict(grade=GRADE, trades=res), open(AQ / "coleta.json", "w"), default=float)
    print("trades", len(res))

if __name__ == "__main__":
    main()
