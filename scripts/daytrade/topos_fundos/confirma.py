"""Confirmacao na RESERVA (out/2025 a out/2026) + variantes, lado a lado com a pesquisa (2022 a set/2025).

Uso da reserva autorizado pelo dono em 2026-10-08 ("testa, nao precisa me perguntar").
Regra CONGELADA (V1), fixada antes de abrir a reserva:
  WIN M5 intradiario, ZigZag 1,5 ATR, estagio >= 1, entrada na abertura seguinte a confirmacao, stop no pivo
  andando com a estrutura, sem alvo, zera no fim do dia; SO quando o H1 fechado esta a favor (close vs MME34 e
  MME9 vs MME21) E o fechamento da barra de confirmacao esta do lado a favor da abertura do dia.
Variantes (exploratorias, nao confirmam nada sozinhas): M15, so compra, K=3, estagio 0 incluido, alvo fixo 2R/3R,
entrada no rompimento do topo anterior.
"""
import os
import numpy as np
import pandas as pd
import motor
import hipoteses

BASE = "scripts/daytrade/topos_fundos/"
PER = {"pesquisa": dict(src="data/win_sem_leiloes/m1_WIN$N_2022_2025.parquet", ini="2022-01-01", fim="2025-10-01", out=BASE + "res/"),
       "reserva": dict(src="data/win_sem_leiloes/m1_WIN$N.parquet", ini="2025-10-01", fim="2026-10-06", out=BASE + "res_conf/")}
UNIDS = [("M5", "dia", 1.5), ("M15", "dia", 1.5), ("M5", "dia", 3.0), ("M15", "dia", 3.0)]


def preparar(p):
    cfg = PER[p]
    motor.SRC, motor.INI, motor.FIM, motor.OUT = cfg["src"], cfg["ini"], cfg["fim"], cfg["out"]
    hipoteses.R = cfg["out"]
    os.makedirs(cfg["out"], exist_ok=True)
    feats = {}
    for tf, modo, K in UNIDS:
        nome = f"{tf}_{modo}_K{K}"
        if not os.path.exists(cfg["out"] + f"ev_{nome}.pkl"):
            motor.unidade(tf, modo, K)
        fp = cfg["out"] + f"feat0_{nome}.pkl"
        if os.path.exists(fp):
            f = pd.read_pickle(fp)
        else:
            f = hipoteses.features(tf, modo, K, min_est=0)
            ev = pd.read_pickle(cfg["out"] + f"ev_{nome}.pkl")
            for c in ("res", "est", "R", "r2", "r3", "mfe"):
                f[c] = ev.loc[f.idx, c].values
            f.to_pickle(fp)
        feats[nome] = f
    return feats


def linha(rot, x, col="pts"):
    if len(x) < 5:
        return dict(variante=rot, n=len(x))
    v = x[col]
    return dict(variante=rot, n=len(x), acerto=(v > 0).mean(), pts=v.mean(), ic=1.96 * v.std() / np.sqrt(len(x)),
                liq=v.mean() - 10, total_liq=(v - 10).sum(), d_acaso=x.d.mean(), compra=x[x.lado == 1][col].mean(),
                venda=x[x.lado == -1][col].mean())


def variantes(feats):
    out = []
    for nome, f in feats.items():
        f = f.copy()
        f["pts"] = f.res
        f["pts2R"] = f.r2 * f.R
        f["pts3R"] = f.r3 * f.R
        f["ptsRomp"] = f.H10 * (f.R / f.H11)  # H10 esta em ATR; R/H11 = ATR
        filt = (f.H07 == 1) & (f.H13 > 0)
        e1 = f.est >= 1
        tag = nome.replace("_dia", "").replace("_K", " K")
        if nome == "M5_dia_K1.5":
            out.append(linha("V1 CONGELADA: M5 K1,5, est>=1, a favor dos dois", f[e1 & filt]))
            out.append(linha("   referencia: M5 K1,5 est>=1 sem filtro", f[e1]))
            out.append(linha("   referencia: contra os dois", f[e1 & (f.H07 == -1) & (f.H13 < 0)]))
            out.append(linha("V3 so compra", f[e1 & filt & (f.lado == 1)]))
            out.append(linha("V5 inclui estagio 0", f[filt]))
            out.append(linha("V6a alvo fixo 2R (stop fixo)", f[e1 & filt], "pts2R"))
            out.append(linha("V6b alvo fixo 3R (stop fixo)", f[e1 & filt], "pts3R"))
            out.append(linha("V7 entrada no rompimento (nao disparou = 0)", f[e1 & filt], "ptsRomp"))
            out.append(linha("V8 so TF superior a favor", f[e1 & (f.H07 == 1)]))
            out.append(linha("V9 so abertura do dia a favor", f[e1 & (f.H13 > 0)]))
        else:
            out.append(linha(f"V-{tag}: est>=1, a favor dos dois", f[e1 & filt]))
            out.append(linha(f"V-{tag}: so compra", f[e1 & filt & (f.lado == 1)]))
            out.append(linha(f"V-{tag}: alvo 3R", f[e1 & filt], "pts3R"))
    return pd.DataFrame(out)


if __name__ == "__main__":
    res = {}
    for p in ("pesquisa", "reserva"):
        res[p] = variantes(preparar(p))
        print(p, "pronto", flush=True)
    t = res["pesquisa"].merge(res["reserva"], on="variante", suffixes=("_pesq", "_res"))
    t.to_pickle(BASE + "res_conf/confirmacao.pkl")
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30)
    cols = ["variante", "n_pesq", "acerto_pesq", "pts_pesq", "ic_pesq", "liq_pesq", "n_res", "acerto_res", "pts_res", "ic_res",
            "liq_res", "total_liq_res", "d_acaso_res", "compra_res", "venda_res"]
    print(t[cols].round(2).to_string(index=False))
