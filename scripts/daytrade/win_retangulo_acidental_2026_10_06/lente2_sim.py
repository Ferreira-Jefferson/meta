"""Lente 2: simula_dia estendido (stop movel/breakeven, saida por tempo). Nao altera sim.py."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np, pandas as pd
import sim
from sim import (Cfg, MARGEM_MORTE, BARRAS_MORTE, detecta, _no_tick, _valido, carregar, resumo)


@dataclass(frozen=True)
class Cfg2(Cfg):
    be_pts: float | None = None     # apos lucro maximo >= be_pts, stop vai para entrada (+be_off)
    be_frac: float | None = None    # idem em multiplos de L
    be_off: float = 0.0
    tempo_min: int | None = None    # sai a mercado N min apos a entrada (abertura da 1a barra >=)


def simula_dia2(df, cfg: Cfg2):
    tick = 0.5 if cfg.modo_defeito else 5.0
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    minuto = (df.index.hour * 60 + df.index.minute).to_numpy()
    ts = df.index; W = cfg.janela
    ops = []; ret = None; fora = 0; pend = None; pos = None; ja = False

    def fecha(i, preco, tipo):
        nonlocal pos
        pts = (preco - pos["ent"]) * pos["lado"]
        ops.append(dict(dia=ts[i].date(), lado=pos["lado"], t_ent=pos["t_ent"], t_sai=ts[i],
                        ent=pos["ent"], sai=preco, saida=tipo, pts=pts))
        pos = None

    for b in range(1, len(df)):
        if minuto[b] >= cfg.zerar:
            pend = None
            if pos is not None:
                fecha(b, o[b], "zeragem")
            break
        if pos is not None and cfg.tempo_min is not None and \
                (ts[b] - pos["t_ent"]).total_seconds() / 60 >= cfg.tempo_min:
            fecha(b, o[b], "tempo")
        i = b - 1
        if ret is not None:
            marg = MARGEM_MORTE * ret[2]
            if c[i] > ret[0] + marg or c[i] < ret[1] - marg:
                fora += 1
                if fora >= BARRAS_MORTE:
                    ret = None; pend = None
            else:
                fora = 0
        if ret is None:
            n = i + 1
            if n >= 3 * W:
                s = slice(n - W, n)
                amp = h[n - 3 * W:n - W].max() - lo[n - 3 * W:n - W].min()
                r = detecta(h[s], lo[s], c[s], cfg.tol, amp)
                if r and r[2] >= max(4.4 * tick, cfg.piso_largura_pts):
                    ret = r; fora = 0
        if ret is not None and pos is None and not (ja and not cfg.rearma) and len(ops) < cfg.max_ops_dia:
            arma = True
            if pend is not None:
                pend["esp"] += 1
                if pend["esp"] < cfg.ttl: arma = False
                else: pend = None
            if arma and cfg.primeira_entrada <= minuto[b] < cfg.ultima_entrada:
                topo, piso, larg, meio = ret
                if c[i] != meio:
                    lado = -1 if c[i] < meio else 1
                    if cfg.inverte: lado = -lado
                    lim = _no_tick(meio, tick, cfg.modo_defeito)
                    ok_lado = (lim > c[i]) if lado == -1 else (lim < c[i])
                    if cfg.inverte: ok_lado = True
                    if ok_lado:
                        d_alvo = cfg.alvo_pts if cfg.alvo_pts is not None else (None if cfg.alvo_frac is None else cfg.alvo_frac * larg)
                        d_stop = cfg.stop_pts if cfg.stop_pts is not None else (None if cfg.stop_frac is None else cfg.stop_frac * larg)
                        alvo = None if d_alvo is None else _no_tick(meio + lado * d_alvo, tick)
                        stop = None if d_stop is None else _no_tick(meio - lado * d_stop, tick)
                        d_be = cfg.be_pts if cfg.be_pts is not None else (None if cfg.be_frac is None else cfg.be_frac * larg)
                        pend = dict(lado=lado, lim=lim, stop=stop, alvo=alvo, esp=0, be=d_be)
        if pos is None and pend is not None:
            lim, lado = pend["lim"], pend["lado"]
            folga = 5.0 if cfg.fill == "atravessa" else 0.0
            if cfg.inverte: cheio = lo[b] <= lim <= h[b]
            else: cheio = (h[b] >= lim + folga) if lado == -1 else (lo[b] <= lim - folga)
            if cheio:
                pos = dict(lado=lado, ent=lim, stop=pend["stop"], alvo=pend["alvo"], t_ent=ts[b], be=pend["be"])
                pend = None; ja = True
                st = pos["stop"]
                if st is not None and ((lado == 1 and lo[b] <= st) or (lado == -1 and h[b] >= st)):
                    fecha(b, st, "stop")
                continue
        if pos is not None:
            lado, st, al = pos["lado"], pos["stop"], pos["alvo"]
            if st is not None and ((lado == 1 and lo[b] <= st) or (lado == -1 and h[b] >= st)):
                fecha(b, min(o[b], st) if lado == 1 else max(o[b], st), "stop")
            elif al is not None and ((lado == 1 and h[b] >= al) or (lado == -1 and lo[b] <= al)):
                fecha(b, al, "alvo")
            elif pos["be"] is not None:
                fav = (h[b] - pos["ent"]) if lado == 1 else (pos["ent"] - lo[b])
                if fav >= pos["be"]:
                    novo = pos["ent"] + lado * cfg.be_off
                    if st is None or (novo > st if lado == 1 else novo < st):
                        pos["stop"] = novo
    else:
        if pos is not None:
            fecha(len(df) - 1, c[-1], "zeragem")
    return ops


def simula2(d, cfg):
    ops = []
    for _, g in d.groupby(d.index.date):
        ops += simula_dia2(g, cfg)
    return pd.DataFrame(ops)


SET = ("2026-09-01", "2026-10-02"); AGO = ("2026-08-12", "2026-09-01")
CUSTO = 2.0
def roda(d, cfg): return resumo(simula2(d, cfg), CUSTO)
