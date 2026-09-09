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
# de custo registrada no modelo. O campo do dataclass continua com default
# 0.0 porque um instrumento com tarifario proprio (futuro, por exemplo) nao
# pode herdar em silencio a tarifa de acao — quem sabe declara no perfil.
#
# UMA constante para todas as acoes, nao uma por papel: a taxa e' do MERCADO
# (B3, day trade em acao), nao do simbolo. Em 2026-08-21 isto existia como
# `PMAM3_EXCHANGE_FEE_PCT_PER_LEG` e ganhou irmas identicas por CSAN3/KLBN4,
# na ideia de que "cada perfil declara o proprio custo". Com a tabela indo a
# 10 simbolos (2026-08-22) essa ideia virou 10 linhas com o MESMO numero --
# duplicacao que nao protege de nada e esconde que o valor e' um so. Um papel
# que um dia tiver tarifario proprio ganha a constante dele naquele dia, com o
# motivo escrito junto.
B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG = B3_DAY_TRADE_FEE_PCT_PER_LEG * 2.0

# DESLIZE do alvo NATIVO da corretora (o `tp` que viaja amarrado no mesmo
# request da entrada, `live/broker_mt5.py::place_pending`), em TICKS, medido
# em dinheiro real -- NAO e' uma estimativa de modelagem.
#
# AMOSTRA (item 4.8 de LICOES_DE_PRODUCAO.md), robo `wdo_grid_reload_maker`
# (WDO F1, WDO@, slot `dt-wdo_grid_reload_maker-wdo@-live`, magic
# 862399285). Reconstruida em 2026-09-08 do historico de DEALS + ORDENS do
# terminal (`history_deals_get`/`history_orders_get`), que e' a UNICA fonte
# que preserva o par (nivel PEDIDO, preco EXECUTADO): em `db/live.sqlite` a
# ordem de saida grava `limit_price == avg_price`, o nivel pedido some, e o
# rotulo `(target)` e' INFERIDO pelo robo -- 19 saidas rotuladas "target" no
# dia contra 8 que a corretora de fato executou por TP nativo (2,4x).
#
# Pareamento: a ordem de ENTRADA carrega `tp` no proprio request; o deal de
# saida disparado por ele vem com `reason=5` (TP nativo) e o nivel no
# `comment`. `entry_order.tp == nivel do comment` em 11 de 11 casos.
#
# POPULACAO COMPLETA de operacao real deste robo -- 3 pregoes (2026-08-28,
# 2026-09-04, 2026-09-08), n=11 saidas por TP nativo, 1 contrato:
#
#     deslize (ticks) |  0   -1   -2      contra: 10   a favor: 0   neutro: 1
#     contagem        |  1    9    1
#     media -1,000  mediana -1,0  desvio 0,447  min -2,0  max 0,0
#
# Por pregao: 2026-09-04 n=3 (media -0,667, geometria T1); 2026-09-08 n=8
# (media -1,125, geometria T2 -- 7 por 1 tick, 1 por 2).
#
# Em dinheiro: 11 ticks x R$5,00 = R$55,00 de deslize. O bruto REAL das 11
# saidas por alvo foi R$40,00 contra R$95,00 se todas tivessem pago o nivel
# pedido -- o deslize comeu 57,9% do bruto teorico. So' no pregao de
# 2026-09-08: R$45,00 sobre R$80,00 (56,25%), num dia que fechou -R$116,00.
#
# Duas propriedades da amostra decidem a MODELAGEM:
# (1) e' DIRECIONAL -- 10 contra, 1 neutro, ZERO a favor (sob moeda justa,
#     p ~ 0,001). Nao e' ruido em torno do nivel, e nenhuma media o compensa;
# (2) e' da REGRA da corretora, nao evento -- o `tp` nativo executa como
#     gatilho varrido a mercado, nao como limite resting na fila (mesmo modo
#     de falha do item 4.3, so' que aqui ninguem escolheu mercado).
#
# n=11 AINDA E' POUCO (2 pregoes efetivos, 1 contrato), e o numero fica aqui
# como CONSTANTE NOMEADA -- e nao escondido dentro do motor -- exatamente por
# isso: e' o default de `backtest.intraday.profiles.config_for`,
# sobrescrivivel por qualquer chamador que queira medir a sensibilidade. Quem
# ampliar a amostra atualiza ESTE numero, num lugar so'. O forte da evidencia
# e' a DIRECIONALIDADE, nao a magnitude exata; 1,0 e' a media E a mediana.
DESLIZE_ALVO_NATIVO_TICKS = 1.0

