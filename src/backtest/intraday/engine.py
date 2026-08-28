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

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from backtest import metrics
from backtest.intraday.machine import (  # noqa: F401  (reexport: API publica historica)
    IntradayBacktestConfig,
    IntradaySessionMachine,
    IntradayTrade,
    PositionClosed,
)
from strategy.daytrade.base import (
    Bar,
    Enter,
    EnterLimit,
    IntradayStrategy,
    barra_diaria,
    capital_minimo_brl,
    mediana_negocio_diario,
)


@dataclass
class IntradayBacktestResult:
    trades: list[IntradayTrade]
    equity_curve: pd.Series
    metrics: dict
    # Timestamp em que o patrimonio (realizado + mark-to-market) chegou a
    # zero ou menos, se algum dia chegou -- `None` se a conta nunca quebrou.
    # A partir deste instante o backtest PARA de simular (ver o motivo
    # completo no comentario dentro de `run_intraday_backtest`): uma conta
    # sem margem nao consegue mandar mais nenhuma ordem depois de zerada,
    # entao continuar gerando barras/trades depois disso e' fantasia --
    # exatamente o que produzia MaxDD como -244% (impossivel: perder mais
    # de 100% do capital sem alavancagem nao existe), achado 2026-08-23
    # com R$100 de capital de teste na CLSC4 (que custa R$151/acao -- 1 lote
    # sozinho e' R$15.195, muito acima do caixa de teste).
    wiped_out_at: pd.Timestamp | None = None
    # Sessoes PULADAS por `config.enforce_capital_minimo` -- o caixa
    # disponivel na abertura nao cobria o piso do dia, entao a sessao
    # inteira roda em branco (nenhuma decisao do robo). O piso e' sempre
    # `capital_minimo_brl` (2x o lote) por padrao (`config.
    # capital_minimo_so_na_entrada=False`) -- MESMA regra do gate diario de
    # `live.intraday_runtime.IntradayLiveRuntime._check_capital` ate
    # 2026-08-24. Dai o dono pediu para o 2x so' valer na ENTRADA
    # (`live_control.start`), o gate diario ao vivo passou a exigir so' 1x
    # o lote -- e o backtest ganhou o MESMO comportamento, opt-in, via
    # `capital_minimo_so_na_entrada=True` (ver a docstring do campo em
    # `IntradayBacktestConfig`). Vazio quando `enforce_capital_minimo` esta
    # desligado (default de quem monta `IntradayBacktestConfig` na mao) ou
    # quando o caixa sempre cobriu o minimo.
    sessoes_puladas_por_capital: list = field(default_factory=list)
    # Diagnostico do teto de contratos (`IntradayBacktestConfig.
    # max_open_contracts`), copiado da maquina no fim da run. Zerados quando
    # nao ha' teto (toda acao). `ordens_recusadas_por_teto / (aceitas +
    # recusadas)` e' o portao G5 do plano da Copa: acima de 5%, a estrategia
    # esta' fazendo o motor apertar o tamanho dela o tempo todo -- o P&L
    # medido nao descreve o desenho que ela acha que tem.
    ordens_aceitas: int = 0
    ordens_recusadas_por_teto: int = 0
    # Diagnostico do teto de contratos por CAPITAL (`IntradayBacktestConfig.
    # margin_per_contract_brl`, 2026-08-28 -- ver a nota longa no campo em
    # `IntradayBacktestConfig` e em `strategy.daytrade.base.RESERVA_CAIXA_
    # SEGURANCA`), copiado da maquina no fim da run. Zerado quando o teto por
    # capital nao esta configurado. SEPARADO de `ordens_recusadas_por_teto`
    # de proposito -- sao causas diferentes de recusa (regulatoria vs caixa
    # real), e esta e' a metrica que teria denunciado o incidente de
    # 2026-08-28 ANTES de virar prejuizo real: uma segunda entrada do grid
    # que hoje abriria posicao de verdade passaria a aparecer aqui, nunca em
    # silencio.
    ordens_recusadas_por_capital: int = 0


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


