"""Testes do motor intrabar (`backtest/intraday/engine.py`): execucao na
abertura da PROXIMA barra (anti-look-ahead), stop/target tocado dentro da
barra (com e sem gap), resolucao de barra ambigua, flatten forcado no fim
da sessao (e descarte de pendencia), multiplos trades por sessao, nao
carregar posicao entre sessoes, lado short, e o contrato explicito com
`backtest.metrics.trade_stats`."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from backtest.metrics import trade_stats
from core.models import IntradayExitReason
from strategy.daytrade.base import Enter, EnterLimit, Exit, IntradayStrategy


class _StubIntradayStrategy(IntradayStrategy):
    name = "stub_intraday"
    version = "0.1"
    # `IntradayStrategy.symbol` nao tem mais default (era `"WIN@"`), porque um
    # default herdado ali e' um robo operando o ativo errado em silencio.
    symbol = "STUB3"

    def __init__(self, actions_by_ts: dict[pd.Timestamp, list] | None = None):
        self.actions_by_ts = actions_by_ts or {}

    def on_bar(self, ts, bar, position, session_pnl_brl):
        return self.actions_by_ts.get(ts, [])


def _mk_bars(session_date: str, rows: list[tuple[float, float, float, float]],
             start: str = "09:00", freq: str = "1min") -> pd.DataFrame:
    idx = pd.date_range(f"{session_date} {start}", periods=len(rows), freq=freq, tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["tick_volume"] = 10
    return df


def _config(**overrides) -> IntradayBacktestConfig:
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=1.0, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    defaults = dict(costs=costs, initial_capital=10_000.0, default_quantity=1, session_end_time=time(23, 59))
    defaults.update(overrides)
    return IntradayBacktestConfig(**defaults)


def test_entrada_executa_na_abertura_da_proxima_barra():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (105, 106, 104, 105),
        (110, 111, 109, 110),
        (112, 113, 111, 112),
        (112, 113, 111, 112),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[1]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(105.0)  # aberto na barra 1, nao na 0
    assert trade.exit_price == pytest.approx(110.0)   # aberto na barra 2, nao na 1
    assert trade.exit_reason == IntradayExitReason.SIGNAL
    assert trade.pnl_brl > 0


def test_stop_dispara_no_nivel_quando_a_barra_nao_abre_alem_dele():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 100, 94, 97),   # low=94 toca stop=95, open=100 nao gapeou alem dele
        (97, 98, 96, 97),
        (97, 98, 96, 97),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=95.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(95.0)
    assert trade.exit_reason == IntradayExitReason.STOP


def test_stop_dispara_no_open_quando_a_barra_abre_alem_dele_gap():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (90, 91, 88, 89),   # gap para baixo, abre JA alem do stop=95
        (89, 90, 88, 89),
        (89, 90, 88, 89),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=95.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.exit_price == pytest.approx(90.0)
    assert trade.exit_reason == IntradayExitReason.STOP


def test_target_dispara_no_nivel_quando_a_barra_nao_abre_alem_dele():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 112, 99, 105),  # high=112 toca target=110, open=100 nao gapeou alem dele
        (105, 106, 104, 105),
        (105, 106, 104, 105),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=50.0, initial_target=110.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.exit_price == pytest.approx(110.0)
    assert trade.exit_reason == IntradayExitReason.TARGET


@pytest.mark.parametrize(
    "resolution,expected_reason,expected_price",
    [
        ("stop_first", IntradayExitReason.STOP, 95.0),
        ("target_first", IntradayExitReason.TARGET, 105.0),
    ],
)
def test_barra_ambigua_resolvida_pela_config(resolution, expected_reason, expected_price):
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 106, 94, 100),  # toca stop=95 E target=105 na MESMA barra
        (100, 101, 99, 100),
        (100, 101, 99, 100),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long", initial_stop=95.0, initial_target=105.0)]})
    result = run_intraday_backtest(bars, strat, _config(ambiguous_bar_resolution=resolution))

    trade = result.trades[0]
    assert trade.exit_reason == expected_reason
    assert trade.exit_price == pytest.approx(expected_price)


def test_flatten_forcado_por_horario_fecha_posicao_e_descarta_pendencia():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),  # 09:00 idx0: Enter
        (100, 101, 99, 100),  # 09:01: executa Enter no open; sem acao nova
        (100, 101, 99, 100),  # 09:02: decide Exit (pendente p/ 09:03 -- a barra de corte)
        (100, 101, 99, 90),   # 09:03: cutoff bate AQUI -> flatten no CLOSE, pendencia descartada
        (100, 101, 99, 100),  # 09:04
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[2]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config(session_end_time=time(9, 3)))

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == IntradayExitReason.FORCED_FLATTEN
    assert trade.exit_ts == bars.index[3]
    assert trade.exit_price == pytest.approx(90.0)  # close da barra de corte, nao o open


def test_multiplas_entradas_e_saidas_na_mesma_sessao_geram_trades_independentes():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (105, 106, 104, 105),
        (110, 111, 109, 110),
        (108, 109, 107, 108),
        (115, 116, 114, 115),
        (115, 116, 114, 115),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[1]: [Exit()],
        bars.index[2]: [Enter(side="long")],
        bars.index[3]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 2
    assert result.trades[0].entry_price == pytest.approx(105.0)
    assert result.trades[0].exit_price == pytest.approx(110.0)
    assert result.trades[1].entry_price == pytest.approx(108.0)
    assert result.trades[1].exit_price == pytest.approx(115.0)
    assert all(t.exit_reason == IntradayExitReason.SIGNAL for t in result.trades)


def test_flatten_forcado_nao_carrega_posicao_para_a_proxima_sessao():
    bars_a = _mk_bars("2026-01-05", [(100, 101, 99, 100)] * 3)
    bars_b = _mk_bars("2026-01-06", [(200, 201, 199, 200)] * 3)
    bars = pd.concat([bars_a, bars_b])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long")]})

    vistas: dict[pd.Timestamp, object] = {}
    original_on_bar = strat.on_bar

    def _spy(ts, bar, positions, session_pnl_brl):
        vistas[ts] = positions
        return original_on_bar(ts, bar, positions, session_pnl_brl)

    strat.on_bar = _spy

    result = run_intraday_backtest(bars, strat, _config())

    flatten_trades = [t for t in result.trades if t.exit_reason == IntradayExitReason.FORCED_FLATTEN]
    assert len(flatten_trades) == 1
    assert flatten_trades[0].exit_ts.date() == bars_a.index[-1].date()
    assert vistas[bars_b.index[0]] == []


def test_seed_volume_window_recebe_a_cauda_da_sessao_anterior_a_cada_dia():
    """`IntradayStrategy.seed_volume_window` (2026-08-22, pedido do dono:
    teto de posicao por volume rolante) precisa da CAUDA do pregao anterior
    para completar a janela na abertura -- e' o motor (aqui) que tem acesso
    ao dataframe inteiro e recorta essa cauda, nunca a propria estrategia
    (AGENTS.md: `strategy/` so' importa `core`)."""
    bars_a = _mk_bars("2026-01-05", [(100, 101, 99, 100)] * 3)
    bars_b = _mk_bars("2026-01-06", [(200, 201, 199, 200)] * 2)
    bars = pd.concat([bars_a, bars_b])

    class _RecordingStrategy(_StubIntradayStrategy):
        def __init__(self):
            super().__init__()
            self.seed_calls: list[list] = []

        def seed_volume_window(self, previous_session_tail):
            self.seed_calls.append(list(previous_session_tail))

    strat = _RecordingStrategy()
    run_intraday_backtest(bars, strat, _config())

    assert len(strat.seed_calls) == 2
    assert strat.seed_calls[0] == []  # primeira sessao do backtest: nao ha pregao anterior carregado
    cauda_dia2 = strat.seed_calls[1]
    assert [b.ts for b in cauda_dia2] == list(bars_a.index)  # as 3 barras do dia 1, dentro da folga de 90min


def test_seed_daily_volatility_recebe_so_sessoes_anteriores_sem_look_ahead():
    """`IntradayStrategy.seed_daily_volatility` (2026-08-23, alvo por
    volatilidade) tem que receber a barra DIARIA de cada sessao ANTERIOR --
    nunca a de HOJE (olhar o proprio dia seria look-ahead) -- e crescer a
    cada sessao nova, mais antiga primeiro."""
    bars_a = _mk_bars("2026-01-05", [(100, 105, 95, 102), (102, 104, 98, 100)])
    bars_b = _mk_bars("2026-01-06", [(200, 210, 190, 205)])
    bars_c = _mk_bars("2026-01-07", [(300, 301, 299, 300)])
    bars = pd.concat([bars_a, bars_b, bars_c])

    class _RecordingStrategy(_StubIntradayStrategy):
        def __init__(self):
            super().__init__()
            self.vol_calls: list[list] = []

        def seed_daily_volatility(self, previous_daily_bars):
            self.vol_calls.append(list(previous_daily_bars))

    strat = _RecordingStrategy()
    run_intraday_backtest(bars, strat, _config())

    assert len(strat.vol_calls) == 3
    assert strat.vol_calls[0] == []  # primeira sessao: nada anterior
    # segunda sessao: so' a diaria do dia 1 (high=105, low=95 -- agregado das 2 barras)
    assert len(strat.vol_calls[1]) == 1
    assert strat.vol_calls[1][0].high == pytest.approx(105.0)
    assert strat.vol_calls[1][0].low == pytest.approx(95.0)
    # terceira sessao: dias 1 e 2, NUNCA o 3 (hoje) -- mais antigo primeiro
    assert len(strat.vol_calls[2]) == 2
    assert strat.vol_calls[2][0].high == pytest.approx(105.0)  # dia 1
    assert strat.vol_calls[2][1].high == pytest.approx(210.0)  # dia 2


def test_lado_short_stop_acima_target_abaixo():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),  # entrada short no open=100
        (95, 96, 90, 92),     # low=90 toca target=93, open=95 nao gapeou alem dele
        (92, 93, 91, 92),
        (92, 93, 91, 92),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="short", initial_stop=110.0, initial_target=93.0)]})
    result = run_intraday_backtest(bars, strat, _config())

    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(93.0)
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert trade.pnl_brl > 0  # vendeu a 100, recomprou a 93


