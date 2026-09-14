"""EXPERIMENTO (nao productivo) -- Virada de mes (turn-of-month) em acoes B3.

Hipotese: comprar uma cesta igual-ponderada da WATCHLIST no FECHAMENTO do
penultimo pregao do mes (executa open[D+1], ou seja no ultimo pregao do mes) e
vender apos W pregoes do mes seguinte captura fluxo institucional (13o/
aportes/rebalance de indice).

Metodo (nao editar strategy/ nesta fase -- este arquivo E o experimento):
- Estrategia so acumulada aqui, nunca registrada em strategy/registry.py nem
  em strategy/discovery.
- Calendario de pregao real construido a partir do INDICE do IBOV (mais
  confiavel que qualquer acao isolada, que pode ter gap proprio).
- Contagem em PREGOES, nunca em dia-do-mes do relogio.
- Engine backtest/engine.py de verdade -- anti-look-ahead e do engine, nao
  desta classe.
- Capital R$1.000, lot_size=1 (fracionario) -- convencao do projeto para
  medicao de swing (memoria "Criterio de ranking oficial", regime historico
  anterior a 2026-08-22; o regime OFICIAL do podio hoje e R$100+taxa
  fracionaria, mas o pedido desta rodada foi explicito em R$1.000).
- CostModel DEFAULT (sem taxa fixa fracionaria) -- mesmo regime da tabela
  historica R$1.000 citada acima, para nao misturar regimes de custo.

Uso:
    python scripts/swing_turn_of_month_2026_09_11.py --mode small
    python scripts/swing_turn_of_month_2026_09_11.py --mode full --window 5
"""
from __future__ import annotations

import argparse
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backtest.engine import run_backtest  # noqa: E402
from core.config import BacktestConfig, WATCHLIST  # noqa: E402
from core.models import ExitReason  # noqa: E402
from market_data.loader import load_universe  # noqa: E402
from strategy.base import Action, Enter, Exit, OpenPosition, Strategy  # noqa: E402


# --------------------------------------------------------------------------- estrategias
class TurnOfMonthStrategy(Strategy):
    """Compra a cesta WATCHLIST perto da virada do mes, vende apos W pregoes.

    - Sinal de ENTRADA: fechamento do penultimo pregao do mes -> engine
      executa no open do pregao seguinte (o ULTIMO pregao do mes).
    - Sinal de SAIDA: fechamento do W-esimo pregao do mes seguinte (contado a
      partir do ultimo pregao do mes anterior, na lista COMPLETA de pregoes,
      nao por grupo-de-mes -- assim nao importa quantos pregoes o mes
      seguinte tem) -> engine executa no open do pregao seguinte.
    - Todos os tickers da cesta entram/saem no MESMO par de datas (mesmo
      evento de calendario); a data-alvo de saida viaja no metadata da
      posicao, gravado no momento do Enter.
    """

    name = "experiment_turn_of_month"
    version = "0.1"

    def __init__(self, exit_window_trading_days: int = 5, tickers: tuple[str, ...] = WATCHLIST):
        self.W = int(exit_window_trading_days)
        self.tickers = tuple(tickers)
        self._exit_decision_by_entry_signal: dict[pd.Timestamp, pd.Timestamp] = {}

    def initialize(self, panels, ibov) -> None:
        td = list(pd.DatetimeIndex(sorted(ibov.index)))
        n = len(td)
        month_end_idx = [k for k in range(n - 1) if td[k].month != td[k + 1].month]
        mapping: dict[pd.Timestamp, pd.Timestamp] = {}
        for k in month_end_idx:
            if k - 1 < 0:
                continue
            entry_signal_date = td[k - 1]
            exit_decision_idx = k + self.W
            if exit_decision_idx >= n:
                continue  # nao ha pregoes futuros suficientes ainda (borda da serie)
            mapping[entry_signal_date] = td[exit_decision_idx]
        self._exit_decision_by_entry_signal = mapping

    def on_bar(self, date: pd.Timestamp, open_positions: dict[str, OpenPosition], cash_available: float) -> list[Action]:
        actions: list[Action] = []
        exit_decision_date = self._exit_decision_by_entry_signal.get(date)
        if exit_decision_date is not None:
            n_tickers = len(self.tickers)
            for ticker in self.tickers:
                if ticker in open_positions:
                    continue
                actions.append(
                    Enter(
                        ticker=ticker,
                        size_hint=1.0 / n_tickers,
                        metadata={"exit_decision_date": exit_decision_date},
                        reason="turn_of_month",
                    )
                )
        for ticker, pos in open_positions.items():
            target = pos.metadata.get("exit_decision_date")
            if target is not None and date >= pd.Timestamp(target):
                actions.append(Exit(ticker=ticker, reason=ExitReason.MANUAL))
        return actions


