# -*- coding: utf-8 -*-
"""`WinBuscaLucroG11OrbTamanhoGraduado` -- Geracao 11 da busca por um EA
lucrativo do WIN.

Mandato do COORDENADOR (nao o orquestrador -- a G10 tinha concluido a busca,
o coordenador pediu para continuar testando 4 alavancas ainda nao tentadas).
Esta geracao ataca a alavanca (1): "tamanho de mao graduado pela forca do
sinal" -- teoria dos jogos do dono, "sinal fraco muda o TAMANHO da mao, nao
so' entra/nao entra".

A R$250 so' cabe 1 contrato (`contracts_from_capital_operacional` nunca libera
o 2o sem a pilha cheia de R$250 dedicada a isso -- ver CLAUDE.md "Capital
inicial: sempre o minimo real"). Entao "tamanho de mao" aqui NAO pode ser
"meio contrato": a traducao discreta do principio e' **so' operar o(s)
balde(s) de sinal FORTE, zero contrato (nao entra) no sinal fraco** -- o
equivalente binario de "mao maior no sinal forte, mao zero no fraco" quando
so' existe 0 ou 1 contrato disponivel. Essa e' a razao de desenho central
desta classe: ela NAO aposta em escalar quantidade, aposta em SELECIONAR
quais sinais (pela forca do rompimento) merecem a unica mao disponivel.

## Copia deliberada da G8 (mesma logica de deteccao de rompimento)

Esta classe e' uma copia DELIBERADA de `WinBuscaLucroG08OrbSobrevivencia`
(`win_busca_lucro_g08_orb_sobrevivencia.py`) -- mesma logica de deteccao de
rompimento da faixa de abertura, mesmos contadores de auditoria (item
6.48/6.49), mesmo desenho de execucao fechado, mesmo teto de 1 operacao
real/pregao (sem fade). A UNICA mudanca de SINAL em relacao a` G8 e' um
FILTRO adicional por "forca do rompimento", aplicado DEPOIS dos filtros de
posicao/ja-armado-hoje da G8 e ANTES de montar a ordem -- nada na deteccao
de rompimento, na geometria stop/alvo ou no teto de 1 trade/dia muda.
Arquivo separado (nao subclasse de G08), mesmo motivo de toda geracao
anterior: cada geracao congela seu proprio modulo
(`..._congelado_vNN.py`) e uma edicao futura de G08 nunca pode afetar,
silenciosamente, o resultado ja' registrado desta geracao.

## Forca do rompimento -- definicao causal, uma unica medida

`forca_relativa = (preco ALEM do nivel rompido) / (tamanho da propria faixa
de abertura)`, calculada no INSTANTE do proprio rompimento (fechamento da
barra que dispara `nova_alta`/`nova_baixa`), usando so' valores ja' conhecidos
nesse instante (a faixa fechada nos primeiros `range_minutos`, e o
fechamento da barra atual) -- nenhum look-ahead. Um rompimento de 2x o
tamanho da faixa (`forca_relativa=2,0`) e' "mais forte" que um de 1,05x
(`forca_relativa=0,05`) no sentido literal do mandato do coordenador (item
1: "magnitude do rompimento alem da faixa, relativa ao tamanho da propria
faixa"). E' uma MEDIDA, nao um filtro -- `stats_forcas` grava a forca de
TODA borda bruta (antes de qualquer filtro de posicao/armado/balde),
exatamente o que o harness desta geracao usa para definir os cortes de
balde (tercis) causalmente, so' com o IS (ver `g11_base.py`/`g11_is_busca.py`).

`forca_min`/`forca_max` sao os limites do BALDE que esta instancia opera
(`forca_min <= forca_relativa < forca_max`); o default (0, +inf) reproduz
EXATAMENTE o comportamento da G8 -- sem filtro de forca -- e serve de
REFERENCIA lado a lado na mesma tabela.

## Desenho de execucao (FECHADO -- CLAUDE.md, nao negociavel)

Identico a` G8: `EnterLimit` com `ttl_bars`; limite `buffer_entrada_pontos`
atras do rompimento; alvo por ordem-limite real fatiada (`exit_split_unit`),
SEM prazo; `anchor_exits_at_fill=True`; so' o STOP e' a mercado;
`target_fills_as_maker=True`. Fila do WIN@ NAO calibrada (premissa otimista
declarada pelo harness). Capital real R$250, 1 contrato fixo (a politica de
"tamanho graduado" desta geracao e' SELECAO de sinal, nunca escala de
quantidade -- ver docstring acima).

## Geometria -- herdada do vencedor da G8, fixa nesta geracao

`stop = clip(faixa_de_abertura, stop_min_pontos, stop_max_pontos)`; `alvo =
stop x alvo_multiplo` (sempre >= 3x por construcao). Default
`stop_max_pontos=140` e' o vencedor composto da G8 (menor p_ruina entre as
celulas nao-censuradas) -- esta geracao NAO revisita a geometria, so' o
filtro de forca, para isolar o efeito desta alavanca especifica.
"""
from __future__ import annotations

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG11OrbTamanhoGraduado"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G10 desta busca.
TTL_BARRAS_ENTRADA = 10


