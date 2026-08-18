"""Consultas do diário. O dashboard fala com o SQLite apenas por aqui."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.config import DB_PATH


def _conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def list_runs(
    db_path: Path = DB_PATH,
    strategy: str | None = None,
    start_from: str | None = None,
    end_to: str | None = None,
    capital_min: float | None = None,
    capital_max: float | None = None,
    ticker: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    q = (
        "SELECT r.*, "
        "  (SELECT GROUP_CONCAT(DISTINCT t.ticker) FROM trades t WHERE t.run_id = r.id) AS tickers, "
        "  ROUND((julianday(r.period_end) - julianday(r.period_start)) / 365.25, 1) AS period_years "
        "FROM runs r WHERE 1=1"
    )
    args: list[Any] = []
    if strategy:
        q += " AND r.strategy_name = ?"; args.append(strategy)
    if start_from:
        q += " AND r.period_start >= ?"; args.append(start_from)
    if end_to:
        q += " AND r.period_end <= ?"; args.append(end_to)
    if capital_min is not None:
        q += " AND r.initial_capital >= ?"; args.append(capital_min)
    if capital_max is not None:
        q += " AND r.initial_capital <= ?"; args.append(capital_max)
    if ticker:
        q += " AND EXISTS (SELECT 1 FROM trades t WHERE t.run_id = r.id AND t.ticker = ?)"
        args.append(ticker)
    q += " ORDER BY r.id DESC"
    if limit is not None:
        q += " LIMIT ? OFFSET ?"; args.extend([limit, offset])
    with _conn(db_path) as c:
        return _rows(c.execute(q, args))


def distinct_strategies(db_path: Path = DB_PATH) -> list[str]:
    with _conn(db_path) as c:
        rows = c.execute("SELECT DISTINCT strategy_name FROM runs ORDER BY strategy_name").fetchall()
    return [r[0] for r in rows]


def distinct_run_tickers(db_path: Path = DB_PATH) -> list[str]:
    with _conn(db_path) as c:
        rows = c.execute("SELECT DISTINCT ticker FROM trades ORDER BY ticker").fetchall()
    return [r[0] for r in rows]


def latest_run(db_path: Path = DB_PATH) -> dict | None:
    runs = list_runs(db_path)
    return runs[0] if runs else None


# Gates do ranking automático (ver memória `ranking-criterion` / decisão do
# usuário 2026-08-16): um robô só compete pelo pódio se tiver no máximo 1 ano
# calendário negativo E um MaxDD não pior que o piso abaixo. O piso é o MaxDD
# do TOP-1 vigente quando o gate foi definido — existe para barrar um robô de
# capital final alto mas risco de ruína pior que o que já se provou sustentável;
# revisitar se um candidato legítimo precisar de folga aqui.
CHAMPION_MAX_NEG_YEARS = 1
CHAMPION_MAXDD_FLOOR = -0.3512


def top_strategies_by_final_capital(
    top_n: int = 3,
    run_kind: str = "champion_full",
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Ranking automático de robôs por capital final, dentro de `run_kind`.

    Para cada `strategy_name` com run do `run_kind` pedido ('champion_full',
    'champion_5y' ou 'champion_1y' — ver `scheduler.refresh_champion_rankings`),
    pega o run mais recente (maior id), aplica os gates de NegYrs e MaxDD, e
    ordena os sobreviventes por `final_capital`. Runs avulsos (`run_kind='ad_hoc'`,
    simulações manuais do dashboard) nunca entram nesta lista.
    """
    q = (
        "WITH latest AS ( "
        "  SELECT strategy_name, MAX(id) AS max_id "
        "  FROM runs WHERE run_kind = ? "
        "  GROUP BY strategy_name "
        ") "
        "SELECT r.id, r.strategy_name, r.strategy_version, "
        "  r.period_start, r.period_end, r.initial_capital, "
        "  r.final_capital, r.cagr, r.sharpe, r.max_drawdown, r.trades_count, r.neg_years, "
        "  ROUND((julianday(r.period_end) - julianday(r.period_start)) / 365.25, 1) AS period_years, "
        "  (SELECT MIN(equity) FROM equity_curve WHERE run_id=r.id) AS min_equity "
        "FROM runs r "
        "JOIN latest lt ON lt.max_id = r.id "
        "ORDER BY r.final_capital DESC"
    )
    with _conn(db_path) as c:
        rows = _rows(c.execute(q, (run_kind,)))
    ranked = []
    for r in rows:
        neg_years = r.get("neg_years")
        maxdd = r.get("max_drawdown")
        # Compara arredondado a 2 casas percentuais: o piso foi definido como
        # "-35,12%", nessa precisão — comparar em float cheio reprovaria o
        # próprio robô de referência por ruído de ponto flutuante (ex.:
        # -35,1223...% vs -35,12% quando os dados avançam um dia).
        qualifies = (
            neg_years is not None and neg_years <= CHAMPION_MAX_NEG_YEARS
            and maxdd is not None and round(maxdd * 100, 2) >= round(CHAMPION_MAXDD_FLOOR * 100, 2)
        )
        r["disqualified"] = not qualifies
        if qualifies:
            ranked.append(r)
    return ranked[:top_n]


