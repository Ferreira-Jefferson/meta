# -*- coding: utf-8 -*-
"""Sensibilidade (NAO e' a celula congelada): o gap do holdout e' PROXY (call = close da ultima barra continua). A serie
WIN@D (M1, ajustada por diferenca) traz o call real na ultima barra M1 (18:24) e o leilao na 1a (09:00): gap_D = open(D) −
close(D−1), rolagens ja' ajustadas. Roda as mesmas celulas, mesma execucao M1, com gap_D no lugar do gap proxy."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import holdout as H  # noqa: E402

ROOT = H.ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    m1 = H.carrega_m1()
    ctx, jan, _ = H.ctx_holdout()
    z = pd.read_csv(ROOT / "data" / "wdo-mt5" / "WIN@D_M1_202110010900_202610011717.csv", sep="\t")
    z.columns = [c.strip("<>").lower() for c in z.columns]
    z.index = pd.to_datetime(z["date"] + " " + z["time"], format="%Y.%m.%d %H:%M:%S")
    z = z[(z.index >= "2025-12-01") & (z.index < "2026-02-21")]
    g = z.groupby(z.index.normalize())
    gd = (g["open"].first() - g["close"].last().shift(1))
    ctx2 = {dia: dict(c, gap=float(gd.loc[pd.Timestamp(dia)])) for dia, c in ctx.items()}
    flips = [str(d) for d in ctx if np.sign(ctx[d]["gap"]) != np.sign(ctx2[d]["gap"])]
    import regras as R
    ent = dict(fam="V2", recuo=0.0)
    trig1 = {d for d in ctx if R.gatilho(ctx[d], ent) != 0}
    trig2 = {d for d in ctx2 if R.gatilho(ctx2[d], ent) != 0}
    mud = [str(d) for d in trig1 ^ trig2]
    dir_mud = [str(d) for d in trig1 & trig2 if R.gatilho(ctx[d], ent) != R.gatilho(ctx2[d], ent)]
    print(f"sinais V2 com gap proxy: {len(trig1)}; com gap WIN@D: {len(trig2)}; dias com gatilho diferente: {len(mud)}; dias com sinal do gap invertido: {len(flips)} {flips}")
    print(f"dias de gatilho em ambos com DIRECAO diferente: {len(dir_mud)}")
    for cid in H.CELULAS:
        for fill in H.FILLS[:1]:
            B, A, dias = H.roda_janela(m1, ctx2, cid, fill)
            nl = H.nulo(B)
            r = H.resumo(B, A, dias, nl, "HOLDOUT gap WIN@D")
            print(f"{cid:<17} gap WIN@D: sinais {r['sinais']} fills {r['fills']} liquido B {r['liquido']:,.0f} R$/trade {r['r_trade']:.1f} win {r['win']:.1f}% BE {r['be']:.1f}% p nulo {nl['p']:.3f} nulo medio {nl['mu']:.0f} [{nl['p5']:.0f};{nl['p95']:.0f}] | A: liquido {r['A_liq']:,.0f} recusadas {r['A_recus']} caixa min {r['A_min_eq']:.0f} censurada={r['A_cens']} | pior {r['pior_pts']:.0f} pts ({r['pior_mult']:.2f}x)")


if __name__ == "__main__":
    main()
