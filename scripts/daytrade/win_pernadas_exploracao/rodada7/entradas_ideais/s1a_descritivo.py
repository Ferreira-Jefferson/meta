"""Passo 3 (descritivo, SO jan-jun) na geometria de referencia + curvas de sensibilidade + selecao de variantes."""
import json, sys
import numpy as np, pandas as pd
from lib import *
from pipe import *

C, Y, PN, EX = carregar()
X = construir_X(C)
mes = C.mes.values; dias = C.dia.values
iN, iP, iK = NS.index(REF["N"]), PISOS.index(REF["piso"]), KS.index(REF["K"])
g = (mes <= 6) & mask_geom(C, REF["m"], REF["S"])
yw = np.where(Y[:, iN, iP, iK, 0] >= 0, Y[:, iN, iP, iK, 0], np.nan).astype(float)
yc = np.where(Y[:, iN, iP, iK, 1] >= 0, Y[:, iN, iP, iK, 1], np.nan).astype(float)
ok = g & ~np.isnan(yw)
print("geometria ref", REF, "n", ok.sum(), "base a favor %.2f%%" % (100 * np.nanmean(yw[ok])),
      "base contra %.2f%%" % (100 * np.nanmean(yc[g & ~np.isnan(yc)])), flush=True)
base = float(np.nanmean(yw[ok]))

sc_w = score_variantes(X, yw, mes, ok)
sc_c = score_variantes(X, yc, mes, g)
linhas = []
for col in X.columns:
    v = X[col].values
    aw = auc(yw[ok], v[ok]); ac = auc(yc[g & ~np.isnan(yc)], v[g & ~np.isnan(yc)])
    mu, sd, sg = sc_w[col]
    linhas.append(dict(variante=col, familia=[f for f, cs in FAMILIAS.items() if col in cs][0], grupo=GRUPOS[col],
                       auc_favor=aw, auc_contra=ac, auc_mes_med=mu, auc_mes_dp=sd,
                       meses_mesmo_sinal=int(sum(1 for m in MESES_TR if (lambda k: k.sum() > 30 and len(np.unique(yw[k])) > 1 and np.sign(auc(yw[k], v[k]) - .5) == np.sign(aw - .5))(ok & (mes == m))))))
U = pd.DataFrame(linhas)
U["dir_ou_so_anda"] = np.where((U.auc_favor - .5) * (U.auc_contra - .5) > 0, "ANDA(ambos)", "DIRECAO")
U.to_csv(PASTA + "univariado_ref.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(U.round(3).sort_values("familia").to_string(index=False), flush=True)

# --- quintis das variantes mais fortes
print("\n== quintis (acerto a favor, geometria ref, jan-jun; IC95 por bootstrap de dias; base %.2f%%) ==" % (100 * base))
top = U.assign(f=(U.auc_favor - .5).abs()).sort_values("f", ascending=False).head(14)
for col in top.variante:
    v = X[col].values
    if len(np.unique(v[ok & ~np.isnan(v)])) < 6:
        cats = [(f"={u}", ok & (v == u)) for u in np.unique(v[ok & ~np.isnan(v)])]
    else:
        qs = np.nanquantile(v[ok], [0, .2, .4, .6, .8, 1])
        cats = [(f"Q{i+1}", ok & (v >= qs[i]) & ((v < qs[i + 1]) if i < 4 else (v <= qs[i + 1]))) for i in range(5)]
    out = []
    for nome, k in cats:
        lo, hi = boot_dias(yw[k], dias[k], B=400)
        out.append(f"{nome}:{100*yw[k].mean():.1f}% [{100*lo:.1f};{100*hi:.1f}] n={int(k.sum())}")
    print(col, " | ".join(out))

# --- curvas de sensibilidade: limiares nas features cruas
print("\n== sensibilidade a limiares (acerto condicional - base, por mes: n de meses com lift>0), a favor ==")
def cond(nome, k):
    k = k & ok
    if k.sum() < 40:
        print(f"{nome:42s} n={int(k.sum())} (pouco)"); return
    lift = [np.nanmean(yw[k & (mes == m)]) - np.nanmean(yw[ok & (mes == m)]) for m in MESES_TR if (k & (mes == m)).sum() > 5]
    lo, hi = boot_dias(yw[k], dias[k], B=400)
    print(f"{nome:42s} n={int(k.sum()):5d} acerto {100*yw[k].mean():5.1f}% [{100*lo:.1f};{100*hi:.1f}] lift {100*(yw[k].mean()-base):+5.1f}pp meses+ {sum(1 for x in lift if x>0)}/{len(lift)}")
for w in (5, 10, 20, 30):
    for t in (1.5, 2.0, 2.5, 3.0):
        cond(f"vela M1 >= {t}x (max {w} velas)", np.exp(X[f"vela_{w}"].values) >= t)
for w in (10, 20, 30, 60):
    for t in (100, 150, 200, 300):
        cond(f"caixa <= {t} pts em {w} min", np.expm1(X[f"caixa_{w}"].values) <= t)
for w in (5, 10, 15, 20):
    v = X[f"saldo_{w}"].values
    for q in (0.8, 0.9):
        cond(f"saldo {w} velas >= q{int(q*100)}", v >= np.nanquantile(v[ok], q))
    cond(f"saldo {w} velas <= q20", v <= np.nanquantile(v[ok], 0.2))
for nm in "abcd":
    cond(f"raso_{nm}", X[f"raso_{nm}"].values == 1)
for thr in (1.0, 1.5, 2.0):
    for rise in (200, 300, 400):
        cond(f"esticado continua (dVWAP>{thr}ATR, sub30>={rise})", X[f"estic_{thr}_{rise}"].values == 1)
for w in (5, 10, 15, 30, 60):
    v = X[f"onda_{w}"].values
    cond(f"onda {w} min >= q80", v >= np.nanquantile(v[ok], 0.8))
    cond(f"onda {w} min <= q20", v <= np.nanquantile(v[ok], 0.2))
cond("manha (<11h aj.)", X["manha"].values == 1); cond("tarde (>=13h aj.)", X["tarde"].values == 1)
cond("meio (11-13h aj.)", (X["manha"].values == 0) & (X["tarde"].values == 0))
for tf in ("M5", "M15", "H1"):
    for st in ("s1", "s2", "s3", "s4"):
        cond(f"EMA {tf} {st} alinhadas a favor (al=1)", X[f"emaal_{tf}_{st}"].values == 1)
        cond(f"EMA {tf} {st} alinhadas contra (al=-1)", X[f"emaal_{tf}_{st}"].values == -1)

# --- selecao de variantes (platô) + correlacoes
esc, sc = selecionar_variantes(X, yw, mes, ok)
print("\n== variantes escolhidas por familia (plato, jan-jun) ==")
for f, c in esc.items():
    print(f"{f:18s} -> {c}")
cols = list(esc.values())
cm = X.loc[ok, cols].corr(method="spearman")
pares = [(cols[i], cols[j], cm.iloc[i, j]) for i in range(len(cols)) for j in range(i + 1, len(cols)) if abs(cm.iloc[i, j]) >= 0.6]
print("\n== pares redundantes (|rho spearman| >= 0,6) entre as variantes escolhidas ==")
for a, b, r in sorted(pares, key=lambda t: -abs(t[2])):
    print(f"{a:16s} {b:16s} {r:+.2f}")
json.dump(esc, open(PASTA + "variantes_escolhidas.json", "w"), indent=1)
print("\nnum variantes na biblioteca:", X.shape[1], "familias:", len(FAMILIAS))