def test_metrics_reaproveita_trade_stats_sem_modificacao():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (105, 106, 104, 105),  # trade1: lucro (100 -> 105)
        (105, 106, 104, 105),
        (95, 96, 94, 95),      # trade2: perda (105 -> 95)
        (95, 96, 94, 95),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[1]: [Exit()],
        bars.index[2]: [Enter(side="long")],
        bars.index[3]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    expected = trade_stats([t.pnl_pct for t in result.trades])
    assert result.metrics["win_rate"] == pytest.approx(expected["win_rate"])
    assert result.metrics["profit_factor"] == pytest.approx(expected["profit_factor"])
    assert result.metrics["n_trades"] == 2


# ------------------------------------------------------------- EnterLimit (maker)

def test_target_fills_as_maker_ignora_slippage_so_no_target_nao_no_stop():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),   # idx0: decide Enter(target=110)
        (100, 101, 99, 100),   # idx1: executa no open=100 (+2 slippage -> entrada em 102)
        (100, 111, 99, 100),   # idx2: high=111 toca target=110
        (100, 101, 99, 100),   # idx3: decide Enter(stop=95)
        (100, 101, 99, 100),   # idx4: executa no open=100 (+2 slippage -> entrada em 102)
        (100, 101, 90, 92),    # idx5: low=90 toca stop=95
        (92, 93, 91, 92),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long", initial_target=110.0)],
        bars.index[3]: [Enter(side="long", initial_stop=95.0)],
    })
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=1.0, fee_round_trip_brl=0.0, slippage_ticks=2.0)
    config = _config(costs=costs, target_fills_as_maker=True)
    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 2
    target_trade = result.trades[0]
    assert target_trade.entry_price == pytest.approx(102.0)  # entrada paga slippage normalmente
    assert target_trade.exit_reason == IntradayExitReason.TARGET
    assert target_trade.exit_price == pytest.approx(110.0)  # sem slippage no target (maker)

    stop_trade = result.trades[1]
    assert stop_trade.exit_reason == IntradayExitReason.STOP
    assert stop_trade.exit_price == pytest.approx(93.0)  # stop=95, MENOS 2 ticks de slippage (taker)


