"""Persistencia dia->dia no WIN@D (M1, ajuste por diferenca). Estudo descritivo."""
import math, io
import numpy as np, pandas as pd
from pathlib import Path
OUT = Path(__file__).parent
CSV = r"C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5\WIN@D_M1_202110010900_202610011717.csv"
rng = np.random.default_rng(7)

d = pd.read_csv(CSV, sep="\t")
d["dt"] = pd.to_datetime(d["<DATE>"] + " " + d["<TIME>"])
d["day"] = d["dt"].dt.normalize()
d = d.rename(columns={"<OPEN>": "o", "<HIGH>": "h", "<LOW>": "l", "<CLOSE>": "c"})
g = d.groupby("day")
D = pd.DataFrame({"O": g["o"].first(), "H": g["h"].max(), "L": g["l"].min(), "C": g["c"].last(),
                  "n": g.size(), "t0": g["dt"].first().dt.hour * 60 + g["dt"].first().dt.minute,
                  "t1": g["dt"].last().dt.hour * 60 + g["dt"].last().dt.minute})
# tratamento: dias que abrem >=10:00 (quarta de cinzas, 13:00) e o ultimo dia (incompleto, termina 17:17) saem
excl = D[(D.t0 >= 600) | (D.index == D.index[-1])]
D = D.drop(excl.index)
print("dias excluidos:", [str(x.date()) for x in excl.index], flush=True)
D["Cp"] = D["C"].shift(1); D["Hp"] = D["H"].shift(1); D["Lp"] = D["L"].shift(1)
D["tr"] = np.maximum(D.H - D.L, np.maximum((D.H - D.Cp).abs(), (D.L - D.Cp).abs()))
D["atr"] = D["tr"].rolling(14).mean().shift(1)   # ATR conhecido antes de D (sem look-ahead)
D["gap"] = D.O - D.Cp
D["cc"] = D.C - D.Cp
D["oc"] = D.C - D.O
D["cc1"] = D.cc.shift(1); D["oc1"] = D.oc.shift(1)
D["atr1"] = D.atr.shift(1)
D["ccn1"] = D.cc1 / D.atr1
D["loc1"] = ((D.C - D.L) / (D.H - D.L)).shift(1)
D["gapn"] = D.gap / D.atr
D = D.dropna(subset=["atr", "cc1", "atr1"]).copy()
D["win"] = np.where(D.index <= "2024-12-31", "IS", "OOS")
print(D.groupby("win").size(), flush=True)
print("barras/dia medianas:", D.n.median(), " t0 moda:", D.t0.mode()[0], "t1 moda:", D.t1.mode()[0], flush=True)

def wilson(k, n):
    if n == 0: return (np.nan, np.nan)
    p = k / n; z = 1.96
    den = 1 + z*z/n; c = (p + z*z/(2*n)) / den; h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return c-h, c+h
def pval(k, n, p0):
    if n == 0 or p0 in (0, 1): return np.nan
    z = (k/n - p0) / math.sqrt(p0*(1-p0)/n)
    return math.erfc(abs(z)/math.sqrt(2))
def ic(k, n):
    lo, hi = wilson(k, n)
    return f"[{lo*100:.1f};{hi*100:.1f}]".replace(".", ",")
def row(label, mask, ev):
    r = {"cond": label}
    for w in ("IS", "OOS"):
        sub = D[D.win == w]
        m = mask.loc[sub.index]; e = ev.loc[sub.index]
        ok = e.notna()
        base = e[ok].astype(float).mean()
        x = e[ok & m].astype(float); n = len(x); k = int(x.sum())
        r.update({f"{w}_n": n, f"{w}_taxa": k/n*100 if n else np.nan, f"{w}_ic": ic(k, n) if n else "",
                  f"{w}_base": base*100, f"{w}_dif_pp": (k/n-base)*100 if n else np.nan, f"{w}_p": pval(k, n, base) if n else np.nan})
    return r
def fmt(df):
    out = df.copy()
    for c in out.columns:
        if out[c].dtype.kind == "f":
            f = (lambda v: "" if pd.isna(v) else f"{v:.4f}") if c.endswith("_p") or c == "p_perm" else (lambda v: "" if pd.isna(v) else f"{v:.1f}")
            out[c] = out[c].map(f).str.replace(".", ",", regex=False)
    return out
