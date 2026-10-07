"""Resumo da varredura Raschke: configuracao escolhida no IS, julgada no OOS.

Duas leituras, ambas SEM olhar o OOS para escolher:
  A) por GRUPO (classe x timeframe): a configuracao (setup+params+saida) e' escolhida
     pelo expR agregado do IS (n-ponderado, >= --min-n trades) e entao lida no OOS.
  B) por ATIVO: melhor config do IS de cada ativo -> seu OOS.
Tambem imprime o NULO: com N configs por grupo, quantas passam IS>0 e OOS>0 por sorte.

Uso: python -m scripts.raschke.analise [--min-n 100] [--top 8]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SAIDA_DIR = Path(__file__).resolve().parent / "saida"
CHAVE = ["setup", "params", "saida"]


def carregar() -> pd.DataFrame:
    fs = list(SAIDA_DIR.glob("unidade_*.csv"))
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df["grupo"] = df["classe"] + "|" + df["tf"]
    return df


def agrega(g: pd.DataFrame) -> pd.Series:
    out = {}
    for p in ("is", "oos"):
        n = g[f"{p}_n"].sum()
        out[f"{p}_n"] = n
        out[f"{p}_exp_r"] = (g[f"{p}_exp_r"] * g[f"{p}_n"]).sum() / n if n else np.nan
        out[f"{p}_liq"] = g[f"{p}_liq"].sum()
        out[f"{p}_win"] = (g[f"{p}_win"] * g[f"{p}_n"]).sum() / n if n else np.nan
    com = g[(g["oos_n"] >= 5)]
    out["ativos"] = g["ativo"].nunique()
    out["ativos_oos_pos"] = float((com["oos_exp_r"] > 0).mean()) if len(com) else np.nan
    return pd.Series(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=100)
    ap.add_argument("--top", type=int, default=6)
    a = ap.parse_args()
    df = carregar()
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 60)

    print("=" * 100, "\nA) configuracao por GRUPO: escolhida no IS, lida no OOS\n", "=" * 100, sep="")
    resumo = []
    for grupo, g in df.groupby("grupo"):
        t = g.groupby(CHAVE).apply(agrega, include_groups=False).reset_index()
        t = t[t["is_n"] >= a.min_n]
        if t.empty:
            continue
        nulo = ((t["is_exp_r"] > 0) & (t["oos_exp_r"] > 0)).mean()
        top = t.sort_values("is_exp_r", ascending=False).head(a.top)
        top.insert(0, "grupo", grupo)
        top["cfgs"] = len(t)
        top["nulo_is+oos+"] = nulo
        resumo.append(top)
    if resumo:
        r = pd.concat(resumo)
        cols = ["grupo", "setup", "params", "saida", "is_n", "is_exp_r", "is_win", "oos_n", "oos_exp_r",
                "oos_win", "oos_liq", "ativos", "ativos_oos_pos", "cfgs", "nulo_is+oos+"]
        print(r[cols].round(3).to_string(index=False))
        r.to_csv(SAIDA_DIR / "resumo_por_grupo.csv", index=False)

    print("\n" + "=" * 100, "\nB) melhor config do IS de CADA ativo (n_IS>=30, expR_IS>0) -> OOS\n", "=" * 100, sep="")
    ok = df[(df["is_n"] >= 30) & (df["is_exp_r"] > 0)]
    mel = ok.sort_values("is_exp_r", ascending=False).groupby(["ativo", "tf"]).head(1)
    mel = mel.sort_values(["classe", "ativo", "tf"])
    cols = ["ativo", "tf", "setup", "params", "saida", "is_n", "is_exp_r", "is_pf", "oos_n", "oos_exp_r", "oos_pf", "oos_liq"]
    fut = mel[~mel["classe"].eq("acao")]
    print(fut[cols].round(3).to_string(index=False))
    acoes = mel[mel["classe"].eq("acao")]
    if len(acoes):
        v = acoes[acoes["oos_n"] >= 5]
        print(f"\nAcoes: {len(acoes)} com config IS>0; OOS lido em {len(v)}; OOS expR>0 em "
              f"{(v['oos_exp_r'] > 0).mean():.1%}; mediana OOS expR {v['oos_exp_r'].median():+.3f}; "
              f"media {v['oos_exp_r'].mean():+.3f}")
        print(v.groupby("setup")["oos_exp_r"].agg(["count", "median", lambda s: (s > 0).mean()]).round(3).to_string())
    mel.to_csv(SAIDA_DIR / "melhor_por_ativo.csv", index=False)


if __name__ == "__main__":
    main()
