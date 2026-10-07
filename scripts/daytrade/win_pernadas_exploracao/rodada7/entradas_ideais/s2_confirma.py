"""Confirmacao FORA DA AMOSTRA (jul-ago e set) com modelos/limiares congelados. Roda uma vez, apos o congelamento."""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/decisao")
import motor
from lib import *
from pipe import *

C, Y, PN, EX = carregar()
X = construir_X(C)
mes = C.mes.values; mi = C["mi"].values; recuo = C["recuo"].values; dias = C.dia.values
gi = C["gi"].values.astype(int)
cong = json.load(open(PASTA + "congelado_ANTES_da_confirmacao.json"))["modelos"]
rng = np.random.default_rng(123)


def prever(mod, rows, cols=None, W=None):
    cols = cols or mod["cols"]
    P = Padroniza()
    P.med, P.lo, P.hi, P.mu, P.sd = (np.array(mod[k]) for k in ("med", "lo", "hi", "mu", "sd"))
    return preve(P, np.array(mod["w"]), X.loc[X.index[rows], cols].values)


def sem_sobreposicao(rows, p, th, ex_idx):
    """Entradas sequenciais: so entra se nao ha posicao aberta (motor nao piramida). rows ordenados no tempo."""
    sel, livre_ate = [], -1
    ordem = np.argsort(gi[rows], kind="stable")
    for o in ordem:
        if p[o] >= th and gi[rows[o]] > livre_ate:
            sel.append(o); livre_ate = ex_idx[o]
    return np.array(sel, int)


def seq_perdas(pn):
    mx = cur = 0
    for v in pn:
        cur = cur + 1 if v <= 0 else 0
        mx = max(mx, cur)
    return mx


