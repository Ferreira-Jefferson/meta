"""Engine event-driven de backtest — adaptativo.

Responsabilidades do engine:
- percorrer o calendário de datas
- entregar o snapshot atual ao robô (via `Strategy.on_bar`)
- executar as ações declarativas devolvidas: `Enter`, `Exit`, `AdjustStop`
- aplicar custos (corretagem + emolumentos + slippage) em toda execução
- disparar stops automáticos quando o `low` do dia rompe o `current_stop`
- gravar snapshots ricos no momento da decisão para o diário

Cada robô é dono da sua política de entrada, saída e ajuste de stop.
O engine só coordena. Anti-look-ahead: toda decisão tomada no close[D]
executa no open[D+1].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

import pandas as pd

from backtest.costs import apply_slippage, cash_yield_series, fees_for_leg
from core.config import BENCHMARK, BacktestConfig
from core.market_features import enrich_features, snapshot_from_row
from core.models import ExitReason, MarketSnapshot, Trade
from strategy.base import AdjustStop, Enter, Exit, OpenPosition, Strategy


@dataclass
class _Position:
    ticker: str
    entry_date: date
    entry_price: float
    quantity: int
    capital_allocated: float
    fees_paid: float
    slippage_paid: float
    entry_snapshot: MarketSnapshot
    max_price_seen: float
    min_price_seen: float
    current_stop: float | None
    bars_held: int
    metadata: dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    metrics: dict
    # Saques executados pelo overlay de gestao de capital (ver
    # `backtest/withdrawal.py`). Vazio quando o run nao usa politica de saque.
    withdrawals: list = field(default_factory=list)
    # Curva de COTA: patrimonio dividido pelo numero de cotas, onde cada aporte
    # compra cotas ao valor do dia. Igual a `equity_curve` quando nao ha aporte
    # (`monthly_contribution=0`), que e o caso de todo o diario gravado. Existe
    # porque com aporte a curva de patrimonio sobe por dinheiro novo, e usar
    # CAGR/MaxDD dela compararia coisas diferentes.
    unit_curve: pd.Series | None = None
    # (data, valor) de cada aporte creditado.
    contributions: list = field(default_factory=list)


# `_enrich`/`_snapshot` foram EXTRAIDOS para `core/market_features.py` quando a
# operacao ao vivo passou a registrar o mesmo contexto de sinal que o backtest
# (`live_signal_snapshots`). Os aliases ficam porque `engine_portfolio` e
# `engine_satellite` importam estes nomes daqui — e, mais importante, porque o
# calculo agora tem UMA implementacao so: se o live e o backtest calculassem
# MM200/IFR14 por caminhos diferentes, comparar o snapshot real com o simulado
# viraria ficcao. Ver a docstring de `core/market_features.py`.
_enrich = enrich_features
_snapshot = snapshot_from_row


def _positions_view(positions: dict[str, _Position]) -> dict[str, OpenPosition]:
    """Espelha o estado interno como view read-only para o robô."""
    return {
        t: OpenPosition(
            ticker=p.ticker,
            entry_date=pd.Timestamp(p.entry_date),
            entry_price=p.entry_price,
            quantity=p.quantity,
            current_stop=p.current_stop,
            bars_held=p.bars_held,
            metadata=dict(p.metadata),
        )
        for t, p in positions.items()
    }


def run_backtest(
    universe: dict[str, pd.DataFrame],
    strategy: Strategy,
    config: BacktestConfig,
    start: str,
    end: str,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> BacktestResult:
    ibov = universe[BENCHMARK]

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    # Passa OHLCV cru para o robô inicializar seus próprios indicadores.
    raw_panels: dict[str, pd.DataFrame] = {
        t: df for t, df in universe.items() if t != BENCHMARK
    }
    strategy.initialize(raw_panels, ibov)

    # Enriquece o histórico para snapshots do diário e recorta na janela.
    enriched: dict[str, pd.DataFrame] = {}
    for ticker, df_full in raw_panels.items():
        e = _enrich(df_full, ibov)
        mask = (e.index >= start_ts) & (e.index <= end_ts)
        enriched[ticker] = e.loc[mask]

    all_dates = sorted({d for df in enriched.values() for d in df.index})
    all_dates = pd.DatetimeIndex(all_dates)

    ibov_slice = ibov.loc[(ibov.index >= start_ts) & (ibov.index <= end_ts)]

    cash = config.initial_capital
    positions: dict[str, _Position] = {}
    closed: list[Trade] = []
    equity_records: list[tuple[pd.Timestamp, float]] = []
    # Último close conhecido por ticker — usado para marcar a posição a mercado
    # em dias onde o parquet do ativo tem um gap (bar faltando) mas outros
    # ativos do universo pregaram normalmente. Sem isso, um gap de 1 dia em
    # um único ticker faz a posição "sumir" do equity naquele dia (o valor
    # não é somado), criando um drawdown fantasma de quase -100%.
    last_price: dict[str, float] = {}

    # Ações filadas ao final de D para execução no open de D+1.
    # Só Enter/Exit vão para a fila; AdjustStop é aplicado imediatamente.
    pending: list = []

    default_stop = config.stop_loss_pct  # fallback quando Enter não trouxer stop

    cash_yield = cash_yield_series(config.cash_yield_path, all_dates)

    # Aporte mensal e contabilidade de COTA. Espelha `engine_portfolio.py`:
    # existia so la, e este engine ACEITAVA `monthly_contribution` e o
    # ignorava em silencio — um robo roteado para ca (ex.: a familia
    # `strategy/lab/`) media "com aporte" sem aporte nenhum, e nada avisava.
    # Comparar dois robos de engines diferentes com o mesmo config produzia
    # numeros incomparaveis sem erro.
    units = 1.0
    unit_records: list[tuple[pd.Timestamp, float]] = []
    contributions: list[tuple[pd.Timestamp, float]] = []
    mes_anterior: tuple[int, int] | None = None

    for i, today in enumerate(all_dates):
        # (0) Remuneracao do caixa parado — mesma regra do engine de portfolio,
        # aplicada antes das execucoes do dia. Desligada por default; ver
        # `backtest.costs.cash_yield_series`.
        if cash_yield is not None and cash > 0.0:
            cash *= 1.0 + float(cash_yield.iat[i])

        # (0b) Aporte: primeiro pregao de cada mes civil, depois do juro de
        # ontem e antes de qualquer execucao. O mes do capital inicial NAO
        # recebe aporte — ele JA e o primeiro deposito. Cotizado pelo
        # patrimonio de FECHAMENTO ANTERIOR (`last_price`), nunca pelo preco
        # de hoje: usar o preco de hoje daria ao aporte uma cota que so seria
        # conhecida no fim do pregao (look-ahead).
        mes = (today.year, today.month)
        if config.monthly_contribution > 0.0 and mes_anterior is not None and mes != mes_anterior:
            aporte = float(config.monthly_contribution)
            patrimonio_antes = cash
            for t, pos in positions.items():
                patrimonio_antes += last_price.get(t, 0.0) * pos.quantity
            if patrimonio_antes > 0.0:
                units += aporte / (patrimonio_antes / units)
            else:
                # Patrimonio zerado: nao ha cota valida para emitir. Reancora
                # em vez de dividir por zero — a serie de cota recomeca aqui e
                # isso fica visivel no proprio numero.
                units = 1.0
            cash += aporte
            contributions.append((today, aporte))
        mes_anterior = mes

        # (1) MFE/MAE usando close do dia
        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                px = float(df.at[today, "close"])
                pos.max_price_seen = max(pos.max_price_seen, px)
                pos.min_price_seen = min(pos.min_price_seen, px)

        # (2) Stop automático: engine dispara Exit se low[D] <= current_stop.
        # Prioridade sobre ações filadas — protege a carteira antes de qualquer coisa.
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            df = enriched.get(ticker)
            if df is None or today not in df.index or pos.current_stop is None:
                continue
            low_px = float(df.at[today, "low"])
            open_px = float(df.at[today, "open"])
            if low_px <= pos.current_stop:
                # gap down abaixo do stop → executa no open (pior); senão no stop
                exec_ref = min(open_px, pos.current_stop)
                exec_px = apply_slippage(exec_ref, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs)
                cash += gross - leg_fees
                snap = _snapshot(df.loc[today])
                closed.append(
                    Trade(
                        ticker=ticker,
                        strategy_name=strategy.name,
                        strategy_version=strategy.version,
                        entry_date=pos.entry_date,
                        entry_price=pos.entry_price,
                        quantity=pos.quantity,
                        capital_allocated=pos.capital_allocated,
                        exit_date=today.date(),
                        exit_price=exec_px,
                        exit_reason=ExitReason.STOP,
                        fees_total=pos.fees_paid + leg_fees,
                        slippage_total=pos.slippage_paid + abs(exec_px - exec_ref) * pos.quantity,
                        max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                        max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                        entry_snapshot=pos.entry_snapshot,
                        exit_snapshot=snap,
                    )
                )
                del positions[ticker]

        # (3) Executa ações filadas de D-1 no open[D]
        # Primeiro os Exits (liberam caixa), depois os Enters.
        exits_pending = [a for a in pending if isinstance(a, Exit)]
        enters_pending = [a for a in pending if isinstance(a, Enter)]
        pending = []

        for act in exits_pending:
            if act.ticker not in positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                # ativo não pregou hoje — reenfileira
                pending.append(act)
                continue
            pos = positions.pop(act.ticker)
            open_px = float(df.at[today, "open"])
            exec_px = apply_slippage(open_px, "sell", config.costs)
            gross = exec_px * pos.quantity
            leg_fees = fees_for_leg(gross, config.costs)
            cash += gross - leg_fees
            snap = _snapshot(df.loc[today])
            closed.append(
                Trade(
                    ticker=act.ticker,
                    strategy_name=strategy.name,
                    strategy_version=strategy.version,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    quantity=pos.quantity,
                    capital_allocated=pos.capital_allocated,
                    exit_date=today.date(),
                    exit_price=exec_px,
                    exit_reason=act.reason,
                    fees_total=pos.fees_paid + leg_fees,
                    slippage_total=pos.slippage_paid + abs(exec_px - open_px) * pos.quantity,
                    max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                    max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                    entry_snapshot=pos.entry_snapshot,
                    exit_snapshot=snap,
                )
            )

        for act in enters_pending:
            if act.ticker in positions:
                continue
            if len(positions) >= config.max_concurrent_positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                # ativo não pregou hoje — descarta (regra de rebalance discreto)
                continue
            open_px = float(df.at[today, "open"])
            exec_px = apply_slippage(open_px, "buy", config.costs)

            # Sizing: prioriza size_hint do robô; senão default (cash / slots_livres)
            if act.size_hint is not None and act.size_hint > 0:
                slot_budget = cash * float(act.size_hint)
            else:
                slots_free = max(1, config.max_concurrent_positions - len(positions))
                slot_budget = cash / slots_free
            budget = slot_budget * (1.0 - config.costs.per_side_pct - 1e-4)
            raw_qty = int(budget // (exec_px * config.lot_size)) * config.lot_size
            if raw_qty <= 0:
                continue
            gross = exec_px * raw_qty
            leg_fees = fees_for_leg(gross, config.costs)
            cost = gross + leg_fees
            if cost > cash:
                continue
            cash -= cost

            snap = _snapshot(df.loc[today])
            initial_stop = act.initial_stop
            if initial_stop is None and default_stop > 0:
                initial_stop = exec_px * (1.0 - default_stop)

            positions[act.ticker] = _Position(
                ticker=act.ticker,
                entry_date=today.date(),
                entry_price=exec_px,
                quantity=raw_qty,
                capital_allocated=cost,
                fees_paid=leg_fees,
                slippage_paid=abs(exec_px - open_px) * raw_qty,
                entry_snapshot=snap,
                max_price_seen=exec_px,
                min_price_seen=exec_px,
                current_stop=initial_stop,
                bars_held=0,
                metadata=dict(act.metadata) if act.metadata else {},
            )

        # (4) Marca equity no close[D] — usa último close conhecido se o
        # ticker tiver um gap de dado hoje (ver `last_price` acima).
        equity = cash
        for ticker, pos in positions.items():
            df = enriched.get(ticker)
            if df is not None and today in df.index:
                last_price[ticker] = float(df.at[today, "close"])
            px = last_price.get(ticker)
            if px is not None:
                equity += px * pos.quantity
        equity_records.append((today, float(equity)))
        unit_records.append((today, float(equity) / units if units > 0 else 0.0))

        # (5) Chama on_bar do robô no close de D
        actions = strategy.on_bar(today, _positions_view(positions), cash)

        # (6) Aplica AdjustStop imediatamente; fila Enter/Exit para D+1
        for act in actions:
            if isinstance(act, AdjustStop):
                pos = positions.get(act.ticker)
                if pos is None:
                    continue
                if pos.current_stop is None or act.new_stop > pos.current_stop:
                    pos.current_stop = float(act.new_stop)
            elif isinstance(act, (Enter, Exit)):
                pending.append(act)

        # (7) Incrementa bars_held
        for pos in positions.values():
            pos.bars_held += 1

        if on_progress and (i % 60 == 0 or i == len(all_dates) - 1):
            on_progress(
                {
                    "index": i,
                    "total": len(all_dates),
                    "date": today.strftime("%Y-%m-%d"),
                    "equity": float(equity),
                    "open_positions": len(positions),
                    "closed_trades": len(closed),
                }
            )

    # Fecha posições abertas ao fim da janela ao último close disponível.
    for ticker in list(positions.keys()):
        pos = positions.pop(ticker)
        df = enriched.get(ticker)
        if df is None or len(df.index) == 0:
            continue
        last_day = df.index[-1]
        close_px = float(df.at[last_day, "close"])
        exec_px = apply_slippage(close_px, "sell", config.costs)
        gross = exec_px * pos.quantity
        leg_fees = fees_for_leg(gross, config.costs)
        cash += gross - leg_fees
        snap = _snapshot(df.loc[last_day])
        closed.append(
            Trade(
                ticker=ticker,
                strategy_name=strategy.name,
                strategy_version=strategy.version,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                quantity=pos.quantity,
                capital_allocated=pos.capital_allocated,
                exit_date=last_day.date(),
                exit_price=exec_px,
                exit_reason=ExitReason.MANUAL,
                fees_total=pos.fees_paid + leg_fees,
                slippage_total=pos.slippage_paid + abs(exec_px - close_px) * pos.quantity,
                max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                entry_snapshot=pos.entry_snapshot,
                exit_snapshot=snap,
            )
        )

    equity_series = pd.Series(dict(equity_records)).sort_index()

    ibov_close = ibov_slice["close"]
    ibov_norm = ibov_close / ibov_close.iloc[0] * config.initial_capital if len(ibov_close) else ibov_close

    from backtest.metrics import (cagr, calmar, irr_annual, max_drawdown, sharpe,
                                  sortino, trade_stats)

    pnls = [t.pnl_pct for t in closed if not t.is_open]
    stats = trade_stats(pnls)

    metrics = {
        "final_capital": float(equity_series.iloc[-1]) if len(equity_series) else config.initial_capital,
        "cagr": cagr(equity_series),
        "sharpe": sharpe(equity_series),
        "sortino": sortino(equity_series),
        "max_drawdown": max_drawdown(equity_series),
        "calmar": calmar(equity_series),
        "win_rate": stats["win_rate"],
        "profit_factor": stats["profit_factor"],
        "trades_count": len(closed),
        "benchmark_cagr": cagr(ibov_norm) if len(ibov_norm) else 0.0,
    }

    # Metricas de fluxo. So aparecem quando houve aporte: sem dinheiro novo a
    # cota E a curva de patrimonio, e publicar as duas sugeriria uma distincao
    # que nao existe. Mesma regra do `engine_portfolio.py`.
    unit_series = pd.Series(dict(unit_records)).sort_index() if unit_records else None
    if contributions:
        metrics["contributed_total"] = float(sum(v for _, v in contributions))
        metrics["contributions_count"] = len(contributions)
        if unit_series is not None and len(unit_series):
            # CAGR/MaxDD da COTA: neutros a fluxo. `cagr` sobre a curva de
            # patrimonio subiria so por dinheiro novo ter entrado.
            metrics["cagr_unit"] = cagr(unit_series)
            metrics["max_drawdown_unit"] = max_drawdown(unit_series)
        if len(equity_series):
            fluxos = [(equity_series.index[0].date(), -float(config.initial_capital))]
            fluxos += [(d.date(), -float(v)) for d, v in contributions]
            fluxos.append((equity_series.index[-1].date(), float(equity_series.iloc[-1])))
            metrics["irr"] = irr_annual(fluxos)

    return BacktestResult(
        trades=closed,
        equity_curve=equity_series,
        benchmark_curve=ibov_norm,
        metrics=metrics,
        unit_curve=unit_series,
        contributions=contributions,
    )
