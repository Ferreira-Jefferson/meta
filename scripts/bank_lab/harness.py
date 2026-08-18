"""Harness de avaliacao para o laboratorio de robos bancarios.

Nao escreve no diario oficial (`db/journal.sqlite`) — este e um espaco de
experimentacao isolado, para nao interferir no ranking automatico do robo
campeao (`portfolio_dip2_hw40`) nem no `refresh_champion_rankings()`.

Uso tipico (dentro de um script de familia de estrategia):

    from bank_lab.harness import evaluate, BANK_UNIVERSE

    result = evaluate(MinhaEstrategia(param=1), tag="minha_estrategia_v1")
    print(json.dumps(result))

`evaluate()` roda a estrategia em 4 janelas (FULL, 5Y, HALF1, HALF2) e devolve
metricas + diagnosticos de overfitting (contagem de trades, concentracao de
lucro no top-1/top-3 trade, consistencia entre metades). Os GATES oficiais
(NegYrs<=1, MaxDD>=-35%) sao os mesmos usados pelo ranking automatico do robo
campeao (`journal/reader.py: CHAMPION_MAX_NEG_YEARS`, `CHAMPION_MAXDD_FLOOR`),
aplicados aqui sobre a janela FULL.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd

from backtest.runner import run as run_backtest
from backtest.metrics import negative_years
from core.config import BacktestConfig
from market_data.loader import load_universe

# Universo bancario com dado baixado em data/raw/ (ver scripts/download_bank_data.py).
# BPAN4.SA falhou no download (ticker sem timeline continua no yfinance — provavel
# resquicio da reestruturacao pos-fraude Panamericano 2010); fora do universo.
BANK_UNIVERSE: tuple[str, ...] = (
    "ITUB4.SA", "BBDC4.SA", "BBAS3.SA", "SANB11.SA", "BPAC11.SA",
    "BRSR6.SA", "ABCB4.SA", "BMGB4.SA", "PINE4.SA",
    "BEES3.SA", "BGIP4.SA", "BMEB4.SA", "BAZA3.SA",
)

# Gates oficiais do ranking automatico (ver journal/reader.py) — aplicados aqui
# sobre a janela FULL para qualquer robo bancario competir como candidato serio.
GATE_MAX_NEG_YEARS = 1
GATE_MAXDD_FLOOR = -0.35  # pedido do usuario: DD <= 35%

_TODAY = None  # preenchido on-demand por _today()


def _today() -> str:
    global _TODAY
    if _TODAY is None:
        ref = load_universe(tickers=["ITUB4.SA"], include_benchmark=False)["ITUB4.SA"]
        _TODAY = ref.index[-1].strftime("%Y-%m-%d")
    return _TODAY


def _windows() -> dict[str, tuple[str, str]]:
    today = _today()
    start = "2010-01-01"
    five_y = (pd.Timestamp(today) - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    mid = (pd.Timestamp(start) + (pd.Timestamp(today) - pd.Timestamp(start)) / 2).strftime("%Y-%m-%d")
    return {
        "full": (start, today),
        "5y": (five_y, today),
        "half1": (start, mid),
        "half2": (mid, today),
    }


def _profit_concentration(trades) -> dict:
    """Quanto do lucro bruto positivo vem do(s) trade(s) mais rentavel(is).

    Um top-1 dominando o lucro total e o exato padrao que a auditoria de
    overfitting anterior (memoria `overfitting_audit_2026_08_17`) encontrou no
    robo campeao atual (1 trade = 53,7% do lucro) — sinal de marcacao a
    mercado favoravel, nao de edge repetivel. Tratamos como diagnostico de
    risco aqui, nao como gate duro (o campeao oficial nem passaria no gate
    duro), mas penaliza no ranking final.
    """
    pnls = sorted((t.pnl_brl for t in trades if not t.is_open and t.pnl_brl > 0), reverse=True)
    total = sum(pnls)
    if total <= 0 or not pnls:
        return {"trades_count": len(trades), "top1_pct": 0.0, "top3_pct": 0.0}
    top1 = pnls[0] / total
    top3 = sum(pnls[:3]) / total
    return {"trades_count": len(trades), "top1_pct": round(top1, 4), "top3_pct": round(top3, 4)}


def _run_window(strategy, universe, config, start, end) -> dict:
    result = run_backtest(universe, strategy, config, start=start, end=end)
    m = result.metrics
    neg = negative_years(result.equity_curve)
    conc = _profit_concentration(result.trades)
    return {
        "final_capital": round(float(m["final_capital"]), 2),
        "cagr": round(float(m["cagr"]), 4),
        "sharpe": round(float(m.get("sharpe", 0.0)), 3),
        "max_drawdown": round(float(m["max_drawdown"]), 4),
        "neg_years": neg,
        "trades_count": conc["trades_count"],
        "top1_pct": conc["top1_pct"],
        "top3_pct": conc["top3_pct"],
        "benchmark_cagr": round(float(m.get("benchmark_cagr", 0.0)), 4),
    }


def evaluate(
    strategy,
    tag: str = "",
    tickers: tuple[str, ...] = BANK_UNIVERSE,
    initial_capital: float = 1000.0,
    lot_size: int = 1,
    stop_loss_pct: float = 0.15,
    max_concurrent_positions: int = 5,
) -> dict:
    """Roda `strategy` nas 4 janelas contra o universo bancario e aplica os gates.

    Retorna um dict pronto para `json.dumps` com: `tag`, metricas por janela,
    `passes_gate` (bool, baseado na janela FULL) e `overfit_flags` (lista de
    strings com alertas — nao bloqueia, so sinaliza para o revisor humano/agente).
    """
    universe = load_universe(tickers=tickers, include_benchmark=True)
    config = BacktestConfig(
        initial_capital=initial_capital, lot_size=lot_size,
        stop_loss_pct=stop_loss_pct, max_concurrent_positions=max_concurrent_positions,
    )
    windows = _windows()
    out = {"tag": tag or getattr(strategy, "name", strategy.__class__.__name__)}
    for label, (start, end) in windows.items():
        try:
            out[label] = _run_window(strategy, universe, config, start, end)
        except Exception as e:
            out[label] = {"error": str(e)}

    full = out.get("full", {})
    passes_gate = (
        "error" not in full
        and full.get("neg_years", 99) <= GATE_MAX_NEG_YEARS
        and full.get("max_drawdown", -1.0) >= GATE_MAXDD_FLOOR
    )
    out["passes_gate"] = passes_gate

    flags = []
    if "error" not in full:
        if full.get("trades_count", 0) < 15:
            flags.append(f"poucos_trades_full({full.get('trades_count')})")
        if full.get("top1_pct", 0) > 0.35:
            flags.append(f"concentracao_top1({full.get('top1_pct')*100:.0f}pct)")
        h1, h2 = out.get("half1", {}), out.get("half2", {})
        if "error" not in h1 and "error" not in h2:
            c1, c2 = h1.get("cagr", 0), h2.get("cagr", 0)
            if (c1 > 0) != (c2 > 0):
                flags.append(f"inconsistente_entre_metades(half1={c1:.2%},half2={c2:.2%})")
    out["overfit_flags"] = flags
    return out


if __name__ == "__main__":
    # Smoke test: roda a familia dip_top1 (ja validada em outros setores) no
    # universo bancario, so para confirmar que o harness funciona ponta a ponta
    # antes de qualquer agente gerar estrategias novas em cima dele.
    import json
    from strategy.h3_hysteresis import DipTop1Hysteresis
    r = evaluate(DipTop1Hysteresis(), tag="smoke_test_dip_top1_hysteresis")
    print(json.dumps(r, indent=2, ensure_ascii=False))
