# -*- coding: utf-8 -*-
"""Autopsia por trade do padrao atual (G21 + EMA34, congelado v29).

Para cada entrada, mede o que o mercado mostrava NO INSTANTE DO SINAL (vela
fechada que armou a limite -- so' passado, nada da propria operacao) e
procura sinais que separam vencedoras de perdedoras. Depois ajusta um modelo
de probabilidade so' no IS e confere no OOS-1/setembro, inclusive com mao
proporcional a probabilidade (0/1/2 contratos -- WIN nao tem fracao).

Disciplina: features escolhidas e modelo ajustado SO' no IS (jan-jun).
OOS-1 (jul-ago) e setembro so' recebem o que saiu pronto do IS.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "g29_ema34"))
import g29_base as b  # noqa: E402

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from strategy.daytrade.lab.win_busca_lucro_g29_retangulo_ema34_congelado_v29 import (  # noqa: E402
    WinBuscaLucroG29RetanguloEma34CongeladoV29 as Base,
)

OUT_CSV = AQUI / "g34_autopsia_trades.csv"


class Gravador(Base):
    """Mesma estrategia, so' anota cada sinal que virou ordem."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.sinais: list[dict] = []

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        for a in acoes:
            lado = getattr(a, "side", None)
            if lado is None or self._retangulo is None:
                continue
            r = self._retangulo
            self.sinais.append(dict(ts_sinal=ts, side=lado, largura=r["largura"],
                                    meio=r["meio"], topo=r["topo"], piso=r["piso"],
                                    limite=a.limit_price, stop=a.initial_stop,
                                    alvo=a.initial_target))
        return acoes


def roda(dias):
    win = b.carrega_win()
    bars = b.bars_dos_dias(win, dias)
    st = Gravador(periodo=34, stop_fracao_largura=b.STOP_FRACAO,
                  alvo_fracao_largura=b.ALVO_FRACAO)
    res = run_intraday_backtest(bars, st, b.monta_config(b.CAPITAL))
    return list(res.trades), st.sinais


# ---------------------------------------------------------------- features
def prepara_serie(win: pd.DataFrame) -> pd.DataFrame:
    d = win[["open", "high", "low", "close", "real_volume"]].copy()
    d["ema34"] = d["close"].ewm(span=34, adjust=False).mean()
    d["ema100"] = d["close"].ewm(span=100, adjust=False).mean()
    d["atr14"] = (d["high"] - d["low"]).rolling(14).mean()
    d["data"] = d.index.date
    g = d.groupby("data")
    d["abertura_dia"] = g["open"].transform("first")
    d["max_dia"] = g["high"].cummax()
    d["min_dia"] = g["low"].cummin()
    d["vol5"] = d["real_volume"].rolling(5).sum()
    d["vol5_med60"] = d["vol5"].rolling(60).mean()
    d["ret_barra"] = d["close"].diff()
    d["choppy30"] = (d["ret_barra"].abs().rolling(30).sum()
                     / (d["close"] - d["close"].shift(30)).abs().clip(lower=5))
    fech_dia = g["close"].last()
    aber_dia = g["open"].first()
    ontem = pd.DataFrame({"fech_ontem": fech_dia.shift(1),
                          "dir_ontem": (fech_dia - aber_dia).shift(1)})
    d = d.join(ontem, on="data")
    return d


def features(sinal: dict, d: pd.DataFrame) -> dict | None:
    ts = sinal["ts_sinal"]
    if ts not in d.index:
        return None
    i = d.index.get_loc(ts)
    if i < 120:
        return None
    row = d.iloc[i]
    s = 1.0 if sinal["side"] == "long" else -1.0
    atr = max(row["atr14"], 5.0)
    c = row["close"]
    rng = max(row["high"] - row["low"], 5.0)
    faixa_dia = max(row["max_dia"] - row["min_dia"], 5.0)
    pos_dia = (c - row["min_dia"]) / faixa_dia
    return {
        "lado_compra": 1.0 if s > 0 else 0.0,
        "hora": ts.hour + ts.minute / 60.0,
        "largura_pts": sinal["largura"],
        "largura_atr": sinal["largura"] / atr,
        "atr14": atr,
        "dist_ema34_atr": s * (c - row["ema34"]) / atr,
        "incl_ema34_10": s * (row["ema34"] - d["ema34"].iloc[i - 10]) / atr,
        "dist_ema100_atr": s * (c - row["ema100"]) / atr,
        "incl_ema100_30": s * (row["ema100"] - d["ema100"].iloc[i - 30]) / atr,
        "ret5_atr": s * (c - d["close"].iloc[i - 5]) / atr,
        "ret30_atr": s * (c - d["close"].iloc[i - 30]) / atr,
        "ret_dia_atr": s * (c - row["abertura_dia"]) / atr,
        "pos_no_dia": pos_dia if s > 0 else 1.0 - pos_dia,
        "corpo_vela": s * (c - row["open"]) / rng,
        "pavio_contra": ((row["high"] - max(c, row["open"])) if s > 0
                         else (min(c, row["open"]) - row["low"])) / rng,
        "vol_rel": row["vol5"] / row["vol5_med60"] if row["vol5_med60"] > 0 else np.nan,
        "choppy30": row["choppy30"],
        "dist_meio_larg": s * (c - sinal["meio"]) / sinal["largura"],
        "dir_ontem": s * np.sign(row["dir_ontem"]) if row["dir_ontem"] == row["dir_ontem"] else 0.0,
        "gap_atr": s * (row["abertura_dia"] - row["fech_ontem"]) / atr
        if row["fech_ontem"] == row["fech_ontem"] else 0.0,
    }


