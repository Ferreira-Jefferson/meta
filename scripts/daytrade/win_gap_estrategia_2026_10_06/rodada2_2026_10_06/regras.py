# -*- coding: utf-8 -*-
"""Traducao de (entrada, saida) em ordem + niveis, e a GRADE da rodada 2 (100 celulas, definida ANTES de rodar).

Entrada: V2 (1a barra M5 contra o gap, entra na direcao dela), V1 (fade do gap), V3 (= V2 sem trade quando o
volume do call de D-1 e' alto), com `recuo` (pullback) em pontos. Saidas: 25 especificacoes em 8 familias.
"""
from __future__ import annotations

import math

import numpy as np

from sim import FEE, PV, TICK, Saida, r5

PISO_ALVO_GAP = 100.0     # alvo "fechar o gap" so' vale se estiver a >= 100 pts do preco de entrada
PISO_STOP_ESTRUT = 100.0


def sinal(x: float) -> int:
    return (x > 0) - (x < 0)


def gatilho(c: dict, ent: dict) -> int:
    """+1 compra / -1 venda / 0 sem ordem (so' a 1a barra FECHADA e dados de D-1 para tras)."""
    gap = c["gap"]
    if gap == 0 or abs(gap) < ent.get("gap_min", 0.0):
        return 0
    if ent["fam"] == "V1":
        return -sinal(gap)
    corpo = c["c1"] - c["o1"]
    if corpo == 0 or sinal(corpo) == sinal(gap):
        return 0
    if ent["fam"] == "V3" and c["vol_alto"]:
        return 0
    return sinal(corpo)


def limite(c: dict, side: int, recuo: float) -> float:
    return r5(c["c1"] - side * recuo)


def _dist(spec, c, lim, side_real_dist_gap=None):
    kind = spec[0]
    if kind == "pts":
        return float(spec[1])
    if kind == "atr":
        return spec[1] * c["atr_prev"]
    if kind == "r1":
        return spec[1] * (c["h1"] - c["l1"])
    if kind == "gap":
        return side_real_dist_gap
    raise ValueError(kind)


def saida_de(c: dict, side: int, lim: float, ex: dict, side_real: int, lim_real: float) -> Saida | None:
    """None = sem ordem (atr indisponivel / gap ja' fechado). Usa a direcao REAL para decidir o skip do alvo-gap
    e as distancias; `side` pode ser a oposta (nulo de direcao aleatoria) com as MESMAS distancias."""
    if (ex["stop"][0] == "atr" or (ex["target"] and ex["target"][0] == "atr")) and not math.isfinite(c["atr_prev"]):
        return None
    st = ex["stop"]
    if st[0] == "bar1":
        d_real = (lim_real - (c["l1"] - TICK)) if side_real > 0 else ((c["h1"] + TICK) - lim_real)
        dstop = max(PISO_STOP_ESTRUT, d_real)
    else:
        dstop = _dist(st, c, lim)
    dstop = max(TICK, round(dstop / TICK) * TICK)
    dtgt = None
    tg = ex["target"]
    if tg is not None:
        if tg[0] == "gap":
            dg = (c["prev_call"] - lim_real) * side_real
            if dg < PISO_ALVO_GAP:
                return None
            dtgt = dg
        elif tg[0] == "rr":
            dtgt = tg[1] * dstop
        else:
            dtgt = _dist(tg, c, lim)
        dtgt = max(TICK, round(dtgt / TICK) * TICK)
    ts = ex.get("tstop")
    t_stop = None if ts is None else (int(ts[:2]) * 3_600_000 + int(ts[3:]) * 60_000)
    return Saida(stop=r5(lim - side * dstop), target=None if dtgt is None else r5(lim + side * dtgt),
                 trail=ex.get("trail"), be_after=ex.get("be"), partial=ex.get("partial"), t_stop=t_stop)


# ----------------------------------------------------------------------------------------------- grade
def _ex(id_, fam, stop, target=None, trail=None, be=None, partial=None, tstop=None):
    return dict(id=id_, fam=fam, stop=stop, target=target, trail=trail, be=be, partial=partial, tstop=tstop)


SAIDAS = [
    # F1 fixo em pontos
    _ex("S350", "F1 fixo", ("pts", 350)),
    _ex("S700", "F1 fixo", ("pts", 700)),
    _ex("S350 T700", "F1 fixo", ("pts", 350), ("pts", 700)),
    _ex("S700 T700", "F1 fixo", ("pts", 700), ("pts", 700)),
    _ex("S700 T1400", "F1 fixo", ("pts", 700), ("pts", 1400)),
    # F2 escalado por volatilidade (ATR 10d = amplitude media dos 10 pregoes anteriores; R1 = faixa da 1a barra)
    _ex("S.3atr", "F2 vol", ("atr", 0.3)),
    _ex("S.6atr", "F2 vol", ("atr", 0.6)),
    _ex("S.3atr T.6atr", "F2 vol", ("atr", 0.3), ("atr", 0.6)),
    _ex("S.6atr T1.2atr", "F2 vol", ("atr", 0.6), ("atr", 1.2)),
    _ex("S1R1 T2R1", "F2 vol", ("r1", 1.0), ("r1", 2.0)),
    # F3 estrutural: stop no outro extremo da 1a barra M5
    _ex("Sbar1", "F3 estrut", ("bar1",)),
    _ex("Sbar1 T2R", "F3 estrut", ("bar1",), ("rr", 2.0)),
    # F4 alvo = fechar o gap (call de D-1)
    _ex("S350 Tgap", "F4 gap", ("pts", 350), ("gap",)),
    _ex("S700 Tgap", "F4 gap", ("pts", 700), ("gap",)),
    _ex("Sbar1 Tgap", "F4 gap", ("bar1",), ("gap",)),
    # F5 trailing (stop inicial 700)
    _ex("S700 trail400", "F5 trail", ("pts", 700), None, ("pts", 400)),
    _ex("S700 trail700", "F5 trail", ("pts", 700), None, ("pts", 700)),
    _ex("S700 swing3", "F5 trail", ("pts", 700), None, ("swing", 3)),
    _ex("S700 ema21", "F5 trail", ("pts", 700), None, ("ema", 21)),
    # F6 breakeven
    _ex("S700 BE500", "F6 BE", ("pts", 700), None, None, 500),
    _ex("S700 BE500 T1400", "F6 BE", ("pts", 700), ("pts", 1400), None, 500),
    # F7 parcial: metade no alvo, resto segura / trailing
    _ex("S700 P50%T700", "F7 parcial", ("pts", 700), ("pts", 700), None, None, 0.5),
    _ex("S700 P50%T700 trail400", "F7 parcial", ("pts", 700), ("pts", 700), ("pts", 400), None, 0.5),
    # F8 stop de tempo
    _ex("S700 sai12h", "F8 tempo", ("pts", 700), tstop="12:00"),
    _ex("S700 sai15h", "F8 tempo", ("pts", 700), tstop="15:00"),
]

ENTRADAS = [
    dict(id="V2 r150", fam="V2", recuo=150.0),
    dict(id="V2 r0", fam="V2", recuo=0.0),
    dict(id="V1 r150", fam="V1", recuo=150.0),
    dict(id="V3 r150", fam="V3", recuo=150.0),
]


def grade() -> list[dict]:
    return [dict(id=f"{e['id']} | {x['id']}", ent=e, ex=x) for e in ENTRADAS for x in SAIDAS]
