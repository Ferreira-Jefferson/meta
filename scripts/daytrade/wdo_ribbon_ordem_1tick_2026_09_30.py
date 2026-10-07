"""Ordem das 4 MMs do ribbon WDO (SMA/EMA/SMMA/LWMA, periodo 34), contando so'
as ocorrencias em que as MMs estao SEPARADAS: toda MM a pelo menos 1 tick
(0,5 pt no WDO) da vizinha na ordenacao. Barra em que alguma vizinha esta a
menos de 1 tick nao define ordem -- e' ignorada (a ultima ordem valida segue
valendo) e so' conta uma nova ocorrencia quando aparece OUTRA ordem valida.

Medicao sobre UM pregao (29/09/2026, WDOV26, M1) -- descritiva, nao e' teste
de estrategia. MMs padrao do MT5, continuas entre pregoes (mesmas do template
com_MM.tpl). Gera dados.js + PNGs em .claude/artifacts/ordem_ribbon_wdo_1tick/.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import MetaTrader5 as mt5  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from core.indicators import ema, lwma, sma, smma  # noqa: E402

TERMINAL = r"C:\Program Files\Rico - MetaTrader 5\terminal64.exe"
SIMBOLO = "WDOV26"
PERIODO = 34
TICK = 0.5  # WDO: tick minimo = 0,5 pt
FOLGA_TICKS = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0  # folga minima entre MMs vizinhas, em ticks (1.0 = 0,5 pt; 0.5 = 0,25 pt)
FOLGA_PT = FOLGA_TICKS * TICK
# 2o argumento "inclinacao": alem da folga, as 4 MMs precisam ter a MESMA inclinacao (todas subindo ou todas
# descendo) medida contra a barra anterior da MESMA COR (alta/baixa/doji) -- pula as de cor diferente no meio.
INCLINACAO = len(sys.argv) > 2 and sys.argv[2] == "inclinacao"
DIA_ALVO = datetime(2026, 9, 29).date()
MM_COLS = ["lwma", "ema", "sma", "smma"]
LABELS = np.array(["Roxa", "Azul", "Amarela", "Verde"])  # lwma, ema, sma, smma
CORES = {"lwma": "#da8ad6", "ema": "#0000ff", "sma": "#ffd700", "smma": "#3cb371"}
_NOME_FOLGA = {1.0: "1tick", 0.5: "meio_tick"}.get(FOLGA_TICKS, f"{FOLGA_TICKS:g}tick".replace(".", "_"))
OUT_DIR = ROOT / ".claude" / "artifacts" / f"ordem_ribbon_wdo_{_NOME_FOLGA}{'_inclinacao' if INCLINACAO else ''}"
(OUT_DIR / "prints").mkdir(parents=True, exist_ok=True)


def carregar() -> pd.DataFrame:
    if not mt5.initialize(path=TERMINAL):
        raise SystemExit(f"mt5: {mt5.last_error()}")
    d0 = datetime(DIA_ALVO.year, DIA_ALVO.month, DIA_ALVO.day)
    r = mt5.copy_rates_range(SIMBOLO, mt5.TIMEFRAME_M1, d0 - timedelta(days=15), d0 + timedelta(days=1))
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("time").sort_index()[["open", "high", "low", "close"]]


def nomes_ordem(idx: np.ndarray, index: pd.Index) -> pd.Series:
    rot = LABELS[idx]
    s = pd.Series(rot[:, 0], index=index)
    for i in range(1, 4):
        s = s + ">" + pd.Series(rot[:, i], index=index)
    return s


def plot_candles(ax, df) -> None:
    for ts, row in df.iterrows():
        cor = "#ffffff" if row.close == row.open else ("#4ade80" if row.close > row.open else "#f87171")  # doji sempre branco
        ax.vlines(ts, row.low, row.high, color=cor, linewidth=1, zorder=2)
        baixo, alto = min(row.open, row.close), max(row.open, row.close)
        ax.add_patch(plt.Rectangle((mdates.date2num(ts) - 0.00035, baixo), 0.0007, max(alto - baixo, 0.05),
                                   facecolor=cor, edgecolor=cor, zorder=3))


def main() -> None:
    df = carregar()
    close = df["close"]
    mm = pd.DataFrame({"sma": sma(close, PERIODO), "ema": ema(close, PERIODO),
                       "smma": smma(close, PERIODO), "lwma": lwma(close, PERIODO)})[MM_COLS]
    vals = mm.to_numpy()
    idx = np.argsort(-vals, axis=1)
    ordenado = np.take_along_axis(vals, idx, axis=1)
    folgas = ordenado[:, :-1] - ordenado[:, 1:]  # 3 distancias entre vizinhas
    tem_mm = mm.notna().all(axis=1).to_numpy()
    ok = tem_mm & (np.nan_to_num(folgas, nan=-1).min(axis=1) >= FOLGA_PT - 1e-9)
    folga_ok = ok.copy()
    incl_ok = np.ones(len(mm), dtype=bool)
    if INCLINACAO:
        cor = np.sign((df["close"] - df["open"]).to_numpy())  # +1 alta, -1 baixa, 0 doji
        ref = np.full(len(df), -1)
        ultimo: dict[float, int] = {}
        for i, c in enumerate(cor):
            ref[i] = ultimo.get(c, -1)
            ultimo[c] = i
        tem_ref = ref >= 0
        delta = vals - vals[np.where(tem_ref, ref, 0)]
        incl_ok = tem_ref & ((delta > 0).all(axis=1) | (delta < 0).all(axis=1))
        ok = ok & incl_ok
    ordem = nomes_ordem(idx, mm.index)
    do_dia = np.array([t.date() == DIA_ALVO for t in mm.index])

    # --- regra nova: so' barras separadas; ordem valida nova = nova ocorrencia
    ocorr = []  # (pos_inicio, ordem)
    ultima = None
    for pos in np.flatnonzero(ok):
        if ordem.iloc[pos] != ultima:
            ocorr.append((pos, ordem.iloc[pos]))
            ultima = ordem.iloc[pos]
    regs = []
    okpos = np.flatnonzero(ok)
    for k, (pos, o) in enumerate(ocorr):
        prox = ocorr[k + 1][0] if k + 1 < len(ocorr) else len(mm)
        fim = okpos[(okpos >= pos) & (okpos < prox)].max()  # ultima barra separada desta ordem
        if mm.index[pos].date() == DIA_ALVO:
            regs.append({"ordem": o, "ini": mm.index[pos], "fim": mm.index[fim]})

    # --- referencia: contagem sem filtro (todas as barras com as 4 MMs)
    grupo = (ordem != ordem.shift()).cumsum()[tem_mm]
    sem_filtro = int(pd.Series(ordem[tem_mm].index, index=grupo.index).groupby(grupo).first().dt.date.eq(DIA_ALVO).sum())

    barras_dia = int((tem_mm & do_dia).sum())
    barras_ok = int((ok & do_dia).sum())
    barras_folga = int((folga_ok & do_dia).sum())
    barras_incl = int((tem_mm & incl_ok & do_dia).sum())
    contagem = pd.Series([r["ordem"] for r in regs]).value_counts()
    todas = sorted({f"{a}>{b}>{c}>{d}" for a in LABELS for b in LABELS for c in LABELS for d in LABELS
                    if len({a, b, c, d}) == 4})
    data = sorted(((o, int(contagem.get(o, 0))) for o in todas), key=lambda x: (-x[1], x[0]))
    print(f"{DIA_ALVO} {SIMBOLO}: barras c/ 4 MMs={barras_dia}  separadas>=folga={barras_ok} "
          f"({barras_ok / barras_dia:.0%})  so_folga={barras_folga} so_incl={barras_incl}  ocorrencias: {len(regs)} (sem filtro: {sem_filtro})", flush=True)
    for o, n in data:
        print(f"  {o.replace('>', ' > '):<28s} {n}", flush=True)

    # --- um print por ocorrencia (ordens com mais de 1 viram carrossel)
    prints: dict[str, list] = {}
    for n_ord, r in enumerate(regs):
        janela = df.loc[r["ini"] - pd.Timedelta(minutes=20): r["fim"] + pd.Timedelta(minutes=20)]
        mmj = mm.loc[janela.index]
        fig, ax = plt.subplots(figsize=(11, 5.5), facecolor="#0a0a0d")
        ax.set_facecolor("#0a0a0d")
        plot_candles(ax, janela)
        for col in MM_COLS:
            ax.plot(mmj.index, mmj[col], color=CORES[col], linewidth=1.8, zorder=4)
        ax.axvspan(r["ini"], r["fim"], color="#5eead4", alpha=0.12, zorder=1)
        ax.axvline(r["ini"], color="#5eead4", linewidth=1, linestyle="--", alpha=0.8, zorder=1)
        dur = int((r["fim"] - r["ini"]).total_seconds() // 60) + 1
        ax.set_title(f"{r['ordem'].replace('>', ' › ')}   —   início {r['ini']:%H:%M}  (fim {r['fim']:%H:%M}, {dur} min)",
                     color="#e9eaef", fontsize=12, loc="left", pad=12)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.tick_params(colors="#8d8f9c", labelsize=9)
        for sp in ax.spines.values():
            sp.set_color("#2a2b35")
        ax.grid(color="#1b1c24", linewidth=0.6)
        fig.tight_layout()
        nome = f"{r['ordem'].replace('>', '-')}_{r['ini']:%H%M}.png"
        fig.savefig(OUT_DIR / "prints" / nome, dpi=140, facecolor=fig.get_facecolor())
        plt.close(fig)
        prints.setdefault(r["ordem"], []).append({"url": f"prints/{nome}", "inicio": f"{r['ini']:%H:%M}", "fim": f"{r['fim']:%H:%M}"})
        print(f"print: {nome} ({r['ini']:%H:%M}-{r['fim']:%H:%M})", flush=True)

    dados = {"DATA": data, "PRINTS": prints,
             "STATS": {"barras": barras_dia, "separadas": barras_ok, "so_folga": barras_folga, "so_incl": barras_incl, "ocorrencias": len(regs), "sem_filtro": sem_filtro}}
    (OUT_DIR / "dados.js").write_text("const DADOS = " + json.dumps(dados, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
