# -*- coding: utf-8 -*-
"""Agrega os resultados por pregao (`out/dia_resultados.pkl`) em: modo A (conta continua R$1.000, sizing de
producao), modo B (R$1.000 por pregao, 2 contratos), nulo de direcao aleatoria por celula, nulo de MAXIMO sobre a
grade inteira (estilo White: por sorteio, a MELHOR celula), metades abr-jun x jul-out, familias de saida."""
from __future__ import annotations

import dataclasses
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import regras as R  # noqa: E402
import sizing as Z  # noqa: E402
from backtest.intraday.report import LinhaResultado, linha_de_resultado, num_br, tabela  # noqa: E402

N_NULO = 20000
SEED = 20261006
CORTE = pd.Timestamp("2026-07-01").date()
FILLS = ("toque", "atrav+1t")
EXTRAS = ("fill", "modo", "ctr", "BE emp%", "sem fill%", "atraso min", "seq perd", "saidas s/a/tr/te/f", "p nulo", "p adj", "sem trade")
LEG = ("stop", "alvo", "trail", "tempo", "flatten")


def carrega():
    res = pickle.load(open(AQUI / "out" / "dia_resultados.pkl", "rb"))
    dias = sorted(res)
    grade = R.grade()
    return res, dias, grade


def maxdd(eq):
    eq = np.asarray(eq, float)
    if len(eq) == 0:
        return 0.0
    return float((np.maximum.accumulate(eq) - eq).max())


def seq_perdas(pnls):
    mx = at = 0
    for p in pnls:
        at = at + 1 if p < 0 else 0
        mx = max(mx, at)
    return mx


def modo_b(res, dias, cid, fm):
    """Vetores por pregao (q=2 = R$1.000 / sizing): real, alt, gatilho, fill, atraso, legs."""
    D = len(dias)
    real = np.zeros(D); alt = np.zeros(D); trig = np.zeros(D, bool); fil = np.zeros(D, bool)
    atraso = []; legs = {k: 0 for k in LEG}; trades = []
    q = Z.n_contratos(Z.CAPITAL)
    for i, d in enumerate(dias):
        r = res[d]["cel"][cid]
        if r is None:
            continue
        trig[i] = True
        f = r["fills"][fm]
        a = f["alt2"]
        if a is not None:
            alt[i] = a["pnl"]
        t = f["real"][q]
        if t is not None:
            real[i] = t["pnl"]; fil[i] = True
            atraso.append((t["fill_t"] - res[d]["t_sinal"]) / 60000.0)
            for (qq, rs, *_ ) in t["legs"]:
                legs[rs] += 1
            trades.append(t)
    return dict(real=real, alt=alt, trig=trig, fil=fil, atraso=atraso, legs=legs, trades=trades, q=q)


def modo_a(res, dias, cid, fm):
    cash = Z.CAPITAL
    eq_pts = [cash]; pnls = []; qts = []; recus = 0; legs = {k: 0 for k in LEG}
    dias_trade = set(); min_eq = cash; atraso = []; trig_n = 0; fills = 0
    cash_dia = []
    for d in dias:
        r = res[d]["cel"][cid]
        if r is not None:
            trig_n += 1
            n = Z.n_contratos(cash)
            if n < 1:
                recus += 1
            else:
                t = r["fills"][fm]["real"][min(n, 5)]
                if t is not None:
                    fills += 1
                    trough = cash + t["mae"] * t["qty"] * 0.2 - 0.0     # pior MtM intradia (aprox: pior excursao x qtd)
                    min_eq = min(min_eq, trough)
                    eq_pts += [trough]
                    cash += t["pnl"]
                    eq_pts.append(cash)
                    pnls.append(t["pnl"]); qts.append(t["qty"]); dias_trade.add(d)
                    atraso.append((t["fill_t"] - res[d]["t_sinal"]) / 60000.0)
                    for (qq, rs, *_ ) in t["legs"]:
                        legs[rs] += 1
        cash_dia.append(cash)
    min_eq = min(min_eq, min(cash_dia + [Z.CAPITAL]))
    return dict(cash=cash, liquido=cash - Z.CAPITAL, pnls=pnls, qts=qts, recus=recus, legs=legs, min_eq=min_eq,
                dd=maxdd(eq_pts), cash_dia=cash_dia, trig=trig_n, fills=fills, dias_trade=len(dias_trade),
                atraso=atraso, pregoes=len(dias))