def latest_champion_window(run_kind: str, db_path: Path = DB_PATH) -> tuple[str, str] | None:
    """(period_start, period_end) do run de ranking mais recente desse `run_kind`.

    Usado para exibir o cabeçalho da janela na home (ex. "5Y (2021-08-16 → hoje)").
    Retorna None se o ranking automático ainda não rodou para esse `run_kind`.
    """
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT period_start, period_end FROM runs WHERE run_kind = ? "
            "ORDER BY id DESC LIMIT 1",
            (run_kind,),
        ).fetchone()
    return (row["period_start"], row["period_end"]) if row else None


def get_run(run_id: int, db_path: Path = DB_PATH) -> dict | None:
    with _conn(db_path) as c:
        row = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def list_trades(
    run_id: int,
    ticker: str | None = None,
    year: int | None = None,
    outcome: str | None = None,
    exit_reason: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    q = "SELECT * FROM trades WHERE run_id = ?"
    args: list[Any] = [run_id]
    if ticker:
        q += " AND ticker = ?"
        args.append(ticker)
    if year:
        q += " AND substr(entry_date, 1, 4) = ?"
        args.append(str(year))
    if exit_reason:
        q += " AND exit_reason = ?"
        args.append(exit_reason)
    if outcome == "winner":
        q += " AND pnl_pct > 0"
    elif outcome == "loser":
        q += " AND pnl_pct < 0"
    q += " ORDER BY entry_date DESC"

    with _conn(db_path) as c:
        return _rows(c.execute(q, args))


def get_trade(trade_id: int, db_path: Path = DB_PATH) -> dict | None:
    with _conn(db_path) as c:
        row = c.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None


def trade_snapshots(trade_id: int, db_path: Path = DB_PATH) -> dict[str, dict]:
    with _conn(db_path) as c:
        rows = _rows(c.execute("SELECT * FROM signal_snapshots WHERE trade_id = ?", (trade_id,)))
    return {r["moment"]: r for r in rows}


def trade_tags(trade_id: int, db_path: Path = DB_PATH) -> list[dict]:
    with _conn(db_path) as c:
        return _rows(c.execute(
            "SELECT tag_type, tag_value FROM notes WHERE trade_id = ? ORDER BY tag_type",
            (trade_id,),
        ))


def equity_curve(run_id: int, db_path: Path = DB_PATH) -> list[dict]:
    with _conn(db_path) as c:
        return _rows(c.execute(
            "SELECT date, equity, benchmark FROM equity_curve WHERE run_id = ? ORDER BY date",
            (run_id,),
        ))


def equity_stats(run_id: int, db_path: Path = DB_PATH) -> dict | None:
    """Estatísticas de capital: inicial, pico, vale, final — a partir da equity_curve."""
    with _conn(db_path) as c:
        first = c.execute(
            "SELECT date, equity FROM equity_curve WHERE run_id = ? ORDER BY date ASC  LIMIT 1", (run_id,)
        ).fetchone()
        last = c.execute(
            "SELECT date, equity FROM equity_curve WHERE run_id = ? ORDER BY date DESC LIMIT 1", (run_id,)
        ).fetchone()
        peak = c.execute(
            "SELECT date, equity FROM equity_curve WHERE run_id = ? ORDER BY equity DESC, date ASC LIMIT 1", (run_id,)
        ).fetchone()
        trough = c.execute(
            "SELECT date, equity FROM equity_curve WHERE run_id = ? ORDER BY equity ASC,  date ASC LIMIT 1", (run_id,)
        ).fetchone()
    if not first:
        return None
    return {
        "initial": {"date": first["date"], "equity": float(first["equity"])},
        "final":   {"date": last["date"],  "equity": float(last["equity"])},
        "peak":    {"date": peak["date"],  "equity": float(peak["equity"])},
        "trough":  {"date": trough["date"], "equity": float(trough["equity"])},
    }


def distinct_tickers(run_id: int, db_path: Path = DB_PATH) -> list[str]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT DISTINCT ticker FROM trades WHERE run_id = ? ORDER BY ticker",
            (run_id,),
        ).fetchall()
    return [r[0] for r in rows]


