"""Varredura de paridades do Qullamaggie, IS x OOS, em B3 (ações, índices, cripto).

Protocolo (congelado ANTES de olhar resultado):
  * IS  = ações B3, entradas 2010-01-01..2019-12-31  -> onde se ESCOLHE a célula
  * OOS = ações B3, entradas 2020-01-01..fim          -> lido uma vez, nunca escolhe
  * índices e cripto B3 (ETFs de Bitcoin da Rico): janela inteira, mesma célula, só leitura
    (universo diferente do da otimização = teste de transferência, não de ajuste)
Capital real do instrumento: ver `--capital`. Um robô por símbolo (NETTING), carteira
com risco fixo por trade, teto por posição, N posições, sem alavancagem.

Paralelismo: ProcessPoolExecutor + submit/as_completed, cada unidade imprime assim que
termina (CLAUDE.md). Workers limitados (RAM) — default 4.
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from qm_core import QmParams, make_arrays, trades_for_symbol          # noqa: E402
from qm_portfolio import run_portfolio                               # noqa: E402

RAW = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")
DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "qullamaggie")
IS = (np.datetime64("2010-01-01"), np.datetime64("2019-12-31"))
OOS = (np.datetime64("2020-01-01"), np.datetime64("2099-01-01"))
FULL = (np.datetime64("1990-01-01"), np.datetime64("2099-01-01"))

# relaxamentos por classe (ETF de índice quase nunca tem ADR de 4%; ETFs de cripto são pouco líquidos)
CLASS_OVERRIDE = {"acao": {}, "indice": {"adr_min": 0.015, "min_dvol": 1e6}, "cripto": {"min_dvol": 1e6}}

_CACHE: dict = {}


def load_universe():
    if _CACHE:
        return _CACHE
    u = pd.read_csv(os.path.join(DATA, "_universo.csv"))
    cls = {r.sym.replace("@", "_"): r.classe for r in u.itertuples()}
    syms, dates = {}, []
    # ações: yfinance (data/raw, 2010-2026) — o terminal da Rico só guarda ~5 anos de D1
    for f in sorted(os.listdir(RAW)):
        if not f.endswith("_SA.parquet"):
            continue
        s = f[:-len("_SA.parquet")]
        if s in {"BOVA11", "GOLD11", "IMAB11"}:        # ETFs: entram como índice, via MT5
            continue
        a = make_arrays(pd.read_parquet(os.path.join(RAW, f)))
        if len(a["c"]) >= 200:
            syms[s] = ("acao", a)
            dates.append(a["date"])
    # índices e cripto: MT5 da Rico (é o que a corretora opera de verdade)
    for f in sorted(os.listdir(DATA)):
        s = f[:-8]
        if not f.endswith(".parquet") or "_" in s or cls.get(s, "acao") == "acao":
            continue
        a = make_arrays(pd.read_parquet(os.path.join(DATA, f)))
        if len(a["c"]) >= 200:
            syms[s] = (cls[s], a)
            dates.append(a["date"])
    cal = np.unique(np.concatenate(dates))
    _CACHE.update(syms=syms, cal=cal)
    return _CACHE


def collect(p: QmParams, setup: str, klass: str):
    U = load_universe()
    cal = U["cal"]
    out = []
    pp = p.with_(**CLASS_OVERRIDE[klass])
    for s, (k, a) in U["syms"].items():
        if k != klass:
            continue
        for t in trades_for_symbol(a, pp, setup):
            e, x = t["e"], t["x"]
            t["sym"], t["date_e"], t["date_x"] = s, a["date"][e], a["date"][x]
            t["ie"], t["ix"] = int(np.searchsorted(cal, t["date_e"])), int(np.searchsorted(cal, t["date_x"]))
            t["rank"] = a["c"][e - 1] / a["c"][max(e - 64, 0)] - 1.0
            out.append(t)
    return out


def row(tag, cell, res):
    return dict(grupo=tag, **cell, retorno=res.ret, liquido=res.net, maxdd_pct=res.maxdd_pct,
                maxdd_brl=res.maxdd_brl, lucro_dd=res.lucro_dd, win=res.win, breakeven=res.breakeven,
                trades=res.trades, r_medio=res.mean_r, r_ic=res.r_ci, final=res.final, cagr=res.cagr)


def unit(setup: str, entry_cfg: dict, exit_cfgs: list[dict], capital: float):
    rows = []
    for ex in exit_cfgs:
        cell = {**entry_cfg, **ex}
        p = QmParams(capital=capital, **cell)
        tr = collect(p, setup, "acao")
        cal = load_universe()["cal"]
        rows.append(row("acoes_IS", cell, run_portfolio(tr, cal, p, *IS)))
        rows.append(row("acoes_OOS", cell, run_portfolio(tr, cal, p, *OOS)))
        for klass in ("indice", "cripto"):
            t2 = collect(p, setup, klass)
            rows.append(row(klass, cell, run_portfolio(t2, cal, p.with_(**CLASS_OVERRIDE[klass]), *FULL)))
    return rows


GRIDS = {
    "breakout": (
        dict(consol_bars=[7, 10, 15, 20], adr_min=[0.03, 0.04, 0.05], pm_min=[0.30, 0.50],
             stop_bars=[1, 3, 5], stop_adr_max=[0.75, 1.0, 1.5]),
        dict(partial_days=[3, 5], partial_frac=[1 / 3, 0.5], trail_ma=[10, 20]),
    ),
    "ep": (
        dict(ep_gap=[0.08, 0.10, 0.15], ep_neglect_max=[0.0, 0.20, 0.50], ep_confirm=[0.0, 0.01, 0.02],
             ep_stop_adr=[0.5, 1.0, 1.5]),
        dict(partial_days=[3, 5], partial_frac=[1 / 3, 0.5], trail_ma=[10, 20]),
    ),
    "para": (
        dict(para_move=[0.20, 0.30, 0.50], para_up_days=[3, 4], para_confirm=[0.0, 0.01],
             para_stop_adr=[0.5, 1.0], para_target_ma=[10, 20]),
        dict(para_max_hold=[5, 10, 20]),
    ),
}


def expand(d):
    ks = list(d)
    return [dict(zip(ks, v)) for v in itertools.product(*d.values())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", choices=list(GRIDS), default="breakout")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--limit", type=int, default=0, help="só as N primeiras unidades (smoke)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    eg, xg = GRIDS[a.setup]
    entries, exits = expand(eg), expand(xg)
    if a.limit:
        entries = entries[:a.limit]
    out = a.out or os.path.join(os.path.dirname(__file__), f"resultado_{a.setup}.csv")
    print(f"{a.setup}: {len(entries)} unidades x {len(exits)} saídas = {len(entries) * len(exits)} células x 4 grupos",
          flush=True)
    t0, allrows = time.time(), []
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(unit, a.setup, e, exits, a.capital): i for i, e in enumerate(entries)}
        for k, f in enumerate(as_completed(futs), 1):
            rows = f.result()
            allrows += rows
            pd.DataFrame(allrows).to_csv(out, index=False)
            best = max((r for r in rows if r["grupo"] == "acoes_IS"), key=lambda r: r["lucro_dd"])
            print(f"[{k}/{len(entries)}] {time.time() - t0:5.0f}s  melhor IS da unidade: lucro/DD "
                  f"{best['lucro_dd']:.2f} trades {best['trades']}", flush=True)
    print("gravado", out, flush=True)


if __name__ == "__main__":
    main()