for nome, mod in cong.items():
    g = mod["geom"]
    a, b, k = NS.index(g["N"]), PISOS.index(g["piso"]), KS.index(g["K"])
    print(f"\n################ {nome} {g} (grupos {mod['grupos']}, lam {mod['lam']}, th90 {mod['th90']:.4f}, th80 {mod['th80']:.4f})", flush=True)
    for janela, ms_ in (("jul-ago", (7, 8)), ("set", (9,))):
        sel = np.isin(mes, ms_) & (recuo >= g["m"]) & (mi % g["S"] == 0) & (Y[:, a, b, k, 0] >= 0)
        rows = np.where(sel)[0]
        y = Y[rows, a, b, k, 0].astype(float); pn = PN[rows, a, b, k, 0]; ex_ = EX[rows, a, b, k, 0]; dd = dias[rows]
        p = prever(mod, rows)
        print(f"\n--- {janela}: n={len(rows)} dias={len(np.unique(dd))} base {y.mean():.4f} BE emp {breakeven_emp(pn, y):.4f} esp {pn.mean():+.1f} pts/op AUC {auc(y, p):.4f}", flush=True)
        # calibracao em decis (decis da propria janela)
        dec = pd.qcut(p, 10, labels=False, duplicates="drop")
        print("decil | prev | acerto | esp pts | n")
        for d in range(dec.max() + 1):
            kk = dec == d
            print(f"  {d+1:2d}  {p[kk].mean():.3f}  {y[kk].mean():.3f}  {pn[kk].mean():+7.1f}  {int(kk.sum())}")
        for lbl, th in (("top10% (th90 congelado)", mod["th90"]), ("top20% (th80 congelado)", mod["th80"])):
            kk = p >= th
            if kk.sum() < 5:
                print(f"  {lbl}: n={int(kk.sum())}"); continue
            lo_a, hi_a = boot_dias(y[kk], dd[kk], B=1000)
            lo_e, hi_e = boot_dias(pn[kk], dd[kk], B=1000)
            beE = breakeven_emp(pn[kk], y[kk])
            print(f"  {lbl}: n={int(kk.sum())} ({kk.sum()/len(np.unique(dd)):.2f}/dia) acerto {y[kk].mean():.3f} [{lo_a:.3f};{hi_a:.3f}] BE emp {beE:.3f} esp {pn[kk].mean():+.1f} pts/op [{lo_e:+.1f};{hi_e:+.1f}]  (base {y.mean():.3f})", flush=True)
            s = sem_sobreposicao(rows, p, th, ex_)
            if len(s):
                pns = pn[s]; ys = y[s]
                print(f"     sem sobreposicao: n={len(s)} ({len(s)/len(np.unique(dd)):.2f}/dia) acerto {ys.mean():.3f} esp {pns.mean():+.1f} pts/op, soma {pns.sum():+.0f} pts, pior sequencia de perdas {seq_perdas(pns)}", flush=True)
        # nulo: rotulos embaralhados por blocos de dias, AUC do modelo congelado
        ud = np.unique(dd); aucs = []
        for _ in range(500):
            blocos = np.array_split(rng.permutation(ud), max(1, len(ud) // 5))
            yp = y.copy()
            for bl in blocos:
                r_ = np.where(np.isin(dd, bl))[0]
                yp[r_] = y[rng.permutation(r_)]
            aucs.append(auc(yp, p))
        print(f"  nulo (rotulos embaralhados em blocos de ~5 dias, 500x): AUC {np.mean(aucs):.3f} dp {np.std(aucs):.3f} p95 {np.percentile(aucs,95):.3f}; AUC real {auc(y, p):.3f}", flush=True)

    # ablacao: re-treina em jan-jun sem cada grupo, avalia em jul-ago (diagnostico)
    tr = (mes <= 6) & (recuo >= g["m"]) & (mi % g["S"] == 0) & (Y[:, a, b, k, 0] >= 0)
    te = np.isin(mes, (7, 8)) & (recuo >= g["m"]) & (mi % g["S"] == 0) & (Y[:, a, b, k, 0] >= 0)
    itr, ite = np.where(tr)[0], np.where(te)[0]
    ytr, yte, pnte = Y[itr, a, b, k, 0].astype(float), Y[ite, a, b, k, 0].astype(float), PN[ite, a, b, k, 0]
    print(f"\n  ABLACAO (treino jan-jun sem o grupo -> jul-ago): AUC / top20% acerto / esp pts")
    for gr in [None] + list(mod["grupos"]):
        cs = [c for c in mod["cols"] if GRUPOS[c] != gr]
        Pd, w = ajusta(X.loc[X.index[itr], cs].values, ytr, mod["lam"])
        pp = preve(Pd, w, X.loc[X.index[ite], cs].values)
        th = np.quantile(pp, 0.8); kk = pp >= th
        print(f"    sem {str(gr):13s} AUC {auc(yte, pp):.4f}  top20 acerto {yte[kk].mean():.3f} esp {pnte[kk].mean():+.1f} (n={int(kk.sum())})", flush=True)

    # motor: fatia superior (th80) pooled jul-set, sem sobreposicao
    sel = (mes >= 7) & (recuo >= g["m"]) & (mi % g["S"] == 0) & (Y[:, a, b, k, 0] >= 0)
    rows = np.where(sel)[0]
    y = Y[rows, a, b, k, 0].astype(float); pn = PN[rows, a, b, k, 0]; ex_ = EX[rows, a, b, k, 0]
    p = prever(mod, rows)
    for lbl, th in (("th90", mod["th90"]), ("th80", mod["th80"])):
        s = sem_sobreposicao(rows, p, th, ex_)
        if len(s) < 10:
            print(f"  motor {lbl}: n={len(s)}"); continue
        pns, ys = pn[s], y[s]
        gan = float(pns[ys == 1].mean()) if (ys == 1).any() else 0.0
        per = float(-pns[ys == 0].mean())
        pb = mod["base_treino"]
        pe = motor.p_encolhido(int(ys.sum()), len(ys), pb)
        n_c = motor.tamanho(pe, gan, per, 250.0)
        mc = motor.ruina_mc(pns * motor.VALOR_PONTO, None, 250.0, n_ops=min(300, max(50, len(s))), n_caminhos=4000, seed=1)
        print(f"  motor {lbl} (jul-set, sem sobreposicao): n={len(s)} acerto {ys.mean():.3f} (base treino {pb:.3f}) p_encolhido {pe:.3f} ganho {gan:.0f} perda {per:.0f} BE {motor.breakeven_p(gan, per):.3f} esp {pns.mean():+.1f} pts/op -> contratos (R$250) {n_c}; ruina MC 1 contrato {mc['p_ruina']:.2f} (t mediano {mc['t_mediano']})", flush=True)
