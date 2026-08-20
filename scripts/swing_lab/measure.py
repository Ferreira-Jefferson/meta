"""Aritmetica UNICA da busca de swing. Todo agente mede por aqui.

Existe por um motivo do protocolo, nao por conveniencia: "parear o benchmark
janela por janela, com a MESMA aritmetica". Se cada agente escrevesse seu
proprio loop de medicao, 120 hipoteses viriam com 120 definicoes de CAGR e o
ranking compararia ruido de implementacao.

CEGUEIRA: este modulo aponta para `data/wide_e/` e SO para lah. O cofre
(`data/vault_1998_2009/`) e outra pasta, lido por outro modulo, no fim. Nao ha
parametro aqui que permita apontar a medicao para o cofre — a ausencia do
parametro E o mecanismo.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from market_data.loader import load_one

DIR_E = ROOT / "data" / "wide_e"
SELIC_E = str(DIR_E / "selic.parquet")
LEDGER = ROOT / "scripts" / "swing_lab" / "trials.jsonl"

INITIAL = 1000.0
ANOS = 5
DD_CEILING = -0.40

# ---------------------------------------------------------------- janelas E1/E2
# E1 — triagem. FULL + duas janelas, declaradas no protocolo.
FULL_START, FULL_END = "2010-01-01", "2026-08-19"
E1_WINDOWS: tuple[pd.Timestamp, ...] = (
    pd.Timestamp("2011-01-01"),
    pd.Timestamp("2017-01-01"),
)
# E2 — selecao. 47 janelas de 5 anos, inicios TRIMESTRAIS 2010-01..2021-07.
E2_WINDOWS: tuple[pd.Timestamp, ...] = tuple(
    pd.Timestamp(f"{y}-{m:02d}-01")
    for y in range(2010, 2022)
    for m in (1, 4, 7, 10)
    if not (y == 2021 and m == 10)
)

_PANELS: dict[str, pd.DataFrame] = {}
_POOL: tuple[str, ...] | None = None


def wide_pool() -> tuple[str, ...]:
    """Todo papel de acao em `data/wide_e/` — macro e o indice ficam fora."""
    global _POOL
    if _POOL is not None:
        return _POOL
    macro = {"selic", "usd_brl", "ipca", "desemprego"}
    out = []
    for p in sorted(glob.glob(str(DIR_E / "*.parquet"))):
        base = os.path.basename(p)[:-8]
        if base in macro or base.startswith("_"):
            continue
        out.append(base.replace("_SA", ".SA"))
    _POOL = tuple(out)
    return _POOL


def panel(ticker: str) -> pd.DataFrame:
    if ticker not in _PANELS:
        df = load_one(ticker, out_dir=DIR_E)
        _PANELS[ticker] = df[df["close"].notna()]
    return _PANELS[ticker]


def panels() -> dict[str, pd.DataFrame]:
    u = {t: panel(t) for t in wide_pool()}
    u[BENCHMARK] = panel(BENCHMARK)
    return u


# ------------------------------------------------------------------- medicao
def _cfg() -> BacktestConfig:
    return BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC_E)


def measure_one(factory, start: str, end: str) -> dict | None:
    """Uma janela. `factory` e um callable sem argumentos que devolve a Strategy."""
    r = run_bt(panels(), factory(), _cfg(), start=start, end=end)
    eq = r.equity_curve
    if len(eq) < 250:
        return None
    anos = (eq.index[-1] - eq.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0]
    return {
        "start": start,
        "end": end,
        "cagr": float(total ** (1.0 / anos) - 1.0) if anos > 0 and total > 0 else -1.0,
        "dd": float(max_drawdown(eq)),
        "w12": float((eq / eq.shift(252) - 1.0).min()),
        "trades": len(r.trades),
        "final": float(eq.iloc[-1]),
        "exposure": _exposure(r),
        "top5_share": _top5_share(r),
    }


def _exposure(r) -> float:
    """Fracao media do patrimonio investida, reconstruida das operacoes.

    `BacktestResult` nao carrega curva de investido, e o controle C2 (exposicao
    pareada) e OBRIGATORIO no protocolo: sem este numero nao se distingue
    "reduziu drawdown por diversificacao" de "reduziu drawdown por ficar fora
    do mercado", que e o erro que k=10 cometeu em `run_champion_k_control.py`.

    Marcado a mercado dia a dia, nao pelo preco de entrada: exposicao e quanto
    do patrimonio esta em risco HOJE.
    """
    eq = r.equity_curve
    if len(eq) == 0 or not r.trades:
        return 0.0
    inv = pd.Series(0.0, index=eq.index)
    for t in r.trades:
        ini = pd.Timestamp(t.entry_date)
        fim = pd.Timestamp(t.exit_date) if t.exit_date else eq.index[-1]
        try:
            px = panel(t.ticker)["close"].reindex(eq.index).ffill()
        except FileNotFoundError:
            continue
        janela = (inv.index >= ini) & (inv.index <= fim)
        inv.loc[janela] += (px[janela] * t.quantity).fillna(0.0)
    return float((inv / eq.replace(0.0, float("nan"))).clip(0, 1).fillna(0.0).mean())


def _top5_share(r) -> float:
    """Peso das 5 maiores operacoes no lucro total — controle de concentracao.

    So operacao FECHADA entra: `Trade.pnl_brl` devolve 0.0 (nao None) para
    posicao aberta, e contar isso como operacao de lucro zero diluiria
    justamente a concentracao que este controle existe para achar.
    """
    pnls = sorted((float(t.pnl_brl) for t in r.trades if t.exit_price is not None), reverse=True)
    if not pnls:
        return float("nan")
    total = sum(pnls)
    if total <= 0:
        return float("inf")
    return float(sum(pnls[:5]) / total)


def measure_windows(factory, windows, anos: int = ANOS) -> list[dict]:
    rows = []
    for s in windows:
        e = s + pd.DateOffset(years=anos)
        row = measure_one(factory, str(s.date()), str(min(e, pd.Timestamp(FULL_END)).date()))
        if row:
            rows.append(row)
    return rows


def ibov_window(start: pd.Timestamp, anos: int = ANOS) -> dict:
    end = min(start + pd.DateOffset(years=anos), pd.Timestamp(FULL_END))
    c = panel(BENCHMARK)["close"].loc[str(start.date()):str(end.date())].dropna()
    if len(c) < 250:
        return {}
    a = (c.index[-1] - c.index[0]).days / 365.25
    return {
        "cagr": float((c.iloc[-1] / c.iloc[0]) ** (1.0 / a) - 1.0),
        "dd": float(max_drawdown(c)),
        "w12": float((c / c.shift(252) - 1.0).min()),
    }


def summarize(rows: list[dict]) -> dict:
    """Objetivo declarado: maximizar CAGR mediano, com teto DURO de MaxDD."""
    if not rows:
        return {"n": 0, "median_cagr": float("nan"), "worst_dd": float("nan"),
                "worst_12m": float("nan"), "dd_gate": False}
    dd = min(r["dd"] for r in rows)
    return {
        "n": len(rows),
        "median_cagr": float(np.median([r["cagr"] for r in rows])),
        "worst_cagr": float(min(r["cagr"] for r in rows)),
        "worst_dd": dd,
        "median_dd": float(np.median([r["dd"] for r in rows])),
        "worst_12m": float(min(r["w12"] for r in rows)),
        "median_trades": float(np.median([r["trades"] for r in rows])),
        "median_exposure": float(np.nanmedian([r["exposure"] for r in rows])),
        "dd_gate": bool(dd >= DD_CEILING),
    }


def log_trial(name: str, family: str, stage: str, summary: dict, note: str = "") -> None:
    """Registra o ensaio. N vem DAQUI, contado, nunca estimado.

    Append-only e uma linha por ensaio: e este arquivo que alimenta a deflacao
    estatistica no fim. Um ensaio que nao esta aqui nao existiu, e um ensaio
    escondido invalida a correcao de multiplicidade de todos os outros.
    """
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = {"name": name, "family": family, "stage": stage, "note": note, **summary}
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def screen(factory, name: str, family: str, note: str = "") -> dict:
    """E1 — triagem: FULL + 2 janelas. Registra e devolve o resumo."""
    rows = []
    full = measure_one(factory, FULL_START, FULL_END)
    if full:
        rows.append(full)
    rows += measure_windows(factory, E1_WINDOWS)
    s = summarize(rows)
    log_trial(name, family, "E1", s, note)
    return s


def select(factory, name: str, family: str, note: str = "") -> dict:
    """E2 — selecao: 47 janelas trimestrais, com o IBOV pareado janela a janela."""
    rows = measure_windows(factory, E2_WINDOWS)
    s = summarize(rows)
    wins = 0
    for r in rows:
        b = ibov_window(pd.Timestamp(r["start"]))
        if b and r["cagr"] > b["cagr"]:
            wins += 1
    s["beat_ibov"] = wins
    s["n_windows"] = len(rows)
    s["cagr_by_window"] = [r["cagr"] for r in rows]
    log_trial(name, family, "E2", {k: v for k, v in s.items() if k != "cagr_by_window"}, note)
    return s