#: Teto de sessoes anteriores mantidas em memoria para `seed_daily_volatility`
#: -- mesmo espirito do teto de 90min de `seed_volume_window` acima: generoso
#: o bastante para qualquer `vol_janela_dias` configurado (default 10) sem
#: guardar o historico inteiro do backtest (que pode ter anos de sessoes).
_CAUDA_DIAS_MAXIMA = 60


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
    previous_daily_bars: deque[Bar] = deque(maxlen=_CAUDA_DIAS_MAXIMA)
    # Mesmo teto/motivo de `previous_daily_bars` acima -- ver
    # `seed_typical_trade_size`/`JanelaNegocioTipicoDiaria`. Deque PARALELO
    # (nao dentro do `Bar`) porque a mediana de evento nao cabe numa barra
    # OHLCV agregada -- precisa dos eventos CRUS da sessao, que `barra_
    # diaria` ja descartou ao agregar.
    previous_daily_medianas: deque[float] = deque(maxlen=_CAUDA_DIAS_MAXIMA)
    sessoes_puladas_por_capital: list[pd.Timestamp] = []
    # Ver a docstring de `IntradayBacktestConfig.capital_minimo_so_na_entrada`.
    # Comeca `True` numa sessao RETOMADA (o robo warm-started ja esta de pe);
    # senao `False` ate a 1a sessao em que o caixa cobre o piso de ENTRADA.
    # So' importa quando `config.capital_minimo_so_na_entrada=True` -- com o
    # default (`False`), o gate abaixo usa sempre `capital_minimo_brl` (2x) e
    # esta variavel fica sem efeito.
    robo_ja_iniciado = resume_same_session
    # Declarado ANTES do loop (nao dentro): se TODA sessao for pulada por
    # `enforce_capital_minimo` (capital insuficiente o backtest inteiro), o
    # corpo do loop que normalmente atribui isto nunca roda, e o `return`
    # no fim da funcao precisa de um valor mesmo assim.
    wiped_out_at: pd.Timestamp | None = None
    for session_idx, (session_date, session_df) in enumerate(bars.groupby(bars.index.date)):
        is_resumed_session = resume_same_session and session_idx == 0

        # `enforce_capital_minimo` (2026-08-23): MESMA regra que `live.
        # intraday_runtime.IntradayLiveRuntime._check_capital` ja aplica ao
        # vivo -- se o caixa disponivel na abertura nao cobre `capital_
        # minimo_brl` no preco de hoje, o dia INTEIRO fica de fora (nenhuma
        # decisao do robo), em vez de deixar a estrategia "comprar" um lote
        # que a conta nao pagaria de verdade. Pulado na sessao RESUMIDA
        # (`resume_same_session`) pelo mesmo motivo de `on_session_start`
        # ser pulado nela: o robo ja foi calibrado/tem posicao por fora
        # (warm start), e a politica de "recusar o pregao" so' faz sentido
        # ANTES de qualquer posicao existir -- day trade nunca carrega
        # posicao entre sessoes, entao esse caso so' ocorre na 1a sessao
        # de um backtest retomado.
        if not is_resumed_session and config.enforce_capital_minimo:
            caixa_disponivel = config.initial_capital + machine.realized_pnl
            preco_abertura = float(session_df.iloc[0]["open"])
            # Ver `IntradayBacktestConfig.capital_minimo_so_na_entrada`: uma
            # vez que o robo ja iniciou, o piso vira 1x o lote de hoje (nao
            # mais 2x) -- mesma regra de `live.intraday_runtime.
            # IntradayLiveRuntime._check_capital`.
            minimo_hoje = (
                preco_abertura * config.default_quantity
                if config.capital_minimo_so_na_entrada and robo_ja_iniciado
                else capital_minimo_brl(preco_abertura, config.default_quantity)
            )
            if caixa_disponivel < minimo_hoje:
                sessoes_puladas_por_capital.append(session_df.index[0])
                session_bars_puladas = [bar_from_row(ts, row) for ts, row in session_df.iterrows()]
                for ts in session_df.index:
                    equity_index.append(ts)
                    equity_values.append(caixa_disponivel)
                previous_session_df = session_df
                daily_bar = barra_diaria(session_bars_puladas)
                if daily_bar is not None:
                    previous_daily_bars.append(daily_bar)
                mediana_dia = mediana_negocio_diario(session_bars_puladas)
                if mediana_dia is not None:
                    previous_daily_medianas.append(mediana_dia)
                continue
            robo_ja_iniciado = True
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
            # `seed_daily_volatility` recebe TODAS as sessoes anteriores ja
            # vistas neste backtest (so' anteriores -- sem look-ahead); quem
            # decide quantas usar e' a propria estrategia (`vol_janela_dias`),
            # nao o motor -- mesmo espirito de `JanelaVolatilidadeDiaria`
            # descartar sozinha o que passa de `janela_dias`.
            strategy.seed_daily_volatility(list(previous_daily_bars))
            # `seed_typical_trade_size` -- mesmo espirito de
            # `seed_daily_volatility` logo acima, so' que para o teto de
            # CAPACIDADE (`JanelaNegocioTipicoDiaria`) em vez do alvo por
            # volatilidade.
            strategy.seed_typical_trade_size(list(previous_daily_medianas))

        if is_resumed_session:
            machine.resume_session(session_date, seed_pending=seed_pending)
        else:
            machine.begin_session(session_date)

        session_bars: list[Bar] = []
        last_ts = session_df.index[-1]
        for ts, row in session_df.iterrows():
            bar = bar_from_row(ts, row)
            session_bars.append(bar)
            for event in machine.on_closed_bar(bar, is_last_bar=(ts == last_ts)):
                if isinstance(event, PositionClosed):
                    trades.append(event.trade)

            # marca patrimonio (realizado + mark-to-market da posicao aberta).
            equity_index.append(ts)
            equity_atual = config.initial_capital + machine.realized_pnl + machine.unrealized_brl(bar.close)
            equity_values.append(equity_atual)

            # Conta QUEBROU (patrimonio <= 0) -- uma conta sem margem nao
            # consegue mandar mais NENHUMA ordem depois disso (nao ha' caixa
            # para cobrir nem 1 lote), entao o backtest tem que PARAR aqui,
            # nao continuar simulando barra/trade contra dinheiro que nao
            # existe mais. Sem este freio, o dimensionamento da estrategia
            # podia continuar "comprando" com caixa negativo (piso de 1 lote
            # em `Gremah._lotes_por_realocacao`, por exemplo) e o MaxDD
            # reportado passava de -100% -- impossivel numa conta a vista,
            # e sinal de capital de teste incompativel com o preco do ativo
            # (achado 2026-08-23: CLSC4 a R$151,95 com R$100 de capital de
            # teste, 1 lote custa R$15.195).
            if equity_atual <= 0:
                wiped_out_at = ts
                break

        if on_progress is not None:
            on_progress({"session_date": session_date, "trades_so_far": len(trades),
                         "session_pnl_brl": machine.session_pnl})

        previous_session_df = session_df
        daily_bar = barra_diaria(session_bars)
        if daily_bar is not None:
            previous_daily_bars.append(daily_bar)
        mediana_dia = mediana_negocio_diario(session_bars)
        if mediana_dia is not None:
            previous_daily_medianas.append(mediana_dia)

        if wiped_out_at is not None:
            break

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
    return IntradayBacktestResult(trades=trades, equity_curve=equity_curve,
                                   metrics=result_metrics, wiped_out_at=wiped_out_at,
                                   sessoes_puladas_por_capital=sessoes_puladas_por_capital,
                                   ordens_aceitas=machine.ordens_aceitas,
                                   ordens_recusadas_por_teto=machine.ordens_recusadas_por_teto,
                                   ordens_recusadas_por_capital=machine.ordens_recusadas_por_capital)