def ns_resultado(trades_pnl, equity_idx, equity_vals, nocional):
    tr = [SimpleNamespace(pnl_brl=p) for p in trades_pnl]
    eq = pd.Series(equity_vals, index=pd.to_datetime(equity_idx))
    return SimpleNamespace(trades=tr, equity_curve=eq, metrics={"max_drawdown": (maxdd(equity_vals) / max(max(equity_vals), 1e-9)) if len(equity_vals) else 0.0},
                           wiped_out_at=None, sessoes_puladas_por_capital=[], deslize_alvo_ticks=0.0,
                           fila_entrada_qty=0.0, fila_saida_qty=0.0, fila_calibrada=False)


def fmt_saidas(legs):
    return "/".join(str(legs[k]) for k in LEG)


def linha_b(cid, fm, b, dias, stats):
    pnl = b["real"][b["fil"]]
    eq = 1000.0 + np.cumsum(b["real"])
    res = ns_resultado(pnl.tolist(), dias, eq, True)
    L = linha_de_resultado(cid, res, Z.CAPITAL, capital_nocional=True)
    be = stats["be"]
    ex = {"fill": fm, "modo": "B pregao", "ctr": str(b["q"]), "BE emp%": num_br(be, 1),
          "sem fill%": num_br(stats["sem_fill"], 1), "atraso min": num_br(stats["atraso_med"], 1),
          "seq perd": str(seq_perdas(pnl)), "saidas s/a/tr/te/f": fmt_saidas(b["legs"]),
          "p nulo": num_br(stats["p"], 3), "p adj": num_br(stats["p_adj"], 3),
          "sem trade": f"{len(dias) - int(b['fil'].sum())}/{len(dias)}"}
    return dataclasses.replace(L, extras=ex, aviso="fila NAO CALIBRADA (WIN); fill " + fm)


def linha_a(cid, fm, a, dias, stats):
    eqv = a["cash_dia"]
    res = ns_resultado(a["pnls"], dias, eqv, False)
    L = linha_de_resultado(cid, res, Z.CAPITAL, capital_nocional=False)
    ctr = f"{np.mean(a['qts']):.1f} [{min(a['qts'])}-{max(a['qts'])}]" if a["qts"] else "—"
    cens = []
    if a["recus"]:
        cens.append(f"CENSURADO recusou {a['recus']}")
    if a["min_eq"] < Z.MARGEM:
        cens.append(f"caixa mín {num_br(a['min_eq'], 0)}<margem")
    ex = {"fill": fm, "modo": "A conta", "ctr": ctr, "BE emp%": num_br(stats["be_a"], 1),
          "sem fill%": num_br(stats["sem_fill_a"], 1), "atraso min": num_br(stats["atraso_med_a"], 1),
          "seq perd": str(seq_perdas(a["pnls"])), "saidas s/a/tr/te/f": fmt_saidas(a["legs"]),
          "p nulo": "—", "p adj": "—", "sem trade": f"{a['pregoes'] - a['dias_trade']}/{a['pregoes']}"}
    return dataclasses.replace(L, extras=ex, aviso=" ".join(cens + ["fila NAO CALIBRADA (WIN)"]))


