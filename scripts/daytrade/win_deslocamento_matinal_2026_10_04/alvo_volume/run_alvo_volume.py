"""Alvo que se aproxima + saida por volume sobre win_deslocamento_matinal (WIN@). Ver PRE_REGISTRO.md.
Uso: python run_alvo_volume.py [smoke]"""
from __future__ import annotations

import bisect
import contextlib
import dataclasses
import io
import json
import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import comum as c  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from strategy.daytrade.base import AdjustTarget, EnterLimit, Exit, no_tick  # noqa: E402
from strategy.daytrade.lab.win_deslocamento_matinal import (  # noqa: E402
    EXIT_TTL_BARS_SEM_PRAZO, WinDeslocamentoMatinal)

CAPITAL = 1000.0
WARM = 40
JAN = {"IS": ("2021-10-01", "2024-12-31"), "OOS": ("2025-01-01", "2026-09-30")}


class Agg:
    """Agrega M1 -> vela de `tf` minutos relativos a abertura do pregao. Devolve a vela so' quando FECHA."""

    def __init__(self, tf):
        self.tf = tf
        self.reset()

    def reset(self):
        self.idx = None
        self.o = self.h = self.l = self.c = self.v = None
        self.t0 = None

    def feed(self, ts, m, bar):
        i = int(m // self.tf)
        out = None
        if self.idx is not None and i != self.idx:      # barra faltante: fecha a anterior (atrasado)
            out = self._pack()
            self.reset()
        if self.idx is None:
            self.idx, self.t0 = i, ts
            self.o, self.h, self.l, self.c, self.v = bar.open, bar.high, bar.low, bar.close, bar.volume
        else:
            self.h = max(self.h, bar.high)
            self.l = min(self.l, bar.low)
            self.c = bar.close
            self.v += bar.volume
        if out is None and (int(m) + 1) % self.tf == 0:
            out = self._pack()
            self.reset()
        return out

    def _pack(self):
        return dict(idx=self.idx, t0=self.t0, o=self.o, c=self.c, v=self.v)


@dataclass
class WinAV(WinDeslocamentoMatinal):
    risco_max_pct: float | None = 0.10
    dia_ini: object = None
    # alvo que se aproxima
    alvo_ini_r: float | None = None
    passo_r: float = 0.22
    cada_velas: int = 5
    piso_r: float = 1.1
    # saida por volume
    vol_modo: str | None = None      # None | "media" | "quantil"
    vol_tf: int = 5
    vol_k: float = 2.0
    vol_contra: bool = True

    _a5: Agg = field(default_factory=lambda: Agg(5), init=False, repr=False)
    _avol: Agg | None = field(default=None, init=False, repr=False)
    _hist_media: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)
    _por_hora: dict = field(default_factory=dict, init=False, repr=False)
    _vrels: list = field(default_factory=list, init=False, repr=False)
    _pos_key: object = field(default=None, init=False, repr=False)
    _velas_pos: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        self._avol = Agg(self.vol_tf) if self.vol_modo == "quantil" else None

    def on_session_start(self, session_date):
        super().on_session_start(session_date)
        self._a5.reset()
        if self._avol is not None:
            self._avol.reset()

    # ---- gatilho de volume numa vela fechada (atualiza historico SEMPRE) ----
    def _gatilho_volume(self, cd):
        v = cd["v"]
        if self.vol_modo == "media":
            h = self._hist_media
            ok = len(h) >= 20 and v >= self.vol_k * (sum(h) / 20.0)
            h.append(v)
            return ok
        # quantil (WinCincoMedias v2.01)
        dq = self._por_hora.setdefault(cd["idx"], deque(maxlen=20))
        ok = False
        if len(dq) >= 5:
            med = float(np.median(dq))
            if med > 0:
                vrel = v / med
                n = len(self._vrels)
                if n >= 100:
                    pos = 0.90 * (n - 1)
                    lo = int(pos)
                    thr = self._vrels[lo] + (pos - lo) * (self._vrels[min(lo + 1, n - 1)] - self._vrels[lo])
                    ok = vrel >= thr
                bisect.insort(self._vrels, vrel)
        dq.append(v)
        return ok

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        acts = super().on_bar(ts, bar, positions, session_pnl_brl)
        if self._open_ts is None:
            return acts
        if acts and self.dia_ini is not None and ts.date() < self.dia_ini:
            return []
        m = (ts - self._open_ts) / pd.Timedelta(minutes=1)
        c5 = self._a5.feed(ts, m, bar)
        if self.vol_modo == "media":
            cv = c5
        elif self._avol is not None:
            cv = self._avol.feed(ts, m, bar)
        else:
            cv = None
        gat = self._gatilho_volume(cv) if (cv is not None and self.vol_modo) else False

        # entrada: acrescenta o alvo inicial em R
        if acts and isinstance(acts[0], EnterLimit) and self.alvo_ini_r:
            a = acts[0]
            lado = 1.0 if a.side == "long" else -1.0
            dist = abs(a.limit_price - a.initial_stop)
            alvo = no_tick(a.limit_price + lado * self.alvo_ini_r * dist, self.tick_size)
            return [dataclasses.replace(a, initial_target=alvo, exit_split_unit=1,
                                        exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO)]
        if not positions:
            self._pos_key, self._velas_pos = None, 0
            return acts
        pos = positions[0]
        if self._pos_key != pos.entry_ts:
            self._pos_key, self._velas_pos = pos.entry_ts, 0
        out = []
        if c5 is not None and c5["t0"] >= pos.entry_ts:
            self._velas_pos += 1
        if gat and cv["t0"] >= pos.entry_ts:
            corpo_contra = (cv["c"] < cv["o"]) if pos.side == "long" else (cv["c"] > cv["o"])
            if corpo_contra or not self.vol_contra:
                return [Exit(reason=f"volume_{self.vol_modo}")]
        if c5 is not None and self.alvo_ini_r and pos.current_stop is not None and self.passo_r > 0:
            R = abs(pos.entry_price - pos.current_stop)
            r = max(self.piso_r, self.alvo_ini_r - self.passo_r * (self._velas_pos // self.cada_velas))
            lado = 1.0 if pos.side == "long" else -1.0
            novo = no_tick(pos.entry_price + lado * r * R, self.tick_size)
            if pos.current_target is not None and novo != pos.current_target:
                out.append(AdjustTarget(new_target=novo))
        return out


def celulas_simples():
    cel = {"REF": dict()}
    for A in (1.5, 2.0, 3.0):
        for N in (5, 10):
            cel[f"AL_A{A}_N{N}"] = dict(alvo_ini_r=A, cada_velas=N)
        cel[f"CT_fixo{A}"] = dict(alvo_ini_r=A, passo_r=0.0)
    for k in (2.0, 3.0):
        for ct in (False, True):
            cel[f"V1_k{k:g}_{'contra' if ct else 'qq'}"] = dict(vol_modo="media", vol_tf=5, vol_k=k, vol_contra=ct)
    cel["V2_q90_M30"] = dict(vol_modo="quantil", vol_tf=30, vol_contra=True)
    cel["V2_q90_M5"] = dict(vol_modo="quantil", vol_tf=5, vol_contra=True)
    return cel


def unid(cid, params, jan):
    ini, fim = JAN[jan]
    df = c.carregar("WIN@")
    c.AQUECIMENTO = WARM
    sel, dias = c.janela(df, pd.Timestamp(ini), pd.Timestamp(fim))
    perf = c.profile_for("WIN@")
    est = WinAV(symbol="WIN@", tick_size=perf.price_tick_size, desloc_min_atr=0.3, dia_ini=dias[0], **params)
    cfg, _ = c.montar_config("WIN@", "P2", capital=CAPITAL, nominal=False)
    with contextlib.redirect_stdout(io.StringIO()):
        res = run_intraday_backtest(sel, est, cfg)
    ds = set(dias)
    tr = [t for t in res.trades if t.entry_ts.date() in ds]
    return dict(cid=cid, jan=jan, trades=c.linhas_trades(tr), n_dias=len(dias), wiped=res.wiped_out_at is not None)


def dd(p):
    eq = CAPITAL + np.cumsum(p)
    pico = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))[1:]
    return float((pico - eq).max()), float(((pico - eq) / pico).max() * 100)


