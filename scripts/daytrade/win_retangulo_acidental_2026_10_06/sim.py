"""Replica em Python do EA mt5/WdoRetangulo.mq5 rodando no WIN, com o defeito e sem ele.

O teste do dono (WINV26, 12/08-01/10/2026, inputs Janela 25 / Tol 0,28 / alvo 4,5xL / stop 4,5xL)
rodou com TickSizeWdo=0,5 num simbolo de tick 5: toda ordem cujo preco nao caiu num multiplo
de 5 foi recusada pela corretora. `modo_defeito=True` reproduz isso; `False` arredonda no tick
certo do WIN e todas as ordens passam.

Simulacao em barras M1 (o EA calcula em M1 qualquer que seja o grafico):
 - a decisao sobre a barra fechada t acontece na abertura de t+1 (mesmo do EA: IsNewBar);
 - a limite de entrada enche no TOQUE (`fill="toque"`, como o Testador) ou so' se o preco
   passar 1 tick alem (`fill="atravessa"`, conservador);
 - na barra do preenchimento so' o stop e' checado (pessimista); depois, se stop e alvo
   cabem na mesma barra, conta o stop (pessimista);
 - zeragem a mercado na abertura da 1a barra >= hora_zerar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

DADOS = Path(__file__).resolve().parents[3] / "data" / "wdo-mt5"
ARQ = {
    "WINV26": "WINV26_M1_202604151210_202610011824.csv",
    "WIN@2026": "WIN@_M1_202601020900_202610051831.csv",
    "WIN@2025": "WIN@_M1_202412020900_202510311824.csv",
}
PONTO_RS = 0.20  # R$ por ponto, 1 contrato WIN

TOQUES_MINIMOS = 2
VISITAS_MINIMAS = 2
CRUZAMENTOS_MINIMOS = 3
CONTENCAO_MINIMA = 0.95
CONTRACAO_MAXIMA = 0.55
ESPALHAMENTO_MINIMO = 1.0 / 3.0
DERIVA_MAXIMA = 0.25
MARGEM_MORTE = 0.25
BARRAS_MORTE = 3


@dataclass(frozen=True)
class Cfg:
    janela: int = 25
    tol: float = 0.28
    alvo_frac: float | None = 4.5      # None = sem alvo
    stop_frac: float | None = 4.5      # None = sem stop
    stop_pts: float | None = None      # stop fixo em pontos (substitui stop_frac se dado)
    alvo_pts: float | None = None
    ttl: int = 10
    zerar: int = 18 * 60 + 20          # minuto do dia
    ultima_entrada: int = 24 * 60      # nao arma limite a partir deste minuto
    primeira_entrada: int = 0          # nao arma limite antes deste minuto
    piso_largura_pts: float = 2.2      # 4,4 ticks x 0,5 (defeito: valor do WDO)
    modo_defeito: bool = False
    fill: str = "toque"
    inverte: bool = False              # nulo: mesmo gatilho, lado oposto
    max_ops_dia: int = 99
    tf_min: int = 1                    # 1 = M1 (como o EA); 5 = deteccao em M5
    rearma: bool = True                # False: depois de zerar/stop nao entra de novo no dia


def carregar(nome: str, ini: str | None = None, fim: str | None = None, tf_min: int = 1) -> pd.DataFrame:
    d = pd.read_csv(DADOS / ARQ[nome], sep="\t")
    d.columns = [c.strip("<>").lower() for c in d.columns]
    d["ts"] = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")
    d = d[["ts", "open", "high", "low", "close"]].set_index("ts").sort_index()
    if ini:
        d = d[d.index >= pd.Timestamp(ini)]
    if fim:
        d = d[d.index < pd.Timestamp(fim)]
    if tf_min > 1:
        d = d.groupby(d.index.date, group_keys=False).apply(
            lambda g: g.resample(f"{tf_min}min", label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna())
    return d


def _visitas(pos):
    return 1 + int(np.sum(np.diff(pos) > 1)) if len(pos) else 0


def detecta(h, l, c, tol, amp_ant):
    n = len(c)
    topo = float(np.quantile(h, 0.90))
    piso = float(np.quantile(l, 0.10))
    larg = topo - piso
    if larg <= 0:
        return None
    meio = (topo + piso) / 2
    zona = tol * larg
    t_mask = h >= topo - zona
    p_mask = (~t_mask) & (l <= piso + zona)
    pt = np.flatnonzero(t_mask)
    pp = np.flatnonzero(p_mask)
    if len(pt) < TOQUES_MINIMOS or len(pp) < TOQUES_MINIMOS:
        return None
    if _visitas(pt) < VISITAS_MINIMAS or _visitas(pp) < VISITAS_MINIMAS:
        return None
    m = ESPALHAMENTO_MINIMO * n
    if pt[-1] - pt[0] < m or pp[-1] - pp[0] < m:
        return None
    lados = np.where(t_mask, 1, np.where(p_mask, -1, 0))
    lados = lados[lados != 0]
    if int(np.sum(lados[1:] != lados[:-1])) < 2:
        return None
    acima = c > meio
    if int(np.sum(acima[1:] != acima[:-1])) < CRUZAMENTOS_MINIMOS:
        return None
    if np.mean((c >= piso) & (c <= topo)) < CONTENCAO_MINIMA:
        return None
    t3 = n // 3
    if abs(c[n - t3:].mean() - c[:t3].mean()) > DERIVA_MAXIMA * larg:
        return None
    if amp_ant > 0 and larg / amp_ant > CONTRACAO_MAXIMA:
        return None
    return topo, piso, larg, meio


def _no_tick(p, tick, defeito=False):
    x = math.floor(p / tick + 0.5) * tick
    # no EA o NormalizeDouble(..., _Digits=0) do WIN leva o x,5 ao inteiro: o preco efetivo e' inteiro
    return math.floor(x + 0.5) if defeito else x


def _valido(p):
    return abs(p / 5.0 - round(p / 5.0)) < 1e-9


def simula_dia(df: pd.DataFrame, cfg: Cfg) -> list[dict]:
    """Um pregao. df: barras do dia em ordem."""
    tick = 0.5 if cfg.modo_defeito else 5.0
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    minuto = (df.index.hour * 60 + df.index.minute).to_numpy()
    ts = df.index
    W = cfg.janela
    ops: list[dict] = []
    ret = None; fora = 0
    pend = None   # dict(lado, lim, stop, alvo, esp)
    pos = None    # dict(lado, ent, stop, alvo, t_ent)
    ja_operou = False

    def fecha(i, preco, tipo):
        nonlocal pos
        pts = (preco - pos["ent"]) * pos["lado"]
        ops.append(dict(dia=ts[i].date(), lado=pos["lado"], t_ent=pos["t_ent"], t_sai=ts[i],
                        ent=pos["ent"], sai=preco, saida=tipo, pts=pts))
        pos = None

    for b in range(1, len(df)):
        # --- abertura da barra b: zeragem ou processamento da barra fechada b-1 ---
        if minuto[b] >= cfg.zerar:
            pend = None
            if pos is not None:
                fecha(b, o[b], "zeragem")
            break
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
        if ret is not None and pos is None and not (ja_operou and not cfg.rearma) \
                and len(ops) < cfg.max_ops_dia:
            arma = True
            if pend is not None:
                pend["esp"] += 1
                if pend["esp"] < cfg.ttl:
                    arma = False
                else:
                    pend = None
            if arma and cfg.primeira_entrada <= minuto[b] < cfg.ultima_entrada:
                topo, piso, larg, meio = ret
                if c[i] != meio:
                    lado = -1 if c[i] < meio else 1
                    if cfg.inverte:
                        lado = -lado
                    lim = _no_tick(meio, tick, cfg.modo_defeito)
                    ok_lado = (lim > c[i]) if lado == -1 else (lim < c[i])
                    if cfg.inverte:
                        ok_lado = True  # nulo: entra no mesmo preco/instante, so' troca o lado
                    if ok_lado and (not cfg.modo_defeito or _valido(lim)):
                        d_alvo = cfg.alvo_pts if cfg.alvo_pts is not None else (
                            None if cfg.alvo_frac is None else cfg.alvo_frac * larg)
                        d_stop = cfg.stop_pts if cfg.stop_pts is not None else (
                            None if cfg.stop_frac is None else cfg.stop_frac * larg)
                        alvo = None if d_alvo is None else _no_tick(meio + lado * d_alvo, tick, cfg.modo_defeito)
                        stop = None if d_stop is None else _no_tick(meio - lado * d_stop, tick, cfg.modo_defeito)
                        if cfg.modo_defeito:
                            alvo = alvo if (alvo is not None and _valido(alvo)) else None
                            stop = stop if (stop is not None and _valido(stop)) else None
                        pend = dict(lado=lado, lim=lim, stop=stop, alvo=alvo, esp=0)

        # --- durante a barra b ---
        if pos is None and pend is not None:
            lim, lado = pend["lim"], pend["lado"]
            folga = 5.0 if cfg.fill == "atravessa" else 0.0
            if cfg.inverte:
                cheio = lo[b] <= lim <= h[b]
            else:
                cheio = (h[b] >= lim + folga) if lado == -1 else (lo[b] <= lim - folga)
            if cheio:
                pos = dict(lado=lado, ent=lim, stop=pend["stop"], alvo=pend["alvo"], t_ent=ts[b])
                pend = None; ja_operou = True
                st = pos["stop"]
                if st is not None and ((lado == 1 and lo[b] <= st) or (lado == -1 and h[b] >= st)):
                    fecha(b, st, "stop")
                continue
        if pos is not None:
            lado, st, al = pos["lado"], pos["stop"], pos["alvo"]
            if st is not None and ((lado == 1 and lo[b] <= st) or (lado == -1 and h[b] >= st)):
                px = min(o[b], st) if lado == 1 else max(o[b], st)
                fecha(b, px, "stop")
            elif al is not None and ((lado == 1 and h[b] >= al) or (lado == -1 and lo[b] <= al)):
                fecha(b, al, "alvo")
    else:
        if pos is not None:  # pregao acabou antes da hora de zerar
            fecha(len(df) - 1, c[-1], "zeragem")
    return ops


def simula(d: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    ops = []
    for _, g in d.groupby(d.index.date):
        ops += simula_dia(g, cfg)
    return pd.DataFrame(ops)


def resumo(t: pd.DataFrame, custo_rs: float = 0.0) -> dict:
    if t.empty:
        return dict(trades=0, pts=0.0, rs=0.0, win=float("nan"), pf=float("nan"), pior_dia=0.0, dd=0.0)
    rs = t["pts"] * PONTO_RS - custo_rs
    dia = rs.groupby(t["dia"]).sum()
    eq = rs.cumsum()
    g, p = rs[rs > 0].sum(), -rs[rs < 0].sum()
    return dict(trades=len(t), pts=float(t["pts"].sum()), rs=float(rs.sum()),
                win=float((rs > 0).mean() * 100), pf=float(g / p) if p > 0 else float("inf"),
                pior_dia=float(dia.min()), dd=float((eq.cummax() - eq).max()))
