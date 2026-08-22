"""GREMAH = abreviacao de "Grid REload MAker Hybrid" (2026-08-21).

Combina os dois desenhos anteriores num robo so'. Ancora FIXA na abertura
(como a geracao anterior, ticks%) enquanto o pregao ainda esta "fresco"
(antes de `fixed_anchor_until`, por padrao 14:00 UTC / ~11h Brasilia); a
partir dai, muda para ancora ROLANTE (recalculada a cada recarga a partir
do preco ATUAL) para o resto da sessao -- nao precisa mais saber onde foi
a abertura a partir desse ponto.

Motivado por um achado empirico direto (2026-08-21, in-sample real,
PMAM3): mesmo com a abertura corretamente calibrada
(`warm_start_calibration`), o grid ancorado na abertura degrada de
+R$747,10 (comecando as 13:00 UTC, a abertura real) para -R$1.000,50
(comecando as 18:00 UTC) no MESMO periodo de dados -- o preco deriva da
abertura conforme o dia avanca e os niveis fixos ficam cada vez mais
"fora do dinheiro" (raramente tocados, e quando tocados o contexto de
preco ja' e' outro). Um grid de ancora rolante pura NAO degrada dessa
forma (fica estavel entre R$305 e R$615 em qualquer horario testado), mas
comecando EXATAMENTE na abertura perde para o fixo (R$514 vs R$747) --
abre mao do edge especifico de reversao-ao-redor-da-abertura que parece
so' existir nas primeiras horas do pregao.

Este hibrido tenta capturar os dois: o edge forte e especifico do inicio
do pregao (fixo) sem herdar a degradacao do fim do pregao (rolante).
`fixed_anchor_until` (14:00 UTC por padrao) NAO foi re-otimizado -- e' so'
o ponto medio observavel entre "13:00 ainda positivo" e "15:00 ja'
negativo" na tabela que motivou este desenho; validar/varrer esse corte e'
trabalho futuro, nao presumir que 14:00 e' o otimo.

Uso correto (decidido pelo CALLER, nao pela classe): so' fazer
`warm_start_calibration` (buscar a abertura real via historico) se a hora
de inicio for ANTES de `fixed_anchor_until` -- se nao sobra janela fixa
real, pular o warm-start e deixar o robo rodar cru desde agora (ele ja se
comporta como puro modo rolante nesse caso). Ver
`strategy/daytrade/base.py::warm_start_calibration` e a memoria do
campeao de day trade PMAM3 para o historico completo da investigacao."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
)


@dataclass(frozen=True)
class _SymbolCalibration:
    profit_pct: float
    stop_multiplier: float


# Calibracao por SIMBOLO, medida 2026-08-21 (backtest M1, janela comum
# 2025-09-16..2026-06-13, capital dimensionado ao custo real de 1 lote
# padrao -- day trade nao usa fracionario porque cada ordem fracionaria
# custa R$1,90 fixos na corretora, proibitivo dado o giro alto da gremah).
#
# IMPORTANTE: estes 3 numeros sao IN-SAMPLE APENAS -- o trecho
# out-of-sample reservado (2026-06-13..2026-08-20) AINDA NAO foi rodado
# com eles. Tratar como candidato, nao como resultado validado.
#
# lucro IS medido vs. o antigo default global (0.42%/20x), mesma janela:
#   PMAM3: +R$759,08 vs +R$609,04 (+24,6%)
#   CSAN3: +R$751,82 vs +R$129,54 (+480%)
#   KLBN4: +R$1.226,35 vs +R$146,75 (+736%)
#
# Um simbolo novo exige a MESMA medicao antes de entrar aqui -- ver
# `Gremah.__init__`, que FALHA ALTO (`ValueError`) para qualquer simbolo
# ausente desta tabela em vez de herdar a calibracao de outro papel (jah
# provado que profit_pct/stop_multiplier nao transferem entre precos).
_CALIBRATION_BY_SYMBOL: dict[str, _SymbolCalibration] = {
    "PMAM3": _SymbolCalibration(profit_pct=0.0032, stop_multiplier=10.0),
    "CSAN3": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=20.0),
    "KLBN4": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=5.0),
}


def capital_minimo_brl(preco_atual: float) -> float:
    """Capital minimo para operar um simbolo SEM ordem fracionaria: custo de
    1 lote padrao (100 acoes, corretagem zero na Rico) arredondado PARA CIMA
    ao proximo multiplo de R$50 (pedido explicito do usuario 2026-08-21).

    A folga de seguranca NAO e' um valor somado a parte -- e' a propria
    distancia ate o multiplo de 50 (ex.: PMAM3 a R$0,14 -> lote de R$14,00
    -> R$50,00; CSAN3 a R$3,64 -> lote de R$364,00 -> R$400,00).

    Uso pretendido, AINDA NAO conectado a nada: o saldo em caixa da conta
    deveria ser conferido contra este numero antes de deixar um slot de day
    trade comecar a operar um dado simbolo -- essa checagem mora no
    dashboard/selecao de conta (fora do escopo deste modulo), nao aqui."""
    custo_lote = preco_atual * 100
    return math.ceil(custo_lote / 50.0) * 50.0


@dataclass
class _SessionState:
    open_price: float | None = None
    session_halted: bool = False
    pending_side: str | None = None
    pending_mode: str | None = None  # "fixed" ou "rolling" -- modo em que a ordem pendente foi armada
    pending_bars_waited: int = 0
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None
    spacing_ticks_today: int = 1
    profit_ticks_today: int = 1
    stop_ticks_today: int | None = None


class Gremah(IntradayStrategy):
    """Ancora fixa na abertura ate' `fixed_anchor_until`; ancora rolante
    (preco atual, recalculada a cada recarga) depois disso.

    ESCOPO: desenhada para operar acoes ABAIXO de R$4 (conservador,
    2026-08-21). Achado do MESMO dia (sessao de pesquisa completa, ver
    `_CALIBRATION_BY_SYMBOL` acima): um `profit_pct`/`stop_multiplier`
    GLOBAL nao transfere bem entre simbolos em faixas de preco diferentes
    -- por isso `profit_pct=None`/`stop_multiplier=None` (os defaults do
    construtor) nao sao mais um numero fixo, e' um LOOKUP por `symbol` na
    tabela de calibracao. PMAM3, CSAN3 e KLBN4 tem numeros IN-SAMPLE
    confirmados ali (nao OOS ainda); qualquer outro simbolo faz
    `Gremah.__init__` levantar `ValueError` em vez de herdar a calibracao
    de outro papel -- medir antes de operar, nao presumir. Acima de ~R$6-7
    o alvo (mesmo calibrado) tende a ficar pequeno demais frente ao piso de
    1 tick (`_ticks_from_pct`) -- ainda nao medido, nao usar `symbol=` com
    uma acao mais cara sem recalibrar."""

    name = "gremah"
    version = "0.1"

    # FICHA TECNICA -- documentacao, nunca decisao: nada disto e' lido por
    # `on_bar`. Mesma convencao (e mesmos nomes de atributo) da familia de
    # swing, declarada em `strategy/base.py::Strategy` -- `IntradayStrategy`
    # nao herda de `Strategy` de proposito, entao os atributos moram aqui e
    # quem le (`dashboard/robot_view.py`) usa `getattr` com default vazio.
    # Existe para a pagina `/strategies/gremah` poder explicar o robo em prosa
    # em vez de mostrar so' a tabela de parametros.
    watched_signals = (
        "Abertura da sessão: o `open` da primeira barra vista antes de "
        "`fixed_anchor_until` — é a âncora de toda a fase fixa do dia.",
        "Preço atual (`close` da barra): âncora da fase rolante, recalculada a cada "
        "rearme de ordem.",
        "Relógio do pregão: `fixed_anchor_until` é o que separa a fase de âncora fixa "
        "da rolante.",
        "P&L agregado da sessão, em reais, contra `session_stop_brl`.",
        "Preenchimentos já feitos em cada lado (long/short), contra "
        "`max_trades_per_side`.",
        "Idade da ordem pendente, em barras, contra `rolling_reanchor_after_bars`.",
    )
    entry_rules = (
        "Uma ordem-limite PARADA por vez, `spacing` ticks abaixo da âncora (long) ou "
        "acima (short) — ele espera o preço vir até ele, nunca paga o spread para "
        "entrar.",
        "Os três níveis saem de `profit_pct` sobre a âncora, convertidos em ticks: "
        "alvo = 1×, espaçamento da entrada = `spacing_multiplier`×, stop = "
        "`stop_multiplier`×.",
        "Antes de `fixed_anchor_until`, a âncora é a ABERTURA do dia; depois, é o "
        "PREÇO ATUAL. O corte não foi otimizado — é o ponto médio observável entre "
        "\"13:00 ainda positivo\" e \"15:00 já negativo\" na medição que motivou o "
        "desenho.",
        "Alterna de lado: depois de fechar um long tenta o short primeiro, e só "
        "insiste no mesmo lado quando o outro estourou `max_trades_per_side`.",
        "Ordem parada obsoleta é abandonada e rearmada no preço/modo atuais — a que "
        "foi armada na fase fixa quando o relógio já virou, e a rolante que esperou "
        "`rolling_reanchor_after_bars` barras sem ser tocada.",
    )
    exit_rules = (
        "Alvo: ordem-limite parada a `profit_pct` do preço de entrada. Sair como MAKER "
        "é o centro do desenho (`target_fills_as_maker`) — capturar o spread em vez de "
        "pagá-lo —, não um detalhe de modelagem.",
        "Stop: `stop_multiplier`× a distância do alvo, na direção contrária.",
        "Stop agregado da sessão: perda acumulada de `session_stop_brl` fecha a posição "
        "aberta e encerra o dia — nada mais é armado até o próximo pregão.",
        "Nunca carrega posição overnight: o motor achata no fim da sessão, pelo "
        "calendário da B3 (`session_end_policy`), não por um horário fixo.",
    )
    sizing_rules = (
        "`quantity` fixa por ordem. `None` = usa o `default_quantity` do perfil do "
        "símbolo (PMAM3: 100 ações, um lote padrão).",
        "Custo do perfil congelado do símbolo (`backtest/intraday/profiles.py`): "
        "corretagem zero em lote padrão na Rico, mais taxa de bolsa por perna — "
        "assumida ao DOBRO da real, de propósito, como margem de segurança.",
        "Giro alto é o risco econômico do desenho: cada round-trip paga taxa de bolsa "
        "duas vezes, e `max_trades_per_side` é o teto que limita isso por sessão.",
    )
    param_docs = {
        "symbol": "Ativo que ele negocia.",
        "tick_size": "Variação mínima de preço do ativo.",
        "profit_pct": "Alvo de lucro por trade, em % do preço da âncora. Vazio = lookup por "
                      "símbolo em `_CALIBRATION_BY_SYMBOL` (falha se o símbolo não estiver lá).",
        "spacing_multiplier": "Distância da entrada, em múltiplos do alvo.",
        "stop_multiplier": "Distância do stop, em múltiplos do alvo. Vazio = mesmo lookup de "
                           "`profit_pct`.",
        "max_trades_per_side": "Teto de preenchimentos por lado, por sessão.",
        "session_stop_brl": "Perda acumulada, em reais, que encerra o dia.",
        "quantity": "Quantidade por ordem. Vazio = default do perfil do símbolo.",
        "fixed_anchor_until": "Hora (UTC) em que a âncora fixa vira rolante.",
        "rolling_reanchor_after_bars": "Barras que uma ordem rolante espera antes de rearmar.",
    }
    # A saida por alvo deste robo e uma ordem-limite parada no nivel: e o
    # centro do desenho (capturar o spread em vez de paga-lo), nao um
    # detalhe de modelagem. Ver `IntradayStrategy.target_fills_as_maker`.
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "PMAM3",
        tick_size: float = 0.01,
        profit_pct: float | None = None,
        spacing_multiplier: float = 2.0,
        stop_multiplier: float | None = None,
        max_trades_per_side: int = 15,
        session_stop_brl: float = 30.0,
        quantity: int | None = None,
        fixed_anchor_until: time = time(14, 0),
        rolling_reanchor_after_bars: int = 30,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        # `None` (o default) = busca a calibracao do SIMBOLO na tabela
        # (mesmo padrao de `default_quantity` em
        # `backtest/intraday/profiles.py::config_for`: sentinela `None`
        # resolvido aqui dentro, nunca herdado de outro papel). Quem passa
        # `profit_pct=`/`stop_multiplier=` explicito sempre vence o lookup.
        if profit_pct is None or stop_multiplier is None:
            calib = _CALIBRATION_BY_SYMBOL.get(symbol)
            if calib is None:
                raise ValueError(
                    f"gremah: sem calibracao para o simbolo {symbol!r} em "
                    "_CALIBRATION_BY_SYMBOL (strategy/daytrade/lab/gremah.py). "
                    "profit_pct/stop_multiplier NAO transferem entre simbolos "
                    "(medido 2026-08-21) -- passe profit_pct= e "
                    "stop_multiplier= explicitamente, ou meca este simbolo "
                    "(backtest IS + OOS) e adicione-o a tabela antes de "
                    "operar com o default."
                )
            if profit_pct is None:
                profit_pct = calib.profit_pct
            if stop_multiplier is None:
                stop_multiplier = calib.stop_multiplier
        self.profit_pct = profit_pct
        self.spacing_multiplier = spacing_multiplier
        self.stop_multiplier = stop_multiplier
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = abs(session_stop_brl)
        self.quantity = quantity
        self.fixed_anchor_until = fixed_anchor_until
        # uma ordem ROLANTE parada esperando por muitas barras acumula o
        # MESMO problema que motivou abandonar a ordem fixa na troca de
        # fase: seu preco de ancora (o preco de QUANDO foi armada) vai
        # ficando cada vez mais desatualizado frente ao preco ATUAL.
        # Achado empirico (2026-08-21): sem isso, uma ordem herdada do
        # warm-start (armada perto do fim da fase fixa, nunca tocada) fica
        # parada com ancora velha por horas ate' o robo comecar a operar
        # de verdade num horario atrasado -- o hibrido ficava pior que a
        # rolling pura em todo horario de entrada atrasada.
        self.rolling_reanchor_after_bars = rolling_reanchor_after_bars

        self._state = _SessionState()

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def _ticks_from_pct(self, price: float, pct: float) -> int:
        return max(1, round(price * pct / self.tick_size))

    def _arm_fixed_session_params(self) -> None:
        price = self._state.open_price
        self._state.profit_ticks_today = self._ticks_from_pct(price, self.profit_pct)
        self._state.spacing_ticks_today = self._ticks_from_pct(price, self.profit_pct * self.spacing_multiplier)
        self._state.stop_ticks_today = self._ticks_from_pct(price, self.profit_pct * self.stop_multiplier)

    def _fills_of(self, side: str) -> int:
        return self._state.long_fills if side == "long" else self._state.short_fills

    def _next_side_to_arm(self) -> str | None:
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def _build_entry(self, side: str, anchor: float, spacing_ticks: int, profit_ticks: int, stop_ticks: int | None) -> EnterLimit:
        spacing_off = spacing_ticks * self.tick_size
        level_price = round(anchor - spacing_off, 2) if side == "long" else round(anchor + spacing_off, 2)
        profit_off = profit_ticks * self.tick_size
        target_price = level_price + profit_off if side == "long" else level_price - profit_off
        stop_price = None
        if stop_ticks is not None:
            stop_off = stop_ticks * self.tick_size
            stop_price = level_price - stop_off if side == "long" else level_price + stop_off
        return EnterLimit(
            side=side,
            limit_price=level_price,
            initial_target=target_price,
            initial_stop=stop_price,
            quantity=self.quantity,
            reason="gremah_" + side,
        )

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []
        is_fixed_phase = ts.time() < self.fixed_anchor_until

        if is_fixed_phase and state.open_price is None:
            state.open_price = bar.open
            self._arm_fixed_session_params()

        if not state.session_halted and session_pnl_brl <= -self.session_stop_brl:
            state.session_halted = True
            if position is not None:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if position is not None:
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                state.pending_bars_waited = 0
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        # ordem pendente parada ficou obsoleta de 1 de 2 jeitos: (a) foi
        # armada na fase FIXA e o relogio ja passou pra fase ROLANTE --
        # nivel so' fazia sentido perto da abertura; (b) foi armada em
        # modo ROLANTE mas ja' esperou tempo demais sem tocar -- seu
        # preco de ancora (de QUANDO foi armada) ja' ficou velho frente
        # ao preco atual. Nos dois casos: abandona (o motor substitui a
        # resting_limit pela nova `EnterLimit` devolvida abaixo) e
        # re-arma no modo/preco atual, mesmo lado.
        stale_fixed_order = state.pending_side is not None and state.pending_mode == "fixed" and not is_fixed_phase
        stale_rolling_order = (
            state.pending_side is not None and state.pending_mode == "rolling"
            and state.pending_bars_waited >= self.rolling_reanchor_after_bars
        )
        stale_order = stale_fixed_order or stale_rolling_order
        if state.pending_side is not None and not stale_order:
            state.pending_bars_waited += 1
            return actions

        next_side = state.pending_side if stale_order else self._next_side_to_arm()
        if next_side is None:
            return actions

        state.pending_side = next_side
        state.pending_bars_waited = 0
        state.pending_mode = "fixed" if is_fixed_phase else "rolling"
        if is_fixed_phase:
            entry = self._build_entry(
                next_side, state.open_price,
                state.spacing_ticks_today, state.profit_ticks_today, state.stop_ticks_today,
            )
        else:
            anchor = bar.close
            profit_ticks = self._ticks_from_pct(anchor, self.profit_pct)
            spacing_ticks = self._ticks_from_pct(anchor, self.profit_pct * self.spacing_multiplier)
            stop_ticks = self._ticks_from_pct(anchor, self.profit_pct * self.stop_multiplier)
            entry = self._build_entry(next_side, anchor, spacing_ticks, profit_ticks, stop_ticks)
        return [entry]
