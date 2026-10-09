"""Validacao do ciclo 3: sorteio aleatorio simples de 20 dias novos; v1, v2, v3; pareado; nulo; caixa; negativos."""
import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import av, cfg3, an, base, robo
import robo_v3

C3 = cfg3.C3
RAIZ = cfg3.RAIZ
SEED = 20261016


def sorteia():
    ef = av.eficiencia_todos()
    usados = set(d for d, _ in cfg3.dias50())
    cand = sorted(d for d in ef if d not in usados)
    rng = np.random.default_rng(SEED)
    return sorted(rng.choice(cand, 20, replace=False).tolist()), len(cand), ef


def registra(dias, ef):
    p = RAIZ / "dias_usados.json"
    j = json.load(open(p))
    if "ciclo3" not in j:
        j["ciclo3"] = dict(seed=SEED, sorteio="aleatorio simples do IS 2022-01-01..2025-09-30 (>=300 barras), fora dos 50 usados",
                           dias=[dict(dia=d, tipo=av.estrato(ef[d]).replace("bom", "bom").replace("int", "intermediario"), ef=round(ef[d], 3)) for d in dias])
        json.dump(j, open(p, "w"), indent=1)


def _v1(dia):
    tr, log, _ = robo.roda_robo(dia)
    return dia, _res(tr), [dict(x) for x in log]


def _res(tr):
    ok = [x for x in tr if x.t_ent is not None]
    return dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok),
                trades=[dict(fonte=x.fonte, lado=x.lado, contratos=x.contratos, sinal=str(x.t_sinal.time()), ent=str(x.t_ent.time()),
                             sai=str(x.t_sai.time()), preco=x.preco, preco_sai=x.preco_sai, stop=x.stop_ini, alvo=x.alvo, motivo=x.motivo,
                             pts=round(x.pts, 1), brl=round(x.brl, 2)) for x in ok])


def _cfg(args):
    ids, dia = args
    c = cfg3.monta(list(ids))
    tr, log = cfg3.roda(dia, c)
    return dia, _res(tr), [dict(x) for x in log]


def estat(res, dias):
    v = np.array([res[d]["brl"] for d in dias])
    tr = [t for d in dias for t in res[d]["trades"]]
    gan = sum(t["brl"] for t in tr if t["brl"] > 0); per = -sum(t["brl"] for t in tr if t["brl"] < 0)
    return dict(total=round(float(v.sum()), 2), por_dia=round(float(v.mean()), 2), ops=len(tr),
                acerto=f"{sum(t['pts'] > 0 for t in tr)}/{len(tr)}", acerto_pct=round(100 * sum(t['pts'] > 0 for t in tr) / max(1, len(tr)), 1),
                fator_lucro=round(gan / per, 2) if per > 0 else float("inf"), pior_dia=round(float(v.min()), 2),
                melhor_dia=round(float(v.max()), 2), dias_pos=int((v > 0).sum()), dias_neg=int((v < 0).sum()), dias_zero=int((v == 0).sum()))


def pareado(a, b, n=10000, seed=1):
    d = a - b
    rng = np.random.default_rng(seed)
    bs = np.array([rng.choice(d, len(d), replace=True).mean() for _ in range(n)])
    sf = np.array([(d * rng.choice([-1, 1], len(d))).mean() for _ in range(n)])
    p = float((np.abs(sf) >= abs(d.mean()) - 1e-12).mean())
    return dict(delta_total=round(float(d.sum()), 2), delta_dia=round(float(d.mean()), 2),
                ic95=[round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)], p_signflip=round(p, 4),
                dias_melhores=int((d > 0.5).sum()), dias_piores=int((d < -0.5).sum()))


# ---------------------------------------------------------------- nulo
def _nulo_sim(m1d, fim, t_sinal, p, lado, dstop, dalvo):
    """Entrada limitada em p (fecha da vela), 45 min de validade, enche 10 pts alem; stop a mercado; alvo limitado (+10); fim zera. Devolve (brl, t_saida)."""
    c = lado == "compra"; sg = 1 if c else -1
    stop = p - sg * dstop; alvo = None if dalvo is None else p + sg * dalvo
    j = m1d[m1d.index >= t_sinal]
    ent = None
    for ts, r in zip(j.index, j.itertuples()):
        if ent is None:
            if ts >= t_sinal + base.VALIDADE: return 0.0, ts
            if (r.low <= p - base.FURA) if c else (r.high >= p + base.FURA): ent = ts
            continue
        bs = (r.low <= stop) if c else (r.high >= stop)
        ba = alvo is not None and ((r.high >= alvo + base.FURA) if c else (r.low <= alvo - base.FURA))
        if bs:
            px = min(r.open, stop) if c else max(r.open, stop)
            return ((px - p) * sg - base.CUSTO) * base.RS_PT, ts
        if ba:
            return ((alvo - p) * sg - base.CUSTO) * base.RS_PT, ts
        if ts >= fim:
            return ((r.close - p) * sg - base.CUSTO) * base.RS_PT, ts
    if ent is None: return 0.0, j.index[-1]
    return ((float(m1d.loc[fim].close) - p) * sg - base.CUSTO) * base.RS_PT, fim