class WinBuscaLucroG11OrbTamanhoGraduado(IntradayStrategy):
    """ORB momentum (mesma deteccao de `WinBuscaLucroG08OrbSobrevivencia`),
    filtrado por um balde de FORCA RELATIVA do rompimento -- Geracao 11
    testa se graduar a selecao do sinal pela sua magnitude (em vez de tratar
    todo rompimento como igual, como G7-G10 fizeram) produz um balde com
    win%/payoff genuinamente melhor que o sinal nao filtrado."""

    name = "win_busca_lucro_g11_orb_tamanho_graduado"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        range_minutos: float = 5.0,
        stop_min_pontos: float = 50.0,
        stop_max_pontos: float = 140.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        forca_min: float = 0.0,
        forca_max: float = float("inf"),
        quantity: int = 1,
    ) -> None:
        if range_minutos <= 0:
            raise ValueError("range_minutos tem que ser positivo")
        if stop_min_pontos <= 0:
            raise ValueError("stop_min_pontos tem que ser positivo")
        if stop_max_pontos < stop_min_pontos:
            raise ValueError("stop_max_pontos tem que ser >= stop_min_pontos")
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
        if forca_min < 0:
            raise ValueError("forca_min nao pode ser negativo")
        if forca_max <= forca_min:
            raise ValueError("forca_max tem que ser > forca_min")
        if symbol is not None:
            self.symbol = symbol
        self.range_minutos = float(range_minutos)
        self.stop_min_pontos = float(stop_min_pontos)
        self.stop_max_pontos = float(stop_max_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.forca_min = float(forca_min)
        self.forca_max = float(forca_max)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49) --
        self.stats_bruto = 0
        self.stats_ja_operou_hoje = 0
        self.stats_ordens_emitidas = 0
        self.stats_fora_forca = 0
        #: forca_relativa de TODA borda bruta (antes de qualquer filtro) --
        #: populacao usada pelo harness para definir os cortes de balde
        #: (tercis), causalmente, so' com o IS.
        self.stats_forcas: list[float] = []
        #: forca_relativa DA ORDEM QUE VIROU TRADE (preenchida), uma entrada
        #: por trade real, na mesma ordem cronologica de `result.trades` --
        #: estratificacao POS-HOC dos trades realmente executados pela forca
        #: do rompimento que os originou (evita o vies de "qual edge do dia
        #: foi escolhido" que um balde EXCLUSIVO introduziria -- ver
        #: `g11_is_busca.py`, analise pos-hoc da REF).
        self.stats_forca_das_entradas: list[float] = []
        self._pendente_forca: float = 0.0

        self._reset_sessao()

    # -- estado por sessao ---------------------------------------------------
    def _reset_sessao(self) -> None:
        self._open_ts: pd.Timestamp | None = None
        self._range_hi: float | None = None
        self._range_lo: float | None = None
        self._fora_hi = False
        self._fora_lo = False
        self._armou_hoje = False
        self._preencheu_hoje = False
        self._tinha_posicao_anterior = False

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    # -- geometria (pura) -----------------------------------------------------
    def _geometria(self) -> tuple[float, float]:
        """`(stop_pontos, alvo_pontos)` -- identico a` G8: stop sai do
        tamanho da faixa, limitado entre piso e teto; alvo = stop x
        `alvo_multiplo` (>= 3x por construcao). Arredondado a` grade de
        preco do WIN@ (5 pontos)."""
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        stop = max(self.stop_min_pontos, min(self.stop_max_pontos, range_pontos))
        stop = round(stop / self.tick_size) * self.tick_size
        alvo = round((stop * self.alvo_multiplo) / self.tick_size) * self.tick_size
        return float(stop), float(alvo)

    def _forca_rompimento(self, bar_close: float, nova_alta: bool) -> float:
        """Magnitude do rompimento ALEM da faixa, relativa ao tamanho da
        propria faixa de abertura -- `(preco alem do nivel rompido) /
        (faixa_hi - faixa_lo)`. Causal: so' usa a faixa ja' fechada
        (`_range_hi`/`_range_lo`, calculados nos primeiros `range_minutos`)
        e o fechamento da PROPRIA barra de rompimento -- nenhum dado futuro.
        `0.0` se a faixa tiver tamanho zero (degenerado, nunca deveria
        acontecer com dado real, mas evita divisao por zero)."""
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        if range_pontos <= 0:
            return 0.0
        if nova_alta:
            return (bar_close - self._range_hi) / range_pontos
        return (self._range_lo - bar_close) / range_pontos

    def _ordem(self, side: str, limite: float, stop_pontos: float,
               alvo_pontos: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(limite, self.tick_size)
        return EnterLimit(
            side=side,
            limit_price=limite,
            initial_stop=no_tick(limite - sinal * stop_pontos, self.tick_size),
            initial_target=no_tick(limite + sinal * alvo_pontos, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=reason,
        )

    # -- loop -------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._open_ts is None:
            self._open_ts = ts

        # Transicao de posicao -- estado do INICIO da barra (item 6.48):
        # `positions` ja' reflete qualquer fill desta barra. So' existe 1
        # operacao REAL possivel por pregao nesta geracao (sem fade), entao
        # a transicao vazio->nao-vazio so' pode acontecer uma vez por dia.
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            self._preencheu_hoje = True
            self.stats_forca_das_entradas.append(self._pendente_forca)
        self._tinha_posicao_anterior = tem_posicao_agora

        # (1) os primeiros `range_minutos`: so' olha e mede a faixa.
        if (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos):
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            return []

        # (2) o estado de rompimento (fora_hi/fora_lo) e' SEMPRE atualizado,
        # com posicao aberta ou nao -- item 6.48 (mesma disciplina da G07/G08).
        if self._range_hi is None or self._range_lo is None:
            return []

        rompeu_alta = bar.close > self._range_hi
        rompeu_baixa = bar.close < self._range_lo

        # Borda NOVA -- transicao de "dentro"/"ja rompido no mesmo sentido
        # sem reentrar" para um rompimento FRESCO. Nao conta de novo barra a
        # barra enquanto o preco so' permanece fora (ver docstring da classe).
        nova_alta = rompeu_alta and not self._fora_hi
        nova_baixa = rompeu_baixa and not self._fora_lo
        self._fora_hi = rompeu_alta
        self._fora_lo = rompeu_baixa

        if not (nova_alta or nova_baixa):
            return []

        # BRUTO: toda borda de rompimento, ANTES de qualquer filtro de
        # "posicao aberta"/"ja armado"/"ja operou hoje"/"balde de forca"
        # (item 6.48). A forca e' gravada AQUI, para a populacao de
        # `stats_forcas` nao sofrer vies de selecao dos filtros seguintes.
        self.stats_bruto += 1
        forca = self._forca_rompimento(bar.close, nova_alta)
        self.stats_forcas.append(forca)

        if positions:
            return []
        if self._preencheu_hoje:
            self.stats_ja_operou_hoje += 1
            return []
        if self._armou_hoje:
            return []
        if not (self.forca_min <= forca < self.forca_max):
            self.stats_fora_forca += 1
            return []

        stop_pontos, alvo_pontos = self._geometria()
        buf = self.buffer_entrada_pontos
        self._pendente_forca = forca
        if nova_alta:
            limite = bar.close - buf
            self._armou_hoje = True
            self.stats_ordens_emitidas += 1
            return [self._ordem("long", limite, stop_pontos, alvo_pontos,
                                "g11_orb_tamanho_graduado_rompimento_alta")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos,
                            "g11_orb_tamanho_graduado_rompimento_baixa")]
