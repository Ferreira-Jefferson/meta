"""EMA10 + EMA100 em conjunto (M5) sobre win_deslocamento_matinal, IS e OOS, fila P2.
Reaproveita WinMulti e as metricas de run_mm_multi.py."""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import comum as c  # noqa: E402
import run_mm_multi as m  # noqa: E402

CELULAS = {
    "BASE": {},
    "A_e10": dict(periodos=(10,), modo="P"),
    "E100": dict(periodos=(100,), modo="P"),
    "P_10_100": dict(periodos=(10, 100), modo="P"),    # preco do lado das duas
    "O_10_100": dict(periodos=(10, 100), modo="O"),    # EMA10 do lado da EMA100
    "PO_10_100": dict(periodos=(10, 100), modo="PO"),  # as duas condicoes
}
JAN = {"IS": ("2021-10-01", "2024-12-31"), "OOS": ("2025-01-01", "2026-09-30")}


def unid(cid, ini, fim):
    c.WinDeslocamentoMatinal = m.WinMulti
    r = c.unidade("WIN@", ini, fim, {**m.BASE, **CELULAS[cid]}, "P2", True)
    r["cid"] = cid
    return r


def main():
    res = {}
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = {ex.submit(unid, cid, *JAN[j]): (j, cid) for j in JAN for cid in CELULAS}
        for f in as_completed(fut):
            j, cid = fut[f]
            r = f.result()
            res[(j, cid)] = r["trades"]
            p = np.array([t["pnl"] for t in r["trades"]])
            print(f"[{j}] {cid:<10} n={len(p)} liq={p.sum():.1f}", flush=True)
    (HERE / "saida_10_100.json").write_text(
        json.dumps({f"{j}|{cid}": t for (j, cid), t in res.items()}, default=str), encoding="utf-8")

    for j in JAN:
        base = res[(j, "BASE")]
        print(f"\n## {j}\n|celula|n|liq|R$/op|IC95|win%|BE%|payoff|FL|stops (R$)|MaxDD|liq/DD|seq|cortados n|cortados R$|anos")
        for cid in CELULAS:
            t = res[(j, cid)]
            x = m.metr(t)
            cn = m.cortados(base, t) if cid != "BASE" else (0, 0.0, 0)
            anos = {}
            for tr in t:
                anos[tr["entry_ts"][:4]] = anos.get(tr["entry_ts"][:4], 0) + tr["pnl"]
            print(f"|{cid}|{x['n']}|{x['liq']:.0f}|{x['r_op']:.1f}|{x['ic']}|{x['acerto']:.1f}|{x['be']:.1f}|"
                  f"{x['payoff']:.2f}|{x['fator']:.2f}|{x['stops']} ({x['stop_rs']:.0f})|{x['maxdd']:.0f}|{x['fr']:.2f}|"
                  f"{x['seq']}|{cn[0]}|{cn[1]:.0f}|" + " ".join(f"{a}:{v:.0f}" for a, v in sorted(anos.items())), flush=True)


if __name__ == "__main__":
    main()