def metr(t, ref=None):
    p = np.array([x["pnl"] for x in t]) if t else np.array([0.0])
    g, l = p[p > 0], p[p < 0]
    mdd, mddp = dd(p)
    rs = lambda r: sum(1 for x in t if x["reason"] == r)
    anos = {}
    for x in t:
        anos[x["entry_ts"][:4]] = anos.get(x["entry_ts"][:4], 0) + x["pnl"]
    o = dict(n=len(t), liq=p.sum(), cap_final=CAPITAL + p.sum(), r_op=p.mean(), acerto=100 * (p > 0).mean(),
             ganho=g.mean() if len(g) else 0.0, perda=-l.mean() if len(l) else np.nan, stop=rs("STOP"), alvo=rs("TARGET"),
             volume=rs("SIGNAL"), fim_dia=rs("FORCED_FLATTEN"), maxdd=mdd, maxdd_pct=mddp,
             fr=p.sum() / mdd if mdd else np.nan, anos=" ".join(f"{a}:{v:.0f}" for a, v in sorted(anos.items())))
    o["payoff"] = o["ganho"] / o["perda"] if o["perda"] == o["perda"] and o["perda"] else np.nan
    if ref is not None:
        a = {x["entry_ts"][:10]: x["pnl"] for x in t}
        b = {x["entry_ts"][:10]: x["pnl"] for x in ref}
        dias = set(a) | set(b)
        dif = [a.get(d, 0.0) - b.get(d, 0.0) for d in dias]
        o["alt_n"] = sum(1 for z in dif if abs(z) > 1e-9)
        o["alt_rs"] = sum(dif)
    return o


