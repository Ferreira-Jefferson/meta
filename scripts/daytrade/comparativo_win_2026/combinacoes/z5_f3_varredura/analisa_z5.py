# -*- coding: utf-8 -*-
import sys
from pathlib import Path
import numpy as np, pandas as pd
AQUI = Path(__file__).resolve().parent
Z4 = AQUI.parent / "z4_ret2024" / "trades"
CUSTO = 2.0
ANOS = ["2022", "2023", "2024", "2025", "2026"]
KS = ["0", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "1.0"]
NS = 1000

def carrega(k, sp):
    a = pd.read_csv(AQUI / "trades" / f"k{k}_2022_2025.csv")
    b = pd.read_csv(AQUI / "trades" / f"k{k}_2026{'_sempos' if sp else ''}.csv")
    df = pd.concat([a, b], ignore_index=True)
    df["ano"] = df.saida.str[:4]; df["liq"] = df.rs - CUSTO
    return df

def ano(df, a):
    g = df[df.ano == a]; eq = g.liq.cumsum()
    mn = 1000 + min(0.0, eq.min()) if len(g) else 1000.0
    return dict(ops=len(g), liq=g.liq.sum(), smin=mn, q=mn <= 0)

def prova():
    ok = True
    for sp in (False, True):
        suf = "_sempos" if sp else ""
        for k, nome in (("0", "base"), ("0.5", "f3")):
            n = carrega(k, sp)
            z = pd.concat([pd.read_csv(Z4 / f"{nome}_2022_2025.csv"), pd.read_csv(Z4 / f"{nome}_2026{suf}.csv")], ignore_index=True)
            igual = len(n) == len(z) and (n.drop(columns=["ano", "liq"]).astype(str).values == z.astype(str).values).all()
            if not igual and len(n) == len(z):
                igual = bool(((n.rs - z.rs).abs() < 1e-9).all() and (n.entrada == z.entrada).all() and (n.saida == z.saida).all())
            print(f"PROVA base={'sempos' if sp else 'oficial'} k={k} vs Z4 {nome}: {'IGUAL' if igual else 'DIFERENTE'} ({len(n)} vs {len(z)})", flush=True)
            ok &= igual
    return ok

def main():
    ok = prova()
    rng = np.random.default_rng(20261006)
    rows = []; md = ["# Z5 — varredura do limite k do f3 (gerado por analisa_z5.py)\n"]
    md.append(f"Prova: {'k=0 reproduz a base e k=0,5 reproduz o f3 da Z4, nas duas bases (operações idênticas)' if ok else 'PROVA FALHOU'}.\n")
    for sp, nb in ((False, "oficial (com tick 18:30 em 2026)"), (True, "sem velas pós-pregão")):
        base = carrega("0", sp); ab = {a: ano(base, a) for a in ANOS}
        md.append(f"## Base {nb}\n")
        md.append("| k | " + " | ".join(f"{a}: líq (ops) · saldo mín" for a in ANOS) + " | total 5 anos | ops | PF | acerto % | anos que melhoram vs k=0 | quebra | percentil (5 anos) | percentil (4 anos, Z4) |")
        md.append("|" + "---|" * (len(ANOS) + 9))
        for k in KS:
            d = carrega(k, sp); r = {a: ano(d, a) for a in ANOS}
            tot = sum(r[a]["liq"] for a in ANOS)
            gp = d.liq[d.liq > 0].sum(); gl = -d.liq[d.liq < 0].sum()
            pf = gp / gl if gl > 0 else np.nan
            ac = (d.liq > 0).mean() * 100
            mel = sum(r[a]["liq"] > ab[a]["liq"] for a in ANOS) if k != "0" else 0
            quebras = [a for a in ANOS if r[a]["q"]]
            t5 = np.zeros(NS); t4 = np.zeros(NS)
            if k != "0":
                for a in ANOS:
                    lb = base[base.ano == a].liq.values; kk = min(r[a]["ops"], len(lb))
                    s = np.array([lb[rng.choice(len(lb), kk, replace=False)].sum() for _ in range(NS)])
                    t5 += s
                    if a != "2024": t4 += s
                tot4 = sum(r[a]["liq"] for a in ANOS if a != "2024")
                p5 = ((t5 < tot).mean() + 0.5 * (t5 == tot).mean()) * 100
                p4 = ((t4 < tot4).mean() + 0.5 * (t4 == tot4).mean()) * 100
            else:
                p5 = p4 = np.nan
            cel = " | ".join(f"{r[a]['liq']:+,.0f} ({r[a]['ops']}) · {r[a]['smin']:,.0f}{' Q' if r[a]['q'] else ''}" for a in ANOS)
            md.append(f"| {k.replace('.', ',')} | {cel} | {tot:+,.0f} | {len(d)} | {pf:.2f} | {ac:.1f} | {mel}/5 | {','.join(quebras) or 'não'} | "
                      f"{'—' if np.isnan(p5) else f'{p5:.1f}'} | {'—' if np.isnan(p4) else f'{p4:.1f}'} |")
            rows.append(dict(base="sempos" if sp else "oficial", k=k, **{f"liq_{a}": round(r[a]["liq"], 2) for a in ANOS},
                             **{f"ops_{a}": r[a]["ops"] for a in ANOS}, **{f"saldo_min_{a}": round(r[a]["smin"], 2) for a in ANOS},
                             total5=round(tot, 2), ops=len(d), pf=round(pf, 3), acerto=round(ac, 1), anos_melhoram=mel,
                             quebra=",".join(quebras), pct5=round(p5, 1), pct4=round(p4, 1)))
            print(rows[-1]["base"], k, f"total={tot:+.0f} pct5={p5:.1f} mel={mel}", flush=True)
        md.append("")
    pd.DataFrame(rows).to_csv(AQUI / "resultado.csv", index=False)
    (AQUI / "resultado_tabelas.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
main()