def test_enter_limit_preenche_no_toque_ao_preco_exato_sem_slippage():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),   # 09:00: decide EnterLimit em 97 (nao toca aqui, decisao no close)
        (100, 101, 99, 100),   # 09:01: high/low nao toca 97
        (98, 99, 96, 97),      # 09:02: low=96 <= 97 -> preenche EXATAMENTE em 97 (nao no open=98)
        (97, 98, 96, 97),      # 09:03: decide Exit
        (100, 101, 99, 100),   # 09:04: Exit executa no open=100
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [EnterLimit(side="long", limit_price=97.0)],
        bars.index[3]: [Exit()],
    })
    # slippage_ticks=5 (bem alto) para provar que o preenchimento por limite NAO paga slippage
    # (se pagasse, o entry_price nao seria exatamente 97.0).
    config = _config(costs=IntradayCostModel(point_value_brl=1.0, tick_size=1.0, fee_round_trip_brl=0.0, slippage_ticks=5.0))
    result = run_intraday_backtest(bars, strat, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_ts == bars.index[2]
    assert trade.entry_price == pytest.approx(97.0)  # preco exato do limite, sem slippage


def test_enter_limit_persiste_por_varias_barras_ate_tocar():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),   # decide EnterLimit em 90
        (100, 101, 99, 100),   # nao toca
        (100, 101, 99, 100),   # nao toca
        (95, 96, 89, 90),      # low=89 <= 90 -> preenche aqui, na 4a barra depois da decisao
        (90, 91, 89, 90),
        (90, 91, 89, 90),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [EnterLimit(side="long", limit_price=90.0)],
        bars.index[3]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_ts == bars.index[3]
    assert trade.entry_price == pytest.approx(90.0)  # preco exato do limite, nao o open=95


