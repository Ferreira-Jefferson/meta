"""Escada de risco progressivo (2026-09-18, ordem do dono).

Cobre as tres coisas que a escada promete, e nada alem: os degraus da conta
pura, o robo subindo E descendo de contrato com o caixa, e a garantia de que
quem nao declarou `quantity_e_unidade` nao cresce.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backtest.intraday.machine import IntradayBacktestConfig, IntradaySessionMachine
from backtest.intraday.profiles import config_for, profile_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayStrategy, contracts_from_capital_escada,
)

MARGEM_WDO = 150.0
TS = pd.Timestamp("2026-09-18 12:30", tz="UTC")


def _bar() -> Bar:
    return Bar(ts=TS, open=5150.0, high=5151.0, low=5149.0,
               close=5150.0, volume=10.0)


# ---------------------------------------------------------------- a conta --

@pytest.mark.parametrize("caixa, esperado", [
    (0.0, 0), (150.0, 0), (299.99, 0),
    (300.0, 1), (375.0, 1), (750.0, 1), (1_199.0, 1),
    (1_200.0, 2), (3_599.0, 2),
    (3_600.0, 3), (9_999.0, 3),
    (10_000.0, 4), (24_999.0, 4),
    (25_000.0, 5), (179_999.0, 5),
    (180_000.0, 6),
])
def test_degraus_da_escada(caixa, esperado):
    assert contracts_from_capital_escada(caixa, MARGEM_WDO) == esperado


def test_hard_cap_nunca_e_ultrapassado():
    assert contracts_from_capital_escada(1_000_000.0, MARGEM_WDO, hard_cap=5) == 5
    assert contracts_from_capital_escada(1_000_000.0, MARGEM_WDO, hard_cap=0) == 0


def test_margem_ou_caixa_invalidos_devolvem_zero():
    assert contracts_from_capital_escada(1_000.0, 0.0) == 0
    assert contracts_from_capital_escada(-1.0, MARGEM_WDO) == 0


def test_escada_e_mais_apertada_que_o_teto_por_margem():
    """R$750 ABRE 2 contratos pela margem, mas nao SOBREVIVE a eles -- e' a
    razao de existir da escada."""
    from strategy.daytrade.base import contracts_from_capital_operacional
    assert contracts_from_capital_operacional(750.0, MARGEM_WDO) == 2
    assert contracts_from_capital_escada(750.0, MARGEM_WDO) == 1


# ------------------------------------------------- o robo sobe e desce -----

class _RoboUnidade(IntradayStrategy):
    """Pede SEMPRE 1 contrato -- quem multiplica e' o sistema."""
    name: str = "robo_unidade"
    version: str = "1.0.0"
    symbol: str = "WDO@"
    is_futuro: bool = True
    quantity_e_unidade: bool = True

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        return [EnterLimit(side="long", limit_price=bar.close - 0.5,
                           initial_stop=bar.close - 15.0,
                           initial_target=bar.close + 22.5,
                           quantity=1, ttl_bars=10, exit_split_unit=1)]


class _RoboQueSeDimensiona(_RoboUnidade):
    """Ja' calculou o proprio tamanho -- a escada so' pode CORTAR."""
    name: str = "robo_dimensionado"
    quantity_e_unidade: bool = False


def _maquina(strategy, caixa: float) -> IntradaySessionMachine:
    cfg = config_for(profile_for("WDO@"), trade_tick_value=0.01,
                     trade_tick_size=0.001, initial_capital=caixa)
    assert cfg.escada_risco_progressivo, "config_for deve ligar a escada em futuro"
    return IntradaySessionMachine(strategy=strategy, config=cfg)


def _pede(strategy, caixa: float) -> int:
    """Quantidade que o motor REALMENTE pede com este caixa."""
    m = _maquina(strategy, caixa)
    acao = strategy.on_bar(TS, _bar(),
                           [], 0.0)[0]
    return m._escala_unidade(acao).quantity


@pytest.mark.parametrize("caixa, contratos", [
    (375.0, 1), (1_199.0, 1), (1_200.0, 2), (3_600.0, 3),
    (10_000.0, 4), (25_000.0, 5),
])
def test_robo_de_unidade_escala_com_o_caixa(caixa, contratos):
    assert _pede(_RoboUnidade(), caixa) == contratos


def test_robo_de_unidade_DESCE_quando_o_caixa_cai():
    """A escada e' reavaliada a cada barra -- nao e' uma foto do inicio."""
    strategy = _RoboUnidade()
    m = _maquina(strategy, 3_600.0)
    acao = strategy.on_bar(TS, _bar(), [], 0.0)[0]
    assert m._escala_unidade(acao).quantity == 3
    m.realized_pnl = -2_500.0          # caixa cai para 1.100
    assert m._escala_unidade(acao).quantity == 1
    m.realized_pnl = -3_400.0          # caixa cai para 200
    assert m._escala_unidade(acao).quantity == 1


def test_robo_que_se_dimensiona_nao_cresce():
    for caixa in (375.0, 1_200.0, 25_000.0):
        assert _pede(_RoboQueSeDimensiona(), caixa) == 1


def test_escada_desligada_preserva_o_motor_antigo():
    strategy = _RoboUnidade()
    cfg = config_for(profile_for("WDO@"), trade_tick_value=0.01,
                     trade_tick_size=0.001, initial_capital=25_000.0,
                     escada_risco_progressivo=False)
    m = IntradaySessionMachine(strategy=strategy, config=cfg)
    acao = strategy.on_bar(TS, _bar(), [], 0.0)[0]
    assert m._escala_unidade(acao).quantity == 1


def test_escada_nunca_afrouxa_o_teto_por_margem():
    """Compoe pelo MENOR: o teto do perfil (5 no WDO@) continua duro."""
    strategy = _RoboUnidade()
    m = _maquina(strategy, 1_000_000.0)
    assert m._cap_capital_atual() == 5
