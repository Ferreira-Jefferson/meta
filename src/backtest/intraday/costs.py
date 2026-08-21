"""Modelo de custo para futuros — por CONTRATO/ponto, nao percentual de
notional como `core.config.CostModel` (feito para acoes; percentual nao faz
sentido para um contrato cujo preco e um indice de pontos, nao um valor em
R$ por unidade).

`FuturesCostModel.from_symbol_info` recebe a economia do contrato JA
EXTRAIDA do terminal MT5 (`market_data_intraday.mt5_source.
symbol_economics`) em vez de hardcodar o valor do ponto do WIN — mesma
filosofia de `live.feed.MT5Feed` autocalibrar o fuso do servidor em vez de
assumir um numero. Este modulo nunca importa `MetaTrader5` nem
`market_data_intraday` (regra de fronteira, feature so importa `core/`):
recebe os numeros ja extraidos como argumentos simples de tipo primitivo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from strategy.daytrade.base import Side


@dataclass(frozen=True)
class FuturesCostModel:
    point_value_brl: float
    tick_size: float
    fee_round_trip_brl: float
    slippage_ticks: float = 1.0

    @classmethod
    def from_symbol_info(
        cls,
        trade_tick_value: float,
        trade_tick_size: float,
        fee_round_trip_brl: float,
        slippage_ticks: float = 1.0,
    ) -> "FuturesCostModel":
        point_value_brl = trade_tick_value / trade_tick_size
        return cls(
            point_value_brl=point_value_brl,
            tick_size=trade_tick_size,
            fee_round_trip_brl=fee_round_trip_brl,
            slippage_ticks=slippage_ticks,
        )


def apply_futures_slippage(price: float, side: Literal["buy", "sell"], model: FuturesCostModel) -> float:
    """Ajusta o preco pela slippage estimada, em TICKS (nao percentual do
    preco — o mesmo numero de ticks custa o mesmo em qualquer nivel de
    indice). Compra sobe, venda desce — mesmo sinal de
    `backtest.costs.apply_slippage`."""
    delta = model.slippage_ticks * model.tick_size
    return price + delta if side == "buy" else price - delta


def gross_pnl_brl(entry_price: float, exit_price: float, quantity: int, side: Side, model: FuturesCostModel) -> float:
    """P&L bruto (antes de taxas), em R$ — pontos convertidos por
    `point_value_brl`. Long ganha quando o preco sobe; short, quando cai."""
    points = (exit_price - entry_price) if side == "long" else (entry_price - exit_price)
    return points * model.point_value_brl * quantity


def fees_round_trip_brl(quantity: int, model: FuturesCostModel) -> float:
    return model.fee_round_trip_brl * quantity
