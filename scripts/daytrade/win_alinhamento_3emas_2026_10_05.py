"""WIN: alinhamento de 3 EMAs (21/50/200) — pedido do dono, 2026-10-05.

Regra (como pedida):
  COMPRA quando EMA21 > EMA50 > EMA200 e as tres apontam para cima
  VENDA  quando EMA21 < EMA50 < EMA200 e as tres apontam para baixo
  ("apontam" = EMA[t] > EMA[t-1] / < para venda)

O que o dono NAO especificou e foi fixado aqui (declarado na saida):
  * saida: quando o alinhamento quebra (qualquer das 3 condicoes cai) ou no fim
    do pregao (18:20) — day trade, nunca carrega.
  * entrada: ordem-limite no fechamento da barra do sinal, valida 5 barras
    (desenho fechado do repo: nunca a mercado). Fill no toque (fila do WIN
    nunca foi calibrada — premissa OTIMISTA).
  * saida por quebra = a mercado na abertura da barra seguinte (papel de stop),
    com 1 tick (5 pts) de deslize.
  * custo R$0,50/contrato ida+volta; 1 ponto = R$0,20.
  * capital R$1.000, 1 contrato fixo; para de operar se o caixa < margem R$100.
  * EMAs continuas entre pregoes (como no grafico do MT5).
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


def contratos(cash: float) -> int:
    if cash < 100:
        return 0
    return 1  # 1 contrato fixo: le o sinal, nao a alavancagem composta


def simula(d: pd.DataFrame, f: int, m: int, s: int, inclina: bool, ini, fim=None):
    c = d["c"]
    e1, e2, e3 = (c.ewm(span=p, adjust=False).mean() for p in (f, m, s))
    up = (e1 > e2) & (e2 > e3)
    dn = (e1 < e2) & (e2 < e3)
    if inclina:
        up &= (e1.diff() > 0) & (e2.diff() > 0) & (e3.diff() > 0)
        dn &= (e1.diff() < 0) & (e2.diff() < 0) & (e3.diff() < 0)
    est = np.where(up, 1, np.where(dn, -1, 0))
    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    o, h, l, cl = (d[k].values[sel] for k in "ohlc")
    est = est[sel]
    dias = idx.normalize()
    tempo = idx.time

    cash = CAP0
    trades = []  # (pnl, dia)
    eq = []
    pos = 0; qty = 0; px = 0.0
    pend = 0; lim = 0.0; ttl = 0
    n = len(idx)
    for t in range(n):
        novo_dia = t == 0 or dias[t] != dias[t - 1]
        if novo_dia:
            pend = 0
        # 1) saida pendente decidida na barra anterior executa na abertura desta
        if pos and (est[t - 1] != pos or tempo[t - 1] >= FIM or novo_dia) and t > 0:
            if novo_dia:  # fechou no fim do pregao anterior (seguranca)
                saida = cl[t - 1] - pos * TICK
            else:
                saida = o[t] - pos * TICK
            pnl = pos * (saida - px) / 1.0 * PT * qty - FEE_RT * qty
            cash += pnl; trades.append((pnl, dias[t - 1], pos * (saida - px))); pos = 0
        # 2) limite de entrada pendente
        if pend and not pos:
            if (pend == 1 and l[t] <= lim) or (pend == -1 and h[t] >= lim):
                q = contratos(cash)
                if q:
                    pos, qty = pend, q
                    px = min(lim, o[t]) if pend == 1 else max(lim, o[t])
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        # 3) sinal novo nesta barra (transicao para alinhado)
        if not pos and not pend and est[t] != 0 and tempo[t] < FIM:
            if t == 0 or est[t - 1] != est[t] or novo_dia:
                pend, lim, ttl = est[t], cl[t], TTL
        # fim do pregao: forca saida na ultima barra do dia
        ultimo = t == n - 1 or dias[t + 1] != dias[t]
        if pos and ultimo:
            saida = cl[t] - pos * TICK
            pnl = pos * (saida - px) * PT * qty - FEE_RT * qty
            cash += pnl; trades.append((pnl, dias[t], pos * (saida - px))); pos = 0
        eq.append(cash)
    return trades, pd.Series(eq, index=idx)


def linha(nome, trades, eq, extras=None):
    pnl = np.array([p for p, _, _ in trades]) if trades else np.array([0.0])
    pts = np.array([x for _, _, x in trades]) if trades else np.array([0.0])
    liq = float(eq.iloc[-1] - CAP0)
    pico = eq.cummax()
    dd = float((pico - eq).max())
    ddp = float(((pico - eq) / pico).max() * 100)
    pregoes = len(set(eq.index.date))
    win = float((pnl > 0).mean() * 100) if trades else 0.0
    ex = dict(extras or {})
    ganhos = pnl[pnl > 0].sum(); perdas = -pnl[pnl < 0].sum()
    ex["PF"] = num_br(ganhos / perdas) if perdas else "-"
    ex["R$/op"] = num_br(liq / len(trades)) if trades else "-"
    ex["min caixa"] = num_br(float(eq.min()))
    ex["pts/op"] = num_br(float(pts.mean()), 1)
    ex["dias s/trd"] = str(pregoes - len({dd for _, dd, _ in trades}))
    return LinhaResultado(
        variante=nome, liquido_brl=liq, maxdd_brl=dd, win_rate_pct=win,
        trades=len(trades), pregoes=pregoes, retorno_pct=liq / CAP0 * 100,
        maxdd_pct=ddp, capital_final=float(eq.iloc[-1]), extras=ex,
    )


def main():
    data = RAIZ / "data" / "wdo-mt5"
    v26 = data / "WINV26_M1_202604151210_202610011824.csv"
    cont = data / "WIN@D_M1_202110010900_202610011717.csv"
    EX = ("PF", "R$/op", "min caixa", "pts/op", "dias s/trd")

    print("=== PEDIDO: WINV26, 01/07-01/10/2026, EMAs 21/50/200, alinhadas+inclinadas ===", flush=True)
    linhas = []
    for tf in ("M1", "M5"):
        d = ler(v26, tf)
        for nome, ini, fim in (("3 meses", INI_JANELA, None),
                               ("so liquido 12/08+", LIQUIDO_DESDE, None),
                               ("so iliquido jul-11/08", INI_JANELA, LIQUIDO_DESDE)):
            tr, eq = simula(d, 21, 50, 200, True, ini, fim)
            linhas.append(linha(f"V26 {tf} 21/50/200 {nome}", tr, eq))
        dc = ler(cont, tf)
        tr, eq = simula(dc, 21, 50, 200, True, INI_JANELA)
        linhas.append(linha(f"WIN@D {tf} 21/50/200 3 meses", tr, eq))
        tr, eq = simula(d, 21, 50, 200, False, INI_JANELA)
        linhas.append(linha(f"V26 {tf} 21/50/200 sem inclinacao", tr, eq))
    print(tabela(linhas, extras=EX), flush=True)

    print("\n=== VARIACOES DE PERIODO (WIN@D, 3 meses, alinhadas+inclinadas) ===", flush=True)
    grade = []
    for tf in ("M1", "M5"):
        dc = ler(cont, tf)
        for f in (9, 13, 21, 34):
            for m in (34, 50, 72):
                if m <= f:
                    continue
                for s in (100, 200, 300):
                    tr, eq = simula(dc, f, m, s, True, INI_JANELA)
                    grade.append(linha(f"{tf} {f}/{m}/{s}", tr, eq))
    print(tabela(grade, extras=EX), flush=True)
    pos = sum(1 for g in grade if g.liquido_brl > 0)
    print(f"\ncelulas positivas: {pos}/{len(grade)}", flush=True)


if __name__ == "__main__":
    main()