def md(df):
    f = fmt(df); cols = list(f.columns)
    s = "| " + " | ".join(cols) + " |\n|" + "---|"*len(cols) + "\n"
    for _, r in f.iterrows(): s += "| " + " | ".join(str(r[c]) for c in cols) + " |\n"
    return s

doc = io.StringIO()
def section(title, df, name, note=""):
    df.to_csv(OUT / f"a_{name}.csv", index=False, sep=";", decimal=",")
    doc.write(f"\n## {title}\n{note}\n\n{md(df)}\n"); print(title, note, "\n", fmt(df).to_string(), flush=True)

up_cc1 = D.cc1 > 0; dn_cc1 = D.cc1 < 0; up_oc1 = D.oc1 > 0; dn_oc1 = D.oc1 < 0
gapup = (D.gap > 0).where(D.gap != 0); gapdn = (D.gap < 0).where(D.gap != 0)
print("gap==0:", (D.gap == 0).sum(), flush=True)
upcc = (D.cc > 0).astype(float).where(D.cc != 0); upoc = (D.oc > 0).astype(float).where(D.oc != 0)

# ---- 1 ----
rows = []
for lab, m in (("D-1 alta (C>C-1)", up_cc1), ("D-1 baixa (C<C-1)", dn_cc1), ("D-1 candle alta (C>O)", up_oc1), ("D-1 candle baixa (C<O)", dn_oc1)):
    rows.append({"evento": "P(gap alta)", **row(lab, m, gapup)})
    rows.append({"evento": "P(gap baixa)", **row(lab, m, gapdn)})
section("1. Direcao de D-1 -> direcao do GAP de abertura (gap==0 excluido)", pd.DataFrame(rows), "1_gap")
rows = []
for w in ("IS", "OOS"):
    s = D[D.win == w]; n = len(s)
    for a, b, lab in ((s.cc1 > 0, s.gap < 0, "D-1 alta E gap baixa"), (s.cc1 < 0, s.gap > 0, "D-1 baixa E gap alta"),
                      (s.cc1 > 0, s.gap > 0, "D-1 alta E gap alta"), (s.cc1 < 0, s.gap < 0, "D-1 baixa E gap baixa")):
        k = int((a & b).sum())
        rows.append({"janela": w, "conjunta": lab, "n": k, "valor": k/n*100, "ic": ic(k, n), "unidade": "% dos dias"})
    rows.append({"janela": w, "conjunta": "gap medio apos D-1 alta", "n": int((s.cc1>0).sum()), "valor": s.gap[s.cc1>0].mean(), "ic": "", "unidade": "pts"})
    rows.append({"janela": w, "conjunta": "gap medio apos D-1 baixa", "n": int((s.cc1<0).sum()), "valor": s.gap[s.cc1<0].mean(), "ic": "", "unidade": "pts"})
    rows.append({"janela": w, "conjunta": "|gap| medio (todos)", "n": n, "valor": s.gap.abs().mean(), "ic": "", "unidade": "pts"})
section("1b. Conjunta e gap medio", pd.DataFrame(rows), "1b_conjunta")

# ---- 2 ----
rows = []
for lab, m in (("D-1 alta cc", up_cc1), ("D-1 baixa cc", dn_cc1), ("D-1 candle alta", up_oc1), ("D-1 candle baixa", dn_oc1)):
    rows.append({"evento": "P(D fecha acima de C-1)", **row(lab, m, upcc)})
    rows.append({"evento": "P(D candle alta, C>O)", **row(lab, m, upoc)})
section("2. Direcao D-1 -> direcao de D", pd.DataFrame(rows), "2_direcao")
rows = []
for w in ("IS", "OOS"):
    s = D[D.win == w]; x = (s.cc / s.atr).values; n = len(x)
    for lagk in range(1, 6):
        a = np.corrcoef(x[lagk:], x[:-lagk])[0, 1]
        rows.append({"janela": w, "lag": lagk, "autocorr": round(a, 3), "nulo_95": f"+-{1.96/math.sqrt(n-lagk):.3f}".replace(".", ","), "n": n})
