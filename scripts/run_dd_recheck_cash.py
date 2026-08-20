"""Retesta os mecanismos de reducao de DD agora que o caixa parado rende.

Contexto
--------
Duas rodadas de 2026-08-16 reprovaram 61 hipoteses de reducao de drawdown e a
conclusao registrada foi "DD e estrutural". Mas TODAS elas foram julgadas com o
engine remunerando caixa a 0% (ver `backtest.costs.cash_yield_series`), e o
unico mecanismo que a propria memoria registra como tendo movido o MaxDD de
verdade — reserva de caixa a partir de LUCRO REALIZADO — e literalmente "segurar
dinheiro parado". Ele foi cobrado 0% por fazer exatamente aquilo que, na vida
real, renderia Selic.

AVISO IMPORTANTE: o codigo original daquelas rodadas nao existe mais (nem em
`scripts/`, nem no historico do git). O que esta aqui e uma REIMPLEMENTACAO a
partir da descricao registrada, nao a re-execucao dos mesmos objetos. Os numeros
absolutos nao sao comparaveis com os de agosto; o que este script mede e o
DELTA entre caixa a 0% e caixa na Selic dentro do mesmo codigo — e essa
comparacao e valida porque so muda uma coisa entre as duas colunas.

Mecanismos (os tres nomeados na memoria):
  cushion_N%   reserva N% de cada lucro realizado; a reserva nunca mais e
               investida (`cash_cushion_70` da rodada de DD)
  regulator    corta a exposicao pela metade enquanto o equity estiver mais de
               X% abaixo do topo (`equity_regulator_15`)
  volgate      nao abre posicao quando a volatilidade recente do IBOV passa de
               k x a mediana longa (`vol_gate`)

`regulator` foi implementado como CORTE DE EXPOSICAO e nao como saida total de
proposito: a saida total ja foi refutada em 2026-08-18 por um beco sem saida
logico — com o robo fora do mercado o drawdown congela e nunca "recupera", entao
o gatilho de volta nunca dispara.

Uso: .venv/Scripts/python.exe scripts/run_dd_recheck_cash.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from safety_lab import panel

from backtest.runner import run as run_bt
from core.config import BENCHMARK, WATCHLIST, BacktestConfig
from strategy.base import Enter
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
FULL = ("2010-01-01", "2026-08-19")
WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]


class _Marked(DipTop1Portfolio):
    """Base com marcacao a mercado — as tres variantes precisam ver o equity."""

    candidate = False

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        self._closes = {t: df["close"] for t, df in panels.items()}
        self._ibov_close = ibov["close"]

    def _mark(self, ticker, date) -> float:
        s = self._closes.get(ticker)
        if s is None or date not in s.index:
            return 0.0
        v = s.loc[date]
        return 0.0 if pd.isna(v) else float(v)

    def _equity(self, date, open_positions, cash) -> float:
        return cash + sum(self._mark(t, date) * p.quantity for t, p in open_positions.items())


class CashCushion(_Marked):
    """Reserva `rate` de cada lucro realizado; a reserva fica parada para sempre."""

    name = "dd_cushion"

    def __init__(self, rate: float = 0.03, **kw):
        super().__init__(**kw)
        self.rate = rate
        self._reserve = 0.0
        self._seen: dict[str, tuple[int, float]] = {}

    def on_bar(self, date, open_positions, cash_available):
        # Fechamento detectado por sumico: o engine e quem executa a venda, a
        # estrategia so percebe que a posicao nao esta mais la.
        for t, (qty, entry) in list(self._seen.items()):
            if t in open_positions:
                continue
            px = self._mark(t, date)
            if px:
                lucro = (px - entry) * qty
                if lucro > 0:
                    self._reserve += lucro * self.rate
            self._seen.pop(t)
        for t, p in open_positions.items():
            self._seen[t] = (p.quantity, p.entry_price)

        acoes = super().on_bar(date, open_positions, cash_available)
        if cash_available > 0 and self._reserve > 0:
            livre = max(0.0, cash_available - self._reserve) / cash_available
            for a in acoes:
                if isinstance(a, Enter):
                    a.size_hint = livre * (a.size_hint if a.size_hint else 1.0)
        return acoes


class EquityRegulator(_Marked):
    """Corta a exposicao pela metade enquanto o equity estiver X% abaixo do topo."""

    name = "dd_regulator"

    def __init__(self, dd_trigger: float = 0.15, exposure: float = 0.5, **kw):
        super().__init__(**kw)
        self.dd_trigger = dd_trigger
        self.exposure = exposure
        self._peak = 0.0

    def on_bar(self, date, open_positions, cash_available):
        eq = self._equity(date, open_positions, cash_available)
        self._peak = max(self._peak, eq)
        afundado = self._peak > 0 and (eq / self._peak - 1.0) < -self.dd_trigger

        acoes = super().on_bar(date, open_positions, cash_available)
        if afundado:
            for a in acoes:
                if isinstance(a, Enter):
                    a.size_hint = self.exposure * (a.size_hint if a.size_hint else 1.0)
        return acoes


class VolGate(_Marked):
    """Nao abre posicao quando a vol recente do IBOV passa de `k` x a mediana longa."""

    name = "dd_volgate"

    def __init__(self, k: float = 1.5, short: int = 21, long: int = 252, **kw):
        super().__init__(**kw)
        self.k, self.short, self.long = k, short, long
        self._quente = pd.Series(dtype=bool)

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        r = ibov["close"].pct_change()
        curta = r.rolling(self.short).std()
        base = curta.rolling(self.long).median()
        self._quente = (curta > self.k * base).fillna(False)

    def on_bar(self, date, open_positions, cash_available):
        acoes = super().on_bar(date, open_positions, cash_available)
        if date in self._quente.index and bool(self._quente.loc[date]):
            return [a for a in acoes if not isinstance(a, Enter)]
        return acoes


VARIANTES = [
    ("REF campeao", lambda: DipTop1Portfolio()),
    ("cushion 2%", lambda: CashCushion(rate=0.02)),
    ("cushion 5%", lambda: CashCushion(rate=0.05)),
    ("cushion 10%", lambda: CashCushion(rate=0.10)),
    ("regulator dd15", lambda: EquityRegulator(dd_trigger=0.15)),
    ("regulator dd25", lambda: EquityRegulator(dd_trigger=0.25)),
    ("volgate k1.5", lambda: VolGate(k=1.5)),
    ("volgate k2.0", lambda: VolGate(k=2.0)),
]


def universe() -> dict[str, pd.DataFrame]:
    u = {t: panel(t) for t in WATCHLIST}
    u[BENCHMARK] = panel(BENCHMARK)
    return u


def medir(factory, cy, start, end, u) -> dict:
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=cy)
    r = run_bt(u, factory(), cfg, start=start, end=end)
    eq = r.equity_curve
    return {"final": float(r.metrics["final_capital"]), "cagr": float(r.metrics["cagr"]),
            "dd": float(r.metrics["max_drawdown"]),
            "calmar": float(r.metrics["cagr"]) / abs(float(r.metrics["max_drawdown"]))
            if r.metrics["max_drawdown"] else float("nan"),
            "w12": float((eq / eq.shift(252) - 1).min())}


def main() -> None:
    u = universe()
    print("\nRETESTE DE REDUCAO DE DD COM CAIXA REMUNERADO")
    print("campeao + watchlist oficial (o mesmo cenario em que as hipoteses foram reprovadas)")
    print("REIMPLEMENTACAO a partir da descricao — o codigo original nao existe mais\n")

    print("JANELA FULL 2010-2026")
    hdr = (f"{'variante':16s} | {'capital 0%':>11s} {'DD 0%':>7s} {'Calmar':>7s} "
           f"| {'capital Selic':>14s} {'DD Selic':>9s} {'Calmar':>7s} | {'ganho DD':>9s}")
    print(hdr)
    print("-" * len(hdr))
    ref0 = ref1 = None
    for label, f in VARIANTES:
        a = medir(f, None, *FULL, u)
        b = medir(f, SELIC, *FULL, u)
        if ref0 is None:
            ref0, ref1 = a, b
        ganho = (b["dd"] - ref1["dd"]) * 100
        print(f"{label:16s} | {a['final']:11,.0f} {a['dd']*100:6.1f}% {a['calmar']:7.2f} "
              f"| {b['final']:14,.0f} {b['dd']*100:8.1f}% {b['calmar']:7.2f} | {ganho:+8.1f}pp",
              flush=True)

    print("\nJANELAS ROLANTES DE 5 ANOS — mediana / pior")
    hdr2 = (f"{'variante':16s} | {'CAGRmed 0%':>11s} {'DDpior 0%':>10s} "
            f"| {'CAGRmed Sel':>12s} {'DDpior Sel':>11s} {'pior12m Sel':>12s}")
    print(hdr2)
    print("-" * len(hdr2))
    for label, f in VARIANTES:
        A = [medir(f, None, s, e, u) for s, e in WINDOWS]
        B = [medir(f, SELIC, s, e, u) for s, e in WINDOWS]
        print(f"{label:16s} | {np.median([m['cagr'] for m in A])*100:10.2f}% "
              f"{min(m['dd'] for m in A)*100:9.1f}% "
              f"| {np.median([m['cagr'] for m in B])*100:11.2f}% "
              f"{min(m['dd'] for m in B)*100:10.1f}% "
              f"{min(m['w12'] for m in B)*100:11.1f}%", flush=True)


if __name__ == "__main__":
    main()
