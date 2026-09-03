"""Teste de `warm_start_calibration` (AGENTS.md: toda regra de entrada/
saida em `strategy/` -> teste com cenario sintetico).

Cobre o ponto de falha identificado ao vivo: um robo de grid (aqui,
`Gremah` em fase fixa) descobre `open_price` na PRIMEIRA
barra que vir (`on_bar`). Se o processo ao vivo so comecar a receber
barra no MEIO do pregao (ex.: 15h), ele calibraria com o preco daquele
momento em vez do preco de abertura real -- grid deslocado do nivel certo
o dia todo ("cold start"). `warm_start_calibration` resolve alimentando
as barras reais desde a abertura (buscadas do historico) em modo seco
(posicao sempre None, P&L sempre 0 -- nenhum trade fabricado) antes de
comecar a operar de verdade; `resume_same_session` no motor evita que a
sessao seja re-inicializada (o que apagaria a calibracao) quando as
barras "ao vivo" comecam a chegar.

Usa `Gremah` com `fixed_anchor_until` bem depois do fim da
janela do teste (sempre em fase fixa aqui) so' como veiculo -- o mecanismo
testado e' generico, de qualquer `IntradayStrategy` que descubra sua
calibracao na primeira barra."""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, warm_start_calibration
from strategy.daytrade.lab.gremah import Gremah
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:00", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


# Abertura real = 10.00 (bar 0). Preco sobe ao longo da manha (bars 1-3,
# nunca fornecidas ao vivo -- so existem no historico) e so entao, com o
# preco ja em 10.10, chegam as barras "ao vivo" (4-6): toque no nivel long
# correto (9.80, calibrado a partir da abertura real) seguido de toque no
# alvo (9.90); bar 6 e' so preenchimento para o "fim de pregao" nao cair
# logo na barra do toque (o que apagaria a ordem antes dela preencher).
ROWS = [
    (10.00, 10.00, 10.00, 10.00),  # abertura real da sessao
    (10.00, 10.05, 10.00, 10.05),
    (10.05, 10.10, 10.05, 10.10),
    (10.10, 10.12, 10.08, 10.10),  # ultima barra so-historico ("agora" comeca depois desta)
    (10.10, 10.10, 9.79, 9.80),    # 1a barra AO VIVO: toca o nivel long (correto: 9.80)
    (9.80, 9.90, 9.80, 9.90),      # toca o alvo (correto: 9.90) -> fecha por TARGET
    (9.90, 9.90, 9.90, 9.90),      # preenchimento, evita que a barra do toque seja "a ultima"
]


def _config() -> IntradayBacktestConfig:
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=0.01, fee_round_trip_brl=0.0, slippage_ticks=0.0)
    return IntradayBacktestConfig(costs=costs, initial_capital=1_000.0,
                                   session_end_time=time(23, 59), target_fills_as_maker=True)


def _strat() -> Gremah:
    return Gremah(profit_pct=0.01, spacing_multiplier=2.0, stop_multiplier=20.0, tick_size=0.01,
                  fixed_anchor_until=time(23, 59),  # sempre fase fixa nesta janela de teste
                  # Filtro de qualidade de entrada (2026-08-27) e' PADRAO
                  # `True` desde entao -- desligado aqui porque este arquivo
                  # testa a mecanica de warm start/cold start (calibracao da
                  # abertura), nao o filtro em si, e a barra "ao vivo" que
                  # toca o nivel chega bem antes dos 216 minutos.
                  filtro_minutos_desde_abertura_min=None,
                  filtro_volume_toque_max=None)


def test_cold_start_no_meio_do_pregao_calibra_errado():
    bars = _bars(ROWS)
    live_bars = bars.iloc[4:]  # comeca a operar so a partir da barra "ao vivo"

    strat_cold = _strat()
    result = run_intraday_backtest(live_bars, strat_cold, _config())

    # calibrou com o preco de 10.10 (1a barra que viu), nao com a abertura
    # real de 10.00 -- nivel/alvo saem do lugar errado (entrou em 9.90 em
    # vez de 9.80) e nunca chega no alvo certo.
    assert len(result.trades) == 1
    assert result.trades[0].entry_price == pytest.approx(9.90)  # devia ser 9.80
    assert result.trades[0].exit_reason != IntradayExitReason.TARGET


def test_warm_start_calibra_certo_independente_do_horario():
    bars = _bars(ROWS)
    seed_bars = [
        Bar(ts=ts, open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close), volume=0.0)
        for ts, row in bars.iloc[:4].iterrows()
    ]
    live_bars = bars.iloc[4:]
    session_date = bars.index[0].date()

    strat_warm = _strat()
    seed_pending = warm_start_calibration(strat_warm, session_date, seed_bars)
    result_warm = run_intraday_backtest(
        live_bars, strat_warm, _config(), resume_same_session=True, seed_pending=seed_pending
    )

    strat_ref = _strat()
    result_ref = run_intraday_backtest(bars, strat_ref, _config())  # dia inteiro, sem cold start

    assert len(result_warm.trades) == 1
    assert result_warm.trades[0].entry_price == pytest.approx(9.80)
    assert result_warm.trades[0].exit_price == pytest.approx(9.90)
    assert result_warm.trades[0].exit_reason == IntradayExitReason.TARGET

    # o trecho "ao vivo" do warm start reproduz EXATAMENTE o trecho
    # equivalente do robo que operou o dia inteiro desde a abertura real.
    ref_trade = result_ref.trades[0]
    assert result_warm.trades[0].entry_price == pytest.approx(ref_trade.entry_price)
    assert result_warm.trades[0].exit_price == pytest.approx(ref_trade.exit_price)


