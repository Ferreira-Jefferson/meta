# -*- coding: utf-8 -*-
"""`WinBuscaLucroG10OrbTendenciaDiaria` -- Geracao 10 da busca por um EA
lucrativo do WIN.

Pergunta desta geracao (`ORQUESTRACAO.md`, raciocinio deixado pela G7/G8/G9):
nenhuma das 9 geracoes anteriores testou um FILTRO DE REGIME (tendencia
DIARIA) sobre o ORB momentum -- a familia que mais perto chegou de
sobreviver (G8: liquido+R$1.365,50 no IS, mas p_ruina(MC)=24,8%, e morreu no
OOS-1 com as 5 primeiras operacoes todas perdedoras). A hipotese: so'
permitir o rompimento DA FAIXA DE ABERTURA quando a TENDENCIA DIARIA do WIN@
concorda com a direcao do rompimento pode (a) subir o win% o suficiente para
folgar contra o breakeven, e/ou (b) mesmo sem subir o win%, encurtar a
sequencia esperada de perdas (menos trades contra-tendencia ruidosos),
reduzindo p_ruina. REGRAS.md R45 ja testou algo parecido (recuo raso) e deu
inconclusivo -- mandato do dono explicito pede para tentar de novo com uma
geometria de ENTRADA diferente antes de descartar a ideia.

Esta classe e' uma copia DELIBERADA de `WinBuscaLucroG08OrbSobrevivencia`
(mesmo rompimento da faixa de abertura, mesmos contadores de auditoria item
6.48/6.49, mesmo desenho de execucao fechado, mesmo teto de 1 operacao
real/pregao) -- a UNICA mudanca de SINAL e' o filtro de tendencia diaria
aplicado ANTES de qualquer outro gate (posicao aberta / ja operou hoje /
ja armou). Arquivo separado, nao subclasse de G08, mesmo motivo de sempre:
cada geracao desta busca congela seu proprio modulo e uma edicao futura de
um modulo de geracao anterior nunca pode afetar, silenciosamente, o
resultado ja registrado de uma geracao posterior.

## O filtro de tendencia diaria -- causal, calculado FORA da classe

A classe NAO calcula a tendencia -- ela recebe `direcao_diaria: dict[date,
int]` pronto (mesmo padrao de `regime_ativo` em `WinBuscaLucroG05RegimeVol`),
onde `1`=favorece LONG (so' aceita rompimento de alta), `-1`=favorece SHORT
(so' aceita rompimento de baixa), `0`=neutro/indefinido (bloqueia os dois
lados -- "nunca contra a tendencia" inclui "nunca sem tendencia definida").
Quem monta esse dict (`g10_base.compute_direcao_diaria`) usa SO' o fechamento
DIARIO do WIN@ ate' o dia ANTERIOR (nunca o fechamento do proprio dia D),
preservando a regra de nao-antecipacao mesmo operando em cima de uma serie
diaria -- ver a docstring de `compute_direcao_diaria` para o detalhe do
burn-in causal (pode olhar para 2025 so' para CALCULAR a media movel que ja'
existe em janeiro/2026, nunca para medir P&L).

## Desenho de execucao (FECHADO -- CLAUDE.md, nao negociavel)

Identico a G07/G08: `EnterLimit` com `ttl_bars` (nunca `Enter` a mercado);
limite `buffer_entrada_pontos` atras do rompimento; alvo por ordem-limite
real fatiada (`exit_split_unit`), SEM prazo (`exit_ttl_bars=None`);
`anchor_exits_at_fill=True`; so' o STOP e' a mercado; `target_fills_as_maker=
True`. Fila do WIN@ NAO calibrada -- toda ordem-limite enche no TOQUE
(premissa otimista declarada pelo harness). Capital real R$250, 1 contrato
fixo (politica desta busca: nunca escalar).

## Geometria -- herdada do vencedor da G8, NAO revisitada aqui

`stop_max_pontos=140` (vencedor composto da G8) e' o PONTO DE PARTIDA desta
geracao -- o eixo que esta geracao varia e' o filtro de tendencia, nao a
geometria de stop/alvo. `stop = clip(faixa_de_abertura, stop_min_pontos,
stop_max_pontos)`; `alvo = stop x alvo_multiplo`, sempre >= 3x por
construcao (mesma guarda de G06-G08).
"""
from __future__ import annotations