def test_enter_limit_expira_por_ttl_e_nunca_preenche():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),   # decide EnterLimit em 90, ttl_bars=2
        (100, 101, 99, 100),   # 1a barra de espera
        (100, 101, 99, 100),   # 2a barra de espera -> expira aqui, nao preenche
        (85, 86, 84, 85),      # mesmo tocando 90 (e muito menos) depois, ordem ja expirou
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [EnterLimit(side="long", limit_price=90.0, ttl_bars=2)],
    })
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 0
    assert result.equity_curve.iloc[-1] == pytest.approx(result.equity_curve.iloc[0])  # nunca abriu posicao


def test_enter_a_mercado_substitui_ordem_limite_pendente():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),   # decide EnterLimit em 90 (long)
        (100, 101, 99, 100),   # decide Enter a mercado -- deve CANCELAR o limite pendente
        (102, 103, 101, 102),  # Enter a mercado executa aqui no open=102; decide Exit
        (95, 96, 89, 95),      # Exit executa no open=95; low=89 tocaria o limite de 90 SE ele
                                # ainda estivesse pendente -- nao deve abrir uma 2a posicao
        (95, 96, 94, 95),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [EnterLimit(side="long", limit_price=90.0)],
        bars.index[1]: [Enter(side="long")],
        bars.index[2]: [Exit()],
    })
    result = run_intraday_backtest(bars, strat, _config())

    assert len(result.trades) == 1  # so a entrada a mercado -- o limite cancelado NAO reabriu em 90
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(102.0)
    assert trade.exit_price == pytest.approx(95.0)


# ---------- conta quebrada (2026-08-23) -------------------------------------
# Achado ao testar CLSC4 (preco alto, R$100 de capital de teste): sem este
# freio, MaxDD passava de -100% -- impossivel numa conta sem margem. Uma
# conta sem caixa nao consegue mandar mais NENHUMA ordem depois de zerada.

def test_patrimonio_zerado_para_o_backtest_e_nao_gera_trade_depois():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),   # 0: Enter long (sem stop -- so' mark-to-market decide)
        (100, 101, 99, 100),   # 1: executa no open=100
        (100, 101, 1, 50),     # 2: close=50 -- perda enorme (quantidade grande, capital minusculo)
        (50, 51, 49, 50),      # 3: NUNCA deveria rodar -- conta ja quebrou na barra 2
        (50, 51, 49, 50),      # 4
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[3]: [Enter(side="long")],  # se isto executasse, seria um 2o trade
    })
    result = run_intraday_backtest(
        bars, strat, _config(initial_capital=10.0, default_quantity=1000),
    )

    assert result.wiped_out_at == bars.index[2]
    # so' as 3 primeiras barras (0,1,2) geraram ponto de patrimonio -- 3 e 4
    # nunca foram processadas.
    assert len(result.equity_curve) == 3
    assert result.equity_curve.iloc[-1] <= 0
    # nenhum SEGUNDO trade -- a acao da barra 3 nunca chegou a rodar.
    assert len(result.trades) == 0  # a 1a posicao nunca fechou (sem stop, conta quebrou antes)


