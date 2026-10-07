"""Simulador da estrategia WIN (WMA 34 + SMMA 34) com a EXECUCAO em barras de 1 minuto.

O sinal e' decidido no fechamento da barra M5 (WMA/Linear Weighted 34 e SMMA/Smoothed 34 sobre o fechamento)
e a ordem entra na abertura da M5 seguinte, como o EA. Stop, alvo e trailing
percorrem o M1: dentro de uma barra de 1 min o stop vale antes do alvo, e o
stop novo do trailing so' vale a partir da barra seguinte. Stop que a barra ja
abre alem do nivel sai na abertura. Em barras de 5 min (range mediano 235 pts)
essa ordem dentro da vela nao era conhecida e o resultado ficava inflado.
Dados: data/wdo-mt5/WIN@D_M5_*.csv e WIN@D_M1_*.csv (scripts/daytrade/baixa_m1_mt5_csv.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from core.indicators import lwma, smma  # noqa: E402

PERIODO = 34
SEM_ENTRADA, ZERAR = 17 * 60 + 30, 17 * 60 + 50
R_PT = 0.20


def ler(prefixo: str) -> pd.DataFrame:
    arq = sorted((ROOT / "data" / "wdo-mt5").glob(prefixo))[-1]
    d = pd.read_csv(arq, sep="\t")
    d.index = pd.to_datetime(d["<DATE>"] + " " + d["<TIME>"], format="%Y.%m.%d %H:%M:%S")
    return d.rename(columns={"<OPEN>": "open", "<HIGH>": "high", "<LOW>": "low", "<CLOSE>": "close"})[
        ["open", "high", "low", "close"]].astype(float)


def preparar(mes: str, limpa: bool = False, periodo: int = PERIODO, so_roxa: bool = False,
             cruz: int | None = None, folga: float | None = None, gap: float | None = None) -> pd.DataFrame:
    """M1 SO' do mes AAAA-MM. As medias usam o historico anterior apenas como aquecimento.
    limpa=True: so' sinal com a vela M5 INTEIRA (maxima/minima) fora das duas medias, sem tocar nelas."""
    m5, m1 = ler("WIN@D_M5_*.csv"), ler("WIN@D_M1_*.csv")
    e, w = smma(m5.close, periodo), lwma(m5.close, periodo)
    if so_roxa:  # roxa (WMA): vela inteira acima + verde (SMMA) abaixo da roxa = compra; espelho = venda
        acima, abaixo = (m5.low > w) & (e < w), (m5.high < w) & (e > w)
        # filtros de "inicio do movimento" (opcionais): so' entra se o movimento ainda e' jovem
        if cruz is not None:  # no maximo N velas seguidas com o fechamento deste lado da roxa
            lado = np.sign(m5.close - w).fillna(0)
            run = lado.groupby((lado != lado.shift()).cumsum()).cumcount() + 1
            acima, abaixo = acima & (run <= cruz), abaixo & (run <= cruz)
        if folga is not None:  # vela a no maximo F pontos da roxa
            acima, abaixo = acima & ((m5.low - w) <= folga), abaixo & ((w - m5.high) <= folga)
        if gap is not None:  # verde a no maximo G pontos da roxa
            acima, abaixo = acima & ((w - e) <= gap), abaixo & ((e - w) <= gap)
    elif limpa:
        acima, abaixo = m5.low > np.maximum(e, w), m5.high < np.minimum(e, w)
    else:
        acima, abaixo = (m5.close > e) & (m5.close > w), (m5.close < e) & (m5.close < w)
    sig5 = pd.Series(np.where(acima, 1, np.where(abaixo, -1, 0)), index=m5.index)
    sig5[e.isna() | w.isna()] = 0
    prev = sig5.shift(1).fillna(0)
    desloc = sig5.index + pd.Timedelta(minutes=5)  # o EA ve o sinal na abertura da M5 seguinte
    m1 = m1[m1.index.strftime("%Y-%m") == mes].copy()
    m1["sinal"] = pd.Series(sig5.values, index=desloc).reindex(m1.index).fillna(0).astype(int)
    m1["troca"] = pd.Series((sig5 != prev).values, index=desloc).reindex(m1.index).fillna(False).astype(bool)
    m1["abre5"] = m1.index.minute % 5 == 0
    return m1


def simular(m1, stop, alvo, troca=False, custo=5.0, slip=2.0, trail_on=100.0, trail_dist=60.0, sinal_override=None):
    o, h, l = (m1[k].to_numpy() for k in ("open", "high", "low"))
    sig = m1["sinal"].to_numpy() if sinal_override is None else sinal_override
    tr_, ab5 = m1["troca"].to_numpy(), m1["abre5"].to_numpy()
    t = (m1.index.hour * 60 + m1.index.minute).to_numpy()
    dia = np.array(m1.index.date)
    out, pos = [], None

    def reg(rs, mot):  # registra a saida junto com o horario e o lado da entrada
        out.append((pos["dia"], rs, mot, pos["t"], m1.index[i], pos["d"], pos["e"]))
    for i in range(len(m1)):
        if pos is not None:
            if t[i] >= ZERAR or dia[i] != pos["dia"]:
                reg((pos["d"] * (o[i] - pos["e"]) - custo) * R_PT, "zera")
                pos = None
                continue
        elif ab5[i] and sig[i] != 0 and t[i] < SEM_ENTRADA and (not troca or tr_[i]):
            d = int(sig[i])
            pos = {"d": d, "e": o[i], "sl": o[i] - d * stop, "tp": o[i] + d * alvo, "mel": o[i],
                   "dia": dia[i], "sl0": o[i] - d * stop, "t": m1.index[i]}
        if pos is None:
            continue
        d = pos["d"]
        if d == 1:
            if l[i] <= pos["sl"]:
                pts = min(pos["sl"], o[i]) - pos["e"] - custo - slip
                reg(pts * R_PT, "stop" if pos["sl"] == pos["sl0"] else "trail")
                pos = None
                continue
            if h[i] >= pos["tp"]:
                reg((pos["tp"] - pos["e"] - custo) * R_PT, "alvo")
                pos = None
                continue
            pos["mel"] = max(pos["mel"], h[i])
            if pos["mel"] - pos["e"] >= trail_on:
                pos["sl"] = max(pos["sl"], pos["mel"] - trail_dist)
        else:
            if h[i] >= pos["sl"]:
                pts = pos["e"] - max(pos["sl"], o[i]) - custo - slip
                reg(pts * R_PT, "stop" if pos["sl"] == pos["sl0"] else "trail")
                pos = None
                continue
            if l[i] <= pos["tp"]:
                reg((pos["e"] - pos["tp"] - custo) * R_PT, "alvo")
                pos = None
                continue
            pos["mel"] = min(pos["mel"], l[i])
            if pos["e"] - pos["mel"] >= trail_on:
                pos["sl"] = min(pos["sl"], pos["mel"] + trail_dist)
    return pd.DataFrame(out, columns=["dia", "rs", "mot", "t_entrada", "t_saida", "dir", "entrada"])