ac = pd.DataFrame(rows)
ac.to_csv(OUT / "a_2b_autocorr.csv", index=False, sep=";", decimal=",")
doc.write("\n## 2b. Autocorrelacao dos retornos diarios (cc / ATR)\n\n| janela | lag | autocorr | nulo 95% | n |\n|---|---|---|---|---|\n")
for _, r in ac.iterrows(): doc.write(f"| {r.janela} | {r.lag} | {str(r.autocorr).replace('.', ',')} | {r.nulo_95} | {r.n} |\n")
print(ac.to_string(), flush=True)

# ---- 3 ----
qs = D[D.win == "IS"].ccn1.quantile([.2, .4, .6, .8]).values
D["q"] = np.digitize(D.ccn1, qs) + 1
rows = []
for q in range(1, 6):
    m = D.q == q
    rows.append({"evento": "P(D alta cc)", **row(f"Q{q}", m, upcc)})
    rows.append({"evento": "P(D candle alta)", **row(f"Q{q}", m, upoc)})
    rows.append({"evento": "P(gap alta)", **row(f"Q{q}", m, gapup)})
section("3a. Quintis (cortes do IS) do retorno de D-1 / ATR", pd.DataFrame(rows), "3a_quintis", f"Cortes IS (ret/ATR): {np.round(qs,2).tolist()}")
rows = []
for lab, m in (("fechou <20% do range (perto da minima)", D.loc1 < .2), ("20-80% (meio)", (D.loc1 >= .2) & (D.loc1 <= .8)), ("fechou >80% (perto da maxima)", D.loc1 > .8)):
    rows.append({"evento": "P(D alta cc)", **row(lab, m, upcc)})
    rows.append({"evento": "P(D candle alta)", **row(lab, m, upoc)})
    rows.append({"evento": "P(gap alta)", **row(lab, m, gapup)})
section("3b. Posicao do fechamento de D-1 no range de D-1", pd.DataFrame(rows), "3b_closeloc")
rows = []
for q in range(1, 6):
    for w in ("IS", "OOS"):
        s = D[(D.q == q) & (D.win == w)]
        rows.append({"quintil": q, "janela": w, "n": len(s), "cc_D_medio_pts": s.cc.mean(), "ic95_pts": f"+-{1.96*s.cc.std()/math.sqrt(len(s)):.0f}", "media_geral_pts": D[D.win == w].cc.mean(), "oc_D_medio_pts": s.oc.mean()})
section("3c. Retorno medio de D (pontos) por quintil de D-1", pd.DataFrame(rows), "3c_pontos")

# ---- 4 ----
fill = (D.L <= D.Cp).where(D.gap > 0).combine_first((D.H >= D.Cp).where(D.gap < 0))
rows = []
for lab, m in (("gap alta", D.gap > 0), ("gap baixa", D.gap < 0)):
    rows.append({"evento": "P(C>O)", **row(lab, m, upoc)})
    rows.append({"evento": "P(C<O)", **row(lab, m, 1 - upoc)})
    rows.append({"evento": "P(gap fecha no dia)", **row(lab, m, fill)})
section("4a. Gap e o dia (nulo do 'gap fecha' = mistura dos dois sinais)", pd.DataFrame(rows), "4a_gap_dia")
gs = D[(D.win == "IS") & (D.gap != 0)].gapn.abs().quantile([.2, .4, .6, .8]).values
D["gq"] = np.digitize(D.gapn.abs(), gs) + 1
rows = []
for sgn, lab in ((1, "gap alta"), (-1, "gap baixa")):
    for q in range(1, 6):
        m = (np.sign(D.gap) == sgn) & (D.gq == q)
        ev = upoc if sgn > 0 else 1 - upoc
        rows.append({"evento": "P(dia a favor do gap)", **row(f"{lab} Q{q}", m, ev)})
        rows.append({"evento": "P(gap fecha)", **row(f"{lab} Q{q}", m, fill)})
section("4b. Por tamanho do gap (quintis |gap|/ATR do IS)", pd.DataFrame(rows), "4b_gap_tamanho", f"Cortes IS |gap|/ATR: {np.round(gs,3).tolist()}")

# ---- 5 ----
def streak_stats(sign):
    out = {}
    for dirn in (1, -1):
        for k in (2, 3, 4):
            cont = n = 0
            for i in range(k, len(sign)):
                if all(sign[i-j-1] == dirn for j in range(k)):
                    n += 1; cont += sign[i] == dirn
            out[(dirn, k)] = (cont, n)
    return out