def roda(unidades, saida):
    res = {}
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = {ex.submit(unid, cid, p, j): (cid, j) for cid, p, j in unidades}
        for f in as_completed(fut):
            r = f.result()
            res[(r["cid"], r["jan"])] = r
            m = metr(r["trades"])
            print(f"[{r['jan']}] {r['cid']:<18} n={m['n']} liq={m['liq']:.1f} dd={m['maxdd']:.0f} "
                  f"stop/alvo/vol/fim={m['stop']}/{m['alvo']}/{m['volume']}/{m['fim_dia']} wiped={r['wiped']}", flush=True)
            saida[f"{r['cid']}|{r['jan']}"] = r["trades"]
    return res


def escolhe(ids, is_t, ref_dd):
    ms = {i: metr(is_t[i]) for i in ids}
    ok = sorted([i for i in ids if ms[i]["maxdd"] <= ref_dd], key=lambda i: -ms[i]["liq"])
    if len(ok) < 2:
        resto = sorted([i for i in ids if i not in ok],
                       key=lambda i: -(ms[i]["fr"] if ms[i]["fr"] == ms[i]["fr"] else -1e9))
        ok += resto
    return ok[:2]


def main():
    smoke = len(sys.argv) > 1 and sys.argv[1] == "smoke"
    cel = celulas_simples()
    if smoke:
        cel = {k: cel[k] for k in ("REF", "AL_A2.0_N5", "V1_k2_contra", "V2_q90_M30")}
    saida = {}
    res = roda([(k, p, j) for k, p in cel.items() for j in JAN], saida)
    json.dump(saida, open(HERE / ("smoke_simples.json" if smoke else "saida_simples.json"), "w"))
    if smoke:
        return
    isT = {k: res[(k, "IS")]["trades"] for k in cel}
    ref_dd = metr(isT["REF"])["maxdd"]
    al = [k for k in cel if k.startswith("AL_")]
    vo = [k for k in cel if k.startswith("V")]
    sa, sv = escolhe(al, isT, ref_dd), escolhe(vo, isT, ref_dd)
    print(f"ESCOLHIDAS (so' IS): alvo={sa} volume={sv}", flush=True)
    comb = {}
    for a in sa:
        for v in sv:
            comb[f"JU_{a}+{v}"] = {**cel[a], **cel[v]}
    saida2 = {}
    roda([(k, p, j) for k, p in comb.items() for j in JAN], saida2)
    json.dump(saida2, open(HERE / "saida_juntas.json", "w"))
    json.dump(dict(alvo=sa, volume=sv, ref_dd=ref_dd, comb=list(comb)), open(HERE / "escolhidas.json", "w"))


if __name__ == "__main__":
    main()