def test_warm_start_nao_fabrica_trade_nem_pnl():
    bars = _bars(ROWS)
    seed_bars = [
        Bar(ts=ts, open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close), volume=0.0)
        for ts, row in bars.iloc[:4].iterrows()
    ]
    session_date = bars.index[0].date()

    strat = _strat()
    warm_start_calibration(strat, session_date, seed_bars)

    # so calibrou (open_price/ticks do dia) -- nao fechou nenhuma posicao,
    # nao arma um trade fantasma, nao mexe em P&L (nada disso e' rastreado
    # pelo motor porque warm_start_calibration nunca chama o motor).
    assert strat._state.open_price == pytest.approx(10.00)
    assert strat._state.long_fills == 0
    assert strat._state.short_fills == 0


def _wdo_grid_com_risco() -> WdoGridReloadMaker:
    """`WdoGridReloadMaker` com dimensionamento dinamico ligado (margem +
    teto por risco) -- os dois numeros de `_quantidade_da_entrada` que ficam
    presos em 0/1 quando `_cash_atual_brl` nunca e' atualizado (LICOES_DE_
    PRODUCAO.md item 3.14)."""
    return WdoGridReloadMaker(
        stop_ticks=16,
        margin_per_contract_brl=150.0,  # margem WDO@ (CLAUDE.md: margem x buffer)
        risco_pct_por_trade=0.01,
        point_value_brl=10.0,  # R$/ponto do WDO@
    )


def _wdo_seed_bars() -> list[Bar]:
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    return [Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=0.0)]


def test_warm_start_sem_cash_brl_mantem_teto_preso_em_1_contrato():
    """Caracteriza o BUG do item 3.14 antes da correcao: sem `cash_brl`
    (comportamento antigo, default `None` preserva compatibilidade com
    qualquer outro chamador que ainda nao tenha esse numero), `on_capital_
    update` nunca e' chamado durante o replay -- `_cash_atual_brl` fica no
    default `0.0` e o teto dinamico (margem E risco) colapsa para 0,
    forcando `max(1, teto)` a devolver sempre 1 contrato, em silencio."""
    strat = _wdo_grid_com_risco()
    seed_bars = _wdo_seed_bars()

    warm_start_calibration(strat, seed_bars[0].ts.date(), seed_bars)

    assert strat._cash_atual_brl == 0.0
    assert strat._quantidade_da_entrada() == 1


def test_warm_start_com_cash_brl_repoe_caixa_antes_do_teto_por_risco():
    """A CORRECAO: passando `cash_brl` (o caixa corrente que o runtime ja
    conhece -- `initial_capital + realized_pnl`, MESMA formula que o motor
    usa em `on_capital_update` a cada barra real), `warm_start_calibration`
    chama `strategy.on_capital_update(cash_brl)` ANTES do primeiro `on_bar`
    do replay -- `_cash_atual_brl` fica sincronizado e o teto por risco volta
    a valer, em vez de ficar preso no piso de 1 contrato.

    Numeros: margem R$150 x buffer 2.0 x reserva 1.25 = R$375/contrato ->
    teto por margem = floor(50_000 / 375) = 133. Stop fixo de 16 ticks x
    R$0,50 x R$10,00/ponto = R$80,00/contrato -> teto por risco = floor(
    50_000 x 0.01 / 80) = 6. O MENOR dos dois teto (risco) e' quem decide,
    e 6 != 1 prova que o teto voltou a ser calculado de verdade, nao mais
    o piso de emergencia."""
    strat = _wdo_grid_com_risco()
    seed_bars = _wdo_seed_bars()

    warm_start_calibration(strat, seed_bars[0].ts.date(), seed_bars, cash_brl=50_000.0)

    assert strat._cash_atual_brl == pytest.approx(50_000.0)
    assert strat._quantidade_da_entrada() == 6


def test_warm_start_cash_brl_nao_fabrica_trade_nem_pnl():
    """Mesma garantia de `test_warm_start_nao_fabrica_trade_nem_pnl`, agora
    com `cash_brl` setado: sincronizar o caixa nao e' o mesmo que executar --
    `on_capital_update` so' guarda um numero, nao abre posicao nem mexe em
    P&L (a chamada em si e' NO-OP em qualquer estrategia sem dimensionamento
    dinamico, e mesmo nas que tem, so' atualiza o caixa GUARDADO)."""
    strat = _wdo_grid_com_risco()
    seed_bars = _wdo_seed_bars()

    warm_start_calibration(strat, seed_bars[0].ts.date(), seed_bars, cash_brl=50_000.0)

    assert strat._state.long_fills == 0
    assert strat._state.short_fills == 0
    assert strat._state.open_side is None