def _nulo_dia(args):
    dia, geos, reps, seed = args
    m1 = base.carrega(dia, 0); d = pd.Timestamp(dia)
    m1d = m1[m1.index.normalize() == d]
    fim = m1d.index[m1d["ultima_continua"]].max() if m1d["ultima_continua"].any() else m1d.index.max()
    m15 = base._m15(m1d)
    fins = [ts + pd.Timedelta(minutes=15) for ts in m15.index if ts + pd.Timedelta(minutes=15) <= fim]
    closes = {ts + pd.Timedelta(minutes=15): float(r.close) for ts, r in m15.iterrows()}
    rng = np.random.default_rng(seed)
    out = np.zeros(reps)
    for k in range(reps):
        if not geos: continue
        ts_ = sorted(rng.choice(len(fins), size=min(len(geos), len(fins)), replace=False))
        livre = None; tot = 0.0
        for gi, ti in enumerate(ts_):
            t = fins[ti]
            if livre is not None and t <= livre: continue
            dstop, dalvo = geos[gi]
            lado = "compra" if rng.random() < 0.5 else "venda"
            brl, tsai = _nulo_sim(m1d, fim, t, closes[t], lado, dstop, dalvo)
            tot += brl; livre = tsai
        out[k] = tot
    return dia, out


# ---------------------------------------------------------------- caixa
def caixa(res, dias, inicial=2000.0):
    cx = inicial; hist = []
    for d in sorted(dias):
        if cx < 1000: hist.append((d, 0, 0.0, cx)); continue
        n = min(2, int(cx // 1000))
        r = res[d]; pl = sum(t["brl"] / t["contratos"] * n for t in r["trades"])
        risco = max([abs(t["preco"] - t["stop"]) * 0.2 * n for t in r["trades"]] or [0.0])
        cx += pl; hist.append((d, n, round(pl, 2), round(cx, 2), round(100 * risco / (cx - pl), 1)))
    return dict(final=round(cx, 2), minimo=min(h[3] for h in hist), parou=any(h[1] == 0 for h in hist), hist=hist)


def principal():
    dias, ncand, ef = sorteia()
    registra(dias, ef)
    print("candidatos:", ncand, "| dias sorteados:", dias, flush=True)
    ids = robo_v3.IDS
    print("v3 ids:", ids, "sha256 robo_v3.py:", hashlib.sha256(open(RAIZ / "robo_v3.py", "rb").read()).hexdigest()[:16], flush=True)
    R = {"v1": {}, "v2": {}, "v3": {}}; L = {"v1": {}, "v2": {}, "v3": {}}
    with ProcessPoolExecutor(11) as ex:
        fut = {ex.submit(_v1, d): ("v1", d) for d in dias}
        fut.update({ex.submit(_cfg, ((), d)): ("v2", d) for d in dias})
        fut.update({ex.submit(_cfg, (tuple(ids), d)): ("v3", d) for d in dias})
        for f in as_completed(fut):
            nome, d = fut[f]; dd, r, lg = f.result(); R[nome][d] = r; L[nome][d] = lg
    out = dict(dias=dias, ef={d: round(ef[d], 3) for d in dias}, estratos={d: av.estrato(ef[d]) for d in dias})
    for k in R: out[k] = estat(R[k], dias); print(k, out[k], flush=True)
    V = {k: np.array([R[k][d]["brl"] for d in dias]) for k in R}
    out["pareado_v3_v2"] = pareado(V["v3"], V["v2"]); out["pareado_v3_v1"] = pareado(V["v3"], V["v1"]); out["pareado_v2_v1"] = pareado(V["v2"], V["v1"])
    for k in ("pareado_v3_v2", "pareado_v3_v1", "pareado_v2_v1"): print(k, out[k], flush=True)
    # nulo
    geos = {d: [(abs(t["preco"] - t["stop"]), None if t["alvo"] is None else abs(t["alvo"] - t["preco"])) for t in R["v3"][d]["trades"]] for d in dias}
    nrep = 200
    nulo = np.zeros(nrep)
    with ProcessPoolExecutor(11) as ex:
        fut = [ex.submit(_nulo_dia, (d, geos[d], nrep, 1000 + i)) for i, d in enumerate(dias)]
        for f in as_completed(fut):
            d, o = f.result(); nulo += o
    tot3 = V["v3"].sum()
    out["nulo"] = dict(reps=nrep, media=round(float(nulo.mean()), 2), dp=round(float(nulo.std()), 2), p5=round(float(np.percentile(nulo, 5)), 2),
                       p95=round(float(np.percentile(nulo, 95)), 2), maximo=round(float(nulo.max()), 2), v3_total=round(float(tot3), 2),
                       p_valor=round(float((nulo >= tot3).mean()), 4), ops_v3=int(sum(len(g) for g in geos.values())))
    print("nulo", out["nulo"], flush=True)
    out["caixa_20"] = {k: caixa(R[k], dias) for k in ("v2", "v3")}
    for k, c in out["caixa_20"].items(): print("caixa", k, {a: b for a, b in c.items() if a != "hist"}, flush=True)
    # 50 dias em ordem cronologica
    d50 = [d for d, _ in cfg3.dias50()]
    r50 = av.avalia([[], list(ids)], d50)
    out["caixa_50"] = {"v2": caixa(r50[()], d50), "v3": caixa(r50[tuple(sorted(ids, key=cfg3.ORDEM.index))], d50)}
    for k, c in out["caixa_50"].items(): print("caixa50", k, {a: b for a, b in c.items() if a != "hist"}, flush=True)
    # negativos do v3
    neg = []
    for d in dias:
        if R["v3"][d]["brl"] < 0:
            neg.append(dict(dia=d, tipo=av.estrato(ef[d]), ef=round(ef[d], 3), brl=R["v3"][d]["brl"], v2=R["v2"][d]["brl"], v1=R["v1"][d]["brl"],
                            trades=R["v3"][d]["trades"], log=[x for x in L["v3"][d]]))
    json.dump(dict(R=R, out=out), open(C3 / "p4_resultados.json", "w"), indent=1, default=str)
    json.dump(neg, open(C3 / "ciclo3_negativos_bruto.json", "w"), indent=1, default=str)
    print("negativos:", [(n["dia"], n["brl"]) for n in neg])


if __name__ == "__main__":
    principal()
