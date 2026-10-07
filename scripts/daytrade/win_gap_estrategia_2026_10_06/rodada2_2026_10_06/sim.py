# -*- coding: utf-8 -*-
"""Simulador de execucao a nivel de TICK para a familia gap/1a barra do WIN (rodada 2).

Mesmas regras do motor (`backtest/intraday/machine.py`), com a resolucao trocada de barra M5 para tick:
  * sinal na barra M5 FECHADA (09:00-09:05); ordem so' existe a partir do instante do fecho (09:05);
  * entrada: `EnterLimit` com prazo `ttl` barras M5 (30 min); long enche quando o preco <= limite
    (toque) ou <= limite-1 tick (`atrav+1t`); preco do fill = o limite (como o motor);
  * `anchor_exits_at_fill`: stop/alvo = distancias a partir do preco preenchido (== limite);
  * alvo = ordem-limite real, sem deslize, sem prazo; stop e demais saidas a MERCADO, 1 tick de
    deslize contra a posicao (`slippage_ticks=1`); fee R$0,50 por contrato (ida e volta);
  * zera no fim do CONTINUO: ultimo tick do dia (a barra das 18:20 / 17:50), nunca o call;
  * a diferenca para o motor: aqui stop/alvo valem a partir do tick seguinte ao fill (o motor so'
    olha a barra seguinte) -- e' a correcao pedida pelo dono.
Stops moveis (trailing, breakeven) e saidas parciais seguem a regra de producao: a ESTRATEGIA
recalcula o nivel no fecho de cada barra M5 e ele vale da barra seguinte (AdjustStop), usando so'
barras fechadas e os extremos dos ticks DESDE A ENTRADA.

`modo="barra"` reproduz a semantica do motor (barra a barra, fill-bar nao avaliado, stop primeiro,
ref = min/max(open, nivel)) so' para o cruzamento com o motor; aceita apenas stop/alvo fixos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

TICK = 5.0
PV = 0.2            # R$ por ponto por contrato
FEE = 0.5           # R$ por contrato (ida e volta)
SLIP = 5.0          # 1 tick de deslize nas saidas a mercado
M5 = 300_000
TTL_BARRAS = 6


def r5(x: float) -> float:
    return float(np.round(x / TICK) * TICK)


@dataclass
class Leg:
    qty: int
    exit_price: float
    reason: str          # stop | alvo | trail | tempo | flatten
    exit_t: int


@dataclass
class Trade:
    side: int
    qty: int
    entry_price: float
    fill_t: int
    legs: list = field(default_factory=list)
    kb0: int = 0                 # indice da barra M5 do fill
    fim_barra_fill: int = 0      # ms do fim dessa barra
    mae_pts: float = 0.0         # pior excursao contra a posicao desde o fill (<=0), em pontos

    @property
    def pnl(self) -> float:
        tot = 0.0
        for g in self.legs:
            pts = (g.exit_price - self.entry_price) * self.side
            tot += pts * PV * g.qty - FEE * g.qty
        return tot

    @property
    def sai_na_barra_do_fill(self) -> bool:
        """saida por stop/alvo/trail DENTRO da barra M5 do fill (o motor so' enxerga a partir da proxima)."""
        g = self.legs[-1]
        return g.reason in ("stop", "alvo", "trail") and g.exit_t < self.fim_barra_fill

    @property
    def pior_pts(self) -> float:
        return min(((g.exit_price - self.entry_price) * self.side for g in self.legs), default=0.0)


@dataclass
class DiaTicks:
    t: np.ndarray       # ms desde 00:00 (int32)
    p: np.ndarray       # pontos (int32)
    bst: np.ndarray     # inicio de cada barra M5 (ms)
    bo: np.ndarray
    bh: np.ndarray
    bl: np.ndarray
    bc: np.ndarray
    bi: np.ndarray = None   # indice do 1o tick de cada barra (+ len)
    ema21: np.ndarray = None

    def __post_init__(self):
        self.bi = np.searchsorted(self.t, np.r_[self.bst, self.bst[-1] + M5], side="left")
        a = 2.0 / 22.0
        e = np.empty(len(self.bc)); e[0] = self.bc[0]
        for k in range(1, len(e)):
            e[k] = a * self.bc[k] + (1 - a) * e[k - 1]
        self.ema21 = e


def _first(mask: np.ndarray) -> int:
    """indice do 1o True ou -1."""
    if mask.size == 0:
        return -1
    i = int(mask.argmax())
    return i if mask[i] else -1


def procura_fill(d: DiaTicks, side: int, lim: float, fill_mode: str, t_sinal: int):
    """(indice do tick do fill ou -1). Janela: [t_sinal, t_sinal + TTL barras)."""
    i0 = int(np.searchsorted(d.t, t_sinal, side="left"))
    i1 = int(np.searchsorted(d.t, t_sinal + TTL_BARRAS * M5, side="left"))
    seg = d.p[i0:i1]
    nivel = lim - (TICK if fill_mode == "atrav+1t" else 0.0) * side
    j = _first(seg <= nivel if side > 0 else seg >= nivel)
    return -1 if j < 0 else i0 + j


@dataclass
class Saida:
    """Regras de saida ja' resolvidas em PRECOS para este pregao/entrada (o chamador traduz a spec)."""
    stop: float
    target: float | None = None
    trail: tuple | None = None       # ("pts", X) | ("swing", N) | ("ema", 21)
    be_after: float | None = None    # pontos de ganho (extremo desde a entrada) que levam o stop ao ponto de entrada
    partial: float | None = None     # fracao saida no alvo (resto segue)
    t_stop: int | None = None        # ms do dia para sair a mercado
    ttl_target_none: bool = True


def simula_tick(d: DiaTicks, side: int, lim: float, saida: Saida, qty: int, fill_mode: str,
                t_sinal: int) -> Trade | None:
    """None = sem fill. Senao Trade com pernas. Resolucao de tick."""
    f = procura_fill(d, side, lim, fill_mode, t_sinal)
    if f < 0:
        return None
    tr = Trade(side=side, qty=qty, entry_price=lim, fill_t=int(d.t[f]))
    kb0 = int(np.searchsorted(d.bst, d.t[f], side="right") - 1)
    stop = saida.stop
    stop0 = stop
    target = saida.target
    qty_aberta = qty
    best = lim                      # extremo favoravel desde a entrada
    n = len(d.t)
    tr.kb0 = kb0
    tr.fim_barra_fill = int(d.bst[kb0] + M5)
    moved = False
    nb = len(d.bst)
    for kb in range(kb0, nb):
        a = f + 1 if kb == kb0 else int(d.bi[kb])
        z = int(d.bi[kb + 1]) if kb + 1 < len(d.bi) else n
        z = min(z, n) if kb < nb - 1 else n
        if a < z:
            seg = d.p[a:z]
            ex = float(seg.min()) if side > 0 else float(seg.max())
            tr.mae_pts = min(tr.mae_pts, (ex - lim) * side)
            if side > 0:
                js = _first(seg <= stop)
                jt = _first(seg >= target) if target is not None else -1
            else:
                js = _first(seg >= stop)
                jt = _first(seg <= target) if target is not None else -1
            jx = -1
            if saida.t_stop is not None:
                jx = _first(d.t[a:z] >= saida.t_stop)
            cand = [(j, k) for j, k in ((js, "s"), (jt, "t"), (jx, "x")) if j >= 0]
            if cand:
                j, k = min(cand)
                px = float(seg[j]); tt = int(d.t[a + j])
                if k == "s":
                    reason = "trail" if moved else "stop"
                    tr.legs.append(Leg(qty_aberta, px - SLIP * side, reason, tt))
                    return tr
                if k == "x":
                    tr.legs.append(Leg(qty_aberta, px - SLIP * side, "tempo", tt))
                    return tr
                # alvo (ordem-limite): preenche no nivel, ou melhor se o tick ja' passou
                px_fill = float(max(px, target) if side > 0 else min(px, target))
                q_alvo = qty_aberta if saida.partial is None or qty_aberta == 1 else max(1, int(qty_aberta * saida.partial))
                tr.legs.append(Leg(q_alvo, px_fill, "alvo", tt))
                qty_aberta -= q_alvo
                target = None
                if qty_aberta <= 0:
                    return tr
                # resto continua: sem alvo; cai para a mesma barra (ticks seguintes) -- reavalia stop/tempo
                rest = seg[j + 1:]
                js2 = _first(rest <= stop if side > 0 else rest >= stop)
                jx2 = _first(d.t[a + j + 1:z] >= saida.t_stop) if saida.t_stop is not None else -1
                c2 = [(jj, kk) for jj, kk in ((js2, "s"), (jx2, "x")) if jj >= 0]
                if c2:
                    jj, kk = min(c2)
                    px2 = float(rest[jj]) if kk == "s" else float(d.p[a + j + 1 + jj])
                    tt2 = int(d.t[a + j + 1 + jj])
                    tr.legs.append(Leg(qty_aberta, px2 - SLIP * side, "trail" if (moved and kk == "s") else ("stop" if kk == "s" else "tempo"), tt2))
                    return tr
            # extremo desde a entrada (so' ticks apos o fill)
            best = max(best, float(seg.max())) if side > 0 else min(best, float(seg.min()))
        # fecha a barra kb: atualiza stop movel (vale da proxima barra)
        if kb == nb - 1:
            break
        novo = None
        if saida.trail is not None:
            kind, par = saida.trail
            if kind == "pts":
                novo = best - par * side
            elif kind == "swing":
                lo = max(0, kb - par + 1)
                novo = float(d.bl[lo:kb + 1].min()) if side > 0 else float(d.bh[lo:kb + 1].max())
            elif kind == "ema":
                novo = float(d.ema21[kb])
            if novo is not None and (novo - d.bc[kb]) * side >= 0:
                novo = None                      # nivel do lado errado do preco: nao arma
        if saida.be_after is not None and (best - lim) * side >= saida.be_after:
            be = lim + TICK * side
            novo = be if novo is None else (max(novo, be) if side > 0 else min(novo, be))
        if novo is not None:
            novo = r5(novo)
            if (novo - stop) * side > 0:
                stop = novo; moved = True
    # fim do continuo: zera no ultimo tick (preco do fechamento do contínuo) a mercado
    tr.legs.append(Leg(qty_aberta, float(d.p[-1]) - SLIP * side, "flatten", int(d.t[-1])))
    return tr


def simula_barra(d: DiaTicks, side: int, lim: float, stop: float, target: float | None, qty: int,
                 fill_mode: str, t_sinal: int) -> Trade | None:
    """Semantica do motor (barra a barra) -- so' para cruzar com ele. stop/alvo fixos."""
    k0 = int(np.searchsorted(d.bst, t_sinal, side="left"))
    nb = len(d.bst)
    fk = -1
    for k in range(k0, min(nb, k0 + TTL_BARRAS)):
        tocou = (d.bl[k] <= lim - (TICK if fill_mode == "atrav+1t" else 0.0)) if side > 0 else (d.bh[k] >= lim + (TICK if fill_mode == "atrav+1t" else 0.0))
        if tocou:
            fk = k
            break
    if fk < 0:
        return None
    tr = Trade(side=side, qty=qty, entry_price=lim, fill_t=int(d.bst[fk]))
    for k in range(fk + 1, nb):
        ult = k == nb - 1
        s_hit = d.bl[k] <= stop if side > 0 else d.bh[k] >= stop
        t_hit = target is not None and (d.bh[k] >= target if side > 0 else d.bl[k] <= target)
        if s_hit:
            ref = min(d.bo[k], stop) if side > 0 else max(d.bo[k], stop)
            tr.legs.append(Leg(qty, ref - SLIP * side, "stop", int(d.bst[k])))
            return tr
        if t_hit:
            ref = max(d.bo[k], target) if side > 0 else min(d.bo[k], target)
            tr.legs.append(Leg(qty, ref, "alvo", int(d.bst[k])))
            return tr
        if ult:
            tr.legs.append(Leg(qty, d.bc[k] - SLIP * side, "flatten", int(d.bst[k])))
            return tr
    tr.legs.append(Leg(qty, d.bc[fk] - SLIP * side, "flatten", int(d.bst[fk])))
    return tr