import datetime as _dt

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG10OrbTendenciaDiaria"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G9 desta busca.
TTL_BARRAS_ENTRADA = 10


class WinBuscaLucroG10OrbTendenciaDiaria(IntradayStrategy):
    """Rompimento da faixa de abertura do WIN@ (mesma logica da G07/G08),
    agora SO' na direcao em que a tendencia DIARIA concorda -- no maximo 1
    operacao REAL por pregao, mesmo quando a tendencia favorece o lado."""

    name = "win_busca_lucro_g10_orb_tendencia_diaria"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        direcao_diaria: dict,
        symbol: str | None = None,
        range_minutos: float = 5.0,
        stop_min_pontos: float = 50.0,
        stop_max_pontos: float = 140.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
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
        if symbol is not None:
            self.symbol = symbol
        self.direcao_diaria: dict = dict(direcao_diaria)
        self.range_minutos = float(range_minutos)
        self.stop_min_pontos = float(stop_min_pontos)
        self.stop_max_pontos = float(stop_max_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49 + mandato desta geracao:
        # ocorrencias BRUTAS separadas das emitidas apos o filtro) --
        self.stats_bruto = 0
        self.stats_bruto_favoravel = 0
        self.stats_bloqueado_tendencia = 0
        self.stats_ja_operou_hoje = 0
        self.stats_ordens_emitidas = 0

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
        self._direcao_dia = 0

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()
        d = session_date.date() if isinstance(session_date, (pd.Timestamp, _dt.datetime)) else session_date
        self._direcao_dia = int(self.direcao_diaria.get(d, 0))

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    # -- geometria (pura) -----------------------------------------------------
    def _geometria(self) -> tuple[float, float]:
        """`(stop_pontos, alvo_pontos)` -- identico a G08: stop sai do
        tamanho da faixa, limitado entre piso e teto; alvo = stop x
        `alvo_multiplo` (>= 3x por construcao). Arredondado a` grade de
        preco do WIN@ (5 pontos)."""
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        stop = max(self.stop_min_pontos, min(self.stop_max_pontos, range_pontos))
        stop = round(stop / self.tick_size) * self.tick_size
        alvo = round((stop * self.alvo_multiplo) / self.tick_size) * self.tick_size
        return float(stop), float(alvo)

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

        # Transicao de posicao -- estado do INICIO da barra (item 6.48).
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            self._preencheu_hoje = True
        self._tinha_posicao_anterior = tem_posicao_agora

        # (1) os primeiros `range_minutos`: so' olha e mede a faixa.
        if (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos):
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            return []

        if self._range_hi is None or self._range_lo is None:
            return []

        rompeu_alta = bar.close > self._range_hi
        rompeu_baixa = bar.close < self._range_lo

        nova_alta = rompeu_alta and not self._fora_hi
        nova_baixa = rompeu_baixa and not self._fora_lo
        self._fora_hi = rompeu_alta
        self._fora_lo = rompeu_baixa

        if not (nova_alta or nova_baixa):
            return []

        # BRUTO: toda borda de rompimento, ANTES do filtro de tendencia e de
        # qualquer gate de posicao/ja-operou (item 6.48, e mandato desta
        # geracao -- "reporte ocorrencias brutas separadas das emitidas").
        self.stats_bruto += 1

        # -- FILTRO DE TENDENCIA DIARIA: unica mudanca de SINAL desta geracao.
        # `_direcao_dia` foi fixado em `on_session_start`, nunca recalculado
        # dentro do pregao -- nao ha' risco do bug do item 6.48 aqui (nao e'
        # estado mutavel atualizado na mesma chamada que a checagem le).
        favoravel = (nova_alta and self._direcao_dia == 1) or (nova_baixa and self._direcao_dia == -1)
        if not favoravel:
            self.stats_bloqueado_tendencia += 1
            return []
        self.stats_bruto_favoravel += 1

        if positions:
            return []
        if self._preencheu_hoje:
            self.stats_ja_operou_hoje += 1
            return []
        if self._armou_hoje:
            return []

        stop_pontos, alvo_pontos = self._geometria()
        buf = self.buffer_entrada_pontos
        if nova_alta:
            limite = bar.close - buf
            self._armou_hoje = True
            self.stats_ordens_emitidas += 1
            return [self._ordem("long", limite, stop_pontos, alvo_pontos,
                                "g10_orb_tendencia_diaria_rompimento_alta")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos,
                            "g10_orb_tendencia_diaria_rompimento_baixa")]
