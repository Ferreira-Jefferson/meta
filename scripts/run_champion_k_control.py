"""Controle: o ganho de k=10 e diversificacao, ou so menos dinheiro na bolsa?

O problema
----------
`scripts/run_champion_k.py` mostrou k=10 com MaxDD -19,9% contra -36,7% de k=5,
custando 2,4 p.p. de CAGR mediano. Parece otimo. Mas com o universo em top-20 e
dez sleeves, cada sleeve escolhe entre DOIS papeis — e sleeve sem sinal fica em
caixa. Se k=10 passa metade do tempo em caixa remunerado na Selic, o MaxDD
menor nao e diversificacao: e exposicao menor, que qualquer um consegue de
graca deixando parte do dinheiro no CDI e nem precisa de robo.

O controle
----------
Para cada k, mede a EXPOSICAO media (fracao do patrimonio em acoes) e depois
compara k=10 contra uma mistura estatica de k=5 com caixa na Selic, calibrada
para ter a MESMA exposicao media. Se k=10 ainda ganhar, o ganho e do desenho.
Se a mistura empatar ou ganhar, k=10 e uma forma cara de segurar caixa.

A mistura e estatica (peso fixo, sem rebalancear). Isso FAVORECE k=10, porque
uma mistura rebalanceada mensalmente teria risco um pouco menor — entao um
empate ja e um resultado ruim para o k=10.

Uso: .venv/Scripts/python.exe scripts/run_champion_k_control.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from run_sleeve_validation import full_panels

from backtest.costs import cash_yield_series
from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
KS = (3, 5, 7, 10)
WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]


class _Watched(LiquidChampion):
    """Igual ao campeao, so anotando exposicao a cada pregao."""

    name = "liquid_champion_watched"
    candidate = False

    def __init__(self, **kw):
        super().__init__(**kw)
        self.expostos: list[float] = []
        self._closes: dict[str, pd.Series] = {}

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        self._closes = {t: df["close"] for t, df in panels.items()}

    def _mark(self, ticker: str, date) -> float:
        s = self._closes.get(ticker)
        if s is None or date not in s.index:
            return 0.0
        v = s.loc[date]
        return 0.0 if pd.isna(v) else float(v)

    def on_bar(self, date, open_positions, cash_available):
        mkt = sum(self._mark(t, date) * p.quantity for t, p in open_positions.items())
        eq = cash_available + mkt
        if eq > 0:
            self.expostos.append(mkt / eq)
        return super().on_bar(date, open_positions, cash_available)


def metricas(eq: pd.Series) -> dict:
    anos = (eq.index[-1] - eq.index[0]).days / 365.25
    return {"cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (1 / anos) - 1),
            "dd": float((eq / eq.cummax() - 1).min()),
            "w12": float((eq / eq.shift(252) - 1).min())}


def rodar(k, u, start, end) -> tuple[pd.Series, float]:
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC)
    bot = _Watched(sleeve_count=k, reserve_rate=0.0)
    r = run_bt(u, bot, cfg, start=start, end=end)
    return r.equity_curve, float(np.mean(bot.expostos)) if bot.expostos else 0.0


def main() -> None:
    u = full_panels()
    curvas: dict[int, list[pd.Series]] = {k: [] for k in KS}
    exp: dict[int, list[float]] = {k: [] for k in KS}

    print("\nEXPOSICAO MEDIA POR k (fracao do patrimonio em acoes)")
    print(f"{'k':>3s} " + "".join(f"{s[2:7]:>9s}" for s, _ in WINDOWS) + f" {'media':>9s}")
    for k in KS:
        for s, e in WINDOWS:
            eq, x = rodar(k, u, s, e)
            curvas[k].append(eq)
            exp[k].append(x)
        print(f"{k:3d} " + "".join(f"{x * 100:8.1f}%" for x in exp[k]) +
              f" {np.mean(exp[k]) * 100:8.1f}%", flush=True)

    print("\nCONTROLE — k=10 contra k=5 misturado com Selic na MESMA exposicao media")
    hdr = f"{'braco':34s} {'CAGRmed':>8s} {'pior':>8s} {'DDpior':>8s} {'12m':>8s}"
    print(f"{'=' * len(hdr)}\n{hdr}\n{'-' * len(hdr)}")

    def resumir(nome, ms):
        g = [m["cagr"] for m in ms]
        print(f"{nome:34s} {np.median(g) * 100:7.1f}% {min(g) * 100:7.1f}% "
              f"{min(m['dd'] for m in ms) * 100:7.1f}% {min(m['w12'] for m in ms) * 100:7.1f}%")

    resumir("k=5 puro", [metricas(c) for c in curvas[5]])
    resumir("k=10 puro", [metricas(c) for c in curvas[10]])

    misturas = []
    for i, c5 in enumerate(curvas[5]):
        w = np.mean(exp[10]) / np.mean(exp[5])  # peso que iguala a exposicao media
        rate = cash_yield_series(SELIC, c5.index)
        caixa = (1.0 + rate).cumprod() if rate is not None else pd.Series(1.0, index=c5.index)
        blend = w * (c5 / c5.iloc[0]) + (1.0 - w) * (caixa / caixa.iloc[0])
        misturas.append(metricas(blend))
    resumir(f"k=5 x {w:.2f} + Selic x {1 - w:.2f}", misturas)

    print("\nse a mistura empata ou ganha, o k=10 nao esta diversificando — "
          "so esta segurando caixa por um caminho mais caro")


if __name__ == "__main__":
    main()
