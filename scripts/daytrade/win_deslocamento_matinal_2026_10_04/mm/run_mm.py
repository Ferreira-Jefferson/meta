"""Teste de media movel sobre win_deslocamento_matinal. Uso: run_mm.py IS | OOS ID1,ID2"""
from __future__ import annotations

import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import comum as c  # noqa: E402
from strategy.daytrade.base import no_tick  # noqa: E402


def _ema(prev, x, n):
    a = 2.0 / (n + 1)
    return x if prev is None else prev + a * (x - prev)


@dataclass
class WinMM(c.WinDeslocamentoMatinal):
    alinha: str | None = None       # 'e10','e20','e50','s10d','s20d'
    slope_min: int = 0              # 0 = off
    esticado_k: float = 0.0         # 0 = off
    recuo_ttl: int = 0              # 0 = off
    _bk: object = field(default=None, init=False, repr=False)
    _last: float = field(default=0.0, init=False, repr=False)
    _emas: dict = field(default_factory=lambda: {10: None, 20: None, 50: None}, init=False, repr=False)
    _h20: list = field(default_factory=list, init=False, repr=False)
    _smas: dict = field(default_factory=dict, init=False, repr=False)

    def seed_daily_volatility(self, previous_daily_bars):
        super().seed_daily_volatility(previous_daily_bars)
        cl = [b.close for b in previous_daily_bars]
        self._smas = {n: (sum(cl[-n:]) / n if len(cl) >= n else None) for n in (10, 20)}

    def _fecha(self):
        for n in self._emas:
            self._emas[n] = _ema(self._emas[n], self._last, n)
        self._h20.append(self._emas[20])
        del self._h20[:-12]

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        b = ts.floor("5min")
        if self._bk is not None and b != self._bk:
            self._fecha()
        self._bk = b
        self._last = bar.close
        antes = len(self.sinais)
        acts = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acts:
            return acts
        a = acts[0]
        lado = 1.0 if a.side == "long" else -1.0
        px = bar.close
        # M5 do bucket corrente esta completa (barra 10:29); EMA provisoria incluindo-a
        e = {n: _ema(v, px, n) for n, v in self._emas.items()}
        if any(v is None for v in e.values()):
            ok = False
        else:
            ok = True
            if self.alinha:
                if self.alinha[0] == "e":
                    ref = e[int(self.alinha[1:])]
                else:
                    ref = self._smas.get(int(self.alinha[1:-1]))
                ok = ref is not None and lado * (px - ref) > 0
            if ok and self.slope_min:
                k = self.slope_min // 5
                if len(self._h20) < k:
                    ok = False
                else:
                    ok = lado * (e[20] - self._h20[-k]) > 0
            if ok and self.esticado_k:
                ok = abs(px - e[20]) <= self.esticado_k * self._atr
        if not ok:
            del self.sinais[antes:]
            return []
        if self.recuo_ttl:
            lim = no_tick(min(px, e[20]) if lado > 0 else max(px, e[20]), self.tick_size)
            a = dataclasses.replace(a, limit_price=lim, ttl_bars=self.recuo_ttl)
            acts = [a]
        return acts


CELULAS = {
    "BASE": {}, "A_e10": dict(alinha="e10"), "A_e20": dict(alinha="e20"), "A_e50": dict(alinha="e50"),
    "A_s10d": dict(alinha="s10d"), "A_s20d": dict(alinha="s20d"),
    "S30": dict(slope_min=30), "S15": dict(slope_min=15),
    "E15": dict(esticado_k=0.15), "E25": dict(esticado_k=0.25),
    "P30": dict(recuo_ttl=30), "P60": dict(recuo_ttl=60),
}
BASE = dict(desloc_min_atr=0.3, stop_atr=None, alvo_atr=None)


def unid(cid, ini, fim, prem):
    c.WinDeslocamentoMatinal_orig = c.WinDeslocamentoMatinal
    c.WinDeslocamentoMatinal = WinMM
    r = c.unidade("WIN@", ini, fim, {**BASE, **CELULAS[cid]}, prem, True)
    r["cid"] = cid
    r["texto"] = r["texto"].replace(c.nome_celula(BASE), f"{cid:<7}", 1)
    return r


def main():
    modo = sys.argv[1]
    if modo == "IS":
        ini, fim, ids = "2021-10-01", "2024-12-31", list(CELULAS)
        prems = ["P2", "P0"]
    else:
        ini, fim = "2025-01-01", "2026-09-30"
        ids = ["BASE"] + sys.argv[2].split(",")
        prems = ["P2", "P0"]
    out, cab = [], False
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = [ex.submit(unid, i, ini, fim, p) for i in ids for p in prems]
        for f in as_completed(fut):
            r = f.result()
            if not cab:
                print(r["cab"], flush=True); cab = True
            print(r["texto"], flush=True)
            out.append(r)
    (HERE / f"saida_{modo}.json").write_text(json.dumps(out, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
