"""Validacao do ciclo 4 (ciclo4/PREREGISTRO.md): sorteio aleatorio simples de 20 dias novos; v1, v2, v3, v4; pareado; nulo; caixa; negativos.
Reaproveita as funcoes de ciclo3/p4_validacao.py (estat, pareado, nulo, caixa)."""
import sys, json, hashlib
from pathlib import Path
C4 = Path(__file__).resolve().parent
RAIZ = C4.parent
sys.path.insert(0, str(C4)); sys.path.insert(0, str(RAIZ / "ciclo3")); sys.path.insert(0, str(RAIZ))
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import cfg4, cfg3, av, robo, robo_v3, robo_v4
import p4_validacao as p4

SEED = 20261017
SHA_V4 = "b503396addfbbcb689657fb16a57ccb7bfdad7c61b38ad243720b682098467f6"
SHA_CFG4 = "42c133785289f82ef690eb8c16726aa29a7754e722a47cf1209e16faa0d0fa50"


def sorteia():
    ef = av.eficiencia_todos()
    usados = set(d for d, _ in cfg4.dias70())
    cand = sorted(d for d in ef if d not in usados and d < "2026-04-01")
    rng = np.random.default_rng(SEED)
    return sorted(rng.choice(cand, 20, replace=False).tolist()), len(cand), ef


def registra(dias, ef):
    p = RAIZ / "dias_usados.json"
    j = json.load(open(p))
    if "ciclo4" not in j:
        j["ciclo4"] = dict(seed=SEED, sorteio="aleatorio simples do IS 2022-01-01..2025-09-30 (>=300 barras), fora dos 70 usados",
                           dias=[dict(dia=d, tipo=av.estrato(ef[d]).replace("int", "intermediario"), ef=round(ef[d], 3)) for d in dias])
        json.dump(j, open(p, "w"), indent=1)


def _v4(dia):
    tr, log = robo_v4.roda_v4(dia)
    return dia, p4._res(tr), [dict(x) for x in log]


def principal():
    assert hashlib.sha256(open(RAIZ / "robo_v4.py", "rb").read()).hexdigest() == SHA_V4, "robo_v4.py mudou depois do congelamento"
    assert hashlib.sha256(open(C4 / "cfg4.py", "rb").read()).hexdigest() == SHA_CFG4, "cfg4.py mudou depois do congelamento"
    dias, ncand, ef = sorteia()
    registra(dias, ef)
    print("candidatos:", ncand, "| dias sorteados:", dias, flush=True)
    print("estratos:", {d: av.estrato(ef[d]) for d in dias}, flush=True)
    R = {k: {} for k in ("v1", "v2", "v3", "v4")}; L = {k: {} for k in R}
    with ProcessPoolExecutor(8) as ex:
        fut = {ex.submit(p4._v1, d): ("v1", d) for d in dias}
        fut.update({ex.submit(p4._cfg, ((), d)): ("v2", d) for d in dias})
        fut.update({ex.submit(p4._cfg, (tuple(robo_v3.IDS), d)): ("v3", d) for d in dias})
        fut.update({ex.submit(_v4, d): ("v4", d) for d in dias})
        for f in as_completed(fut):
            nome, d = fut[f]; dd, r, lg = f.result(); R[nome][d] = r; L[nome][d] = lg
            print(f"  {nome} {d} R$ {r['brl']:+.2f} ops {r['ops']}", flush=True)
    out = dict(dias=dias, ef={d: round(ef[d], 3) for d in dias}, estratos={d: av.estrato(ef[d]) for d in dias})
    for k in R: out[k] = p4.estat(R[k], dias); print(k, out[k], flush=True)
    est = {}
    for k in R:
        for e in ("bom", "int", "ruim"):
            ds = [d for d in dias if av.estrato(ef[d]) == e]
            est.setdefault(k, {})[e] = dict(n=len(ds), total=round(sum(R[k][d]["brl"] for d in ds), 2))
    out["por_estrato"] = est; print("por estrato", est, flush=True)
    V = {k: np.array([R[k][d]["brl"] for d in dias]) for k in R}
    for a, b in (("v4", "v3"), ("v4", "v2"), ("v4", "v1")):
        out[f"pareado_{a}_{b}"] = p4.pareado(V[a], V[b]); print(f"pareado_{a}_{b}", out[f"pareado_{a}_{b}"], flush=True)
    geos = {d: [(abs(t["preco"] - t["stop"]), None if t["alvo"] is None else abs(t["alvo"] - t["preco"])) for t in R["v4"][d]["trades"]] for d in dias}
    nrep = 200; nulo = np.zeros(nrep)
    with ProcessPoolExecutor(8) as ex:
        fut = [ex.submit(p4._nulo_dia, (d, geos[d], nrep, 2000 + i)) for i, d in enumerate(dias)]
        for f in as_completed(fut):
            d, o = f.result(); nulo += o
    tot = V["v4"].sum()
    out["nulo"] = dict(reps=nrep, media=round(float(nulo.mean()), 2), p95=round(float(np.percentile(nulo, 95)), 2), v4_total=round(float(tot), 2),
                       p_valor=round(float((nulo >= tot).mean()), 4), ops_v4=int(sum(len(g) for g in geos.values())))
    print("nulo", out["nulo"], flush=True)
    out["caixa_20"] = {k: p4.caixa(R[k], dias) for k in ("v3", "v4")}
    for k, c in out["caixa_20"].items(): print("caixa20", k, {a: b for a, b in c.items() if a != "hist"}, flush=True)
    neg = []
    for d in dias:
        if R["v4"][d]["brl"] < 0:
            neg.append(dict(dia=d, tipo=av.estrato(ef[d]), ef=round(ef[d], 3), brl=R["v4"][d]["brl"], v3=R["v3"][d]["brl"], v2=R["v2"][d]["brl"],
                            v1=R["v1"][d]["brl"], trades=R["v4"][d]["trades"], log=L["v4"][d]))
    json.dump(dict(R=R, out=out), open(C4 / "p_validacao_resultados.json", "w"), indent=1, default=str)
    json.dump(neg, open(RAIZ / "ciclo4_negativos.json", "w"), indent=1, default=str)
    print("negativos v4:", [(n["dia"], n["brl"]) for n in neg], flush=True)


if __name__ == "__main__":
    principal()