def monta_tabela(trades, sinais, d, janela: str) -> pd.DataFrame:
    sin = pd.DataFrame(sinais).sort_values("ts_sinal")
    linhas = []
    for t in sorted(trades, key=lambda x: x.entry_ts):
        cand = sin[(sin["ts_sinal"] < t.entry_ts) & (sin["side"] == t.side)]
        if cand.empty:
            continue
        s = cand.iloc[-1].to_dict()
        f = features(s, d)
        if f is None:
            continue
        f.update(janela=janela, ts_sinal=s["ts_sinal"], entry_ts=t.entry_ts,
                 side=t.side, pnl=t.pnl_brl, ganhou=int(t.pnl_brl > 0),
                 atraso_min=(t.entry_ts - s["ts_sinal"]).total_seconds() / 60)
        linhas.append(f)
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------- estatistica
def auc(score: np.ndarray, y: np.ndarray) -> float:
    ok = ~np.isnan(score)
    score, y = score[ok], y[ok]
    n1, n0 = y.sum(), len(y) - y.sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = pd.Series(score).rank().to_numpy()
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def logistica(X, y, l2=1.0, it=4000, lr=0.1):
    w = np.zeros(X.shape[1]); b0 = 0.0
    for _ in range(it):
        p = 1 / (1 + np.exp(-(X @ w + b0)))
        g = p - y
        w -= lr * (X.T @ g / len(y) + l2 * w / len(y))
        b0 -= lr * g.mean()
    return w, b0


def br(v, dec=2):
    return b.br(v, dec)


