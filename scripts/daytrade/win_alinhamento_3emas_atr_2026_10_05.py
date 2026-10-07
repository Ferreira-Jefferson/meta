"""WIN: alinhamento de 3 EMAs 21/50/200 com stop 0,75xATR e alvo 3x o stop.

Pedido do dono, 2026-10-05 (segunda rodada — a primeira saia na quebra do
alinhamento, ver win_alinhamento_3emas_2026_10_05.py).

Regra:
  COMPRA: EMA21 > EMA50 > EMA200 e as tres subindo (EMA[t] > EMA[t-1])
  VENDA : espelho
  stop  = 0,75 x ATR(14) da barra do sinal, a partir do preco de fill
  alvo  = 3 x stop (= 2,25 x ATR)

Fixado aqui (o dono nao especificou):
  * entrada: ordem-limite no fechamento da barra do sinal, valida 5 barras,
    cancelada se o alinhamento sumir. Fill no toque (fila do WIN nao
    calibrada -> otimista).
  * "reentra": flat + alinhado = arma nova entrada (inclusive depois de stop/
    alvo no mesmo alinhamento). "transicao": so na barra em que alinha.
  * stop a mercado, 1 tick (5 pts) de deslize; abertura alem do stop sai na
    abertura. Alvo = limite, so enche se o preco NEGOCIAR 1 tick alem (nao no
    toque). Stop e alvo na mesma barra -> conta o stop.
  * fim do pregao: zera no fechamento da ultima barra do dia; sem entrada
    depois de 18:20. Nunca carrega.
  * custo R$0,50/contrato ida+volta; 1 pt = R$0,20; 1 contrato fixo;
    capital R$1.000, para se o caixa < R$100 (margem).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
from backtest.intraday.report import LinhaResultado, tabela, num_br  # noqa: E402

PT = 0.20
TICK = 5.0
FEE_RT = 0.50
CAP0 = 1000.0
TTL = 5
FIM = pd.Timestamp("18:20").time()
INI_JANELA = pd.Timestamp("2026-07-01")
LIQUIDO_DESDE = pd.Timestamp("2026-08-12")


def ler(path: Path, tf: str) -> pd.DataFrame:
    d = pd.read_csv(path, sep="\t")
    d.columns = [c.strip("<>") for c in d.columns]
    d.index = pd.to_datetime(d["DATE"] + " " + d["TIME"], format="%Y.%m.%d %H:%M:%S")
    d = d[["OPEN", "HIGH", "LOW", "CLOSE"]].astype(float)
    d.columns = ["o", "h", "l", "c"]
    if tf == "M5":
        d = d.resample("5min").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    return d


def atr(d: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = d["c"].shift()
    tr = pd.concat([d["h"] - d["l"], (d["h"] - pc).abs(), (d["l"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def tick(x: float) -> float:
    return max(TICK, round(x / TICK) * TICK)


def simula(d, f, m, s, k_stop, k_alvo, ini, fim=None, reentra=True):
    c = d["c"]
    e1, e2, e3 = (c.ewm(span=p, adjust=False).mean() for p in (f, m, s))
    up = (e1 > e2) & (e2 > e3) & (e1.diff() > 0) & (e2.diff() > 0) & (e3.diff() > 0)
    dn = (e1 < e2) & (e2 < e3) & (e1.diff() < 0) & (e2.diff() < 0) & (e3.diff() < 0)
    est_all = np.where(up, 1, np.where(dn, -1, 0))
    a_all = atr(d).values
    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    o, h, l, cl = (d[k].values[sel] for k in "ohlc")
    est, av = est_all[sel], a_all[sel]
    dias = idx.normalize()
    tempo = idx.time
    n = len(idx)

    cash = CAP0
    trades = []  # (pnl R$, dia, pts, motivo)
    eq = np.empty(n)
    pos = 0; px = stp = alv = 0.0
    pend = 0; lim = 0.0; ttl = 0; dist = 0.0

    def fecha(saida, dia, motivo):
        nonlocal cash, pos
        pts = pos * (saida - px)
        pnl = pts * PT - FEE_RT
        cash += pnl
        trades.append((pnl, dia, pts, motivo))
        pos = 0

    for t in range(n):
        if t == 0 or dias[t] != dias[t - 1]:
            pend = 0
        # entrada pendente
        if pend and not pos:
            if (pend == 1 and l[t] <= lim) or (pend == -1 and h[t] >= lim):
                if cash >= 100:
                    pos = pend
                    px = min(lim, o[t]) if pend == 1 else max(lim, o[t])
                    stp = px - pos * dist
                    alv = px + pos * k_alvo * dist
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        # stop / alvo (inclusive na barra do fill; stop tem prioridade)
        if pos == 1:
            if l[t] <= stp:
                fecha(min(o[t], stp) - TICK, dias[t], "stop")
            elif h[t] >= alv + TICK:
                fecha(alv, dias[t], "alvo")
        elif pos == -1:
            if h[t] >= stp:
                fecha(max(o[t], stp) + TICK, dias[t], "stop")
            elif l[t] <= alv - TICK:
                fecha(alv, dias[t], "alvo")
        # sinal
        if not pos and not pend and est[t] != 0 and tempo[t] < FIM and np.isfinite(av[t]):
            novo = t == 0 or est[t - 1] != est[t] or dias[t] != dias[t - 1]
            if reentra or novo:
                pend, lim, ttl = est[t], cl[t], TTL
                dist = tick(k_stop * av[t])
        # fim do pregao
        if pos and (t == n - 1 or dias[t + 1] != dias[t]):
            fecha(cl[t] - pos * TICK, dias[t], "fim")
        eq[t] = cash
    return trades, pd.Series(eq, index=idx)


def linha(nome, trades, eq):
    pnl = np.array([x[0] for x in trades]) if trades else np.array([0.0])
    liq = float(eq.iloc[-1] - CAP0)
    pico = eq.cummax()
    pregoes = len(set(eq.index.date))
    g = pnl[pnl > 0]; p = -pnl[pnl < 0]
    ex = {}
    ex["PF"] = num_br(g.sum() / p.sum()) if p.sum() else "-"
    ex["R$/op"] = num_br(liq / len(trades)) if trades else "-"
    be = p.mean() / (g.mean() + p.mean()) * 100 if len(g) and len(p) else float("nan")
    ex["BE emp%"] = num_br(be, 1)
    mot = [x[3] for x in trades]
    ex["alvo/stop/fim"] = f"{mot.count('alvo')}/{mot.count('stop')}/{mot.count('fim')}"
    ex["min caixa"] = num_br(float(eq.min()))
    ex["dias s/trd"] = str(pregoes - len({x[1] for x in trades}))
    return LinhaResultado(
        variante=nome, liquido_brl=liq, maxdd_brl=float((pico - eq).max()),
        win_rate_pct=float((pnl > 0).mean() * 100) if trades else 0.0,
        trades=len(trades), pregoes=pregoes, retorno_pct=liq / CAP0 * 100,
        maxdd_pct=float(((pico - eq) / pico).max() * 100),
        capital_final=float(eq.iloc[-1]), extras=ex,
    )


EX = ("PF", "R$/op", "BE emp%", "alvo/stop/fim", "min caixa", "dias s/trd")


def main():
    base = RAIZ / "data" / "wdo-mt5"
    v26 = base / "WINV26_M1_202604151210_202610011824.csv"
    cont = base / "WIN@D_M1_202110010900_202610011717.csv"
    dados = {(s, tf): ler(p, tf) for s, p in (("V26", v26), ("WIN@D", cont)) for tf in ("M1", "M5")}

    print("=== PEDIDO: EMAs 21/50/200 alinhadas+inclinadas, stop 0,75 ATR, alvo 3x ===", flush=True)
    L = []
    for tf in ("M1", "M5"):
        for nome, ini, fim in (("3 meses", INI_JANELA, None),
                               ("liquido 12/08+", LIQUIDO_DESDE, None)):
            for reentra in (True, False):
                tr, eq = simula(dados[("V26", tf)], 21, 50, 200, 0.75, 3, ini, fim, reentra)
                L.append(linha(f"V26 {tf} {nome} {'reentra' if reentra else 'transicao'}", tr, eq))
        for reentra in (True, False):
            tr, eq = simula(dados[("WIN@D", tf)], 21, 50, 200, 0.75, 3, INI_JANELA, None, reentra)
            L.append(linha(f"WIN@D {tf} 3 meses {'reentra' if reentra else 'transicao'}", tr, eq))
    print(tabela(L, extras=EX), flush=True)

    print("\n=== SENSIBILIDADE stop (xATR) x alvo (x stop) — WIN@D 3 meses, 21/50/200, reentra ===", flush=True)
    G = []
    for tf in ("M1", "M5"):
        for ks in (0.5, 0.75, 1.0, 1.5):
            for ka in (2, 3, 4, 5):
                tr, eq = simula(dados[("WIN@D", tf)], 21, 50, 200, ks, ka, INI_JANELA)
                G.append(linha(f"{tf} stop {num_br(ks)} alvo {ka}x", tr, eq))
    print(tabela(G, extras=EX), flush=True)
    print(f"celulas positivas: {sum(g.liquido_brl > 0 for g in G)}/{len(G)}", flush=True)

    print("\n=== PERIODOS DAS EMAs — WIN@D 3 meses, stop 0,75 ATR, alvo 3x, reentra ===", flush=True)
    P = []
    for tf in ("M1", "M5"):
        for f in (9, 13, 21, 34):
            for m in (34, 50, 72):
                if m <= f:
                    continue
                for s in (100, 200, 300):
                    tr, eq = simula(dados[("WIN@D", tf)], f, m, s, 0.75, 3, INI_JANELA)
                    P.append(linha(f"{tf} {f}/{m}/{s}", tr, eq))
    print(tabela(P, extras=EX), flush=True)
    print(f"celulas positivas: {sum(g.liquido_brl > 0 for g in P)}/{len(P)}", flush=True)


if __name__ == "__main__":
    main()
