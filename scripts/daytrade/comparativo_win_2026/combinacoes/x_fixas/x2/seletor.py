"""X2 - SELETOR. Regra pre-registrada no TODO.md. Uso: python seletor.py dev | conf"""
import sys, json, hashlib, itertools
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).parent
BASE = HERE.parent.parent.parent
D2225 = HERE.parent / "x0b" / "resultados_2022_2025"
D26 = BASE / "resultados"
ROBOS = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
CUSTO = 2.0
PER = {"DEV": ("2022-01-03", "2024-06-28"), "VAL": ("2024-07-01", "2025-09-30"), "2026": ("2026-01-01", "2026-12-31")}

def carrega(robo, per):
    src = D26 if per == "2026" else D2225
    d = pd.read_csv(src / f"{robo}.csv", parse_dates=["entrada", "saida"])
    a, b = PER[per]
    d = d[(d.entrada >= a) & (d.entrada < pd.Timestamp(b) + pd.Timedelta(days=1))].copy()
    d["estrategia"] = robo
    d["liq"] = d.rs - CUSTO
    return d.reset_index(drop=True)

def metricas(t, meses_per=None):
    """t: trades ordenados por entrada, colunas rs, liq, entrada."""
    n = len(t)
    if n == 0:
        return dict(ops=0)
    liq = t.liq.values
    eq = np.cumsum(liq)
    pico = np.maximum.accumulate(np.concatenate([[0], eq]))[1:]
    dd = float((pico - eq).max())
    g = liq[liq > 0].sum(); p = -liq[liq < 0].sum()
    w = liq[liq > 0]; l = liq[liq < 0]
    mes = t.groupby(t.entrada.dt.to_period("M")).liq.sum()
    return dict(ops=n, sem_custo=round(float(t.rs.sum()), 1), com_custo=round(float(liq.sum()), 1),
                acerto=round(float((t.rs > 0).mean() * 100), 1),
                payoff=round(float(w.mean() / -l.mean()), 2) if len(w) and len(l) else np.nan,
                fl=round(float(g / p), 2) if p > 0 else np.nan,
                dd=round(dd, 1), fr=round(float(liq.sum() / dd), 2) if dd > 0 else np.nan,
                meses_pos=f"{int((mes > 0).sum())}/{len(mes)}",
                quebra="SIM" if (1000 + eq).min() <= 0 else "nao")

def seleciona(cands, prio):
    """cands: DataFrame de todas as operacoes; prio: dict robo->rank (menor = melhor)."""
    c = cands.copy()
    c["min"] = c.entrada.dt.floor("min")
    c["pr"] = c.estrategia.map(prio)
    c = c.sort_values(["min", "pr", "entrada"], kind="stable")
    livre = pd.Timestamp.min; esc = []; ign = 0; emp = 0
    for _, g in c.groupby("min", sort=True):
        rows = list(g.itertuples())
        if livre <= rows[0].entrada.floor("min") or any(r.entrada >= livre for r in rows):
            pass
        escolhida = None
        for r in rows:
            if livre <= r.entrada:
                escolhida = r; break
        if escolhida is None:
            ign += len(rows); continue
        if len(rows) > 1:
            emp += 1
        esc.append(escolhida.Index); ign += len(rows) - 1
        livre = escolhida.saida
    return c.loc[esc].sort_values("entrada"), ign, emp

def ranking_dev():
    linhas = []
    for r in ROBOS:
        m = metricas(carrega(r, "DEV"))
        linhas.append(dict(robo=r, **m))
    return pd.DataFrame(linhas)

def prios(rk):
    p1 = rk.sort_values(["fr", "acerto"], ascending=False).robo.tolist()
    p2 = rk.sort_values("acerto", ascending=False).robo.tolist()
    p3 = sorted(ROBOS)
    return {"P1": {r: i for i, r in enumerate(p1)}, "P2": {r: i for i, r in enumerate(p2)}, "P3": {r: i for i, r in enumerate(p3)}}

def todas(per):
    return pd.concat([carrega(r, per) for r in ROBOS], ignore_index=True)

def roda(per, pri):
    sel, ign, emp = seleciona(todas(per), pri)
    return sel, ign, emp

if __name__ == "__main__":
    modo = sys.argv[1]
    rk = ranking_dev()
    print(rk.to_string(), flush=True)
    P = prios(rk)
    print({k: sorted(v, key=v.get) for k, v in P.items()}, flush=True)
    if modo == "dev":
        res = []
        for k, pri in P.items():
            sel, ign, emp = roda("DEV", pri)
            m = metricas(sel); m.update(var=k, ignoradas=ign, empates=emp); res.append(m)
            print(m, flush=True)
        df = pd.DataFrame(res); df.to_csv(HERE / "dev_variantes.csv", index=False)
        rk.to_csv(HERE / "ranking_dev.csv", index=False)
        ok = df[(df.quebra == "nao") & (df.com_custo > 0)]
        if ok.empty:
            print("REFUTADA NO DEV", flush=True)
        else:
            v = ok.sort_values("fr", ascending=False).iloc[0].var
            print("VARIANTE", v, flush=True)
            json.dump({"variante": v, "prioridade": {r: P[v][r] for r in ROBOS}}, open(HERE / "congelada.json", "w"))
    else:
        cg = json.load(open(HERE / "congelada.json")); pri = cg["prioridade"]
        rng = np.random.default_rng(42)
        out = []
        for per in ["VAL", "2026"]:
            allt = todas(per)
            sel, ign, emp = seleciona(allt, pri)
            m = metricas(sel); m.update(periodo=per, ignoradas=ign, empates=emp)
            sel.drop(columns=["liq", "min", "pr"]).to_csv(HERE / "trades" / f"X2_{per}.csv", index=False)
            orig = {r: metricas(carrega(r, per)) for r in ROBOS}
            sim = []
            for _ in range(1000):
                perm = rng.permutation(len(ROBOS))
                s, _, _ = seleciona(allt, {r: int(perm[i]) for i, r in enumerate(ROBOS)})
                sim.append(s.liq.sum())
            pct = float((np.array(sim) < sel.liq.sum()).mean() * 100)
            print(per, m, flush=True)
            for r, o in orig.items(): print("  orig", r, o, flush=True)
            print("  percentil sorteio", pct, "mediana", np.median(sim), flush=True)
            # mensal
            mes = sel.groupby(sel.entrada.dt.to_period("M")).agg(ops=("rs", "size"), sem_custo=("rs", "sum"), com_custo=("liq", "sum"))
            print(mes.round(1).to_string(), flush=True)
            out.append(dict(periodo=per, sel=m, orig=orig, pct=pct, mediana_sorteio=float(np.median(sim)), mes=mes.round(1).reset_index().astype(str).to_dict("records")))
        json.dump(out, open(HERE / "conf.json", "w"), default=str, indent=1)