def main():
    win = b.carrega_win()
    d = prepara_serie(win)
    janelas = {
        "IS jan-jun": (b.CORTE_IS_INICIO, b.CORTE_IS_FIM),
        "OOS-1 jul-ago": (b.CORTE_IS_FIM, b.CORTE_OOS1_FIM),
        "set": (b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM),
    }
    tabs = []
    for nome, (ini, fim) in janelas.items():
        dias = b.dias_da_janela(win, ini, fim)
        trades, sinais = roda(dias)
        t = monta_tabela(trades, sinais, d, nome)
        print(f"{nome}: {len(trades)} trades, {len(t)} casados com sinal, "
              f"liquido R${br(sum(x.pnl_brl for x in trades))}", flush=True)
        tabs.append(t)
    df = pd.concat(tabs, ignore_index=True)
    df.to_csv(OUT_CSV, index=False, sep=";", decimal=",")

    feats = [c for c in df.columns if c not in
             ("janela", "ts_sinal", "entry_ts", "side", "pnl", "ganhou", "atraso_min")]
    IS = df[df.janela == "IS jan-jun"]
    O1 = df[df.janela == "OOS-1 jul-ago"]
    ST = df[df.janela == "set"]

    # ---- 1) cada sinal sozinho: AUC no IS e a MESMA direcao fora dele
    print("\n== 1) cada sinal sozinho (AUC: 0,50 = nao separa; >0,50 = valor alto ganha mais) ==")
    print(f"{'sinal':18s} {'AUC IS':>7s} {'AUC OOS1':>8s} {'AUC set':>8s}  replica?")
    linhas = []
    for f in feats:
        a_is = auc(IS[f].to_numpy(float), IS.ganhou.to_numpy())
        a_o1 = auc(O1[f].to_numpy(float), O1.ganhou.to_numpy())
        a_st = auc(ST[f].to_numpy(float), ST.ganhou.to_numpy())
        mesmo = (np.sign(a_is - .5) == np.sign(a_o1 - .5) == np.sign(a_st - .5))
        linhas.append((f, a_is, a_o1, a_st, mesmo))
    for f, a_is, a_o1, a_st, mesmo in sorted(linhas, key=lambda x: -abs(x[1] - .5)):
        print(f"{f:18s} {br(a_is,3):>7s} {br(a_o1,3):>8s} {br(a_st,3):>8s}  "
              f"{'SIM, 3 janelas' if mesmo and abs(a_is-.5) >= .03 else '-'}")

    # ---- 2) quintis dos sinais mais fortes do IS, mostrando as 3 janelas
    top = [x[0] for x in sorted(linhas, key=lambda x: -abs(x[1] - .5))[:6]]
    print("\n== 2) quintis (cortes do IS) dos 6 sinais mais fortes no IS -- win% e R$/trade ==")
    for f in top:
        cortes = np.nanquantile(IS[f], [.2, .4, .6, .8])
        print(f"\n{f}  (cortes IS: {', '.join(br(c,2) for c in cortes)})")
        for nome, w in (("IS", IS), ("OOS1", O1), ("set", ST)):
            q = np.digitize(w[f].to_numpy(float), cortes)
            partes = []
            for k in range(5):
                m = q == k
                if m.sum() == 0:
                    partes.append(f"Q{k+1}: --")
                    continue
                partes.append(f"Q{k+1}: {100*w.ganhou[m].mean():4.0f}% {br(w.pnl[m].mean(),0):>5s} (n{m.sum()})")
            print(f"  {nome:4s} " + " | ".join(partes))

    # ---- 3) modelo de probabilidade (ajustado so' no IS)
    mu = IS[feats].mean(); sd = IS[feats].std().replace(0, 1)
    def Z(w):
        return ((w[feats] - mu) / sd).fillna(0).to_numpy(float)
    wts, b0 = logistica(Z(IS), IS.ganhou.to_numpy(float), l2=20.0)
    def prob(w):
        return 1 / (1 + np.exp(-(Z(w) @ wts + b0)))
    p_is, p_o1, p_st = prob(IS), prob(O1), prob(ST)
    print("\n== 3) modelo de probabilidade (logistica, ajustada so' no IS) ==")
    print(f"AUC IS={br(auc(p_is, IS.ganhou.to_numpy()),3)}  OOS1={br(auc(p_o1, O1.ganhou.to_numpy()),3)}  "
          f"set={br(auc(p_st, ST.ganhou.to_numpy()),3)}")
    print("pesos (padronizados):")
    for f, w in sorted(zip(feats, wts), key=lambda x: -abs(x[1]))[:10]:
        print(f"  {f:18s} {w:+.3f}")

    c1, c2 = np.quantile(p_is, [1/3, 2/3])
    print(f"\nterços de probabilidade (cortes do IS: {br(c1,3)} / {br(c2,3)})")
    print(f"{'janela':6s} {'terço':12s} {'n':>4s} {'win%':>6s} {'R$/trade':>9s} {'liquido':>10s}")
    for nome, w, p in (("IS", IS, p_is), ("OOS1", O1, p_o1), ("set", ST, p_st)):
        q = np.digitize(p, [c1, c2])
        for k, rot in enumerate(("baixa", "media", "alta")):
            m = q == k
            if m.sum() == 0:
                continue
            print(f"{nome:6s} {rot:12s} {m.sum():>4d} {100*w.ganhou[m].mean():>5.1f}% "
                  f"{br(w.pnl[m].mean()):>9s} {br(w.pnl[m].sum()):>10s}")

    # ---- 4) mao proporcional a probabilidade
    print("\n== 4) mao pela probabilidade (WIN nao tem fracao: 0/1/2 contratos) ==")
    print(f"{'janela':6s} {'regra':26s} {'trades':>6s} {'liquido':>10s} {'pior DD':>9s}")
    for nome, w, p in (("IS", IS, p_is), ("OOS1", O1, p_o1), ("set", ST, p_st)):
        q = np.digitize(p, [c1, c2])
        pnl = w.pnl.to_numpy()
        regras = {
            "atual (1 sempre)": np.ones(len(q)),
            "pula baixa, 1 no resto": np.where(q == 0, 0, 1),
            "0 / 1 / 2 contratos": q.astype(float),
            "1 / 1 / 2 contratos": np.where(q == 2, 2, 1),
        }
        for rot, mao in regras.items():
            serie = np.cumsum(pnl * mao)
            dd = (np.maximum.accumulate(np.r_[0, serie]) - np.r_[0, serie]).max()
            print(f"{nome:6s} {rot:26s} {int((mao>0).sum()):>6d} {br(serie[-1]):>10s} {br(-dd):>9s}")
    print(f"\ntabela por trade salva em {OUT_CSV}")


if __name__ == "__main__":
    main()
