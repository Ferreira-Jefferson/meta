"""Qullamaggie (Kristjan Kullamägi) — núcleo PURO em barras diárias.

Espelho 1:1 de `mt5/QullamaggieLib.mqh`: toda regra daqui existe lá com a mesma
matemática, e o `qm_parity.py` confere as duas contra o testador do MT5.

As 3 configurações da fonte primária (qullamaggie.com, "3 timeless setups"):

  1. BREAKOUT  — alta de 30-100%+ nos últimos 1-3 meses, consolidação de 2 sem a 2 meses
                 (mínimas ascendentes, range apertando, preço "surfando" a 10/20 SMA),
                 entrada no rompimento da máxima da consolidação; stop na mínima;
                 stop NÃO mais largo que o ADR; vende 1/3-1/2 após 3-5 dias, stop no
                 zero a zero, resto no trailing da 10/20 (1º fechamento abaixo).
  2. EP        — gap de 10%+ com volume, ação "dormente" 3-6 meses; entra na máxima do
                 range de abertura, stop na mínima do dia, trailing 10/20.
  3. PARABOLIC SHORT — +50-100% em dias/semanas, 3-5+ altas seguidas; short no range de
                 abertura; stop na máxima do dia; alvo nas 10/20 SMA.

LIMITE HONESTO DO CANDLE DIÁRIO: o original é INTRADIÁRIO (ORH de 1/5/60 min, "mínima
do dia"). Candle diário não diz o que veio antes, então aqui o ORH vira ordem
buy-stop no nível de rompimento e a "mínima do dia" vira mínima das últimas N barras
(`stop_bars`) — ambos conhecidos ANTES do pregão, sem look-ahead. O volume dos primeiros
15 min do EP não existe em candle diário: não é filtrado (documentado no relatório).

Regra de tempo: decisão no fechamento da barra i -> ordem vale na barra i+1.
Intrabarra ambígua (stop e entrada na mesma barra): `same_bar='pess'` assume stop
(cota inferior); `'opt'` só conta o stop se o fechamento ficar abaixo dele (cota superior).
A verdade está no meio — quem desempata é o testador do MT5 em ticks reais.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

NAN = np.nan


# --------------------------------------------------------------------------- params
@dataclass(frozen=True)
class QmParams:
    # liquidez / volatilidade (universo)
    min_price: float = 3.0
    min_dvol: float = 5e6            # média 20d de close*volume, R$
    adr_min: float = 0.04            # ADR20 = mean(h/l) - 1 (fórmula do TC2000 dele)
    # breakout
    pm_window: int = 63              # "1-3 meses" em barras
    pm_min: float = 0.30
    consol_bars: int = 10            # 2 semanas = 10; 2 meses = 40
    max_depth: float = 0.35          # (HH-LL)/HH da consolidação
    tight_ratio: float = 1.0         # range médio 5 barras <= ratio * range médio da consolidação
    stop_bars: int = 2               # proxy da "mínima do dia"
    stop_adr_max: float = 1.0        # stop <= ADR (regra dele)
    # gestão (comum às 3 configs de compra)
    partial_days: int = 3
    partial_frac: float = 1.0 / 3.0
    trail_ma: int = 10
    # EP
    ep_gap: float = 0.10
    ep_neglect_bars: int = 63
    ep_neglect_max: float = 0.20
    ep_confirm: float = 0.0          # buy-stop em open*(1+confirm) = ORH proxy
    ep_stop_adr: float = 1.0
    # parabolic short
    para_up_days: int = 3
    para_win: int = 5
    para_move: float = 0.30
    para_confirm: float = 0.0
    para_stop_adr: float = 1.0
    para_target_ma: int = 10
    para_max_hold: int = 10
    # execução / custo
    leg_cost: float = 0.0018         # corretagem+emolumentos 0,03% + slippage 0,15% (config.py)
    same_bar: str = "pess"
    # conta
    capital: float = 100_000.0
    risk_pct: float = 0.005
    max_pos_pct: float = 0.25
    max_positions: int = 6
    lot: int = 100

    def with_(self, **kw) -> "QmParams":
        return replace(self, **kw)


# ------------------------------------------------------------------------ indicators
def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), NAN)
    if len(x) < n:
        return out
    cs = np.cumsum(np.insert(x.astype(float), 0, 0.0))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def roll_max(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), NAN)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).max(axis=1)
    return out


def roll_min(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), NAN)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).min(axis=1)
    return out


def adr(h: np.ndarray, l: np.ndarray, n: int = 20) -> np.ndarray:
    """ADR% = média(h/l) - 1 em n barras (TC2000: 100*(avg(h/l,20)-1))."""
    return sma(h / l, n) - 1.0


def dollar_volume(c: np.ndarray, v: np.ndarray, n: int = 20) -> np.ndarray:
    return sma(c * v, n)


def prior_move_up(h: np.ndarray, l: np.ndarray, window: int) -> np.ndarray:
    """Maior alta 'mínima -> máxima posterior' dentro da janela de `window` barras
    terminando em i: max_k  h[k] / min(l[ini..k]) - 1."""
    out = np.full(len(h), NAN)
    if len(h) < window:
        return out
    wl = sliding_window_view(l, window)
    wh = sliding_window_view(h, window)
    runmin = np.minimum.accumulate(wl, axis=1)
    out[window - 1:] = (wh / runmin).max(axis=1) - 1.0
    return out


def make_arrays(df) -> dict:
    """DataFrame OHLCV (index datetime) -> dict de arrays; descarta barras sem close."""
    d = df.dropna(subset=["open", "high", "low", "close"])
    d = d[(d["low"] > 0) & (d["high"] >= d["low"])]
    return {
        "date": d.index.values,
        "o": d["open"].to_numpy(float), "h": d["high"].to_numpy(float),
        "l": d["low"].to_numpy(float), "c": d["close"].to_numpy(float),
        "v": d["volume"].to_numpy(float),
    }


# --------------------------------------------------------------------------- setups
def breakout_setup(a: dict, p: QmParams):
    """Condições avaliadas no FECHAMENTO da barra i. Devolve (ok, trigger, stop):
    arrays indexados por i; a ordem buy-stop vale na barra i+1."""
    o, h, l, c, v = a["o"], a["h"], a["l"], a["c"], a["v"]
    n = len(c)
    C = p.consol_bars
    ok = np.zeros(n, bool)
    s10, s20 = sma(c, 10), sma(c, 20)
    adr20 = adr(h, l, 20)
    dv = dollar_volume(c, v, 20)
    pm = prior_move_up(h, l, p.pm_window)
    hh, ll = roll_max(h, C), roll_min(l, C)
    half = C // 2
    ll_recent = roll_min(l, half)
    ll_first = np.full(n, NAN)
    ll_first[C - 1:] = roll_min(l, C - half)[C - 1 - half: n - half] if n >= C else NAN
    rng = (h - l) / c
    rng5 = sma(rng, 5)
    rngC = sma(rng, C)
    stop_raw = roll_min(l, p.stop_bars)
    s20_lag = np.full(n, NAN)
    s20_lag[5:] = s20[:-5]
    with np.errstate(invalid="ignore"):
        ok = (
            (c >= p.min_price) & (dv >= p.min_dvol) & (adr20 >= p.adr_min)
            & (pm >= p.pm_min)
            & ((hh - ll) / hh <= p.max_depth)
            & (ll_recent >= ll_first)
            & (rng5 <= p.tight_ratio * rngC)
            & (c > s10) & (c > s20) & (s10 >= s20) & (s20 > s20_lag)
        )
        trig = hh
        stop = stop_raw
        width = (trig - stop) / trig
        ok &= (width > 0) & (width <= p.stop_adr_max * adr20)
    ok &= np.isfinite(trig) & np.isfinite(stop)
    return ok, trig, stop


def ep_setup(a: dict, p: QmParams):
    """EP decidido na ABERTURA de d (gap conhecido): devolve (ok, nível de entrada, stop)
    indexados por d (usam só close[d-1], open[d] e indicadores até d-1)."""
    o, h, l, c, v = a["o"], a["h"], a["l"], a["c"], a["v"]
    n = len(c)
    adr20 = adr(h, l, 20)
    dv = dollar_volume(c, v, 20)
    ok = np.zeros(n, bool)
    lvl = np.full(n, NAN)
    stp = np.full(n, NAN)
    N = p.ep_neglect_bars
    for d in range(N + 1, n):
        i = d - 1
        if not (c[i] >= p.min_price and dv[i] >= p.min_dvol and adr20[i] >= p.adr_min):
            continue
        if o[d] / c[i] - 1.0 < p.ep_gap:
            continue
        if c[i] / c[i - N] - 1.0 > p.ep_neglect_max:
            continue
        ok[d] = True
        lvl[d] = o[d] * (1.0 + p.ep_confirm)
        stp[d] = o[d] * (1.0 - p.ep_stop_adr * adr20[i])
    return ok, lvl, stp


def para_setup(a: dict, p: QmParams):
    """Parabolic short decidido na abertura de d: devolve (ok, nível de venda, stop)."""
    o, h, l, c, v = a["o"], a["h"], a["l"], a["c"], a["v"]
    n = len(c)
    adr20 = adr(h, l, 20)
    dv = dollar_volume(c, v, 20)
    ok = np.zeros(n, bool)
    lvl = np.full(n, NAN)
    stp = np.full(n, NAN)
    U, W = p.para_up_days, p.para_win
    for d in range(max(U, W) + 21, n):
        i = d - 1
        if not (c[i] >= p.min_price and dv[i] >= p.min_dvol and adr20[i] >= p.adr_min):
            continue
        if not all(c[i - k] > c[i - k - 1] for k in range(U)):
            continue
        if c[i] / c[i - W] - 1.0 < p.para_move:
            continue
        ok[d] = True
        lvl[d] = o[d] * (1.0 - p.para_confirm)
        stp[d] = lvl[d] * (1.0 + p.para_stop_adr * adr20[i])
    return ok, lvl, stp


# -------------------------------------------------------------------------- trade sim
def _finish(a, e, x, side, fills, path, reason, p, entry, stop_pct, open_end=False):
    """fills: lista (frac, preço) das saídas. Retorno em % do nocional de entrada."""
    gross = sum(fr * side * (px / entry - 1.0) for fr, px in fills)
    ret = gross - p.leg_cost * (1.0 + sum(fr for fr, _ in fills))
    return {
        "e": e, "x": x, "side": side, "entry": entry, "stop_pct": stop_pct,
        "ret": ret, "reason": reason, "open_end": open_end,
        "path": np.asarray(path, float),     # mark-to-market em % do nocional, de e até x
        "exit_at_open": reason in ("gap", "trail", "target", "time"),
    }


def run_long(a: dict, e: int, level: float, stop: float, p: QmParams,
             entry_must_cross: bool = True) -> Optional[dict]:
    """Posição comprada: buy-stop em `level` válido na barra e. None se não preenche."""
    o, h, l, c = a["o"], a["h"], a["l"], a["c"]
    n = len(c)
    if h[e] < level:
        return None
    f = max(o[e], level)
    stop_pct = (level - stop) / level
    ma = sma(c, p.trail_ma)
    cur = stop
    cost = p.leg_cost
    # barra de entrada
    stopped = (l[e] <= stop) if p.same_bar == "pess" else (c[e] < stop)
    if stopped:
        return _finish(a, e, e, 1, [(1.0, stop)], [-0.0 + (stop / f - 1.0) - 2 * cost], "stop", p, f, stop_pct)
    path = [c[e] / f - 1.0 - cost]
    rem, fills, done = 1.0, [], False
    for d in range(e + 1, n):
        held = d - e
        if o[d] <= cur:
            fills.append((rem, o[d]))
            return _finish(a, e, d, 1, fills, path + [_mtm(fills, 0.0, f, c[d], 1, cost)], "gap", p, f, stop_pct)
        if held >= p.partial_days and c[d - 1] < ma[d - 1]:
            fills.append((rem, o[d]))
            return _finish(a, e, d, 1, fills, path + [_mtm(fills, 0.0, f, c[d], 1, cost)], "trail", p, f, stop_pct)
        if held == p.partial_days and not done:
            fr = rem * p.partial_frac
            fills.append((fr, o[d]))
            rem -= fr
            done = True
            cur = max(cur, f)
        if l[d] <= cur:
            fills.append((rem, cur))
            return _finish(a, e, d, 1, fills, path + [_mtm(fills, 0.0, f, c[d], 1, cost)], "stop", p, f, stop_pct)
        path.append(_mtm(fills, rem, f, c[d], 1, cost))
    fills.append((rem, c[n - 1]))
    return _finish(a, e, n - 1, 1, fills, path, "open", p, f, stop_pct, open_end=True)


def _mtm(fills, rem, entry, close, side, cost):
    real = sum(fr * side * (px / entry - 1.0) for fr, px in fills)
    unreal = rem * side * (close / entry - 1.0)
    return real + unreal - cost * (1.0 + sum(fr for fr, _ in fills))


def run_short(a: dict, e: int, level: float, stop: float, p: QmParams) -> Optional[dict]:
    """Short: sell-stop em `level` na barra e; stop acima; alvo dinâmico = SMA(para_target_ma)[d-1]."""
    o, h, l, c = a["o"], a["h"], a["l"], a["c"]
    n = len(c)
    if l[e] > level:
        return None
    f = min(o[e], level)
    stop_pct = (stop - level) / level
    ma = sma(c, p.para_target_ma)
    cost = p.leg_cost
    stopped = (h[e] >= stop) if p.same_bar == "pess" else (c[e] > stop)
    if stopped:
        return _finish(a, e, e, -1, [(1.0, stop)], [-(stop / f - 1.0) - 2 * cost], "stop", p, f, stop_pct)
    path = [-(c[e] / f - 1.0) - cost]
    for d in range(e + 1, n):
        held = d - e
        tgt = ma[d - 1]
        if o[d] >= stop:
            fills = [(1.0, o[d])]
            return _finish(a, e, d, -1, fills, path + [_mtm(fills, 0.0, f, c[d], -1, cost)], "gap", p, f, stop_pct)
        if tgt == tgt and o[d] <= tgt:
            fills = [(1.0, o[d])]
            return _finish(a, e, d, -1, fills, path + [_mtm(fills, 0.0, f, c[d], -1, cost)], "target", p, f, stop_pct)
        if held >= p.para_max_hold:
            fills = [(1.0, o[d])]
            return _finish(a, e, d, -1, fills, path + [_mtm(fills, 0.0, f, c[d], -1, cost)], "time", p, f, stop_pct)
        if h[d] >= stop:
            fills = [(1.0, stop)]
            return _finish(a, e, d, -1, fills, path + [_mtm(fills, 0.0, f, c[d], -1, cost)], "stop", p, f, stop_pct)
        if tgt == tgt and l[d] <= tgt:
            fills = [(1.0, tgt)]
            return _finish(a, e, d, -1, fills, path + [_mtm(fills, 0.0, f, c[d], -1, cost)], "target", p, f, stop_pct)
        path.append(_mtm([], 1.0, f, c[d], -1, cost))
    fills = [(1.0, c[n - 1])]
    return _finish(a, e, n - 1, -1, fills, path, "open", p, f, stop_pct, open_end=True)


def trades_for_symbol(a: dict, p: QmParams, setup: str = "breakout") -> list[dict]:
    """Um robô por símbolo, uma posição por vez (conta NETTING)."""
    n = len(a["c"])
    if setup == "breakout":
        ok, trig, stop = breakout_setup(a, p)
        shift = 1            # sinal no fechamento de i vale em i+1
    elif setup == "ep":
        ok, trig, stop = ep_setup(a, p)
        shift = 0
    elif setup == "para":
        ok, trig, stop = para_setup(a, p)
        shift = 0
    else:
        raise ValueError(setup)
    out = []
    e = 1
    while e < n:
        i = e - shift
        if i < 0 or not ok[i]:
            e += 1
            continue
        if setup == "para":
            t = run_short(a, e, trig[i], stop[i], p)
        else:
            t = run_long(a, e, trig[i], stop[i], p)
        if t is None:
            e += 1
            continue
        out.append(t)
        e = t["x"] if t["exit_at_open"] else t["x"] + 1
        if e <= t["e"]:
            e = t["e"] + 1
    return out
