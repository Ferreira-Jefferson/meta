"""Com o stop preenchido no PIOR caso possivel, o campeao ainda bate o IBOV?

A pergunta
----------
`scripts/run_stop_fill_sensitivity.py` mediu que a hipotese pessimista de
execucao do stop (`stop_fill="low"`, sair na minima do dia) custa 16,8% do
capital na janela FULL. A duvida que sobra e a unica que importa: nesse
cenario, a vantagem sobre o indice sobrevive?

Nao da para responder com FULL e 5Y. Sao duas janelas, e duas janelas e
exatamente o tamanho de amostra que produziu os portoes sobreajustados que
`run_holdout_frozen.py` derrubou. A resposta honesta tem de usar as MESMAS 48
janelas do holdout — inicios mensais de 2010-01 a 2013-12, territorio que
nunca participou de escolha nenhuma — e comparar contra o IBOV DA MESMA
JANELA, uma a uma.

Protocolo, declarado antes de rodar
-----------------------------------
Para cada uma das 48 janelas de 5 anos, roda o campeao tres vezes (uma por
hipotese de execucao do stop) e o IBOV uma vez. Nada mais muda: mesmo
universo, mesmo capital, mesmo sinal congelado, caixa remunerado na Selic.

  stop_or_open  hipotese do diario: dispara em `low <= stop`, preenche em
                `min(open, stop)`
  low           piso de qualquer feed atrasado: preenche na minima do dia
  close         o que o `ParquetCloseFeed` faz hoje: dispara so se o
                fechamento estiver abaixo do stop

A coluna que responde a pergunta e `bate_ibov`: em quantas das 48 janelas o
CAGR do robo superou o CAGR do indice NA MESMA JANELA. Comparacao pareada,
nao "a distribuicao dele contra um numero meu".

Critério declarado antes do resultado: a vantagem sobrevive se, no arm `low`,
(a) a mediana de CAGR continuar acima da mediana do IBOV e (b) `bate_ibov`
continuar sendo maioria das 48. Se cair de um lado so, o resultado e misto e
sera reportado como misto, nao arredondado para "passa".

Uso: .venv/Scripts/python.exe scripts/run_stop_fill_vs_ibov.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

import run_holdout_frozen as hf

from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
ANOS = 5
ARMS = ["stop_or_open", "low", "close"]


def medir(u, start: pd.Timestamp, fill: str) -> dict | None:
    """Uma janela, um arm. `None` quando a janela nao tem pregao suficiente."""
    end = start + pd.DateOffset(years=ANOS)
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1,
                         cash_yield_path=SELIC, stop_fill=fill)
    r = run_bt(u, LiquidChampion(), cfg, start=str(start.date()), end=str(end.date()))
    eq = r.equity_curve
    if len(eq) < 250:
        return None
    return {"cagr": float(r.metrics["cagr"]), "dd": float(r.metrics["max_drawdown"]),
            "w12": float((eq / eq.shift(252) - 1).min()), "trades": len(r.trades)}


def main() -> None:
    print("\ncarregando paineis...", flush=True)
    u = hf.full_panels()

    print(f"IBOV nas mesmas {len(hf.HOLDOUT)} janelas...", flush=True)
    ib = [hf.ibov_janela(s) for s in hf.HOLDOUT]
    ibg = np.array([m["cagr"] for m in ib])

    print(f"\n{'=' * 104}")
    print(f"HOLDOUT — {len(hf.HOLDOUT)} janelas de {ANOS} anos, inicios mensais "
          f"2010-01 a 2013-12, pareado contra o IBOV")
    print(f"{'=' * 104}")
    print(f"{'arm':14s} {'n':>3s} {'p05':>7s} {'mediana':>8s} {'p95':>7s} "
          f"{'pior':>7s} {'MaxDD':>8s} {'pior 12m':>9s} {'neg':>4s} "
          f"{'bate IBOV':>10s} {'trades':>7s}")

    linhas = {}
    for fill in ARMS:
        rows, pares = [], []
        for i, s in enumerate(hf.HOLDOUT):
            m = medir(u, s, fill)
            if m is None:
                continue
            rows.append(m)
            pares.append(ibg[i])
        g = np.array([m["cagr"] for m in rows])
        par = np.array(pares)
        linhas[fill] = {
            "n": len(rows), "med": float(np.median(g)),
            "bate": int((g > par).sum()), "neg": int((g < 0).sum()),
            "dd": min(m["dd"] for m in rows), "w12": min(m["w12"] for m in rows),
        }
        print(f"{fill:14s} {len(rows):3d} {np.percentile(g, 5) * 100:6.1f}% "
              f"{np.median(g) * 100:7.1f}% {np.percentile(g, 95) * 100:6.1f}% "
              f"{g.min() * 100:6.1f}% {min(m['dd'] for m in rows) * 100:7.1f}% "
              f"{min(m['w12'] for m in rows) * 100:8.1f}% {int((g < 0).sum()):4d} "
              f"{int((g > par).sum()):5d}/{len(rows):<4d} "
              f"{int(np.median([m['trades'] for m in rows])):7d}", flush=True)

    print(f"{'IBOV':14s} {len(ib):3d} {np.percentile(ibg, 5) * 100:6.1f}% "
          f"{np.median(ibg) * 100:7.1f}% {np.percentile(ibg, 95) * 100:6.1f}% "
          f"{ibg.min() * 100:6.1f}% {min(m['dd'] for m in ib) * 100:7.1f}% "
          f"{min(m['w12'] for m in ib) * 100:8.1f}% {int((ibg < 0).sum()):4d} "
          f"{'—':>10s} {0:7d}")

    med_ibov = float(np.median(ibg))
    print(f"\nCriterio declarado antes de rodar, aplicado ao arm `low`:")
    l = linhas["low"]
    a = l["med"] >= med_ibov
    b = l["bate"] > l["n"] / 2
    print(f"  (a) mediana acima da do IBOV: {l['med']*100:.1f}% vs "
          f"{med_ibov*100:.1f}% -> {'SIM' if a else 'NAO'}")
    print(f"  (b) bate o IBOV na maioria das janelas: {l['bate']}/{l['n']} -> "
          f"{'SIM' if b else 'NAO'}")
    print(f"  vantagem {'SOBREVIVE' if a and b else 'MISTA/NAO SOBREVIVE'} "
          f"ao pior caso de execucao do stop")
    print(f"\nexcesso de CAGR mediano sobre o IBOV, por arm:")
    for fill in ARMS:
        print(f"  {fill:14s} {(linhas[fill]['med'] - med_ibov) * 100:+5.1f} p.p.")


if __name__ == "__main__":
    main()
