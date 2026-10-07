"""Carteira sobre as trades do `qm_core`: dimensionamento por risco, teto de posição,
no máximo N posições, sem alavancagem, marcação a mercado diária (o MaxDD NÃO é o do
realizado — ver `LICOES_DE_PRODUCAO.md`).

Cada trade é independente de capital (retorno em % do nocional + `stop_pct`), então a
geração roda uma vez por (símbolo, parâmetros) e a carteira só empilha.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from qm_core import QmParams


@dataclass
class Result:
    capital: float
    final: float
    net: float
    ret: float
    cagr: float
    maxdd_pct: float
    maxdd_brl: float
    lucro_dd: float
    trades: int
    win: float
    breakeven: float
    mean_r: float
    r_ci: float
    days: int
    skipped: int


def run_portfolio(trades: list[dict], cal: np.ndarray, p: QmParams,
                  lo: np.datetime64, hi: np.datetime64) -> Result:
    """trades: dicts com 'sym','date_e','date_x','ie','ix','entry','stop_pct','ret','path','rank'
    (ie/ix = índices na agenda comum `cal`). Entra só quem tem date_e em [lo, hi]."""
    sel = [t for t in trades if lo <= t["date_e"] <= hi]
    sel.sort(key=lambda t: (t["ie"], -t["rank"]))
    if not sel:
        return Result(p.capital, p.capital, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    i0 = sel[0]["ie"]
    i1 = max(t["ix"] for t in sel)
    daily = np.zeros(i1 - i0 + 2)
    open_pos: list[tuple[int, float]] = []          # (ix, nocional)
    realized = 0.0
    done: list[tuple[int, float]] = []              # (ix, pnl) p/ realizado
    taken, skipped, wins, rs = 0, 0, 0, []
    gains, losses = [], []
    for t in sel:
        ie = t["ie"]
        # fecha o que já saiu antes desta entrada (saída no dia ie libera só depois: conservador)
        still = []
        for ix, nv in open_pos:
            still.append((ix, nv)) if ix >= ie else None
        open_pos = still
        for ix, pnl in [d for d in done if d[0] < ie]:
            realized += pnl
        done = [d for d in done if d[0] >= ie]
        equity = p.capital + realized
        if len(open_pos) >= p.max_positions or equity <= 0:
            skipped += 1
            continue
        risk_brl = equity * p.risk_pct
        notional = min(risk_brl / t["stop_pct"], equity * p.max_pos_pct,
                       equity - sum(nv for _, nv in open_pos))
        shares = math.floor(notional / t["entry"] / p.lot) * p.lot if p.lot > 1 else notional / t["entry"]
        notional = shares * t["entry"]
        if notional <= 0:
            skipped += 1
            continue
        pnl = notional * t["ret"]
        open_pos.append((t["ix"], notional))
        done.append((t["ix"], pnl))
        path = t["path"] * notional
        k = ie - i0
        daily[k:k + len(path)] += np.diff(np.concatenate(([0.0], path)))
        if len(path) and k + len(path) <= len(daily):
            daily[k + len(path):] += 0.0
        taken += 1
        r = t["ret"] / t["stop_pct"]
        rs.append(r)
        (gains if t["ret"] > 0 else losses).append(t["ret"])
        wins += t["ret"] > 0
    # equity: capital + soma acumulada dos incrementos diários (path de trade fechado fica no
    # valor final porque o último incremento já é o retorno líquido)
    eq = p.capital + np.cumsum(daily)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq)
    maxdd_brl = float(dd.max()) if len(dd) else 0.0
    maxdd_pct = float((dd / peak).max()) if len(dd) else 0.0
    final = float(eq[-1])
    net = final - p.capital
    yrs = max((cal[i1] - cal[i0]).astype("timedelta64[D]").astype(int) / 365.25, 1e-9)
    cagr = (final / p.capital) ** (1 / yrs) - 1 if final > 0 else -1.0
    win = wins / taken if taken else 0.0
    ag = float(np.mean(gains)) if gains else 0.0
    al = -float(np.mean(losses)) if losses else 0.0
    be = al / (ag + al) if (ag + al) > 0 else 0.0
    mr = float(np.mean(rs)) if rs else 0.0
    ci = 1.96 * float(np.std(rs, ddof=1)) / math.sqrt(len(rs)) if len(rs) > 1 else 0.0
    return Result(p.capital, final, net, final / p.capital - 1, cagr, maxdd_pct, maxdd_brl,
                  net / maxdd_brl if maxdd_brl > 0 else float("inf") if net > 0 else 0.0,
                  taken, win, be, mr, ci, int(i1 - i0 + 1), skipped)
