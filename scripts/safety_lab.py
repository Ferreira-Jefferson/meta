"""Laboratorio de robustez — biblioteca compartilhada dos testes de seguranca.

Por que existe
--------------
Todo numero bonito deste repositorio nasceu de uma busca sobre 2010-2026 e nao
sobreviveu ao walk-forward (ver `run_walk_forward.py` e `run_walk_forward_params.py`).
As tres fontes de mentira identificadas foram:

  1. a watchlist foi escolhida sabendo quem subiu    -> vies de selecao (+17 p.p.)
  2. os parametros foram escolhidos da mesma forma   -> tunar no IS piora (2/6)
  3. o criterio de aceite era capital final no FULL  -> premia sorte concentrada

Este modulo remove as tres de uma vez:

  1. UNIVERSO POINT-IN-TIME por LIQUIDEZ. `liquid_universe(asof)` ordena por
     giro financeiro mediano dos 252 pregoes ANTERIORES a data e corta os N
     primeiros. Nenhuma informacao de retorno entra na escolha — o mesmo
     universo teria sido montavel naquele dia, com os dados daquele dia.
  2. PARAMETROS CONGELADOS nos defaults do repo, ou combinados em ensemble.
     Nunca re-otimizados dentro do teste.
  3. CRITERIO DE ACEITE POR SEGURANCA, nao por capital: pior janela positiva,
     drawdown maximo limitado, tempo submerso limitado, pior 12 meses limitado.

Sleeves
-------
Diversificacao sem reescrever a histerese: em vez de um robo com N posicoes
(a logica de `DipTop1Hysteresis` assume UMA posicao — `held[0]`), rodamos K
contas independentes, cada uma com capital/K e seu proprio sub-universo, e
somamos as curvas. E exatamente o que o usuario faria com K contas na corretora,
e reproduz o unico mecanismo de reducao de DD que ja funcionou neste projeto
(ver memoria `bank_specialist_robots_2026_08_18`).
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.metrics import negative_years
from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from market_data.loader import load_one
from strategy.base import Exit
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1000.0

_PANELS: dict[str, pd.DataFrame] = {}
_POOL: list[str] | None = None


# --------------------------------------------------------------------------- dados


def panel(ticker: str) -> pd.DataFrame:
    """Painel sem linhas de close vazio (o ultimo pregao as vezes vem incompleto)."""
    if ticker not in _PANELS:
        df = load_one(ticker)
        _PANELS[ticker] = df[df["close"].notna()]
    return _PANELS[ticker]


def full_pool() -> list[str]:
    """Todo ticker de acao disponivel em data/raw/ (macro e indices fora)."""
    global _POOL
    if _POOL is not None:
        return _POOL
    out = []
    for p in sorted(glob.glob("data/raw/*.parquet")):
        base = os.path.basename(p)[:-8]
        if base.startswith("_") or "_" not in base or base.startswith("DX-Y"):
            continue
        head, _, tail = base.rpartition("_")
        ticker = f"{head}.{tail}"
        try:
            df = panel(ticker)
        except Exception:
            continue
        if "close" not in df.columns or "volume" not in df.columns or len(df) == 0:
            continue
        out.append(ticker)
    _POOL = out
    return out


def liquid_universe(asof: str, n: int = 20, min_history_days: int = 504) -> list[str]:
    """Top-N por giro financeiro mediano dos 252 pregoes ANTERIORES a `asof`.

    So liquidez e historico entram — zero informacao de retorno. Exige
    `min_history_days` de historico para o momentum 12-1 ter o que calcular no
    primeiro mes, senao o robo comeca cego e a janela nao e comparavel.
    """
    cut = pd.Timestamp(asof)
    ranked = []
    for t in full_pool():
        df = panel(t)
        hist = df.loc[df.index <= cut]
        if len(hist) < min_history_days:
            continue
        tail = hist.tail(252)
        adtv = float((tail["close"] * tail["volume"]).median())
        if not np.isfinite(adtv) or adtv <= 0:
            continue
        ranked.append((t, adtv))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in ranked[:n]]


def split_sleeves(tickers: list[str], k: int) -> list[list[str]]:
    """Reparte o universo em K grupos por rodizio na ordem de liquidez.

    Rodizio (e nao blocos) de proposito: em blocos, o sleeve 1 ficaria so com as
    blue chips e o sleeve K so com as menos liquidas — cada conta teria um perfil
    de risco diferente e a media viraria uma mistura de coisas incomparaveis.
    """
    groups: list[list[str]] = [[] for _ in range(k)]
    for i, t in enumerate(tickers):
        groups[i % k].append(t)
    return [g for g in groups if g]


# --------------------------------------------------------------------------- robos


class TrendGated(DipTop1Portfolio):
    """Campeao + trava de tendencia do indice: so opera com IBOV acima da media longa.

    Motivacao empirica: no walk-forward, a janela que quebrou (-78,6%) quebrou por
    whipsaw — quatro stops seguidos em 2018, com o robo reentrando todo mes num
    mercado sem direcao. O gate de Selic ja provou ser o filtro que mais segura o
    DD (sem ele o MaxDD do FULL vai de -35% para -66%); esta e a mesma ideia
    aplicada ao preco em vez do juro.
    """

    name = "trend_gated"
    candidate = False

    def __init__(self, sma: int = 200, **kwargs):
        super().__init__(**kwargs)
        self.sma = sma
        self._trend_ok = pd.Series(dtype=bool)

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        c = ibov["close"]
        self._trend_ok = (c > c.rolling(self.sma).mean()).fillna(False)

    def on_bar(self, date, open_positions, cash_available):
        ok = bool(self._trend_ok.loc[date]) if date in self._trend_ok.index else False
        if not ok:
            # Mesmo protocolo do gate de Selic: zera posicao e nao entra.
            # Sai pelo mesmo ExitReason para o diario nao inventar categoria nova.
            from core.models import ExitReason
            if open_positions:
                self._pending_rebalance = False
                return [Exit(ticker=t, reason=ExitReason.IBOV_DEFENSIVE) for t in open_positions]
            return []
        return super().on_bar(date, open_positions, cash_available)


class CooldownAfterStop(DipTop1Portfolio):
    """Campeao + quarentena depois de um stop: nao reentra por N meses.

    O stop e disparado pelo ENGINE (intra-bar), nao pela estrategia, entao o robo
    so descobre que foi stopado ao notar que a posicao sumiu sem ele ter mandado
    sair. E esse o mecanismo aqui: guarda o que via no bar anterior e o que
    mandou fechar; sumico nao solicitado = stop.
    """

    name = "cooldown_stop"
    candidate = False

    def __init__(self, cooldown_months: int = 2, **kwargs):
        super().__init__(**kwargs)
        self.cooldown_months = cooldown_months
        self._prev_positions: set[str] = set()
        self._ordered_exits: set[str] = set()
        self._skip_months = 0

    def on_bar(self, date, open_positions, cash_available):
        now = set(open_positions)
        vanished = self._prev_positions - now - self._ordered_exits
        if vanished:
            self._skip_months = self.cooldown_months
        self._prev_positions = now
        self._ordered_exits = set()

        is_me = date in self._month_end.index and bool(self._month_end.loc[date])
        if self._skip_months > 0:
            if is_me:
                self._skip_months -= 1
            self._pending_rebalance = False
            return []

        actions = super().on_bar(date, open_positions, cash_available)
        self._ordered_exits = {a.ticker for a in actions if isinstance(a, Exit)}
        return actions


# --------------------------------------------------------------------------- medida


@dataclass(frozen=True)
class Variant:
    """Uma configuracao completa a ser medida: robos, capital e universo."""

    key: str
    label: str
    factories: list = field(default_factory=list)   # callables () -> Strategy
    sleeves: int = 1
    config: BacktestConfig = field(default_factory=lambda: BacktestConfig(initial_capital=INITIAL, lot_size=1))
    universe_n: int = 20


def combined_equity(variant: Variant, tickers: list[str], start: str, end: str) -> tuple[pd.Series, int]:
    """Soma das curvas de K contas independentes. Retorna (equity, n_trades)."""
    groups = split_sleeves(tickers, variant.sleeves)
    n_accounts = len(groups) * len(variant.factories)
    per_account = INITIAL / n_accounts
    cfg = BacktestConfig(
        initial_capital=per_account,
        lot_size=variant.config.lot_size,
        stop_loss_pct=variant.config.stop_loss_pct,
        max_concurrent_positions=variant.config.max_concurrent_positions,
        ibov_defensive_days=variant.config.ibov_defensive_days,
        costs=variant.config.costs,
        cash_yield_path=variant.config.cash_yield_path,
    )
    curves, trades = [], 0
    for group in groups:
        universe = {t: panel(t) for t in group}
        universe[BENCHMARK] = panel(BENCHMARK)
        for factory in variant.factories:
            r = run_bt(universe, factory(), cfg, start=start, end=end)
            curves.append(r.equity_curve)
            trades += len(r.trades)
    idx = curves[0].index
    for c in curves[1:]:
        idx = idx.union(c.index)
    total = sum(c.reindex(idx).ffill().bfill() for c in curves)
    return total, trades


def metrics(eq: pd.Series, trades: int) -> dict:
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    peak = eq.cummax()
    dd = eq / peak - 1.0
    r12 = eq / eq.shift(252) - 1.0
    return {
        "final": float(eq.iloc[-1]),
        "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1),
        "max_dd": float(dd.min()),
        "underwater": float((dd < -0.01).mean()),
        "worst_12m": float(r12.min()) if r12.notna().any() else float("nan"),
        "neg_yrs": negative_years(eq),
        "trades": trades,
    }
