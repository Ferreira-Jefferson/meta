"""Engine de portfolio com satelites acumulativos e saida por momentum.

Satelites acumulam a cada rotacao (5% do capital no ativo anterior).
Saida do satelite: score < 0 (momentum negativo) OU valor < 20% do ref.

Modos de redistribuicao ao fechar satelite:
  'main'    - Teste 1: vai para a posicao principal atual
  'pool'    - Teste 2: vai para o caixa geral (proximo rebalance)
  'best_sat'- Teste 3: vai para o satelite com maior valor atual
  'confirm' - Teste 4: igual a 'pool' mas com sinal confirmado (2 meses)
              (controlado por strategy.signal_confirm_months=2)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import pandas as pd

from backtest.costs import apply_slippage, cash_yield_series, fees_for_leg
from backtest.engine import BacktestResult, _Position, _enrich, _snapshot
from backtest.metrics import cagr, calmar, max_drawdown, sharpe, sortino, trade_stats
from backtest.sizing import has_free_slot, initial_stop, liquidation_quantity, plan_entry
from backtest.withdrawal import WithdrawalEvent, WithdrawalPolicy
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason, Trade
from strategy.base import AdjustStop, Enter, Exit, OpenPosition, Strategy


@dataclass
class _Sat:
    ticker: str
    entry_date: object
    entry_price: float
    quantity: int
    ref_value: float
    fees_paid: float = 0.0
    slippage_paid: float = 0.0
    max_price_seen: float = 0.0
    min_price_seen: float = 0.0


RedistMode = Literal["main", "pool", "best_sat"]
EntryFillMode = Literal["open"]


def _positions_view(positions: dict[str, _Position]) -> dict[str, OpenPosition]:
    return {
        t: OpenPosition(
            ticker=p.ticker, entry_date=pd.Timestamp(p.entry_date),
            entry_price=p.entry_price, quantity=p.quantity,
            current_stop=p.current_stop, bars_held=p.bars_held,
            metadata=dict(p.metadata),
        )
        for t, p in positions.items()
    }


def run_portfolio_backtest(
    universe: dict[str, pd.DataFrame],
    strategy,                          # PortfolioHysteresis
    config: BacktestConfig,
    start: str,
    end: str,
    satellite_pct: float = 0.05,
    satellite_stop_pct: float = 0.20,
    redist_mode: RedistMode = "pool",
    on_progress: Optional[Callable] = None,
    withdrawal_policy: Optional[WithdrawalPolicy] = None,
    entry_fill_mode: EntryFillMode = "open",
) -> BacktestResult:
    ibov = universe[BENCHMARK]
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    raw_panels = {t: df for t, df in universe.items() if t != BENCHMARK}
    strategy.initialize(raw_panels, ibov)

    enriched: dict[str, pd.DataFrame] = {}
    for ticker, df_full in raw_panels.items():
        e = _enrich(df_full, ibov)
        mask = (e.index >= start_ts) & (e.index <= end_ts)
        enriched[ticker] = e.loc[mask]

    all_dates = pd.DatetimeIndex(sorted({d for df in enriched.values() for d in df.index}))
    ibov_slice = ibov.loc[(ibov.index >= start_ts) & (ibov.index <= end_ts)]

    cash = config.initial_capital
    positions: dict[str, _Position] = {}
    satellites: dict[str, _Sat] = {}
    closed: list[Trade] = []
    equity_records = []
    pending: list = []
    last_sat_check_month = None
    # Contadores dos modos != 'open' — quantos sinais de Enter chegaram a
    # ponto de executar vs quantos de fato preencheram a ordem. So vao para
    # `metrics` quando o modo nao e o default (ver bloco de metrics no fim),
    # para o modo padrao continuar byte-a-byte identico ao de antes desta opcao.
    entries_attempted = 0
    entries_filled = 0
    # Saque programado: decidido no close[D] pela politica, executado no
    # open[D+1] (mesma disciplina anti-look-ahead das ordens).
    withdrawals: list[WithdrawalEvent] = []
    pending_withdraw = 0.0
    pending_withdraw_equity = 0.0
    # Último close conhecido por ticker — só para marcação de equity (ver
    # `engine.py`). Não usado nas decisões de trading (`_price` continua
    # exigindo cotação real do dia para entrar/sair/disparar stop); um gap
    # de 1 dia num único ticker do universo não pode fazer a posição sumir
    # do equity e criar um drawdown fantasma.
    last_mark_price: dict[str, float] = {}

    def _price(ticker, date, col="close"):
        df = enriched.get(ticker)
        return float(df.at[date, col]) if (df is not None and date in df.index) else None

    def _equity_marked(date, col="close") -> float:
        """Equity marcado numa coluna especifica (ex. 'open', para decidir no open[D]).

        Usa o ultimo preco conhecido quando o ticker tem gap de dado no dia —
        mesma protecao contra drawdown fantasma da marcacao oficial de equity.
        """
        total = cash
        for t, p in list(positions.items()) + [(k, v) for k, v in satellites.items()]:
            px = _price(t, date, col) or _price(t, date) or last_mark_price.get(t, 0.0)
            total += px * p.quantity
        return float(total)

    def _sat_value(ticker, date):
        sat = satellites.get(ticker)
        if sat is None:
            return 0.0
        px = _price(ticker, date)
        return sat.quantity * px if px else 0.0

    def _close_satellite(ticker, price, today, reason) -> float:
        """Fecha satelite, retorna o valor liquido recebido."""
        nonlocal cash
        sat = satellites.pop(ticker)
        exec_px = apply_slippage(price, "sell", config.costs)
        gross = exec_px * sat.quantity
        leg_fees = fees_for_leg(gross, config.costs)
        net = gross - leg_fees
        df = enriched.get(ticker)
        snap = _snapshot(df.loc[today]) if (df is not None and today in df.index) else _snapshot(pd.Series(dtype=float))
        closed.append(Trade(
            ticker=ticker, strategy_name=strategy.name + "_sat",
            strategy_version=strategy.version,
            entry_date=sat.entry_date, entry_price=sat.entry_price,
            quantity=sat.quantity, capital_allocated=sat.ref_value,
            exit_date=today.date(), exit_price=exec_px, exit_reason=reason,
            fees_total=sat.fees_paid + leg_fees,
            slippage_total=sat.slippage_paid + abs(exec_px - price) * sat.quantity,
            max_favorable_excursion=(sat.max_price_seen - sat.entry_price) / sat.entry_price,
            max_adverse_excursion=(sat.min_price_seen - sat.entry_price) / sat.entry_price,
            entry_snapshot=None, exit_snapshot=snap,
        ))
        return net

    def _redistribute(net: float, today, source_ticker: str):
        """Direciona o dinheiro do satelite fechado conforme o modo."""
        nonlocal cash
        if redist_mode == "pool" or not positions:
            cash += net
            return

        if redist_mode == "main":
            # Adiciona ao caixa para reforcar a posicao principal no proximo rebalance
            # (compra imediata nao e possivel — execucao D+1; vai para caixa mesmo)
            cash += net
            return

        if redist_mode == "best_sat":
            # Vai para o satelite com maior valor atual (excluindo o que acabou de sair)
            best = max(
                ((t, _sat_value(t, today)) for t in satellites if t != source_ticker),
                key=lambda x: x[1], default=None
            )
            if best is None or best[1] == 0:
                cash += net
                return
            # Converte net em cotas do melhor satelite
            best_ticker = best[0]
            px = _price(best_ticker, today, "close")
            if px is None or px <= 0:
                cash += net
                return
            extra_qty = int(net // px)
            if extra_qty > 0:
                exec_px = apply_slippage(px, "buy", config.costs)
                cost = exec_px * extra_qty + fees_for_leg(exec_px * extra_qty, config.costs)
                if cost <= net:
                    sat = satellites[best_ticker]
                    sat.quantity += extra_qty
                    sat.ref_value += cost
                    cash += net - cost
                else:
                    cash += net
            else:
                cash += net

    def _execute_withdrawal(today, want: float, equity_before: float) -> None:
        """Retira `want` do sistema no open[D]: caixa primeiro, depois liquida posicao.

        Liquida a MAIOR posicao principal primeiro (satelites, quando existem,
        sao residuais por desenho e ficam de fora). Vende so o necessario, com
        slippage e taxas normais — sacar custa dinheiro. Se nem liquidando tudo
        da, o evento registra o `shortfall` em vez de inventar caixa.
        """
        nonlocal cash
        fees_paid = 0.0
        liquidated: list[tuple[str, int, float]] = []
        need = want - cash

        if need > 0 and positions:
            by_value = sorted(
                ((t, (_price(t, today, "open") or 0.0) * positions[t].quantity) for t in positions),
                key=lambda kv: kv[1], reverse=True,
            )
            for ticker, _val in by_value:
                if need <= 1e-9:
                    break
                pos = positions.get(ticker)
                opn = _price(ticker, today, "open")
                if pos is None or not opn:
                    continue
                exec_px = apply_slippage(opn, "sell", config.costs)
                qty = liquidation_quantity(need, exec_px, pos.quantity, config)
                if qty <= 0:
                    continue
                gross = exec_px * qty
                leg_fees = fees_for_leg(gross, config.costs)
                net = gross - leg_fees
                cash += net
                fees_paid += leg_fees
                need -= net
                liquidated.append((ticker, qty, exec_px))

                frac_out = qty / pos.quantity
                if qty >= pos.quantity:
                    # posicao zerada para pagar o saque — registra o trade
                    df = enriched.get(ticker)
                    snap = (_snapshot(df.loc[today]) if (df is not None and today in df.index)
                            else _snapshot(pd.Series(dtype=float)))
                    closed.append(Trade(
                        ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                        entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=qty,
                        capital_allocated=pos.capital_allocated, exit_date=today.date(),
                        exit_price=exec_px, exit_reason=ExitReason.WITHDRAWAL,
                        fees_total=pos.fees_paid + leg_fees,
                        slippage_total=pos.slippage_paid + abs(exec_px - opn) * qty,
                        max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                        max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                        entry_snapshot=pos.entry_snapshot, exit_snapshot=snap,
                    ))
                    del positions[ticker]
                else:
                    # venda parcial: encolhe a posicao proporcionalmente. Nao gera
                    # Trade (o trade original segue aberto) — a auditoria da venda
                    # fica no WithdrawalEvent.
                    pos.quantity -= qty
                    pos.capital_allocated *= (1.0 - frac_out)
                    pos.fees_paid *= (1.0 - frac_out)
                    pos.slippage_paid *= (1.0 - frac_out)

        executed = max(0.0, min(want, cash))
        cash -= executed
        withdrawals.append(WithdrawalEvent(
            date=today, requested=want, executed=executed,
            equity_before=equity_before, fees_paid=fees_paid, liquidated=liquidated,
        ))
        if withdrawal_policy is not None:
            withdrawal_policy.on_executed(today, executed)

    cash_yield = cash_yield_series(config.cash_yield_path, all_dates)

    for i, today in enumerate(all_dates):
        # Remuneracao do caixa ANTES de qualquer execucao do dia: o dinheiro que
        # amanheceu parado rende; o que vai ser gasto hoje rendeu enquanto
        # estava parado. Desligado por default (`cash_yield_path=None`).
        if cash_yield is not None and cash > 0.0:
            cash *= 1.0 + float(cash_yield.iat[i])

        # MFE/MAE
        for t, pos in positions.items():
            px = _price(t, today)
            if px:
                pos.max_price_seen = max(pos.max_price_seen, px)
                pos.min_price_seen = min(pos.min_price_seen, px)
        for t, sat in satellites.items():
            px = _price(t, today)
            if px:
                sat.max_price_seen = max(sat.max_price_seen, px)
                sat.min_price_seen = min(sat.min_price_seen, px)

        # Motivo da ultima venda que creditou caixa hoje (None = nada vendido).
        # Alimenta o gancho de saque por evento de liquidez, mais abaixo.
        # Satelites, quando existem, sao residuais por desenho e nao disparam.
        liquidity_reason: str | None = None

        # Stop principal
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            if pos.current_stop is None:
                continue
            low = _price(ticker, today, "low")
            opn = _price(ticker, today, "open")
            if low is None or low > pos.current_stop:
                continue
            exec_ref = min(opn, pos.current_stop)
            exec_px = apply_slippage(exec_ref, "sell", config.costs)
            gross = exec_px * pos.quantity
            leg_fees = fees_for_leg(gross, config.costs)
            cash += gross - leg_fees
            df = enriched.get(ticker)
            snap = _snapshot(df.loc[today]) if (df is not None and today in df.index) else _snapshot(pd.Series(dtype=float))
            closed.append(Trade(
                ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                capital_allocated=pos.capital_allocated, exit_date=today.date(),
                exit_price=exec_px, exit_reason=ExitReason.STOP,
                fees_total=pos.fees_paid + leg_fees,
                slippage_total=pos.slippage_paid + abs(exec_px - exec_ref) * pos.quantity,
                max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                entry_snapshot=pos.entry_snapshot, exit_snapshot=snap,
            ))
            del positions[ticker]
            liquidity_reason = ExitReason.STOP.value

        # Saque programado no close de ontem — sai antes de qualquer compra de
        # hoje, para a entrada ser dimensionada pelo caixa JA descontado.
        if pending_withdraw > 0.0:
            want, eq_before = pending_withdraw, pending_withdraw_equity
            pending_withdraw = 0.0
            _execute_withdrawal(today, want, eq_before)

        # Check mensal de satelites
        month_key = (today.year, today.month)
        if month_key != last_sat_check_month:
            last_sat_check_month = month_key
            for ticker in list(satellites.keys()):
                px = _price(ticker, today)
                if px is None:
                    continue
                sat = satellites[ticker]
                curr_val = sat.quantity * px
                # Sinal de saida: momentum negativo OU stop de valor
                neg_signal = strategy.satellite_exit_signal(ticker, today)
                stop_hit = curr_val < satellite_stop_pct * sat.ref_value
                if neg_signal or stop_hit:
                    reason = ExitReason.ROTATION_OUT if neg_signal else ExitReason.STOP
                    net = _close_satellite(ticker, px, today, reason)
                    _redistribute(net, today, ticker)

        # Executa acoes filadas
        exits_p = [a for a in pending if isinstance(a, Exit)]
        enters_p = [a for a in pending if isinstance(a, Enter)]
        pending = []

        for act in exits_p:
            if act.ticker not in positions:
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                # Ticker sem dado hoje: DESCARTA, nunca reenfileira. Reenfileirar
                # faria uma saida decidida no close[D] executar em D+2, D+3... se
                # o ticker tiver um gap — exatamente o "executar tarde" que a
                # regra 7 do AGENTS.md proibe (decisao atrasada nunca executa
                # tarde), e quebra o contrato "close[D] -> open[D+1], nunca outro
                # dia" da regra 4. Simetrico ao laco `enters_p` logo abaixo, que
                # ja descarta (nao reenfileira) quando o ticker nao tem dado.
                # Seguro por desenho: a familia BuyTheDip reavalia o alvo de
                # rotacao TODO mes (`on_bar` roda no month-end e recalcula `tgt`
                # do zero a partir de `_scores`/`_dist_from_high`) — uma saida
                # descartada por falta de dado simplesmente sera re-decidida (ou
                # nao) no proximo rebalance mensal, nao fica presa em limbo.
                continue

            pos = positions.pop(act.ticker)
            opn = float(df.at[today, "open"])

            if act.reason == ExitReason.ROTATION_OUT:
                liquidity_reason = ExitReason.ROTATION_OUT.value  # gatilho de saque
                # 95% sai, 5% vira satelite
                total_qty = pos.quantity
                sat_qty = max(0, int(total_qty * satellite_pct))
                sell_qty = total_qty - sat_qty

                if sell_qty > 0:
                    exec_px = apply_slippage(opn, "sell", config.costs)
                    gross = exec_px * sell_qty
                    leg_fees = fees_for_leg(gross, config.costs)
                    cash += gross - leg_fees
                    closed.append(Trade(
                        ticker=act.ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                        entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=sell_qty,
                        capital_allocated=pos.capital_allocated * (sell_qty / total_qty),
                        exit_date=today.date(), exit_price=exec_px, exit_reason=act.reason,
                        fees_total=pos.fees_paid * (sell_qty / total_qty) + leg_fees,
                        slippage_total=pos.slippage_paid * (sell_qty / total_qty) + abs(exec_px - opn) * sell_qty,
                        max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                        max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                        entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[today]),
                    ))

                if sat_qty > 0:
                    ref_val = sat_qty * opn
                    if act.ticker in satellites:
                        old = satellites[act.ticker]
                        satellites[act.ticker] = _Sat(
                            ticker=act.ticker, entry_date=today.date(), entry_price=opn,
                            quantity=old.quantity + sat_qty, ref_value=old.ref_value + ref_val,
                            max_price_seen=opn, min_price_seen=opn,
                        )
                    else:
                        satellites[act.ticker] = _Sat(
                            ticker=act.ticker, entry_date=today.date(), entry_price=opn,
                            quantity=sat_qty, ref_value=ref_val,
                            max_price_seen=opn, min_price_seen=opn,
                        )
            else:
                # Saida total (Selic defensive etc) — tambem credita caixa
                liquidity_reason = getattr(act.reason, "value", str(act.reason))
                exec_px = apply_slippage(opn, "sell", config.costs)
                gross = exec_px * pos.quantity
                leg_fees = fees_for_leg(gross, config.costs)
                cash += gross - leg_fees
                closed.append(Trade(
                    ticker=act.ticker, strategy_name=strategy.name, strategy_version=strategy.version,
                    entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
                    capital_allocated=pos.capital_allocated, exit_date=today.date(),
                    exit_price=exec_px, exit_reason=act.reason,
                    fees_total=pos.fees_paid + leg_fees,
                    slippage_total=pos.slippage_paid + abs(exec_px - opn) * pos.quantity,
                    max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
                    max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
                    entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[today]),
                ))
                if act.reason == ExitReason.IBOV_DEFENSIVE:
                    for st in list(satellites.keys()):
                        sp = _price(st, today, "open") or satellites[st].entry_price
                        net = _close_satellite(st, sp, today, ExitReason.IBOV_DEFENSIVE)
                        cash += net  # em modo defensivo sempre vai pro caixa

        # Saque em EVENTO DE LIQUIDEZ: alguma venda de hoje (rotacao, stop ou
        # saida defensiva) acabou de creditar caixa no open e nada foi comprado
        # ainda — o dinheiro esta liquido na mao, entao o saque nao paga
        # corretagem nem slippage extra. Sai aqui, antes das compras, para a
        # entrada ser dimensionada pelo que sobrou.
        if withdrawal_policy is not None and liquidity_reason is not None:
            eq_open = _equity_marked(today, "open")
            due = float(withdrawal_policy.on_liquidity_event(today, eq_open, liquidity_reason))
            if due > 0.0:
                _execute_withdrawal(today, due, eq_open)

        for act in enters_p:
            if act.ticker in positions:
                continue
            if not has_free_slot(len(positions), config):
                continue
            df = enriched.get(act.ticker)
            if df is None or today not in df.index:
                continue

            entries_attempted += 1

            # Consolida satelite do mesmo ticker de volta ao caixa
            if act.ticker in satellites:
                sat = satellites[act.ticker]
                sp = _price(act.ticker, today, "open") or sat.entry_price
                exec_px_s = apply_slippage(sp, "sell", config.costs)
                gross_s = exec_px_s * sat.quantity
                leg_s = fees_for_leg(gross_s, config.costs)
                cash += gross_s - leg_s
                del satellites[act.ticker]

            opn = float(df.at[today, "open"])
            ref_price = opn
            # Sizing, stop default e teto de slots vivem em `backtest/sizing.py`
            # para o runtime ao vivo chamar a MESMA mecanica — ver o docstring
            # de la: e o unico jeito de a carteira real nao divergir da testada.
            plan = plan_entry(cash, ref_price, act.size_hint, config)
            if not plan.is_feasible:
                continue
            # So conta como "preenchida" a entrada que de fato virou posicao —
            # incrementar antes do teste de viabilidade fazia `entries_skipped`
            # (`entries_attempted - entries_filled`) nunca poder ser > 0.
            entries_filled += 1
            exec_px = plan.exec_price
            cash -= plan.cost

            snap = _snapshot(df.loc[today])
            stop_px = initial_stop(exec_px, act.initial_stop, config)

            positions[act.ticker] = _Position(
                ticker=act.ticker, entry_date=today.date(), entry_price=exec_px,
                quantity=plan.quantity, capital_allocated=plan.cost, fees_paid=plan.fees,
                slippage_paid=abs(exec_px - ref_price) * plan.quantity,
                entry_snapshot=snap, max_price_seen=exec_px, min_price_seen=exec_px,
                current_stop=stop_px, bars_held=0, metadata={},
            )

        # Equity — usa último close conhecido se o ticker tiver gap de dado hoje.
        equity = cash
        for t, pos in positions.items():
            px = _price(t, today)
            if px:
                last_mark_price[t] = px
            equity += last_mark_price.get(t, 0.0) * pos.quantity
        for t, sat in satellites.items():
            px = _price(t, today)
            if px:
                last_mark_price[t] = px
            equity += last_mark_price.get(t, 0.0) * sat.quantity
        equity_records.append((today, float(equity)))

        # Politica de saque decide no close — executa no open de amanha.
        # `invested` = quanto esta a mercado (equity - caixa); 0 significa robo
        # fora do mercado, o que algumas politicas tratam de forma diferente.
        if withdrawal_policy is not None:
            amount = float(withdrawal_policy.on_close(today, float(equity),
                                                      max(0.0, float(equity) - cash)))
            if amount > 0.0:
                pending_withdraw += amount
                pending_withdraw_equity = float(equity)

        # on_bar so ve posicao principal
        actions = strategy.on_bar(today, _positions_view(positions), cash)
        for act in actions:
            if isinstance(act, AdjustStop):
                pos = positions.get(act.ticker)
                if pos and (pos.current_stop is None or act.new_stop > pos.current_stop):
                    pos.current_stop = float(act.new_stop)
            elif isinstance(act, (Enter, Exit)):
                pending.append(act)
        for pos in positions.values():
            pos.bars_held += 1

        if on_progress and (i % 60 == 0 or i == len(all_dates) - 1):
            on_progress({"date": today.strftime("%Y-%m-%d"), "equity": float(equity),
                         "positions": len(positions), "satellites": len(satellites)})

    # Fecha tudo no fim
    for ticker in list(positions.keys()):
        pos = positions.pop(ticker)
        df = enriched.get(ticker)
        if df is None or not len(df.index):
            continue
        last_day = df.index[-1]
        px = float(df.at[last_day, "close"])
        exec_px = apply_slippage(px, "sell", config.costs)
        gross = exec_px * pos.quantity
        leg_fees = fees_for_leg(gross, config.costs)
        cash += gross - leg_fees
        closed.append(Trade(
            ticker=ticker, strategy_name=strategy.name, strategy_version=strategy.version,
            entry_date=pos.entry_date, entry_price=pos.entry_price, quantity=pos.quantity,
            capital_allocated=pos.capital_allocated, exit_date=last_day.date(),
            exit_price=exec_px, exit_reason=ExitReason.MANUAL,
            fees_total=pos.fees_paid + leg_fees,
            slippage_total=pos.slippage_paid + abs(exec_px - px) * pos.quantity,
            max_favorable_excursion=(pos.max_price_seen - pos.entry_price) / pos.entry_price,
            max_adverse_excursion=(pos.min_price_seen - pos.entry_price) / pos.entry_price,
            entry_snapshot=pos.entry_snapshot, exit_snapshot=_snapshot(df.loc[last_day]),
        ))

    for ticker in list(satellites.keys()):
        df = enriched.get(ticker)
        if df is None or not len(df.index):
            continue
        last_day = df.index[-1]
        px = float(df.at[last_day, "close"])
        net = _close_satellite(ticker, px, last_day, ExitReason.MANUAL)
        cash += net

    equity_series = pd.Series(dict(equity_records)).sort_index()
    ibov_close = ibov_slice["close"]
    ibov_norm = ibov_close / ibov_close.iloc[0] * config.initial_capital if len(ibov_close) else ibov_close
    pnls = [t.pnl_pct for t in closed if not t.is_open]
    stats = trade_stats(pnls)
    metrics = {
        "final_capital": float(equity_series.iloc[-1]) if len(equity_series) else config.initial_capital,
        "cagr": cagr(equity_series), "sharpe": sharpe(equity_series),
        "sortino": sortino(equity_series), "max_drawdown": max_drawdown(equity_series),
        "calmar": calmar(equity_series),
        "win_rate": stats["win_rate"], "profit_factor": stats["profit_factor"],
        "trades_count": len(closed),
        "benchmark_cagr": cagr(ibov_norm) if len(ibov_norm) else 0.0,
    }
    if withdrawals:
        metrics["withdrawn_total"] = float(sum(w.executed for w in withdrawals))
        metrics["withdrawals_count"] = len(withdrawals)
        metrics["withdrawal_fees"] = float(sum(w.fees_paid for w in withdrawals))
    if entry_fill_mode != "open":
        # So aparece fora do modo default — o modo 'open' tem de devolver o
        # mesmo dict de sempre, byte-a-byte, para nao quebrar quem ja consome
        # `metrics` hoje.
        metrics["entries_attempted"] = entries_attempted
        metrics["entries_filled"] = entries_filled
        metrics["entries_skipped"] = entries_attempted - entries_filled
    return BacktestResult(trades=closed, equity_curve=equity_series,
                          benchmark_curve=ibov_norm, metrics=metrics,
                          withdrawals=withdrawals)
