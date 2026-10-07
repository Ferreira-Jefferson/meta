"""Alvo em multiplos do stop (R) sobre win_deslocamento_matinal: sem alvo x 1R, 1,5R, 2R, 3R.
Alvo = ordem-limite real fatiada (desenho fechado), stop e entrada iguais. IS e OOS, fila P2."""
from __future__ import annotations

import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import comum as c  # noqa: E402
import run_mm_multi as m  # noqa: E402
from strategy.daytrade.lab.win_deslocamento_matinal import EXIT_TTL_BARS_SEM_PRAZO  # noqa: E402


@dataclass
class WinAlvoR(c.WinDeslocamentoMatinal):
    alvo_r: float = 0.0   # 0 = sem alvo (sai no stop ou no fim do pregao)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        acts = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acts or self.alvo_r <= 0:
            return acts
        a = acts[0]
        lado = 1.0 if a.side == "long" else -1.0
        dist = abs(a.limit_price - a.initial_stop)
        alvo = c.no_tick(a.limit_price + lado * self.alvo_r * dist, self.tick_size) if hasattr(c, "no_tick") else \
            round((a.limit_price + lado * self.alvo_r * dist) / self.tick_size) * self.tick_size
        return [dataclasses.replace(a, initial_target=alvo, exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO)]


CELULAS = {"sem_alvo": 0.0, "1R": 1.0, "1,5R": 1.5, "2R": 2.0, "3R": 3.0}
JAN = {"IS": ("2021-10-01", "2024-12-31"), "OOS": ("2025-01-01", "2026-09-30")}
BASE = dict(desloc_min_atr=0.3, stop_atr=None, alvo_atr=None)


def unid(cid, ini, fim):
    c.WinDeslocamentoMatinal = WinAlvoR
    r = c.unidade("WIN@", ini, fim, {**BASE, "alvo_r": CELULAS[cid]}, "P2", True)
    return r["trades"]


def main():
    res = {}
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = {ex.submit(unid, cid, *JAN[j]): (j, cid) for j in JAN for cid in CELULAS}
        for f in as_completed(fut):
            j, cid = fut[f]
            res[(j, cid)] = f.result()
            p = np.array([t["pnl"] for t in res[(j, cid)]])
            print(f"[{j}] {cid:<8} n={len(p)} liq={p.sum():.1f}", flush=True)
    (HERE / "saida_alvo_r.json").write_text(json.dumps({f"{j}|{k}": v for (j, k), v in res.items()}, default=str),
                                            encoding="utf-8")
    for j in JAN:
        print(f"\n## {j}\n|alvo|n|liq|R$/op|IC95|acerto|BE|ganho med|perda med|payoff|FL|alvos|stops|fim do dia|MaxDD|liq/DD|anos")
        for cid in CELULAS:
            t = res[(j, cid)]
            x = m.metr(t)
            alvos = sum(1 for z in t if z["reason"] not in ("STOP", "FORCED_FLATTEN"))
            fim = sum(1 for z in t if z["reason"] == "FORCED_FLATTEN")
            anos = {}
            for z in t:
                anos[z["entry_ts"][:4]] = anos.get(z["entry_ts"][:4], 0) + z["pnl"]
            print(f"|{cid}|{x['n']}|{x['liq']:.0f}|{x['r_op']:.1f}|{x['ic']}|{x['acerto']:.1f}|{x['be']:.1f}|{x['gan']:.0f}|"
                  f"{-x['perda']:.0f}|{x['payoff']:.2f}|{x['fator']:.2f}|{alvos}|{x['stops']}|{fim}|{x['maxdd']:.0f}|{x['fr']:.2f}|"
                  + " ".join(f"{a}:{v:.0f}" for a, v in sorted(anos.items())), flush=True)


if __name__ == "__main__":
    main()