rows = []
for w in ("IS", "OOS"):
    sg = np.sign(D[D.win == w].cc.values)
    obs = streak_stats(sg)
    perm = {key: [] for key in obs}
    for _ in range(2000):
        for key, (c, n) in streak_stats(rng.permutation(sg)).items(): perm[key].append(c / n if n else np.nan)
    for key, (c, n) in obs.items():
        pr = c / n; pm = np.array(perm[key])
        pv = (np.sum(np.abs(pm - np.nanmean(pm)) >= abs(pr - np.nanmean(pm))) + 1) / (len(pm) + 1)
        rows.append({"janela": w, "sequencia": f"{key[1]} dias {'alta' if key[0]>0 else 'baixa'}", "n": n, "P_continuar": pr*100, "ic": ic(c, n),
                     "nulo_embaralhado": np.nanmean(pm)*100, "nulo_p2_5_p97_5": f"[{np.nanpercentile(pm,2.5)*100:.1f};{np.nanpercentile(pm,97.5)*100:.1f}]".replace(".", ","), "p_perm": pv})
section("5. Sequencias de dias (cc) vs embaralhamento (2000 permutacoes)", pd.DataFrame(rows), "5_sequencias")

# ---- 6 ----
brk = {}
for day, s in d[d.day.isin(D.index)].groupby("day"):
    hp, lp = D.at[day, "Hp"], D.at[day, "Lp"]
    hh = s.h.values > hp; ll = s.l.values < lp
    brk[day] = (int(np.argmax(hh)) if hh.any() else -1, int(np.argmax(ll)) if ll.any() else -1)
D["hi_i"] = [brk[x][0] for x in D.index]; D["lo_i"] = [brk[x][1] for x in D.index]
D["brkH"] = D.hi_i >= 0; D["brkL"] = D.lo_i >= 0
D["first"] = np.where(D.brkH & ~D.brkL, "H", np.where(~D.brkH & D.brkL, "L",
              np.where(D.brkH & D.brkL, np.where(D.hi_i < D.lo_i, "H", np.where(D.lo_i < D.hi_i, "L", "emp")), "nenhuma")))
rows = []
for lab, m in (("D-1 alta", up_cc1), ("D-1 baixa", dn_cc1)):
    rows.append({"evento": "rompe maxima D-1", **row(lab, m, D.brkH.astype(float))})
    rows.append({"evento": "rompe minima D-1", **row(lab, m, D.brkL.astype(float))})
    rows.append({"evento": "rompe as duas", **row(lab, m, (D.brkH & D.brkL).astype(float))})
section("6a. Rompimento da maxima/minima de D-1 (base = todos os dias)", pd.DataFrame(rows), "6a_rompimento")
rows = []
for w in ("IS", "OOS"):
    s = D[D.win == w]
    for first, lvl, lab in (("H", s.Hp, "rompe maxima primeiro -> fecha acima dela"), ("L", s.Lp, "rompe minima primeiro -> fecha abaixo dela")):
        m = s["first"] == first
        ev = (s.C > lvl) if first == "H" else (s.C < lvl)
        n = int(m.sum()); k = int(ev[m].sum())
        ev2 = (s.C > s.O) if first == "H" else (s.C < s.O)
        rows.append({"janela": w, "evento": lab, "n": n, "taxa": k/n*100, "ic": ic(k, n),
                     "nulo_mesmos_dias_C_a_favor_da_abertura": ev2[m].mean()*100,
                     "nulo_geral_dia_a_favor": ((s.C > s.O) if first == "H" else (s.C < s.O)).mean()*100})
    rows.append({"janela": w, "evento": "sem ordem definida (mesma barra) / nenhuma rompeu", "n": int((s["first"] == "emp").sum()), "taxa": np.nan,
                 "ic": f"nenhuma={int((s['first']=='nenhuma').sum())}", "nulo_mesmos_dias_C_a_favor_da_abertura": np.nan, "nulo_geral_dia_a_favor": np.nan})
section("6b. Rompe o nivel de D-1 primeiro -> fecha alem dele", pd.DataFrame(rows), "6b_fecha_alem", "Se o gap ja abre alem do nivel, o rompimento conta na barra 0.")

(OUT / "a_persistencia_diaria_tabelas.md").write_text(doc.getvalue(), encoding="utf-8")
D.to_csv(OUT / "a_diario.csv", sep=";", decimal=",")
