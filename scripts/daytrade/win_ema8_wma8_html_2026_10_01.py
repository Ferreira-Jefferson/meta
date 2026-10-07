"""Simula a estrategia do EA mt5/WinEma8Wma8.mq5 (EMA8 + WMA8, M5, WIN) sobre os
ultimos N pregoes de data/raw_intraday/WIN_A_M5.parquet e grava dados.js + PNGs
em .claude/artifacts/win_ema8_wma8/ para o index.html mostrar.

Simulacao em barras de 5 min (sem tick): dentro da mesma barra o stop vale
ANTES do alvo (leitura conservadora) e o stop novo do trailing so' vale a
partir da barra seguinte. Decide no fechamento da barra i, entra no open da i+1
(como o EA, que age no 1o tick da barra nova). Custos: 5 pts por operacao
+ 2 pts de slippage nas saidas por stop. 1 ponto = R$0,20 por contrato.
Horarios em BRT: sem entrada a partir de 17:30, zera 17:50.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from core.indicators import ema, lwma  # noqa: E402

MES = sys.argv[1] if len(sys.argv) > 1 else "2026-09"  # AAAA-MM; dados: WIN@D M5 baixado do MT5 (5 anos)
PERIODO = 8
STOP = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
ALVO0 = float(sys.argv[3]) if len(sys.argv) > 3 else 600.0
INC0, ALVO_MAX = 150.0, 600.0
TAG = f"s{STOP:g}_a{ALVO0:g}"  # uma aba do HTML por combinacao stop/alvo
TRAIL_ON, TRAIL_DIST = 100.0, 60.0
SEM_ENTRADA, ZERAR = 17 * 60 + 30, 17 * 60 + 50
CUSTO_OP, SLIP_STOP, R_POR_PONTO = 5.0, 2.0, 0.20
MAX_PRINTS = 12
TROCA = False  # True = so entra quando o sinal MUDA (vela anterior nao tinha o mesmo sinal)
OUT = ROOT / ".claude" / "artifacts" / f"win_ema8_wma8_{MES}"
PRINTS_DIR = OUT / "prints" / TAG
PRINTS_DIR.mkdir(parents=True, exist_ok=True)
for f in PRINTS_DIR.glob("*.png"):
    f.unlink()

CATS = ["Stop inicial", "Trailing", "Alvo", "Zeragem 17:50"]
ARQ = {"Stop inicial": "stop", "Trailing": "trailing", "Alvo": "alvo", "Zeragem 17:50": "zeragem"}


def carregar() -> pd.DataFrame:
    arq = sorted((ROOT / "data" / "wdo-mt5").glob("WIN@D_M5_*.csv"))[-1]
    d = pd.read_csv(arq, sep="	")
    d.index = pd.to_datetime(d["<DATE>"] + " " + d["<TIME>"], format="%Y.%m.%d %H:%M:%S")
    d = d.rename(columns={"<OPEN>": "open", "<HIGH>": "high", "<LOW>": "low", "<CLOSE>": "close"})[["open", "high", "low", "close"]].astype(float)
    # medias continuas entre pregoes (como o iMA do MT5): calcula na serie inteira e corta o mes depois
    d["ema"] = ema(d["close"], PERIODO)
    d["wma"] = lwma(d["close"], PERIODO)
    return d[d.index.strftime("%Y-%m") == MES]


def simular(d: pd.DataFrame) -> list[dict]:
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    e, w = d["ema"].to_numpy(), d["wma"].to_numpy()
    sig = np.where((c > e) & (c > w), 1, np.where((c < e) & (c < w), -1, 0))
    sig[np.isnan(e) | np.isnan(w)] = 0
    t = d.index.hour * 60 + d.index.minute
    dia = d.index.date
    trades, pos = [], None

    def fechar(i, preco, motivo, stop):
        nonlocal pos
        pts = pos["dir"] * (preco - pos["entrada"]) - CUSTO_OP - (SLIP_STOP if stop else 0.0)
        trades.append({**pos, "i_saida": i, "saida": preco, "motivo": motivo, "pts": pts,
                       "rs": pts * R_POR_PONTO, "sl_final": pos["sl"], "tp_final": pos["tp"]})
        pos = None

    for i in range(1, len(d)):
        if pos:
            if t[i] >= ZERAR or dia[i] != dia[pos["i_entrada"]]:
                fechar(i, o[i], "Zeragem 17:50", False)
                continue
            if sig[i - 1] == pos["dir"] and pos["alvo"] < ALVO_MAX:
                pos["alvo"] = min(pos["alvo"] + pos["inc"], ALVO_MAX)
                pos["inc"] /= 2.0
                pos["tp"] = pos["entrada"] + pos["dir"] * pos["alvo"]
        elif sig[i - 1] != 0 and t[i] < SEM_ENTRADA and (not TROCA or sig[i - 2] != sig[i - 1]):
            dr = int(sig[i - 1])
            pos = {"i_entrada": i, "dir": dr, "entrada": o[i], "sl": o[i] - dr * STOP,
                   "tp": o[i] + dr * ALVO0, "alvo": ALVO0, "inc": INC0, "melhor": o[i], "sl0": o[i] - dr * STOP}
        if not pos:
            continue
        dr = pos["dir"]
        if dr == 1:
            if l[i] <= pos["sl"]:
                fechar(i, min(pos["sl"], o[i]), "Stop inicial" if pos["sl"] == pos["sl0"] else "Trailing", True)
                continue
            if h[i] >= pos["tp"]:
                fechar(i, pos["tp"], "Alvo", False)
                continue
            pos["melhor"] = max(pos["melhor"], h[i])
            if pos["melhor"] - pos["entrada"] >= TRAIL_ON:
                pos["sl"] = max(pos["sl"], pos["melhor"] - TRAIL_DIST)
        else:
            if h[i] >= pos["sl"]:
                fechar(i, max(pos["sl"], o[i]), "Stop inicial" if pos["sl"] == pos["sl0"] else "Trailing", True)
                continue
            if l[i] <= pos["tp"]:
                fechar(i, pos["tp"], "Alvo", False)
                continue
            pos["melhor"] = min(pos["melhor"], l[i])
            if pos["entrada"] - pos["melhor"] >= TRAIL_ON:
                pos["sl"] = min(pos["sl"], pos["melhor"] + TRAIL_DIST)
    if pos:  # janela acabou com posicao aberta: zera no ultimo close
        fechar(len(d) - 1, c[-1], "Zeragem 17:50", False)
    return trades


def candles(ax, df) -> None:
    for ts, r in df.iterrows():
        cor = "#ffffff" if r.close == r.open else ("#4ade80" if r.close > r.open else "#f87171")
        ax.vlines(ts, r.low, r.high, color=cor, linewidth=1, zorder=2)
        ax.add_patch(plt.Rectangle((mdates.date2num(ts) - 0.0013, min(r.open, r.close)), 0.0026,
                                   max(abs(r.close - r.open), 5.0), facecolor=cor, edgecolor=cor, zorder=3))


def print_trade(d: pd.DataFrame, tr: dict, nome: str) -> None:
    a, b = max(tr["i_entrada"] - 12, 0), min(tr["i_saida"] + 4, len(d) - 1)
    jan = d.iloc[a : b + 1]
    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#0a0a0d")
    ax.set_facecolor("#0a0a0d")
    candles(ax, jan)
    ax.plot(jan.index, jan["ema"], color="#4aa3ff", lw=1.4, label="EMA 8")
    ax.plot(jan.index, jan["wma"], color="#da8ad6", lw=1.4, label="WMA 8")
    ti, ts_ = d.index[tr["i_entrada"]], d.index[tr["i_saida"]]
    ax.hlines(tr["entrada"], ti, ts_, color="#ffffff", lw=1, ls=":")
    ax.hlines(tr["sl_final"], ti, ts_, color="#f87171", lw=1, ls="--")
    ax.hlines(tr["tp_final"], ti, ts_, color="#4ade80", lw=1, ls="--")
    ax.plot([ti], [tr["entrada"]], marker="^" if tr["dir"] == 1 else "v", color="#5eead4", ms=11, zorder=5)
    ax.plot([ts_], [tr["saida"]], marker="x", color="#ffd700", ms=10, mew=2.5, zorder=5)
    ax.set_title(f"{'COMPRA' if tr['dir'] == 1 else 'VENDA'} · {ti:%d/%m/%Y %H:%M} · {nome} · {tr['pts']:+.0f} pts · R$ {tr['rs']:+.2f}",
                 color="#e9eaef", fontsize=11)
    ax.tick_params(colors="#8d8f9c")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    for s in ax.spines.values():
        s.set_color("#2a2b35")
    ax.grid(color="#1b1c24")
    ax.legend(facecolor="#131319", edgecolor="#2a2b35", labelcolor="#e9eaef", loc="upper left")
    fig.tight_layout()
    fig.savefig(PRINTS_DIR / f"{ARQ[nome]}_{ti:%Y%m%d_%H%M}.png", dpi=90, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    d = carregar()
    trades = simular(d)
    df = pd.DataFrame(trades)
    df["dia"] = [d.index[i].date() for i in df["i_entrada"]]
    por_dia = df.groupby("dia")["rs"].sum()
    por_mes = df.groupby(pd.to_datetime(df["dia"]).dt.strftime("%Y-%m"))["rs"].sum()

    saidas = []
    prints = {}
    for cat in CATS:
        sub = [t for t in trades if t["motivo"] == cat]
        saidas.append([cat, len(sub), round(sum(t["rs"] for t in sub), 2)])
        if not sub:
            continue
        idx = np.unique(np.linspace(0, len(sub) - 1, min(MAX_PRINTS, len(sub))).round().astype(int))
        prints[cat] = []
        for k in idx:  # amostra espacada no tempo, nao escolhida por resultado
            tr = sub[k]
            print_trade(d, tr, cat)
            ti = d.index[tr["i_entrada"]]
            prints[cat].append({"url": f"prints/{TAG}/{ARQ[cat]}_{ti:%Y%m%d_%H%M}.png",
                                "inicio": f"{ti:%d/%m/%Y %H:%M}", "fim": f"{d.index[tr['i_saida']]:%H:%M}",
                                "lado": "compra" if tr["dir"] == 1 else "venda",
                                "pts": round(tr["pts"], 1), "rs": round(tr["rs"], 2)})

    stats = {
        "pregoes": int(len(por_dia)), "ini": f"{d.index[0]:%d/%m/%Y}", "fim": f"{d.index[-1]:%d/%m/%Y}",
        "trades": len(df), "liquido": round(float(df["rs"].sum()), 2),
        "acerto": round(float((df["rs"] > 0).mean() * 100), 1),
        "dias_neg": int((por_dia < 0).sum()), "pior_dia": round(float(por_dia.min()), 2),
        "media_dia": round(float(por_dia.mean()), 2), "trades_dia": round(len(df) / len(por_dia), 1),
        "compras": int((df["dir"] == 1).sum()), "vendas": int((df["dir"] == -1).sum()),
    }
    dados = {"PARAMS": {"stop": STOP, "alvo": ALVO0, "alvo_max": ALVO_MAX}, "STATS": stats, "SAIDAS": saidas, "PRINTS": prints,
             "DIAS": [[str(k), round(float(v), 2)] for k, v in por_dia.items()],
             "MESES": [[k, round(float(v), 2)] for k, v in por_mes.items()]}
    (OUT / f"dados_{TAG}.js").write_text(f"DADOS_VARIANTES[\"{TAG}\"] = " + json.dumps(dados, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1), flush=True)
    print(saidas, flush=True)


if __name__ == "__main__":
    main()