def distinct_years(run_id: int, db_path: Path = DB_PATH) -> list[int]:
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT DISTINCT substr(entry_date,1,4) FROM trades WHERE run_id = ? ORDER BY 1",
            (run_id,),
        ).fetchall()
    return [int(r[0]) for r in rows]


# --- Aggregations for Insights page --------------------------------------

def pnl_by_tag(run_id: int, tag_type: str, db_path: Path = DB_PATH) -> list[dict]:
    with _conn(db_path) as c:
        return _rows(c.execute(
            """SELECT n.tag_value AS tag,
                      COUNT(*)     AS trades,
                      AVG(t.pnl_pct) AS avg_pnl_pct,
                      SUM(CASE WHEN t.pnl_pct > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS win_rate
               FROM trades t
               JOIN notes  n ON n.trade_id = t.id
               WHERE t.run_id = ? AND t.status = 'closed' AND n.tag_type = ?
               GROUP BY n.tag_value
               ORDER BY avg_pnl_pct DESC""",
            (run_id, tag_type),
        ))


def ifr_distribution(run_id: int, db_path: Path = DB_PATH) -> list[dict]:
    with _conn(db_path) as c:
        return _rows(c.execute(
            """SELECT s.ifr14 AS ifr, t.pnl_pct AS pnl,
                      CASE WHEN t.pnl_pct > 0 THEN 'winner' ELSE 'loser' END AS outcome
               FROM trades t
               JOIN signal_snapshots s ON s.trade_id = t.id
               WHERE t.run_id = ? AND s.moment = 'entry' AND t.status = 'closed'""",
            (run_id,),
        ))


def ticker_ranking(run_id: int, db_path: Path = DB_PATH) -> list[dict]:
    """Ranking por ativo enriquecido, para responder 'esse robô ganhou onde?'.

    Além de PnL total, devolve contribuição % (share do PnL total do run),
    winrate, holding médio, melhor/pior trade e ROI sobre o capital efetivamente
    alocado (`roi_deployed`) — a métrica correta para comparar contra buy&hold,
    já que abate o tempo em que o dinheiro esteve fora do ativo.
    """
    with _conn(db_path) as c:
        rows = _rows(c.execute(
            """SELECT ticker,
                      COUNT(*)                                         AS trades,
                      SUM(pnl_brl)                                     AS total_pnl,
                      SUM(capital_allocated)                           AS capital_deployed,
                      AVG(pnl_pct)                                     AS avg_pnl_pct,
                      AVG(r_multiple)                                  AS avg_r,
                      AVG(holding_days)                                AS avg_holding_days,
                      MAX(pnl_pct)                                     AS best_pnl_pct,
                      MIN(pnl_pct)                                     AS worst_pnl_pct,
                      SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) * 1.0
                          / NULLIF(COUNT(*), 0)                        AS win_rate
               FROM trades
               WHERE run_id = ? AND status = 'closed'
               GROUP BY ticker
               ORDER BY total_pnl DESC""",
            (run_id,),
        ))
    total = sum((r["total_pnl"] or 0.0) for r in rows)
    for r in rows:
        pnl = r["total_pnl"] or 0.0
        r["contribution_pct"] = (pnl / total) if total else 0.0
        cap = r["capital_deployed"] or 0.0
        r["roi_deployed"] = (pnl / cap) if cap else 0.0
    return rows


def ticker_ranking_with_benchmark(run_id: int, db_path: Path = DB_PATH) -> list[dict]:
    """Ranking por ativo + retorno buy&hold do próprio ticker na mesma janela.

    `edge_pp` positivo = o robô rendeu mais que segurar o papel; negativo = o
    robô destruiu valor naquele ativo.
    """
    from market_data.loader import load_one, slice_period

    rows = ticker_ranking(run_id, db_path)
    run = get_run(run_id, db_path)
    if not run:
        return rows

    start, end = run["period_start"], run["period_end"]
    for r in rows:
        try:
            df = slice_period(load_one(r["ticker"]), start, end)
            if len(df) >= 2:
                first, last = float(df["close"].iloc[0]), float(df["close"].iloc[-1])
                bh = (last / first) - 1.0 if first else None
            else:
                bh = None
        except FileNotFoundError:
            bh = None
        r["buy_hold_return"] = bh
        r["edge_pp"] = (r["roi_deployed"] - bh) if bh is not None else None
    return rows
