"""6 prints de entradas "de manual" da estrategia WIN (vela M5 inteira fora da WMA 34 roxa + SMMA 34 verde do lado oposto).

Criterio de "perfeita" = so' a QUALIDADE DO SETUP, nunca o resultado:
  - vela M5 limpa (minima acima da roxa para compra / maxima abaixo dela para venda),
  - 60+ pontos de folga entre a vela e a roxa,
  - a verde do lado oposto da roxa (compra: verde abaixo; venda: verde acima),
  - a vela anterior NAO era limpa do mesmo lado (sinal que acabou de nascer),
  - a roxa inclinada a favor (vs 5 velas antes),
  - sinal entre 10:00 e 16:30, e o robo realmente abriu a operacao (nao estava posicionado).
Dos candidatos de ago e set/2026, sorteados em ordem de data, pega 3 compras e 3 vendas em dias
diferentes, espacadas no tempo. O resultado de cada uma (stop 300 / alvo 600) vai no titulo.
Gera PNGs + dados_prints.js em .claude/artifacts/win_ema8_wma8_2026-09/.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_ema8_wma8_sim_m1 as sim  # noqa: E402

MESES = ["2026-08", "2026-09"]
STOP, ALVO = 300.0, 600.0
FOLGA_MIN = 60.0
OUT = sim.ROOT / ".claude" / "artifacts" / "win_ema8_wma8_2026-09"
(OUT / "entradas").mkdir(parents=True, exist_ok=True)
for f in (OUT / "entradas").glob("*.png"):
    f.unlink()


def candles(ax, df) -> None:
    for ts, r in df.iterrows():
        cor = "#ffffff" if r.close == r.open else ("#4ade80" if r.close > r.open else "#f87171")
        ax.vlines(ts, r.low, r.high, color=cor, linewidth=1, zorder=2)
        ax.add_patch(plt.Rectangle((mdates.date2num(ts) - 0.0013, min(r.open, r.close)), 0.0026,
                                   max(abs(r.close - r.open), 5.0), facecolor=cor, edgecolor=cor, zorder=3))


def main() -> None:
    m5 = sim.ler("WIN@D_M5_*.csv")
    m5["wma"], m5["smma"] = sim.lwma(m5.close, sim.PERIODO), sim.smma(m5.close, sim.PERIODO)
    folga_c, folga_v = m5.low - m5.wma, m5.wma - m5.high
    comp, vend = (folga_c > 0) & (m5.smma < m5.wma), (folga_v > 0) & (m5.smma > m5.wma)
    inc_c, inc_v = m5.wma > m5.wma.shift(5), m5.wma < m5.wma.shift(5)
    hora = m5.index.hour * 60 + m5.index.minute
    jan = (hora >= 600) & (hora <= 16 * 60 + 30)
    cand_c = comp & (folga_c >= FOLGA_MIN) & ~comp.shift(1, fill_value=False) & inc_c & jan
    cand_v = vend & (folga_v >= FOLGA_MIN) & ~vend.shift(1, fill_value=False) & inc_v & jan

    trades = []
    for mes in MESES:
        trades.append(sim.simular(sim.preparar(mes, limpa=True, so_roxa=True), STOP, ALVO))
    tr = pd.concat(trades).set_index("t_entrada")

    def escolher(cand: pd.Series, lado: int) -> list:
        # entrada = abertura da M5 seguinte ao sinal; so' vale se o robo abriu de fato
        achados, dias = [], set()
        for ts in m5.index[cand.to_numpy()]:
            te = ts + pd.Timedelta(minutes=5)
            if te in tr.index and int(tr.loc[te, "dir"]) == lado and ts.date() not in dias:
                dias.add(ts.date())
                achados.append((ts, tr.loc[te]))
        if len(achados) < 3:
            raise SystemExit(f"so' {len(achados)} candidatos de {'compra' if lado == 1 else 'venda'}")
        idx = np.unique(np.linspace(0, len(achados) - 1, 3).round().astype(int))
        return [achados[k] for k in idx]

    escolhidos = [(1, *a) for a in escolher(cand_c, 1)] + [(-1, *a) for a in escolher(cand_v, -1)]
    lista = []
    for lado, ts, t in escolhidos:
        te, tsaida = ts + pd.Timedelta(minutes=5), t.t_saida
        j = m5.loc[ts - pd.Timedelta(minutes=5 * 30): max(tsaida, te) + pd.Timedelta(minutes=5 * 6)]
        j = j[j.index.date == ts.date()]  # o dia da operacao
        fig, ax = plt.subplots(figsize=(10, 5), facecolor="#0a0a0d")
        ax.set_facecolor("#0a0a0d")
        candles(ax, j)
        ax.plot(j.index, j.wma, color="#da8ad6", lw=1.5, label="WMA 34")
        ax.plot(j.index, j.smma, color="#3cb371", lw=1.5, label="SMMA 34")
        ax.axvspan(ts - pd.Timedelta(minutes=2.5), ts + pd.Timedelta(minutes=2.5), color="#5eead4", alpha=.18, zorder=1)
        ax.hlines(t.entrada, te, tsaida, color="#ffffff", lw=1, ls=":")
        ax.hlines(t.entrada - lado * STOP, te, tsaida, color="#f87171", lw=1, ls="--")
        ax.hlines(t.entrada + lado * ALVO, te, tsaida, color="#4ade80", lw=1, ls="--")
        ax.plot([te], [t.entrada], marker="^" if lado == 1 else "v", color="#5eead4", ms=11, zorder=5)
        ax.plot([tsaida], [t.entrada + lado * (t.rs / sim.R_PT + 5)], marker="x", color="#ffd700", ms=10, mew=2.5, zorder=5)
        folga = (folga_c if lado == 1 else folga_v)[ts]
        ax.set_title(f"{'COMPRA' if lado == 1 else 'VENDA'} · {te:%d/%m/%Y %H:%M} · folga {folga:.0f} pts · "
                     f"{t.mot} · R$ {t.rs:+.2f}", color="#e9eaef", fontsize=11)
        ax.tick_params(colors="#8d8f9c")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        for sp in ax.spines.values():
            sp.set_color("#2a2b35")
        ax.grid(color="#1b1c24")
        ax.legend(facecolor="#131319", edgecolor="#2a2b35", labelcolor="#e9eaef", loc="upper left")
        fig.tight_layout()
        nome = f"{'compra' if lado == 1 else 'venda'}_{te:%Y%m%d_%H%M}.png"
        fig.savefig(OUT / "entradas" / nome, dpi=90, facecolor=fig.get_facecolor())
        plt.close(fig)
        lista.append({"url": f"entradas/{nome}", "lado": "compra" if lado == 1 else "venda",
                      "quando": f"{te:%d/%m/%Y %H:%M}", "folga": round(float(folga)), "saida": t.mot, "rs": round(float(t.rs), 2)})
        print(lista[-1], flush=True)
    (OUT / "dados_prints.js").write_text("const ENTRADAS = " + json.dumps(lista, ensure_ascii=False) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
