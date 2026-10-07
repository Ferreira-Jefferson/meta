"""WIN: alinhamento 21/50/200 + posicao do candle em relacao as medias.

Pedido do dono, 2026-10-05: a rodada com saida na quebra do alinhamento
(win_alinhamento_3emas_2026_10_05.py) e' a melhor que temos; so' WINV26 (nao
WIN@D); o teste nao olhava se o candle estava acima, abaixo ou entre as MMs.

Mesma execucao da rodada de saida-na-quebra (limite no fechamento do sinal,
TTL 5, saida a mercado na abertura seguinte com 1 tick, R$0,50 ida+volta,
1 contrato, R$1.000). Muda so' QUANDO arma a entrada:

  transicao      : so' na barra em que alinha (rodada original)
  reentra        : qualquer barra alinhada com a posicao zerada
  fecha>21       : reentra + fechamento do lado certo da EMA21 (compra: acima)
  corpo>21       : reentra + corpo inteiro do lado certo da EMA21
  candle>21      : reentra + candle inteiro (minima/maxima) do lado certo
  recuo 21-50    : reentra + fechamento ENTRE a EMA21 e a EMA50
  toque 21       : reentra + candle toca a EMA21 e fecha do lado certo

Saidas:
  quebra   : alinhamento quebra (original)
  fecha<21 : quebra OU fechamento do lado errado da EMA21
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
from backtest.intraday.report import LinhaResultado, tabela, num_br  # noqa: E402

PT, TICK, FEE_RT, CAP0, TTL = 0.20, 5.0, 0.50, 1000.0, 5
FIM = pd.Timestamp("18:20").time()

# MELHOR ATUAL do WIN (dono, 2026-10-05): toda melhoria e' testada sobre esta.
MELHOR = dict(filtro="reentra", saida="quebra", periodos=(9, 21, 34, 100, 200), tipo="EMA")


def ler(path: Path, tf: str) -> pd.DataFrame:
    d = pd.read_csv(path, sep="\t")
    d.columns = [c.strip("<>") for c in d.columns]
    d.index = pd.to_datetime(d["DATE"] + " " + d["TIME"], format="%Y.%m.%d %H:%M:%S")
    d = d[["OPEN", "HIGH", "LOW", "CLOSE"]].astype(float)
    d.columns = ["o", "h", "l", "c"]
    if tf == "M5":
        d = d.resample("5min").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    return d


def media(c: pd.Series, p: int, tipo: str) -> pd.Series:
    if tipo == "EMA":
        return c.ewm(span=p, adjust=False).mean()
    if tipo == "SMA":
        return c.rolling(p).mean()
    if tipo == "SMMA":  # Wilder / "suavizada" do MT5
        return c.ewm(alpha=1 / p, adjust=False).mean()
    if tipo == "WMA":
        w = np.arange(1, p + 1, dtype=float)
        return c.rolling(p).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)
    raise ValueError(tipo)


def simula(d, filtro, saida, ini, fim=None, periodos=(21, 50, 200), tipo="EMA",
           permite_long=None, permite_short=None, qtd_long=None, qtd_short=None):
    """permite_*: array bool alinhado a d.index (None = sempre). Decidido na barra
    do SINAL, entao so' pode usar informacao ate o fechamento dela.
    qtd_*: array int de contratos alinhado a d.index (None = 1). Contrato extra
    exige caixa >= 100 + 250 x (q-1); se nao couber, reduz."""
    o_, h_, l_, c_ = d["o"], d["h"], d["l"], d["c"]
    es = [media(c_, p, tipo) for p in periodos]
    e1, e2 = es[0], es[1]
    up = pd.Series(True, index=d.index); dn = up.copy()
    for a_, b_ in zip(es, es[1:]):
        up &= a_ > b_; dn &= a_ < b_
    for e in es:
        up &= e.diff() > 0; dn &= e.diff() < 0
    est_all = np.where(up, 1, np.where(dn, -1, 0))
    lo_c, hi_c = np.minimum(o_, c_), np.maximum(o_, c_)
    filtros = {
        "transicao": (pd.Series(True, index=d.index), pd.Series(True, index=d.index)),
        "reentra": (pd.Series(True, index=d.index), pd.Series(True, index=d.index)),
        "fecha>21": (c_ > e1, c_ < e1),
        "corpo>21": (lo_c > e1, hi_c < e1),
        "candle>21": (l_ > e1, h_ < e1),
        "recuo 21-50": ((c_ <= e1) & (c_ > e2), (c_ >= e1) & (c_ < e2)),
        "toque 21": ((l_ <= e1) & (c_ > e1), (h_ >= e1) & (c_ < e1)),
    }
    fl, fs = (x.values for x in filtros[filtro])
    lado21 = np.where(c_ > e1, 1, np.where(c_ < e1, -1, 0))

    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    o, h, l, cl = (d[k].values[sel] for k in "ohlc")
    est, fl, fs, lado21 = est_all[sel], fl[sel], fs[sel], lado21[sel]
    n_all = len(d)
    pl = np.ones(n_all, bool) if permite_long is None else np.asarray(permite_long, bool)
    ps = np.ones(n_all, bool) if permite_short is None else np.asarray(permite_short, bool)
    ql = np.ones(n_all, int) if qtd_long is None else np.asarray(qtd_long, int)
    qs = np.ones(n_all, int) if qtd_short is None else np.asarray(qtd_short, int)
    pl, ps, ql, qs = pl[sel], ps[sel], ql[sel], qs[sel]
    q_pend = 1; qty = 1
    dias = idx.normalize()
    tempo = idx.time
    n = len(idx)

    cash = CAP0
    trades = []
    eq = np.empty(n)
    pos = 0; px = 0.0; pend = 0; lim = 0.0; ttl = 0
    t_ent = None; lado_ent = 0

    def fecha(s, dia):
        nonlocal cash, pos, t_ent, lado_ent, t_atual
        pts = pos * (s - px)
        pnl = (pts * PT - FEE_RT) * qty
        cash += pnl
        trades.append((pnl, dia, pts, t_ent, lado_ent, idx[t_atual], qty))
        pos = 0

    for t in range(n):
        t_atual = t
        novo_dia = t == 0 or dias[t] != dias[t - 1]
        if novo_dia:
            pend = 0
        if pos and t > 0 and not novo_dia:
            sai = est[t - 1] != pos or tempo[t - 1] >= FIM
            if saida == "fecha<21" and lado21[t - 1] == -pos:
                sai = True
            if sai:
                fecha(o[t] - pos * TICK, dias[t])
        if pend and not pos:
            if (pend == 1 and l[t] <= lim) or (pend == -1 and h[t] >= lim):
                q = q_pend
                while q > 1 and cash < 100 + 250 * (q - 1):
                    q -= 1
                if cash >= 100 and q >= 1:
                    pos, qty = pend, q
                    px = min(lim, o[t]) if pend == 1 else max(lim, o[t])
                    t_ent, lado_ent = idx[t], pend
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        if not pos and not pend and est[t] != 0 and tempo[t] < FIM:
            ok = fl[t] if est[t] == 1 else fs[t]
            if filtro == "transicao":
                ok = t == 0 or est[t - 1] != est[t] or novo_dia
            if ok:
                ok = pl[t] if est[t] == 1 else ps[t]
            if ok:
                pend, lim, ttl = est[t], cl[t], TTL
                q_pend = int(ql[t] if est[t] == 1 else qs[t])
                if q_pend < 1:
                    pend = 0
        if pos and (t == n - 1 or dias[t + 1] != dias[t]):
            fecha(cl[t] - pos * TICK, dias[t])
        eq[t] = cash
    return trades, pd.Series(eq, index=idx)


def linha(nome, trades, eq):
    pnl = np.array([x[0] for x in trades]) if trades else np.array([0.0])
    pts = np.array([x[2] for x in trades]) if trades else np.array([0.0])
    liq = float(eq.iloc[-1] - CAP0)
    pico = eq.cummax()
    pregoes = len(set(eq.index.date))
    g = pnl[pnl > 0]; p = -pnl[pnl < 0]
    be = p.mean() / (g.mean() + p.mean()) * 100 if len(g) and len(p) else float("nan")
    ex = {
        "PF": num_br(g.sum() / p.sum()) if p.sum() else "-",
        "R$/op": num_br(liq / len(trades)) if trades else "-",
        "pts/op": num_br(float(pts.mean()), 1),
        "BE emp%": num_br(be, 1),
        "min caixa": num_br(float(eq.min())),
        "dias s/trd": str(pregoes - len({x[1] for x in trades})),
    }
    return LinhaResultado(
        variante=nome, liquido_brl=liq, maxdd_brl=float((pico - eq).max()),
        win_rate_pct=float((pnl > 0).mean() * 100) if trades else 0.0,
        trades=len(trades), pregoes=pregoes, retorno_pct=liq / CAP0 * 100,
        maxdd_pct=float(((pico - eq) / pico).max() * 100),
        capital_final=float(eq.iloc[-1]), extras=ex,
    )


EX = ("PF", "R$/op", "pts/op", "BE emp%", "min caixa", "dias s/trd")
FILTROS = ("transicao", "reentra", "fecha>21", "corpo>21", "candle>21", "recuo 21-50", "toque 21")
JANELAS = (
    ("liq 12/08+", pd.Timestamp("2026-08-12"), None),
    ("ago 12-31", pd.Timestamp("2026-08-12"), pd.Timestamp("2026-09-01")),
    ("set", pd.Timestamp("2026-09-01"), None),
)


def main():
    v26 = RAIZ / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
    for tf in ("M5", "M1"):
        d = ler(v26, tf)
        for saida in ("quebra", "fecha<21"):
            for jn, a, b in JANELAS:
                L = [linha(f"{tf} {f}", *simula(d, f, saida, a, b)) for f in FILTROS]
                print(f"\n=== WINV26 {tf} | saida: {saida} | {jn} ===", flush=True)
                print(tabela(L, extras=EX), flush=True)


if __name__ == "__main__":
    main()
