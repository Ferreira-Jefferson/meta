"""Scheduler: mantém dados frescos e rerroda o ranking automático de robôs.

- Janela FULL = HISTORY_START → data mais recente comum a todos os dados.
- Janela 5Y   = (data mais recente) - 5 anos → data mais recente (móvel).
- Janela 1Y   = último ano-calendário COMPLETO (ex.: 2025-01-01 → 2025-12-31
  enquanto 2026 não fechar) — fixa, não é uma janela móvel de 365 dias; avança
  sozinha quando o ano vigente terminar.
- TODO robô descoberto em `strategy/` (ver `strategy.discovery`) é rerrodado
  nas três janelas com o capital/lote do critério oficial de ranking
  (R$ 100, lote fracionário, com a taxa fixa de R$ 1,90/ordem que o
  fracionário cobra de verdade) e persistido no diário com `run_kind` marcado
  ('champion_full' / 'champion_3y') — isso que o ranking em
  `journal.reader.top_strategies_by_final_capital()` lê para montar o pódio.
  Não há promoção manual: um robô novo em `strategy/` entra na disputa no
  próximo refresh sem editar nada aqui.
- Uma run de campeão é considerada atual só quando cobre o período E foi
  calculada sobre o MESMO dado (`data_fingerprint`). Comparar apenas
  `period_end` deixava métrica velha no pódio: o provedor revisa closes
  ajustados retroativamente (split/dividendo/correção), mudando a série
  histórica inteira sem mover a última data um único dia.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from backtest.metrics import negative_years
from backtest.runner import run as run_backtest_dispatch
from core.config import (
    BENCHMARK,
    DB_PATH,
    HISTORY_START,
    WATCHLIST,
    BacktestConfig,
    CostModel,
)
from journal.enrichment import enrich
from journal.writer import append_equity, create_run, finalize_run, insert_trade, journal
from market_data.download import download_all
from market_data.loader import load_one, load_universe, universe_fingerprint
from strategy.registry import list_strategies

# Critério oficial de ranking (ver memória `ranking-criterion`): capital
# inicial pequeno, lote fracionário — não os R$ 100k/lote 100 do canonical antigo.
#
# 2026-08-22 — R$ 1.000 virou R$ 100, e a taxa fixa do fracionário passou a ser
# COBRADA. Decisão do dono do capital, com o motivo dele: "pra conseguir operar
# com o capital que realmente tenho só é possível com ele fracionado, pq testou
# sem se não consigo operar um lote completo?".
#
# O que a medição mostrou e por que os DOIS números tinham de mudar juntos:
# ligar a taxa mantendo os R$ 1.000 muda o `liqflop` no FULL em -1,2%
# (R$28.341,70 -> R$27.998,29), praticamente nada — a R$ 1.000 boa parte das
# ordens fecha lote padrão e não paga taxa fixa nenhuma. O que vira o resultado
# é a INTERAÇÃO capital x taxa: a R$ 100, com a mesma taxa, o mesmo robô faz
# R$ 2.957,93 no FULL e PERDE do IBOV em 2019-2026 (R$ 106,12 contra R$ 184,51).
# Ranquear a R$ 1.000 media um regime que o dono não consegue executar.
#
# O default de `CostModel.fractional_fixed_fee` continua 0.0 de propósito (ver
# o comentário lá): mudá-lo reescreveria o significado de todo o diário
# gravado. Aqui a taxa é explícita, como o `CHAMPION_CASH_YIELD` logo abaixo —
# mesma regra: a run OFICIAL compara robôs no mundo real, e o resto do repo
# continua reproduzindo o que gravou.
CHAMPION_CAPITAL = 100.0
CHAMPION_LOT_SIZE = 1
# R$ 1,90 por ORDEM no fracionário (não percentual), confirmado pelo dono em
# 2026-08-22 — ver memória `rico_fractional_fee_2026_08_21`. Cobrada em cada
# perna cuja quantidade não fecha lote padrão, a mesma regra que
# `live/broker_mt5.py` aplica ao vivo.
CHAMPION_FRACTIONAL_FEE = 1.90
# Caixa parado rende Selic nas runs de ranking. Até 2026-08-20 rendia 0%, e isso
# não era um detalhe: `liquid_champion` passa 32% do tempo com algum sleeve
# descoberto, o campeão antigo 24%, e a Selic média do período foi 9,48% a.a. O
# viés não era neutro — caía inteiro sobre quem segura mais caixa, exatamente os
# robôs mais defensivos. O default do `BacktestConfig` continua `None` (não
# reescreve o passado de quem chama sem saber), mas a run OFICIAL de ranking tem
# de comparar robôs no mundo real, onde dinheiro parado rende.
CHAMPION_CASH_YIELD = "data/raw/selic.parquet"
CHAMPION_5Y_YEARS = 5


def regime_fingerprint(data_fingerprint: str) -> str:
    """Junta o dado E o regime econômico num só carimbo de validade.

    `_champion_is_current` compara `period_end` + este carimbo para decidir se
    rerroda. Enquanto ele era só o fingerprint do DADO, mudar o regime oficial
    (capital, taxa) não invalidava nada: as runs do regime velho continuariam
    no pódio, com o preço novo escrito no cabeçalho da página e o número antigo
    embaixo. Aconteceu de verdade em 2026-08-22, ao trocar R$ 1.000/taxa zero
    por R$ 100/R$ 1,90 — só um `force=True` na mão salvou.
    """
    return f"{data_fingerprint}|cap={CHAMPION_CAPITAL:g}|frac={CHAMPION_FRACTIONAL_FEE:g}"


def champion_costs() -> CostModel:
    """Custos da run OFICIAL de ranking: os percentuais padrão do repo + a
    taxa fixa do fracionário, que é real e o dono paga.

    Função, e não constante de módulo, para que quem for medir fora do
    `scheduler` (script de laboratório, teste, contraprova) consiga rodar no
    MESMO regime do painel chamando UMA coisa, em vez de reconstruir o
    `CostModel` de memória e errar um campo — foi assim que o ranking passou
    meses cobrando taxa zero num mercado que cobra R$ 1,90.
    """
    return replace(CostModel(), fractional_fixed_fee=CHAMPION_FRACTIONAL_FEE)


# ---------- data freshness -------------------------------------------------

def latest_common_date() -> pd.Timestamp:
    """Última data comum a todos os parquets necessários (watchlist + IBOV + macro)."""
    latest: pd.Timestamp | None = None
    for t in list(WATCHLIST) + [BENCHMARK]:
        try:
            idx_last = load_one(t).index[-1]
        except FileNotFoundError:
            continue
        if latest is None or idx_last < latest:
            latest = idx_last

    for macro in ("selic", "usd_brl"):
        p = Path("data/raw") / f"{macro}.parquet"
        if p.exists():
            m_last = pd.read_parquet(p).index[-1]
            if latest is None or m_last < latest:
                latest = m_last

    return latest or pd.Timestamp.today().normalize()


# ---------- backtest execution --------------------------------------------

def _run_champion(strategy_key: str, factory, start: str, end: str, run_kind: str,
                  fingerprint: str | None = None) -> int:
    """Roda um backtest oficial de ranking e persiste. Retorna run_id."""
    strategy = factory()
    # universe_tickers permite a um robô experimental (setor bancário, universo
    # largo, etc.) escolher seu próprio universo em vez do WATCHLIST canonical
    # — ver o comentário em `strategy/base.py`.
    universe = load_universe(tickers=strategy.universe_tickers) if strategy.universe_tickers else load_universe()
    config = BacktestConfig(initial_capital=CHAMPION_CAPITAL, lot_size=CHAMPION_LOT_SIZE,
                            cash_yield_path=CHAMPION_CASH_YIELD,
                            costs=champion_costs())
    result = run_backtest_dispatch(universe, strategy, config, start=start, end=end)

    metrics = dict(result.metrics)
    metrics["neg_years"] = negative_years(result.equity_curve)

    with journal() as conn:
        run_id = create_run(
            conn,
            strategy_name=strategy_key,
            strategy_version=strategy.version,
            period_start=start,
            period_end=end,
            initial_capital=config.initial_capital,
            run_kind=run_kind,
            data_fingerprint=fingerprint,
        )
        for trade in result.trades:
            trade.tags = enrich(trade)
            insert_trade(conn, run_id, trade)
        bench = result.benchmark_curve.reindex(result.equity_curve.index).ffill()
        equity_points = [
            (d.strftime("%Y-%m-%d"), float(e), float(bench.get(d)) if d in bench.index else None)
            for d, e in result.equity_curve.items()
        ]
        append_equity(conn, run_id, equity_points)
        finalize_run(conn, run_id, metrics)
    return run_id


def _latest_champion_state(
    strategy_key: str, run_kind: str, db_path: Path | None = None
) -> tuple[str | None, str | None]:
    """(period_end, data_fingerprint) da run oficial mais recente desse robô/janela."""
    with sqlite3.connect(db_path or DB_PATH) as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(runs)")}
        field = "data_fingerprint" if "data_fingerprint" in cols else "NULL"
        row = c.execute(
            f"SELECT period_end, {field} FROM runs WHERE strategy_name = ? AND run_kind = ? "
            "ORDER BY id DESC LIMIT 1",
            (strategy_key, run_kind),
        ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _champion_is_current(
    strategy_key: str, run_kind: str, end: str, fingerprint: str
) -> bool:
    """A run gravada cobre o período E foi calculada sobre ESTE dado?

    A checagem de fingerprint é o que impede métrica stale no pódio: o yfinance
    revisa closes ajustados retroativamente (split, dividendo, correção), então
    a série de 2010-2025 pode mudar sem a última data avançar um dia. Antes daqui
    o ranking só olhava `period_end` e nunca rerrodava nesse caso.
    """
    last_end, last_fp = _latest_champion_state(strategy_key, run_kind)
    if (last_end or "0000-00-00") < end:
        return False
    return last_fp == fingerprint


# ---------- orchestration -------------------------------------------------

def refresh_champion_rankings(force: bool = False) -> dict:
    """Rerroda todo robô descoberto nas janelas FULL, 5Y e 1Y se os dados avançaram.

    force=True: rerroda mesmo se já está no dia (útil pra testar). Retorna
    resumo com {refreshed, failed, full_window, five_y_window, one_y_window}.
    """
    target_end_ts = latest_common_date()
    target_end = target_end_ts.strftime("%Y-%m-%d")
    five_y_start = (target_end_ts - pd.DateOffset(years=CHAMPION_5Y_YEARS)).strftime("%Y-%m-%d")
    # Último ano-calendário COMPLETO: se a data mais recente é em 2026, o
    # último ano fechado é 2025 (2026-01-01 -> 2025-12-31 continua sendo o
    # mesmo par até 2026 terminar). Janela fixa, não móvel.
    last_complete_year = target_end_ts.year - 1
    one_y_start = f"{last_complete_year}-01-01"
    one_y_end = f"{last_complete_year}-12-31"
    windows = [
        ("champion_full", HISTORY_START, target_end),
        ("champion_5y", five_y_start, target_end),
        ("champion_1y", one_y_start, one_y_end),
    ]

    refreshed: list[dict] = []
    failed: list[dict] = []
    strategies = list_strategies()
    print(f"[champion-refresh] target_end={target_end}, 5y_start={five_y_start}, "
          f"1y={one_y_start}..{one_y_end}, {len(strategies)} robôs")
    for info in strategies:
        # Fingerprint por robô: um robô com `universe_tickers` próprio (ex.
        # especialista em bancos) tem que ser invalidado quando O SEU dado
        # avança, não quando o WATCHLIST canonical avança — e vice-versa.
        strategy_tickers = info.factory().universe_tickers
        fingerprint = regime_fingerprint(
            universe_fingerprint(tickers=strategy_tickers or WATCHLIST))
        for run_kind, start, end in windows:
            if not force and _champion_is_current(info.key, run_kind, end, fingerprint):
                continue
            t0 = time.perf_counter()
            try:
                run_id = _run_champion(info.key, info.factory, start, end, run_kind, fingerprint)
                dt = time.perf_counter() - t0
                print(f"  [ok] {info.key:30s} {run_kind:14s} run_id={run_id} {dt:.1f}s")
                refreshed.append({"key": info.key, "run_kind": run_kind, "run_id": run_id, "seconds": round(dt, 1)})
            except Exception as e:
                dt = time.perf_counter() - t0
                print(f"  [FAIL] {info.key:30s} {run_kind:14s} {dt:.1f}s -> {type(e).__name__}: {e}")
                failed.append({"key": info.key, "run_kind": run_kind, "error": str(e)})
    return {
        "refreshed": refreshed,
        "failed": failed,
        "full_window": (HISTORY_START, target_end),
        "five_y_window": (five_y_start, target_end),
        "one_y_window": (one_y_start, one_y_end),
    }


def refresh_market_data() -> dict:
    """Baixa OHLCV + macro. Chamada periodicamente. Retorna paths escritos."""
    written = download_all()
    return {"paths": {k: str(v) for k, v in written.items()}}


def refresh_all(force_champions: bool = False) -> dict:
    """Fluxo completo: market data → ranking automático de robôs."""
    data = refresh_market_data()
    champions = refresh_champion_rankings(force=force_champions)
    return {"data": data, "champions": champions}
