"""Motor de backtest INTRABAR para day trade — 4o motor de `backtest/`, ao
lado de `engine.py`/`engine_portfolio.py`/`engine_satellite.py`, so que para
outro instrumento (futuro, nao acao) e outra granularidade (M1, nao D1).

Mesma disciplina anti-look-ahead do motor diario, portada para barra: uma
acao decidida no fechamento da barra `t` executa na abertura da barra
`t+1`, nunca na propria barra `t`. Mesma prioridade do motor diario tambem:
stop/target automatico do motor tem prioridade sobre qualquer acao filada
pelo robo.

Diferencas estruturais que o day trade exige e o motor diario nao tem:
- Multiplas entradas/saidas por SESSAO (o diario decide 1x por pregao).
- Flatten forcado no fim da sessao — day trade nunca carrega posicao
  overnight; isto nao e uma regra da estrategia, e do motor (nenhuma
  estrategia pode escolher nao flatten).
- `AdjustTarget` alem de `AdjustStop` (o diario nao tem alvo).

A partir de 2026-08-21 este arquivo e' um DRIVER FINO: toda a maquina de
estados por barra vive em `backtest/intraday/machine.py::
IntradaySessionMachine`, compartilhada com a operacao ao vivo
(`live/intraday_runtime.py`) — ver a docstring de `machine.py` para o
porque. O que sobra aqui e' o que so o backtest faz: agrupar um DataFrame
em sessoes, acumular trades, montar a curva de patrimonio e calcular
metricas.

Dependencia direcional em `strategy.daytrade.base` (Bar/acoes/ABC) mirroria
a excessao ja existente em `backtest/engine.py` (que importa `strategy.
base`): quem executa depende do contrato de quem decide.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from backtest import metrics
from backtest.intraday.machine import (  # noqa: F401  (reexport: API publica historica)
    IntradayBacktestConfig,
    IntradaySessionMachine,
    IntradayTrade,
    PositionClosed,
)
from strategy.daytrade.base import Bar, Enter, EnterLimit, IntradayStrategy


@dataclass
class IntradayBacktestResult:
    trades: list[IntradayTrade]
    equity_curve: pd.Series
    metrics: dict


def _bar_volume(row: pd.Series) -> float:
    """MT5 nao devolve coluna `volume` — devolve `real_volume` (volume
    negociado real, nem sempre populado pela corretora) e `tick_volume`
    (contagem de variacoes de preco, sempre presente). Prefere
    `real_volume` quando ele for genuinamente reportado (> 0); cai para
    `tick_volume` senao. `row.get("volume", 0.0)` sozinho zeraria em
    silencio para todo dado real vindo de `mt5_source.py`."""
    real = row.get("real_volume", 0.0)
    if real and real > 0:
        return float(real)
    return float(row.get("tick_volume", row.get("volume", 0.0)))


def bar_from_row(ts: pd.Timestamp, row: pd.Series) -> Bar:
    """Uma linha de DataFrame OHLCV vira `Bar`. Compartilhado com o feed ao
    vivo (`live/bar_feed.py`) para os dois lerem `real_volume`/`tick_volume`
    do MT5 pela MESMA regra — ver `_bar_volume`."""
    return Bar(ts=ts, open=float(row["open"]), high=float(row["high"]),
               low=float(row["low"]), close=float(row["close"]), volume=_bar_volume(row))


def run_intraday_backtest(
    bars: pd.DataFrame,
    strategy: IntradayStrategy,
    config: IntradayBacktestConfig,
    on_progress: Optional[Callable[[dict], None]] = None,
    resume_same_session: bool = False,
    seed_pending: Enter | EnterLimit | None = None,
) -> IntradayBacktestResult:
    """`bars`: OHLCV M1 de UM simbolo, index = timestamp de fechamento da
    barra, pode abranger muitas sessoes. Agrupado por sessao (dia
    calendario) internamente.

    `resume_same_session=True`: nao chama `strategy.on_session_start(...)`
    para a PRIMEIRA sessao encontrada em `bars` — usar quando o robo ja foi
    calibrado para essa sessao por fora (ex.: `warm_start_calibration`,
    ao ligar ao vivo no meio do pregao) e chamar de novo apagaria o
    estado que acabou de ser montado. Sessoes seguintes (se `bars`
    abranger mais de um dia) continuam chamando normalmente.

    `seed_pending`: ordem (`Enter`/`EnterLimit`) ja decidida ANTES da
    primeira barra deste `bars` (tipicamente o retorno de
    `warm_start_calibration`) — passa a ser vigiada desde a PRIMEIRA
    barra, em vez de precisar de uma barra extra de decisao. So faz
    sentido junto de `resume_same_session=True`."""
    strategy.initialize(bars)

    machine = IntradaySessionMachine(strategy, config)
    trades: list[IntradayTrade] = []
    equity_index: list[pd.Timestamp] = []
    equity_values: list[float] = []

    previous_session_df: pd.DataFrame | None = None
    for session_idx, (session_date, session_df) in enumerate(bars.groupby(bars.index.date)):
        is_resumed_session = resume_same_session and session_idx == 0
        # `seed_volume_window` (RollingVolumeWindow) precisa da CAUDA do
        # pregao anterior para completar a janela de volume rolante logo na
        # abertura -- pulado para a sessao RESUMIDA porque ela ja foi
        # calibrada por fora (mesmo motivo de pular `on_session_start`
        # abaixo). `bars` ja carrega tudo em memoria (`strategy.initialize`
        # acima recebeu o mesmo dataframe): so' precisamos do TRECHO final
        # da sessao anterior, nao dela inteira -- 90min de folga sobre a
        # janela default de 30min do robo, generico o bastante para
        # qualquer janela configurada sem carregar o dia inteiro.
        if not is_resumed_session:
            tail_bars: list[Bar] = []
            if previous_session_df is not None and not previous_session_df.empty:
                corte = previous_session_df.index[-1] - pd.Timedelta(minutes=90)
                tail_df = previous_session_df[previous_session_df.index > corte]
                tail_bars = [bar_from_row(ts, row) for ts, row in tail_df.iterrows()]
            strategy.seed_volume_window(tail_bars)

        if is_resumed_session:
            machine.resume_session(session_date, seed_pending=seed_pending)
        else:
            machine.begin_session(session_date)

        last_ts = session_df.index[-1]
        for ts, row in session_df.iterrows():
            bar = bar_from_row(ts, row)
            for event in machine.on_closed_bar(bar, is_last_bar=(ts == last_ts)):
                if isinstance(event, PositionClosed):
                    trades.append(event.trade)

            # marca patrimonio (realizado + mark-to-market da posicao aberta).
            equity_index.append(ts)
            equity_values.append(
                config.initial_capital + machine.realized_pnl + machine.unrealized_brl(bar.close)
            )

        if on_progress is not None:
            on_progress({"session_date": session_date, "trades_so_far": len(trades),
                         "session_pnl_brl": machine.session_pnl})

        previous_session_df = session_df

    equity_curve = pd.Series(equity_values, index=pd.DatetimeIndex(equity_index), name="equity")
    pnl_pcts = [t.pnl_pct for t in trades]
    result_metrics = {
        # `period_return`, nao `cagr` puro: o split IS/OOS deste motor roda
        # em janelas de semanas/meses, nunca de anos -- anualizar isso
        # amplifica o retorno em vez de estima-lo (ver a docstring de
        # `metrics.period_return`). A chave continua "cagr" (nao muda o
        # contrato de quem le `result.metrics`), so' o CALCULO troca quando
        # o periodo e' curto demais pra anualizar de verdade.
        "cagr": metrics.period_return(equity_curve),
        "max_drawdown": metrics.max_drawdown(equity_curve),
        "calmar": metrics.calmar(equity_curve, min_years_to_annualize=1.0),
        **metrics.trade_stats(pnl_pcts),
        "n_trades": len(trades),
    }
    return IntradayBacktestResult(trades=trades, equity_curve=equity_curve, metrics=result_metrics)
