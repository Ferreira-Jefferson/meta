# -*- coding: utf-8 -*-
"""`WinBuscaLucroG06AmplitudeTeto` -- Geracao 6 da busca por um EA lucrativo do WIN.

Pergunta desta geracao (`ORQUESTRACAO.md`, raciocinio deixado pela Geracao 5):
a G5 achou que o proxy `regime_amplitude_bloco` (continuacao da pernada maior
quando a amplitude de um bloco de 15min supera o quantil causal 0,90 condi-
cionado ao horario) bate win% POSITIVO com folga grande de amostra (667
trades, IC95 [27,4%;34,3%] acima do breakeven empirico 27,3%) -- mas a
concentracao top-3-pregoes/liquido fica EXATAMENTE igual a` da G4 (59%), nao
menor, apesar de 5x mais trades. A auditoria por pregao da G5 mostrou o
motivo: o proxy realmente opera em mais dias (95/122 contra 62/122 da G4),
mas RE-DISPARA dezenas de vezes DENTRO do mesmo pregao favoravel (maximo 24
operacoes num unico dia, 2026-03-03) -- a amostra "maior" e', em boa parte, a
MESMA informacao ressonando mais vezes nos poucos dias que ja eram bons, nao
uma amostra mais independente.

Esta geracao testa se limitar o numero de REENTRADAS por pregao (parametro
`max_trades_por_pregao`) devolve a concentracao para perto de 35-40% mantendo
a maior parte do liquido e um win%/breakeven favoravel -- ou se a causa e'
mais profunda (distribuicao de caudas do proprio WIN, nao desenho do robo).

## Desenho -- identico a` G5, so' ACRESCENTA o teto de reentradas

Mesma geometria/execucao da G5 (que ja herdava da G4): continuacao da pernada
maior (R43, 750 pontos, inegociavel), `EnterLimit` com `ttl_barras_entrada`,
stop/alvo em PONTOS fixos (`alvo_multiplo >= 3.0` por construcao), alvo so'
como limite fatiada sem prazo, so' o stop a mercado, `anchor_exits_at_fill`,
`target_fills_as_maker`, 1 contrato fixo, fila WIN@ nao calibrada (premissa
otimista declarada pelo harness).

A UNICA mudanca de comportamento desta geracao e' `max_trades_por_pregao:
int | None` -- quando setado, a estrategia para de ARMAR novas entradas no
dia corrente assim que `max_trades_por_pregao` posicoes JA TIVEREM SIDO
ABERTAS naquele pregao (nao tentadas -- abertas de verdade, ver abaixo).
`None` (default) = sem teto, comportamento identico ao da G5.

## Decisao de QUAL trade manter quando ha' mais de um candidato no pregao

O criterio e' o mais simples e causal possivel: os PRIMEIRO(S)
`max_trades_por_pregao` sinais do pregao, na ORDEM EM QUE O GATILHO DISPARA.
Nao ha' selecao retroativa de "qual foi o melhor sinal do dia" -- isso seria
look-ahead (a estrategia nao pode saber, no momento de armar o 1o sinal,
se um 2o ou 3o sinal mais tarde no mesmo dia teria sido melhor). O motor so'
bloqueia a EMISSAO de sinais ALEM do teto; os que chegam primeiro sempre
passam (sujeitos aos filtros de sempre: pernada definida, sem posicao aberta,
sem ordem pendente).

## Contagem do teto -- a parte que exige cuidado (item 6.48 de
LICOES_DE_PRODUCAO.md: ordem de operacoes dentro de `on_bar` decide se um
contador mede o que deveria)

O contador `self._trades_abertos_hoje` so' incrementa quando uma posicao e'
ABERTA DE VERDADE -- nunca quando uma ordem e' apenas EMITIDA (`EnterLimit`
pode ser rejeitada por teto/capital, pode expirar por TTL sem preencher, ou
pode preencher). O motor (`IntradaySessionMachine.on_bar`, ver `machine.py`)
ja' processa qualquer fill de ordem-limite pendente ANTES de chamar
`strategy.on_bar(...)` na mesma passada de barra -- ou seja, o argumento
`positions` que `on_bar` recebe JA' reflete o fill desta barra, se houve um.
Isso permite detectar "uma posicao nova abriu" por uma simples transicao de
estado (vazio -> nao-vazio) LIDA NO INICIO de `on_bar`, no MESMO lugar e pela
MESMA razao que `pode_armar` ja' le o `_espera` do inicio da barra (G2/G4/G5):
ler o estado ANTES de qualquer atualizacao feita nesta chamada evita o exato
bug do item 6.48 (um contador que apaga, na mesma passada, o que acabou de
contar). Como esta estrategia nunca tem mais de 1 posicao simultanea (o
motor nao piramida, e uma nova `EnterLimit` so' e' colocada quando `not
self.positions`), a transicao vazio->nao-vazio ocorre no MAXIMO uma vez por
fill, nunca duas vezes para o mesmo trade.

O teto e' verificado (`self._trades_abertos_hoje >= max_trades_por_pregao`)
no MESMO ponto onde `pode_armar` ja' e' computado -- antes de ler a borda do
regime -- e reseta em `on_session_start` (zero reentradas no pregao novo).
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)
# Reusa a funcao pura de proxy da G5 -- nao duplica a logica de deteccao de
# regime, so' a classe de estrategia muda (teto de reentradas).
from strategy.daytrade.lab.win_busca_lucro_g05_regime_vol import (
    regime_amplitude_bloco,
)

__all__ = ["WinBuscaLucroG06AmplitudeTeto", "regime_amplitude_bloco"]

#: Limiar da pernada maior (zigzag causal sobre o caminho da vela, R43).
#: Nao e' parametro desta geracao -- mesmo valor de G1-G5.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Dias INTEIROS de historico, estritamente anteriores ao dia corrente,
#: exigidos antes de qualquer quantil/media causal comecar a valer -- mesmo
#: valor da G5 (usado so' pelo proxy, reexportado para o harness).
MIN_DIAS_BURN_IN = 20


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """O "caminho" desta vela -- definicao CONGELADA em `REGRAS.md`, identica
    a` usada em R43/R65/R57/G4/G5. Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


class WinBuscaLucroG06AmplitudeTeto(IntradayStrategy):
    """Opera o WIN@ na direcao de CONTINUACAO da pernada maior em curso (R43)
    sempre que o proxy `regime_amplitude_bloco` (G5) dispara uma borda nova,
    com um TETO opcional de quantas posicoes podem ser ABERTAS no mesmo
    pregao -- Geracao 6 da busca por um EA lucrativo do WIN
    (`ORQUESTRACAO.md`)."""

    name = "win_busca_lucro_g06_amplitude_teto"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        regime_ativo: pd.Series,
        symbol: str | None = None,
        pernada_pontos: float = PERNADA_PONTOS,
        stop_pontos: float = 150.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 30.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        max_trades_por_pregao: int | None = None,
        quantity: int = 1,
    ) -> None:
        if pernada_pontos <= 0:
            raise ValueError("pernada_pontos tem que ser positivo")
        if stop_pontos <= 0:
            raise ValueError("stop_pontos tem que ser positivo")
        if alvo_multiplo < 3.0:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo de 3x -- fere a disciplina "
                f"alvo >= 3x o stop do mandato do dono")
        if buffer_entrada_pontos < 0:
            raise ValueError("buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if max_trades_por_pregao is not None and max_trades_por_pregao <= 0:
            raise ValueError("max_trades_por_pregao, quando setado, tem que ser >= 1")
        if symbol is not None:
            self.symbol = symbol
        self._regime_ativo = (
            regime_ativo.to_dict() if isinstance(regime_ativo, pd.Series) else dict(regime_ativo)
        )
        self.pernada_pontos = float(pernada_pontos)
        self.stop_pontos = float(stop_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.max_trades_por_pregao = (
            int(max_trades_por_pregao) if max_trades_por_pregao is not None else None
        )
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (licao da G2/G4/G5 / item 6.48) --
        self.stats_bruto = 0
        self.stats_sem_tendencia = 0
        self.stats_teto_pregao = 0  # descartado so' por ja' ter batido o teto do dia
        self.stats_ordens_emitidas = 0

        self._reset_sessao()

    # -- estado por sessao --------------------------------------------------
    def _reset_sessao(self) -> None:
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        self._regime_anterior = False
        self._espera: int | None = None
        self._hist: deque[Bar] = deque(maxlen=4)
        self._trades_abertos_hoje = 0
        self._tinha_posicao_anterior = False

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._espera = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._espera = None

    # -- pernada maior (R43) --------------------------------------------------
    def _atualiza_perna(self, p: float) -> None:
        if self._origem is None:
            self._origem = p
            self._extremo = p
            return
        s = self._direcao
        if s is None:
            if p - self._origem >= self.pernada_pontos:
                self._direcao = 1
                self._extremo = p
            elif self._origem - p >= self.pernada_pontos:
                self._direcao = -1
                self._extremo = p
            return
        if s == 1:
            if p > self._extremo:
                self._extremo = p
            elif self._extremo - p >= self.pernada_pontos:
                self._origem = self._extremo
                self._direcao = -1
                self._extremo = p
        else:
            if p < self._extremo:
                self._extremo = p
            elif p - self._extremo >= self.pernada_pontos:
                self._origem = self._extremo
                self._direcao = 1
                self._extremo = p

    def _monta_entrada(self, direcao_entrada: int, bar: Bar) -> IntradayAction | None:
        buf = self.buffer_entrada_pontos
        if direcao_entrada == 1:
            lado = "long"
            limite = bar.close - buf
            stop = limite - self.stop_pontos
            alvo = limite + self.alvo_multiplo * self.stop_pontos
        else:
            lado = "short"
            limite = bar.close + buf
            stop = limite + self.stop_pontos
            alvo = limite - self.alvo_multiplo * self.stop_pontos

        limite = no_tick(limite, self.tick_size)
        if lado == "long" and limite >= bar.close:
            return None
        if lado == "short" and limite <= bar.close:
            return None

        self._espera = 0
        return EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=f"g06_amplitude_teto_s{self.stop_pontos:.0f}_a{self.alvo_multiplo:.0f}x",
        )

    # -- loop -----------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)

        # Contagem do teto diario -- estado do INICIO da barra (item 6.48):
        # `positions` ja' reflete qualquer fill desta barra (o motor processa
        # fills de ordem-limite pendente ANTES de chamar `on_bar`), entao uma
        # transicao vazio->nao-vazio aqui e' uma posicao ABERTA DE VERDADE,
        # nunca uma ordem so' emitida/tentada. So' 1 posicao por vez existe
        # nesta estrategia, entao essa transicao acontece no maximo 1x por
        # fill -- nunca conta o mesmo trade duas vezes.
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            self._trades_abertos_hoje += 1
        self._tinha_posicao_anterior = tem_posicao_agora

        pode_armar = True
        if positions:
            self._espera = None
            pode_armar = False
        elif self._espera is not None:
            self._espera += 1
            if self._espera < self.ttl_barras_entrada:
                pode_armar = False
            else:
                self._espera = None

        teto_batido = (
            self.max_trades_por_pregao is not None
            and self._trades_abertos_hoje >= self.max_trades_por_pregao
        )
        if teto_batido:
            pode_armar = False

        for p in _caminho_da_barra(bar):
            self._atualiza_perna(p)

        ativo_agora = bool(self._regime_ativo.get(ts, False))
        disparo_novo = ativo_agora and not self._regime_anterior
        self._regime_anterior = ativo_agora

        if not disparo_novo:
            return []

        # BRUTO: toda borda de regime, ANTES de qualquer filtro de
        # tendencia/execucao/capital/teto.
        self.stats_bruto += 1

        if self._direcao is None:
            # Pernada maior ainda nao definida quando o regime disparou --
            # nao ha' direcao a seguir. DESCARTA.
            self.stats_sem_tendencia += 1
            return []

        if teto_batido:
            # Gatilho real, tendencia definida, mas o pregao ja' bateu o
            # teto de reentradas -- descarta SEM contar como "sem tendencia"
            # nem misturar com o descarte por posicao/espera aberta (esses
            # dois ja' existiam antes desta geracao e nao tem contador
            # proprio porque sao transitorios, nao uma decisao de desenho).
            self.stats_teto_pregao += 1
            return []

        if not pode_armar:
            return []

        acao = self._monta_entrada(self._direcao, bar)
        if acao is None:
            return []
        self.stats_ordens_emitidas += 1
        return [acao]
