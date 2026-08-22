"""Modelo de custo INTRADIARIO — por ponto de preco e por perna executada,
nao percentual de notional como `core.config.CostModel`.

Chamava-se `FuturesCostModel` ate 2026-08-21, quando o unico instrumento em
operacao passou a ser uma ACAO (PMAM3) e o nome virou mentira. A forma do
modelo (valor do ponto x quantidade + tarifa por perna + slippage em ticks)
serve os dois casos; o que muda de instrumento para instrumento sao os
NUMEROS, e eles vem de fora.

`IntradayCostModel.from_symbol_info` recebe a economia do simbolo JA EXTRAIDA
do terminal MT5 (`market_data_intraday.mt5_source.symbol_economics`) em vez
de hardcodar valor de ponto — pelo mesmo motivo que o fuso do servidor e'
medido e declarado em `core.b3_session` em vez de chutado. Este modulo nunca
importa `MetaTrader5` nem `market_data_intraday` (regra de fronteira, feature
so importa `core/`): recebe os numeros ja extraidos como argumentos simples
de tipo primitivo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from strategy.daytrade.base import Side

# Taxa REAL de bolsa (B3) para day trade em acoes, pesquisada em 2026-08-21:
# emolumentos + liquidacao ~0,025% do notional POR PERNA (compra e venda
# cobradas separadamente) -- tarifa day trade, menor que a de swing trade
# (~0,0325%). Corretagem (Rico, lote redondo) confirmada R$0 em multiplas
# fontes nessa mesma pesquisa -- so a taxa de bolsa entra aqui, nao
# corretagem.
B3_DAY_TRADE_FEE_PCT_PER_LEG = 0.00025

# Margem de seguranca pedida explicitamente pelo usuario (2026-08-21): toda
# compra/venda ja assume o pagamento de 2x a taxa real de bolsa, por
# padrao -- nao como um ajuste posterior de sensibilidade, e sim a premissa
# de custo registrada no modelo. Ver `PMAM3_EXCHANGE_FEE_PCT_PER_LEG` abaixo
# para o uso concreto no dia a dia; o campo do dataclass continua com default
# 0.0 porque um instrumento com tarifario proprio (futuro, por exemplo) nao
# pode herdar em silencio a tarifa de acao — quem sabe declara no perfil.
PMAM3_EXCHANGE_FEE_PCT_PER_LEG = B3_DAY_TRADE_FEE_PCT_PER_LEG * 2.0

# Mesma tarifa de bolsa (a taxa e' do MERCADO -- B3 day trade em acoes --, nao
# do papel), mesma margem de seguranca de 2x. Constante SEPARADA por simbolo
# de proposito (nao um alias generico "EQUITY_FEE"): a regra deste modulo e'
# cada perfil declarar explicitamente o custo que usa, nunca herdar em
# silencio o de outro papel (ver comentario acima) -- mesmo quando o valor
# numerico e' identico hoje.
CSAN3_EXCHANGE_FEE_PCT_PER_LEG = B3_DAY_TRADE_FEE_PCT_PER_LEG * 2.0
KLBN4_EXCHANGE_FEE_PCT_PER_LEG = B3_DAY_TRADE_FEE_PCT_PER_LEG * 2.0


@dataclass(frozen=True)
class IntradayCostModel:
    point_value_brl: float
    tick_size: float
    fee_round_trip_brl: float
    slippage_ticks: float = 1.0
    # Taxa de bolsa (emolumentos+liquidacao), percentual do notional, POR
    # PERNA (cobrada na entrada E na saida, cada uma sobre o preco
    # efetivamente executado daquela perna). Default 0.0 preserva
    # comportamento antigo -- quem monta o modelo para acoes day trade deve
    # passar `PMAM3_EXCHANGE_FEE_PCT_PER_LEG` (ou equivalente) explicitamente.
    exchange_fee_pct_per_leg: float = 0.0

    @classmethod
    def from_symbol_info(
        cls,
        trade_tick_value: float,
        trade_tick_size: float,
        fee_round_trip_brl: float,
        slippage_ticks: float = 1.0,
        exchange_fee_pct_per_leg: float = 0.0,
    ) -> "IntradayCostModel":
        point_value_brl = trade_tick_value / trade_tick_size
        return cls(
            point_value_brl=point_value_brl,
            tick_size=trade_tick_size,
            fee_round_trip_brl=fee_round_trip_brl,
            slippage_ticks=slippage_ticks,
            exchange_fee_pct_per_leg=exchange_fee_pct_per_leg,
        )


def apply_intraday_slippage(price: float, side: Literal["buy", "sell"], model: IntradayCostModel) -> float:
    """Ajusta o preco pela slippage estimada, em TICKS (nao percentual do
    preco — o mesmo numero de ticks custa o mesmo em qualquer nivel de
    indice). Compra sobe, venda desce — mesmo sinal de
    `backtest.costs.apply_slippage`."""
    delta = model.slippage_ticks * model.tick_size
    return price + delta if side == "buy" else price - delta


def gross_pnl_brl(entry_price: float, exit_price: float, quantity: int, side: Side, model: IntradayCostModel) -> float:
    """P&L bruto (antes de taxas), em R$ — pontos convertidos por
    `point_value_brl`. Long ganha quando o preco sobe; short, quando cai."""
    points = (exit_price - entry_price) if side == "long" else (entry_price - exit_price)
    return points * model.point_value_brl * quantity


def fees_round_trip_brl(quantity: int, entry_price: float, exit_price: float, model: IntradayCostModel) -> float:
    """Taxa FIXA por acao/contrato (`fee_round_trip_brl`, ex.: corretagem de
    futuros) somada a taxa de bolsa PERCENTUAL do notional (`exchange_fee_
    pct_per_leg`), cobrada em CADA perna sobre o preco efetivamente
    executado dela -- entrada e saida podem ter notional levemente
    diferente (preco mudou entre as duas), a taxa segue o preco real de
    cada uma, nao uma media."""
    fixed = model.fee_round_trip_brl * quantity
    pct = model.exchange_fee_pct_per_leg * quantity * (entry_price + exit_price)
    return fixed + pct