class BuyHoldBasket(Strategy):
    """Baseline: compra a cesta igual-ponderada no dia 1 e segura ate o fim."""

    name = "experiment_buyhold_basket"
    version = "0.1"

    def __init__(self, tickers: tuple[str, ...] = WATCHLIST):
        self.tickers = tuple(tickers)
        self._bought = False

    def initialize(self, panels, ibov) -> None:
        self._bought = False

    def on_bar(self, date, open_positions, cash_available) -> list[Action]:
        if self._bought:
            return []
        self._bought = True
        n = len(self.tickers)
        return [Enter(ticker=t, size_hint=1.0 / n, reason="buy_hold") for t in self.tickers]


# --------------------------------------------------------------------------- estatistica
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """IC de Wilson para uma proporcao. Sem scipy: formula fechada."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adj = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    lo = (centre - adj) / denom
    hi = (centre + adj) / denom
    return (max(0.0, lo), min(1.0, hi))


# --------------------------------------------------------------------------- runner
def _run_one(window: int, start: str, end: str, capital: float) -> dict:
    """Roda TurnOfMonth para um W e devolve o resumo. Top-level p/ pickling do PPE."""
    universe = load_universe()  # WATCHLIST + benchmark, default
    config = BacktestConfig(
        initial_capital=capital,
        lot_size=1,
        max_concurrent_positions=len(WATCHLIST),
    )
    strat = TurnOfMonthStrategy(exit_window_trading_days=window)
    result = run_backtest(universe, strat, config, start=start, end=end)

    closed = [t for t in result.trades if not t.is_open]
    n_trades = len(closed)
    wins = [t for t in closed if t.pnl_brl > 0]
    losses = [t for t in closed if t.pnl_brl <= 0]
    n_win = len(wins)
    n_stops = len([t for t in closed if t.exit_reason == ExitReason.STOP])
    win_pct = 100.0 * n_win / n_trades if n_trades else float("nan")
    lo, hi = wilson_ci(n_win, n_trades) if n_trades else (float("nan"), float("nan"))

    ganho_medio = sum(t.pnl_brl for t in wins) / len(wins) if wins else 0.0
    perda_media = abs(sum(t.pnl_brl for t in losses) / len(losses)) if losses else 0.0
    breakeven_empirico = (
        100.0 * perda_media / (ganho_medio + perda_media) if (ganho_medio + perda_media) > 0 else float("nan")
    )

    liquido = float(result.metrics["final_capital"]) - capital

    # consistencia por MES calendario -- agrupa os trades pela data de ENTRADA
    # (cada mes so tem 1 cohort de ate 7 trades simultaneos; o pnl do mes e a
    # soma dos pnl_brl da cohort daquele mes).
    by_month: dict[tuple[int, int], float] = {}
    for t in closed:
        key = (t.entry_date.year, t.entry_date.month)
        by_month[key] = by_month.get(key, 0.0) + t.pnl_brl
    n_months = len(by_month)
    n_months_pos = sum(1 for v in by_month.values() if v > 0)
    pct_months_pos = 100.0 * n_months_pos / n_months if n_months else float("nan")

    # dias/pregoes SEM NENHUMA posicao aberta (fora do desenho -- ficar fora
    # do mercado a maior parte do tempo E a regra da estrategia, nao censura
    # por capital; reportado mesmo assim por honestidade de metodo).
    equity_idx = result.equity_curve.index
    dias_totais = len(equity_idx)
    entry_dates = {t.entry_date for t in closed}
    exit_dates = {t.exit_date for t in closed if t.exit_date}
    dias_com_posicao = 0
    open_flag = False
    # aproximacao simples: dia tem posicao se esta entre alguma entrada e saida
    intervals = [(t.entry_date, t.exit_date) for t in closed if t.exit_date]
    for d in equity_idx:
        dd = d.date()
        if any(en <= dd <= ex for en, ex in intervals):
            dias_com_posicao += 1
    dias_sem_posicao = dias_totais - dias_com_posicao

    return {
        "window": window,
        "n_trades": n_trades,
        "n_stops": n_stops,
        "win_pct": win_pct,
        "ic95_lo": lo,
        "ic95_hi": hi,
        "breakeven_empirico_pct": breakeven_empirico,
        "liquido_brl": liquido,
        "capital_final": float(result.metrics["final_capital"]),
        "max_drawdown_pct": 100.0 * float(result.metrics["max_drawdown"]),
        "n_months": n_months,
        "pct_months_pos": pct_months_pos,
        "dias_totais": dias_totais,
        "dias_sem_posicao": dias_sem_posicao,
        "start": start,
        "end": end,
        "capital": capital,
    }


def _run_buyhold(start: str, end: str, capital: float) -> dict:
    universe = load_universe()
    config = BacktestConfig(initial_capital=capital, lot_size=1, max_concurrent_positions=len(WATCHLIST))
    strat = BuyHoldBasket()
    result = run_backtest(universe, strat, config, start=start, end=end)
    return {
        "capital_final": float(result.metrics["final_capital"]),
        "max_drawdown_pct": 100.0 * float(result.metrics["max_drawdown"]),
        "cagr_pct": 100.0 * float(result.metrics["cagr"]),
    }


def print_row(r: dict) -> None:
    print(
        f"  W={r['window']:>3d}  trades={r['n_trades']:>4d} (stops={r['n_stops']:>2d})  "
        f"meses={r['n_months']:>3d} (dos quais +={r['pct_months_pos']:.1f}%)  "
        f"win%={r['win_pct']:.1f} IC95=[{r['ic95_lo']*100:.1f};{r['ic95_hi']*100:.1f}]  "
        f"breakeven_emp={r['breakeven_empirico_pct']:.1f}%  "
        f"liquido=R${r['liquido_brl']:.2f}  MaxDD={r['max_drawdown_pct']:.1f}%  "
        f"dias_sem_posicao={r['dias_sem_posicao']}/{r['dias_totais']}",
        flush=True,
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["small", "full"], default="small")
    p.add_argument("--window", type=int, default=None, help="so no modo full: um W especifico")
    p.add_argument("--capital", type=float, default=1000.0)
    args = p.parse_args()

    if args.mode == "small":
        start, end = "2024-09-01", "2026-09-11"  # ~24 meses -> ~24 eventos independentes
        windows = [1, 3, 5, 10, 15, 21]
        print(f"=== TESTE PEQUENO: {start} -> {end} (~24 meses), varrendo W em {windows} ===", flush=True)
    else:
        start, end = "2010-01-01", "2026-09-11"
        windows = [args.window] if args.window is not None else [1, 3, 5, 10, 15, 21]
        print(f"=== JANELA CHEIA: {start} -> {end}, W em {windows} ===", flush=True)

    bh = _run_buyhold(start, end, args.capital)
    print(
        f"[baseline buy&hold cesta] capital_final=R${bh['capital_final']:.2f} "
        f"CAGR={bh['cagr_pct']:.2f}% MaxDD={bh['max_drawdown_pct']:.1f}%",
        flush=True,
    )

    results = []
    with ProcessPoolExecutor(max_workers=min(len(windows), 6)) as ex:
        futs = {ex.submit(_run_one, w, start, end, args.capital): w for w in windows}
        for fut in as_completed(futs):
            r = fut.result()
            print_row(r)
            results.append(r)

    results.sort(key=lambda r: r["window"])
    print("\n=== resumo ordenado por W ===", flush=True)
    for r in results:
        print_row(r)


if __name__ == "__main__":
    main()
