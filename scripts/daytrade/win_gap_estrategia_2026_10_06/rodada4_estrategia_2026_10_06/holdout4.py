# -*- coding: utf-8 -*-
"""DESCRITIVO. A mesma grade stop x alvo no holdout 2025-12-19..2026-02-19 -- JA GASTO na rodada 3. Nao e' validacao.
Execucao M1 conservadora: stop dentro da faixa da barra do fill = stop acionado; alvo NAO e' creditado na barra do fill;
stop antes do alvo na mesma barra; breakeven e' armado so' com maximas de barras posteriores a do fill e vale da barra seguinte."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "rodada3_holdout_2026_10_06"))
sys.path.insert(0, str(AQUI))
import holdout as H  # noqa: E402  (rodada 3)
import run4 as G  # noqa: E402
import regras as R  # noqa: E402
import sizing as Z  # noqa: E402

TICK, SLIP, PV, FEE = 5.0, 5.0, 0.2, 0.5


def sim(m, side, lim, S, alvo, qty, t_sinal):
    st, o, h, l, c = m["st"], m["o"], m["h"], m["l"], m["c"]
    n = len(st)
    k0 = int(np.searchsorted(st, t_sinal, side="left"))
    k1 = int(np.searchsorted(st, t_sinal + H.TTL_MS, side="left"))
    fk = -1
    for k in range(k0, min(k1, n)):
        if (l[k] <= lim) if side > 0 else (h[k] >= lim):
            fk = k
            break
    if fk < 0:
        return None
    stop = lim - side * S
    tgt = None
    partial = alvo == "P50@1R"
    be = alvo == "BE1R"
    if alvo.startswith("T"):
        tgt = lim + side * float(alvo[1:])
    elif alvo in ("1R", "1.5R", "2R", "3R"):
        tgt = lim + side * S * float(alvo[:-1])
    elif partial:
        tgt = lim + side * S
    legs = []

    def pnl_leg(px, q):
        return ((px - lim) * side * PV - FEE) * q

    if (l[fk] <= stop) if side > 0 else (h[fk] >= stop):
        return dict(pnl=pnl_leg(stop - SLIP * side, qty), worst=(stop - SLIP * side - lim) * side)
    q_open, tot, worst = qty, 0.0, 0.0
    best = lim
    for k in range(fk + 1, n):
        sh = (l[k] <= stop) if side > 0 else (h[k] >= stop)
        th = tgt is not None and ((h[k] >= tgt) if side > 0 else (l[k] <= tgt))
        if sh:
            px = (min(o[k], stop) if side > 0 else max(o[k], stop)) - SLIP * side
            tot += pnl_leg(px, q_open); worst = min(worst, (px - lim) * side)
            return dict(pnl=tot, worst=worst)
        if th:
            px = max(o[k], tgt) if side > 0 else min(o[k], tgt)
            q_t = q_open if (not partial or q_open == 1) else max(1, int(q_open * 0.5))
            tot += pnl_leg(px, q_t); q_open -= q_t; tgt = None
            if q_open <= 0:
                return dict(pnl=tot, worst=worst)
        best = max(best, h[k]) if side > 0 else min(best, l[k])
        if be and (best - lim) * side >= S:
            nv = lim + TICK * side
            if (nv - stop) * side > 0:
                stop = nv
        if k == n - 1:
            px = c[k] - SLIP * side
            tot += pnl_leg(px, q_open); worst = min(worst, (px - lim) * side)
            return dict(pnl=tot, worst=worst)
    return dict(pnl=tot, worst=worst)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    m1 = H.carrega_m1()
    ctx, jan, _ = H.ctx_holdout()
    dias = sorted(ctx)
    q = Z.n_contratos(Z.CAPITAL)
    liq = np.zeros((len(G.STOPS), len(G.ALVOS))); nt = np.zeros_like(liq); win = np.zeros_like(liq)
    ent = G.ENT
    for dia in dias:
        c = ctx[dia]
        s = R.gatilho(c, ent)
        if s == 0:
            continue
        lim = R.limite(c, s, ent["recuo"])
        m = H.dia_m1(m1, dia)
        for ai, a in enumerate(G.ALVOS):
            for si, S in enumerate(G.STOPS):
                r = sim(m, s, lim, float(S), a, q, 32_400_000 + 300_000)
                if r is not None:
                    liq[si, ai] += r["pnl"]; nt[si, ai] += 1; win[si, ai] += r["pnl"] > 0
    rtr = liq / np.where(nt > 0, nt, np.nan)
    def heat(M, fmt, t):
        return t + "\n" + pd.DataFrame(M, index=[f"S{s}" for s in G.STOPS], columns=G.ALVOS).to_string(float_format=fmt)
    print(f"HOLDOUT 2025-12-19..2026-02-19 (JA GASTO na rodada 3; descritivo; M1 conservador; {len(dias)} pregoes, entrada V2 r0, 2 contratos)")
    print("\n" + heat(liq, "{:,.0f}".format, "=== LIQUIDO B (R$) ==="))
    print("\n" + heat(rtr, "{:,.0f}".format, "=== R$ POR TRADE ==="))
    print("\n" + heat(nt, "{:.0f}".format, "=== trades ==="))
    print("\n=== por alvo: stops positivos / 10 e vizinhos de 700 (500,600,800,900) positivos / 4 ===")
    for ai, a in enumerate(G.ALVOS):
        col = liq[:, ai]
        print(f"{a:<8} positivos {int((col>0).sum())}/10 | viz700 {sum(col[j]>0 for j in (2,3,5,6))}/4 | liquido S700 {col[4]:,.0f} | mediana viz {np.median([col[j] for j in (2,3,5,6)]):,.0f}")
    np.save(AQUI / "out" / "holdout4_liq.npy", liq)


if __name__ == "__main__":
    main()