def stats_be(pnl):
    g = pnl[pnl > 0]; p = -pnl[pnl < 0]
    return 100.0 * p.mean() / (g.mean() + p.mean()) if len(g) and len(p) else float("nan")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    res, dias, grade = carrega()
    D = len(dias)
    rng = np.random.default_rng(SEED)
    S = rng.integers(0, 2, size=(N_NULO, D)).astype(np.float32)       # 1 = direcao REAL, 0 = oposta (mesmo sorteio p/ toda celula)
    ids = [g["id"] for g in grade]
    out = {}
    for fm in FILLS:
        B = {cid: modo_b(res, dias, cid, fm) for cid in ids}
        Rm = np.stack([B[c]["real"] for c in ids], 1).astype(np.float32)      # D x C
        Am = np.stack([B[c]["alt"] for c in ids], 1).astype(np.float32)
        nulo = S @ Rm + (1 - S) @ Am                                         # N x C
        obs = Rm.sum(0)
        mu, sd = nulo.mean(0), nulo.std(0) + 1e-9
        tobs = (obs - mu) / sd
        tnull = (nulo - mu) / sd
        M = tnull.max(1)
        p_cel = ((nulo >= obs[None, :]).sum(0) + 1) / (N_NULO + 1)
        p_adj = np.array([((M >= tobs[j]).sum() + 1) / (N_NULO + 1) for j in range(len(ids))])
        Mraw = nulo.max(1)
        p_adj_raw = np.array([((Mraw >= obs[j]).sum() + 1) / (N_NULO + 1) for j in range(len(ids))])
        out[fm] = dict(B=B, obs=obs, mu=mu, sd=sd, tobs=tobs, p_cel=p_cel, p_adj=p_adj, p_adj_raw=p_adj_raw, Rm=Rm, Am=Am)
    # modo A
    A = {fm: {cid: modo_a(res, dias, cid, fm) for cid in ids} for fm in FILLS}
    pickle.dump(dict(out=out, A=A, dias=dias, ids=ids), open(AQUI / "out" / "analise.pkl", "wb"))

    def stats_cel(fm, j):
        cid = ids[j]
        b = out[fm]["B"][cid]
        pnl = b["real"][b["fil"]]
        a = A[fm][cid]
        ap = np.array(a["pnls"])
        return dict(be=stats_be(pnl), sem_fill=100.0 * (b["trig"].sum() - b["fil"].sum()) / max(b["trig"].sum(), 1),
                    atraso_med=float(np.median(b["atraso"])) if b["atraso"] else float("nan"),
                    p=out[fm]["p_cel"][j], p_adj=out[fm]["p_adj"][j],
                    be_a=stats_be(ap) if len(ap) else float("nan"),
                    sem_fill_a=100.0 * (a["trig"] - a["recus"] - a["fills"]) / max(a["trig"], 1),
                    atraso_med_a=float(np.median(a["atraso"])) if a["atraso"] else float("nan"))

    ordem = np.argsort(-out["toque"]["tobs"])
    print(f"Grade: {len(ids)} celulas | {D} pregoes elegiveis | nulo: {N_NULO} sorteios de direcao (mesmo sorteio para todas as celulas)")
    print("\n=== TOP 10 por t (excesso sobre o nulo de direcao em desvios-padrao; modo B toque) ===")
    linhas = []
    for j in ordem[:10]:
        for fm in FILLS:
            st = stats_cel(fm, j)
            linhas.append(linha_b(ids[j], fm, out[fm]["B"][ids[j]], dias, st))
            linhas.append(linha_a(ids[j], fm, A[fm][ids[j]], dias, st))
    print(tabela(linhas, EXTRAS, 12))
    # tabela compacta de todas
    print("\n=== TODAS as celulas (modo B toque): liquido R$, t, p celula, p ajustado (max-stat), modo A liquido / censura ===")
    rows = []
    for j in range(len(ids)):
        a = A["toque"][ids[j]]
        b = out["toque"]["B"][ids[j]]
        rows.append(dict(id=ids[j], entrada=grade[j]["ent"]["id"], fam=grade[j]["ex"]["fam"], B_liq=out["toque"]["obs"][j], B_liq_atrav=out["atrav+1t"]["obs"][j],
                         t=out["toque"]["tobs"][j], p=out["toque"]["p_cel"][j], p_adj=out["toque"]["p_adj"][j], p_adj_raw=out["toque"]["p_adj_raw"][j],
                         trig=int(b["trig"].sum()), fills=int(b["fil"].sum()), A_liq=a["liquido"], A_recus=a["recus"], A_min_eq=a["min_eq"],
                         A_trades=len(a["pnls"]), A_cens=bool(a["recus"] or a["min_eq"] < Z.MARGEM)))
    T = pd.DataFrame(rows)
    T.to_csv(AQUI / "out" / "celulas.csv", sep=";", decimal=",", index=False)
    print(T.sort_values("t", ascending=False).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # ----- selecao: vencedor, p ajustado
    jv = int(ordem[0])
    print(f"\n=== SELECAO === vencedor por t: {ids[jv]} | B toque liquido {out['toque']['obs'][jv]:.2f} | t={out['toque']['tobs'][jv]:.2f} | "
          f"p celula={out['toque']['p_cel'][jv]:.4f} | p ajustado (max-stat sobre {len(ids)} celulas)={out['toque']['p_adj'][jv]:.4f} | "
          f"p ajustado com estatistica em R$ bruto={out['toque']['p_adj_raw'][jv]:.4f}")
    jl = int(np.argmax(out['toque']['obs']))
    print(f"vencedor por liquido B: {ids[jl]} liquido {out['toque']['obs'][jl]:.2f} t={out['toque']['tobs'][jl]:.2f} p celula={out['toque']['p_cel'][jl]:.4f} "
          f"p ajustado={out['toque']['p_adj'][jl]:.4f} p ajustado R$={out['toque']['p_adj_raw'][jl]:.4f}")
    print(f"celulas com p celula<0,05: {(out['toque']['p_cel']<0.05).sum()}/{len(ids)} (esperado ao acaso ~{0.05*len(ids):.0f}); com p ajustado<0,05: {(out['toque']['p_adj']<0.05).sum()}")
    # ----- metades
    print("\n=== METADES (modo B toque, liquido R$) ===")
    h1 = np.array([d <= pd.Timestamp('2026-06-30').date() for d in dias])
    tot1 = out["toque"]["Rm"][h1].sum(0); tot2 = out["toque"]["Rm"][~h1].sum(0)
    def pct(x):
        return pd.Series(x).rank().to_numpy()
    rho = float(np.corrcoef(pct(tot1), pct(tot2))[0, 1])
    top1 = set(np.argsort(-tot1)[:10]); top2 = set(np.argsort(-tot2)[:10])
    print(f"pregoes: abr-jun {int(h1.sum())} | jul-out {int((~h1).sum())} | correlacao de postos entre metades (100 celulas) = {rho:.2f} | "
          f"celulas no top10 das DUAS metades: {len(top1 & top2)}")
    print(f"vencedor ({ids[jv]}): abr-jun {tot1[jv]:.2f} | jul-out {tot2[jv]:.2f} | positivo nas 2 metades: {tot1[jv] > 0 and tot2[jv] > 0}")
    print(f"celulas com liquido>0 nas duas metades: {int(((tot1>0)&(tot2>0)).sum())}/{len(ids)}; >0 so' numa: {int(((tot1>0)^(tot2>0)).sum())}; <=0 nas duas: {int(((tot1<=0)&(tot2<=0)).sum())}")
    print("top10 abr-jun:", [ids[j] for j in np.argsort(-tot1)[:10]])
    print("top10 jul-out:", [ids[j] for j in np.argsort(-tot2)[:10]])
    # as 10 melhores (por t) em cada metade
    print("top10 geral em cada metade (abr-jun / jul-out):")
    for j in ordem[:10]:
        print(f"   {ids[j]:<34} {tot1[j]:10.2f} {tot2[j]:10.2f}")
    # ----- familias de saida, entrada fixa V2 r150
    print("\n=== FAMILIAS DE SAIDA com entrada fixa V2 r150 (modo B toque; media de t, melhor celula) ===")
    fams = {}
    for j, g in enumerate(grade):
        if g["ent"]["id"] != "V2 r150":
            continue
        fams.setdefault(g["ex"]["fam"], []).append(j)
    fr = []
    for f, js in fams.items():
        jj = max(js, key=lambda j: out["toque"]["tobs"][j])
        fr.append(dict(familia=f, celulas=len(js), melhor=ids[jj].split(" | ")[1], B_liq=out["toque"]["obs"][jj], t_melhor=out["toque"]["tobs"][jj],
                       t_mediano=float(np.median([out["toque"]["tobs"][j] for j in js])), liq_mediano=float(np.median([out["toque"]["obs"][j] for j in js])),
                       frac_liq_pos=float(np.mean([out["toque"]["obs"][j] > 0 for j in js])), p_adj_melhor=out["toque"]["p_adj"][jj],
                       A_liq_melhor=A["toque"][ids[jj]]["liquido"], A_censurada=bool(A["toque"][ids[jj]]["recus"] or A["toque"][ids[jj]]["min_eq"] < Z.MARGEM)))
    print(pd.DataFrame(fr).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    print("\n=== ENTRADAS x SAIDAS (B toque, liquido R$) ===")
    mat = pd.DataFrame({g["id"]: out["toque"]["obs"][j] for j, g in enumerate(grade)}.items(), columns=["id", "liq"])
    mat["entrada"] = mat.id.str.split(" \\| ").str[0]; mat["saida"] = mat.id.str.split(" \\| ").str[1]
    piv = mat.pivot(index="saida", columns="entrada", values="liq")
    print(piv.loc[[g["id"] for g in R.SAIDAS]].to_string(float_format=lambda x: f"{x:,.0f}"))
    print("\ncolunas: entrada | liquido por saida; soma por entrada:", piv.sum().round(0).to_dict())


if __name__ == "__main__":
    main()