# ---------- caixa insuficiente para o minimo do ativo (2026-08-23) ---------
# Ate 2026-08-24 era a MESMA regra que o gate diario de
# `live.intraday_runtime.IntradayLiveRuntime._check_capital` aplicava ao
# vivo. O dono pediu para o 2x so' valer na ENTRADA (`live_control.start`);
# o gate diario ao vivo caiu para 1x o lote, mas este flag de backtest
# continua em 2x -- dimensiona a calibracao, nao decide se um robo ja
# rodando pode continuar. Desligado por padrao (`enforce_capital_minimo=
# False` no dataclass) para nao quebrar testes com capital sintetico
# pequeno de proposito; `config_for` liga por padrao para todo backtest
# real.

def test_enforce_capital_minimo_desligado_e_o_default_e_nao_muda_nada():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (105, 106, 104, 105),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long")]})
    config = _config(initial_capital=10.0)  # 10 nao cobre 1 lote a 100 (default_quantity=1 aqui, ok)
    assert config.enforce_capital_minimo is False
    result = run_intraday_backtest(bars, strat, config)

    assert result.sessoes_puladas_por_capital == []
    assert len(result.trades) == 1  # comportamento de sempre, nada bloqueado


def test_enforce_capital_minimo_pula_a_sessao_inteira_quando_caixa_nao_cobre():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),  # se rodasse, entraria aqui
        (100, 101, 99, 100),
        (105, 106, 104, 105),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long")]})
    # preco~100, default_quantity=1 -> 1 lote de VERDADE seria so' 1 acao
    # (`default_quantity`, nao `LOTE_PADRAO_B3`) -- uso default_quantity=100
    # para o custo do lote (R$10.000) ficar bem acima do caixa (R$50).
    config = _config(initial_capital=50.0, default_quantity=100, enforce_capital_minimo=True)
    result = run_intraday_backtest(bars, strat, config)

    assert result.sessoes_puladas_por_capital == [bars.index[0]]
    assert len(result.trades) == 0  # a sessao inteira ficou de fora -- Enter nunca rodou
    # equity fica FLAT no caixa disponivel, sem gap na serie.
    assert len(result.equity_curve) == len(bars)
    assert (result.equity_curve == 50.0).all()


def test_enforce_capital_minimo_com_caixa_suficiente_opera_normal():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (105, 106, 104, 105),
    ])
    strat = _StubIntradayStrategy({
        bars.index[0]: [Enter(side="long")],
        bars.index[1]: [Exit()],
    })
    # caixa (R$100.000) cobre de sobra o minimo (2x R$100x100=R$20.000).
    config = _config(initial_capital=100_000.0, default_quantity=100, enforce_capital_minimo=True)
    result = run_intraday_backtest(bars, strat, config)

    assert result.sessoes_puladas_por_capital == []
    assert len(result.trades) == 1


def test_enforce_capital_minimo_nao_pula_sessao_resumida():
    """A sessao RESUMIDA (`resume_same_session=True`, ex.: warm start ao
    vivo no meio do pregao) ja tem calibracao/posicao por fora -- a
    politica de recusar o pregao so' faz sentido ANTES de qualquer
    decisao, entao nunca se aplica a ela."""
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
    ])
    strat = _StubIntradayStrategy({})
    config = _config(initial_capital=10.0, default_quantity=100, enforce_capital_minimo=True)
    result = run_intraday_backtest(bars, strat, config, resume_same_session=True)

    assert result.sessoes_puladas_por_capital == []


def test_patrimonio_positivo_nunca_marca_wiped_out():
    bars = _mk_bars("2026-01-05", [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (105, 106, 104, 105),
    ])
    strat = _StubIntradayStrategy({bars.index[0]: [Enter(side="long")]})
    result = run_intraday_backtest(bars, strat, _config())

    assert result.wiped_out_at is None
    assert len(result.equity_curve) == len(bars)
