"""Seleciona geometria/lambda/grupos SO com jan-jun (CV por mes) e CONGELA modelo + limiar ANTES de olhar jul-ago."""
import json, datetime
import numpy as np, pandas as pd
from lib import *
from pipe import *

C, Y, PN, EX = carregar()
assert True
X = construir_X(C)
mes = C.mes.values; mi = C["mi"].values; recuo = C["recuo"].values
esc = json.load(open(PASTA + "variantes_escolhidas.json"))
cols_all = [c for f, c in esc.items() if not f.startswith("ctrl_")]
df = pd.read_csv(PASTA + "geometrias_cv_janjun.csv")
ok = df[df.n >= 250]
sel = ok.sort_values("esp_top_suav", ascending=False).iloc[0]
k5 = ok[ok.K == 5].sort_values("esp_top_suav", ascending=False).iloc[0]
configs = {
    "SEL": dict(m=int(sel.m), S=int(sel.S), N=int(sel.N), piso=float(sel.piso), K=int(sel.K)),
    "K5": dict(m=int(k5.m), S=int(k5.S), N=int(k5.N), piso=float(k5.piso), K=int(k5.K)),
    "REF": dict(REF),
}
print("configs", configs, flush=True)
LAMS = (3, 10, 30, 100, 300, 1000)
GRP = ["relogio", "volatilidade", "estrutura", "esticamento", "micro", "fluxo", "medias", "dia"]
out = {"criado_em": datetime.datetime.now().isoformat(timespec="seconds"),
       "nota": "Congelado ANTES de qualquer leitura de jul-ago/set. Treino/CV so jan-jun.", "modelos": {}}
for nome, g in configs.items():
    a, b, k = NS.index(g["N"]), PISOS.index(g["piso"]), KS.index(g["K"])
    sel_rows = (mes <= 6) & (recuo >= g["m"]) & (mi % g["S"] == 0) & (Y[:, a, b, k, 0] >= 0)
    idx = np.where(sel_rows)[0]
    y = Y[idx, a, b, k, 0].astype(float); pn = PN[idx, a, b, k, 0]; ms = mes[idx]
    print(f"\n=== {nome} {g} n={len(idx)} base={y.mean():.4f} BE emp={breakeven_emp(pn, y):.4f}", flush=True)
    # lambda
    cols = list(cols_all)
    res = {}
    for lam in LAMS:
        o = oof_lomo(X.loc[X.index[idx], cols].values, y, ms, lam)
        r = resumo_oof(o, y, pn, ms)
        res[lam] = r
        print(f"  lam={lam:5d} AUC {r['auc']:.4f} AUCmes {r['auc_mes']:.4f} top20 acerto {r['acerto_top']:.3f} BE {r['be_top']:.3f} esp {r['esp_top']:+.1f}", flush=True)
    lam = max(LAMS, key=lambda l: res[l]["auc"])
    # ablacao em CV + eliminacao regressiva por grupo
    def auc_cv(cs):
        o = oof_lomo(X.loc[X.index[idx], cs].values, y, ms, lam)
        return resumo_oof(o, y, pn, ms)
    base_r = auc_cv(cols)
    print("  ablacao CV (AUC sem o grupo):", flush=True)
    abl = {}
    for gr in GRP:
        cs = [c for c in cols if GRUPOS[c] != gr]
        r = auc_cv(cs); abl[gr] = (r["auc"], r["esp_top"])
        print(f"    sem {gr:13s} AUC {r['auc']:.4f} ({r['auc']-base_r['auc']:+.4f}) esp_top {r['esp_top']:+.1f}", flush=True)
    atuais = list(GRP); auc_atual = base_r["auc"]
    while len(atuais) > 1:
        cand = []
        for gr in atuais:
            cs = [c for c in cols if GRUPOS[c] in atuais and GRUPOS[c] != gr]
            cand.append((auc_cv(cs)["auc"], gr))
        best = max(cand)
        if best[0] - auc_atual >= -0.002:
            atuais.remove(best[1]); auc_atual = best[0]
            print(f"  elimina grupo {best[1]} -> AUC {auc_atual:.4f}", flush=True)
        else:
            break
    cols_f = [c for c in cols if GRUPOS[c] in atuais]
    o = oof_lomo(X.loc[X.index[idx], cols_f].values, y, ms, lam)
    r = resumo_oof(o, y, pn, ms)
    ok_o = ~np.isnan(o)
    th10, th20 = float(np.quantile(o[ok_o], 0.90)), float(np.quantile(o[ok_o], 0.80))
    print(f"  FINAL grupos={atuais} cols={len(cols_f)} lam={lam} AUC_CV {r['auc']:.4f} top20 acerto {r['acerto_top']:.3f} BE {r['be_top']:.3f} esp {r['esp_top']:+.1f} | th90={th10:.4f} th80={th20:.4f}", flush=True)
    # decis OOF
    dec = pd.qcut(o[ok_o], 10, labels=False, duplicates="drop")
    print("  decis OOF (prev media / acerto / esp pts):", [(round(float(o[ok_o][dec == d].mean()), 3), round(float(y[ok_o][dec == d].mean()), 3), round(float(pn[ok_o][dec == d].mean()), 1)) for d in range(10)], flush=True)
    Pd, w = ajusta(X.loc[X.index[idx], cols_f].values, y, lam)
    out["modelos"][nome] = dict(geom=g, cols=cols_f, grupos=atuais, lam=lam, w=w.tolist(), med=Pd.med.tolist(), lo=Pd.lo.tolist(),
                                hi=Pd.hi.tolist(), mu=Pd.mu.tolist(), sd=Pd.sd.tolist(), th90=th10, th80=th20,
                                n_treino=int(len(idx)), base_treino=float(y.mean()), be_treino=float(breakeven_emp(pn, y)),
                                cv=dict(auc=r["auc"], acerto_top20=r["acerto_top"], be_top20=r["be_top"], esp_top20=r["esp_top"]),
                                ablacao_cv={k_: list(v) for k_, v in abl.items()})
json.dump(out, open(PASTA + "congelado_ANTES_da_confirmacao.json", "w"), indent=1)
print("\nCONGELADO.", flush=True)