# O STOP nativo (`sl`) NAO ganha constante propria -- ele continua pagando
# `IntradayCostModel.slippage_ticks` (1,0 por default), que ja e' o custo de
# uma ordem a mercado. Medido na MESMA reconstrucao: n=2 do robo (0 tick e
# +1 tick A FAVOR) mais 3 saidas manuais por SL no mesmo contrato (0 tick nas
# 3). Em 5 de 5 o SL nunca executou PIOR que o nivel pedido -- direcao
# oposta a do TP, consistente com a hipotese de que o stop vira ordem a
# mercado no toque enquanto o alvo e' limite na fila. n=2 nao prova nada, mas
# tambem nao ha nenhuma evidencia de deslize adverso no stop para modelar, e
# cobrar 1 tick por ele (o que o motor ja faz) e' o lado CONSERVADOR do erro.


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
    # passar `B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG` explicitamente.
    exchange_fee_pct_per_leg: float = 0.0
    # Ticks de DESLIZE cobrados na saida por ALVO quando ela e' modelada como
    # MAKER (`IntradayBacktestConfig.target_fills_as_maker=True`) e NAO e'
    # uma saida fatiada. Sempre CONTRA a posicao (venda sai mais baixo,
    # compra sai mais alto) -- ver `DESLIZE_ALVO_NATIVO_TICKS` para a
    # medicao que da' origem ao numero.
    #
    # Existe porque `target_fills_as_maker=True` afirma duas coisas ao mesmo
    # tempo, e so' UMA e' verdade na corretora real: que o alvo nao paga o
    # spread de uma ordem a mercado (verdade -- ele nao e' varrido pela
    # estrategia) e que ele preenche EXATAMENTE no nivel pedido (falso -- 8
    # de 8 em 2026-09-08 sairam piores). Sem este campo o motor entregava um
    # alvo de graca, e uma varredura de `profit_ticks` num motor assim nao
    # escolhe a melhor geometria: escolhe a que melhor explora a otimizacao
    # que falta no modelo de preenchimento.
    #
    # NAO se aplica ao STOP nem a qualquer saida a mercado: essas ja pagam
    # `slippage_ticks` por `apply_intraday_slippage`, e cobrar as duas
    # coisas seria contar o mesmo custo duas vezes. Stop e alvo nao tem por
    # que deslizar igual -- o stop vira ordem a mercado no toque, o alvo
    # e' limite na fila -- entao sao dois numeros separados de proposito.
    #
    # Default `0.0` preserva o comportamento antigo para quem monta o modelo
    # na mao (todo teste sintetico); `config_for` liga o valor real.
    target_slippage_ticks: float = 0.0

    @classmethod
    def from_symbol_info(
        cls,
        trade_tick_value: float,
        trade_tick_size: float,
        fee_round_trip_brl: float,
        slippage_ticks: float = 1.0,
        exchange_fee_pct_per_leg: float = 0.0,
        target_slippage_ticks: float = 0.0,
    ) -> "IntradayCostModel":
        point_value_brl = trade_tick_value / trade_tick_size
        return cls(
            point_value_brl=point_value_brl,
            tick_size=trade_tick_size,
            fee_round_trip_brl=fee_round_trip_brl,
            slippage_ticks=slippage_ticks,
            exchange_fee_pct_per_leg=exchange_fee_pct_per_leg,
            target_slippage_ticks=target_slippage_ticks,
        )


def apply_intraday_slippage(price: float, side: Literal["buy", "sell"], model: IntradayCostModel) -> float:
    """Ajusta o preco pela slippage estimada, em TICKS (nao percentual do
    preco — o mesmo numero de ticks custa o mesmo em qualquer nivel de
    indice). Compra sobe, venda desce — mesmo sinal de
    `backtest.costs.apply_slippage`."""
    delta = model.slippage_ticks * model.tick_size
    return price + delta if side == "buy" else price - delta


def apply_deslize_alvo_nativo(price: float, side: Literal["buy", "sell"],
                              model: IntradayCostModel) -> float:
    """Ajusta o preco de saida por ALVO pelo deslize do TP NATIVO da
    corretora (`model.target_slippage_ticks`), sempre CONTRA a posicao.

    Mesma direcao de `apply_intraday_slippage` (`side` e' o lado da ordem de
    SAIDA: fechar comprado e' `"sell"` e sai mais BAIXO; fechar vendido e'
    `"buy"` e sai mais ALTO) -- e' funcao separada, e nao um segundo uso
    daquela, porque os dois numeros medem coisas diferentes e nao tem por
    que ser iguais: `slippage_ticks` e' o custo de VARRER o book com ordem a
    mercado (stop, flatten, `Exit`), `target_slippage_ticks` e' o erro que a
    corretora comete ao converter o `tp` amarrado na posicao (item 4.8 de
    LICOES_DE_PRODUCAO.md, 8 de 8 saidas piores que o nivel pedido em
    2026-09-08).

    `target_slippage_ticks=0.0` (default do modelo) devolve o preco intacto
    -- e' o comportamento antigo, em que o alvo maker preenchia de graca."""
    if not model.target_slippage_ticks:
        return price
    delta = model.target_slippage_ticks * model.tick_size
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
