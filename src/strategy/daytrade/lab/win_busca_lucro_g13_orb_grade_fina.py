# -*- coding: utf-8 -*-
"""`WinBuscaLucroG13OrbGradeFina` -- Geracao 13 da busca por um EA lucrativo
do WIN.

Pergunta desta geracao (`ORQUESTRACAO.md`, mandato do COORDENADOR): a G8 (mesma
logica de rompimento de faixa de abertura da G7, `WinBuscaLucroG07Orb`/
`WinBuscaLucroG08OrbSobrevivencia`) varreu SO' `stop_max_pontos` (um unico
eixo) e achou um PENHASCO abrupto -- `stop_max=140` sobrevive (121/122
pregoes com trade, p_ruina=24,8%), `stop_max=150/160` colapsam para censura
total (5/122 trades, equity cruza a margem crua logo no inicio do IS). O
coordenador pediu uma grade MULTIDIMENSIONAL de verdade -- multiplo do alvo x
definicao do stop x limiar de confirmacao do rompimento -- para checar se
existe algum PLATO robusto (varias celulas vizinhas concordando em sinal e
magnitude) em alguma combinacao, nao mais um unico eixo.

Esta classe e' uma extensao DELIBERADA da logica de deteccao de rompimento de
`WinBuscaLucroG08OrbSobrevivencia` (mesmo `_reset_sessao`/`on_session_start`/
`on_order_rejected`/`on_order_expired`, mesma disciplina de separar
"atualizar estado de rompimento" de "decidir se emite ordem" -- item 6.48,
mesmo teto de 1 operacao REAL por pregao, sem fade). Arquivo NOVO (nao
subclasse), mesmo motivo de toda geracao anterior desta busca: cada geracao
congela seu proprio modulo (`..._congelado_v13.py`) e uma edicao futura de um
modulo de geracao anterior nunca pode afetar, silenciosamente, o resultado ja'
registrado de uma geracao posterior.

## O que mudou em relacao a' G8 -- os 3 eixos desta geracao

1. **`alvo_multiplo`** -- continua >= 3x por construcao (guarda do
   construtor, mesma disciplina de toda a linha), mas agora e' eixo de busca
   explicito em {3, 4, 5} (G8 so' testou com stop_max=140 fixo, Estagio B).

2. **Definicao do STOP -- `stop_family`, 3 familias:**
   - `"tecnico"` (default, identica a` G7/G8): `stop = clip(faixa_de_abertura,
     stop_min_pontos, stop_max_pontos)`. O eixo que varia aqui e' o TETO
     (`stop_max_pontos`), em pelo menos 4-5 valores ao redor da regiao
     interessante achada na G8 (100 a 180).
   - `"atr"` -- `stop = atr_multiplo x ATR14(M15)`, causal (ver
     `atr_m15_causal` abaixo -- funcao pura module-level, mesmo molde de
     `regime_amplitude_bloco` da G5: so' usa M15 ja' FECHADO antes da barra
     corrente, nunca a barra em formacao).
   - `"fixo"` -- `stop = stop_fixo_pontos`, constante, sem depender da faixa
     nem de ATR.
   Em TODAS as familias, `alvo = stop x alvo_multiplo`, arredondado a` grade
   de preco do WIN@ (5 pontos), e o item 6.47 (checagem com ticks reais se o
   stop mediano realizado cair abaixo de 100 pontos) continua valendo.

3. **`confirma_pontos`** -- filtro de CONFIRMACAO do rompimento, em vez de
   validar o sinal no primeiro toque do nivel (comportamento G7/G8, que e' o
   que `confirma_pontos=0` reproduz exatamente): o fechamento da barra de
   rompimento so' valida o sinal se ultrapassar o nivel da faixa por pelo
   menos `confirma_pontos` pontos. Isto e' ORTOGONAL ao `buffer_entrada_
   pontos` (que so' desloca o PRECO da ordem-limite de entrada, nao muda que
   borda conta como "rompimento valido") -- os dois permanecem parametros
   separados.

## Desenho de execucao (FECHADO -- CLAUDE.md, nao negociavel)

Identico a` G7/G8: `EnterLimit` com `ttl_bars` (nunca `Enter` a mercado);
limite `buffer_entrada_pontos` ATRAS do rompimento; alvo por ordem-limite real
fatiada (`exit_split_unit`), SEM prazo (`exit_ttl_bars=None`);
`anchor_exits_at_fill=True`; so' o STOP e' a mercado; `target_fills_as_maker=
True`. Fila do WIN@ NAO calibrada -- toda ordem-limite enche no TOQUE
(premissa otimista declarada pelo harness, mesmo precedente de G1-G12).
Capital real R$250 (margem crua R$100 x buffer 2,0 x reserva 1,25), 1
contrato fixo -- nunca escala (mesma politica de G8-G12, confirmada de novo
pelo sizing/Kelly no harness desta geracao).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.indicators import atr as _atr_wilder
from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG13OrbGradeFina", "atr_m15_causal"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G12 desta busca.
TTL_BARRAS_ENTRADA = 10

STOP_FAMILIAS = ("tecnico", "atr", "fixo")


def atr_m15_causal(df_m1: pd.DataFrame, periodo: int = 14) -> dict:
    """ATR(14) de Wilder sobre barras M15 (resample causal do M1), devolvido
    como `dict {timestamp_m1 -> valor_atr}` -- funcao PURA module-level (sem
    I/O, sem estado), mesmo molde de `regime_amplitude_bloco`/`regime_vela_
    extrema` da G5 (`win_busca_lucro_g05_regime_vol.py`).

    Causalidade: o M15 e' resampleado com `label="right"` (cada barra M15 e'
    rotulada no seu instante de FECHAMENTO), o ATR e' calculado sobre essa
    serie e depois DESLOCADO 1 posicao (`shift(1)`) -- o valor disponivel no
    fechamento da barra M15 X so' passa a valer a partir da barra M15
    SEGUINTE, nunca dentro da propria janela que o gerou. O resultado e'
    then propagado para o indice M1 por `reindex(..., method="ffill")`: toda
    barra M1 recebe o ultimo ATR M15 que ja' tinha FECHADO e sido conhecido
    antes dela -- nunca a barra M15 em formacao. Primeiras `periodo` barras
    M15 de todo o historico (sem janela completa) saem `NaN` por construcao
    (`min_periods=window` dentro de `core.indicators.atr`).
    """
    m15 = df_m1.resample("15min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna(subset=["open", "high", "low", "close"])
    serie_atr = _atr_wilder(m15["high"], m15["low"], m15["close"], window=periodo)
    serie_atr = serie_atr.shift(1)
    full_index = df_m1.index.union(serie_atr.index).sort_values()
    atr_m1 = serie_atr.reindex(full_index, method="ffill").reindex(df_m1.index)
    return {ts: float(v) for ts, v in atr_m1.items()}


class WinBuscaLucroG13OrbGradeFina(IntradayStrategy):
    """Rompimento da faixa de abertura do WIN@ (mesma deteccao de G07/G08),
    NO MAXIMO 1 operacao REAL por pregao, sempre a favor do proprio
    rompimento (momentum) -- Geracao 13 varia 3 eixos cruzados: multiplo do
    alvo, familia/teto do stop, e limiar de confirmacao do rompimento, em
    busca de um PLATO (nao so' um pico isolado) de baixa probabilidade de
    ruina."""

    name = "win_busca_lucro_g13_orb_grade_fina"
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
        stop_family: str = "tecnico",
        stop_min_pontos: float = 50.0,
        stop_max_pontos: float = 140.0,
        atr_multiplo: float = 1.5,
        atr_serie: dict | None = None,
        stop_fixo_pontos: float = 140.0,
        alvo_multiplo: float = 3.0,
        confirma_pontos: float = 0.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        if range_minutos <= 0:
            raise ValueError("range_minutos tem que ser positivo")
        if stop_family not in STOP_FAMILIAS:
            raise ValueError(f"stop_family tem que ser um de {STOP_FAMILIAS}")
        if stop_min_pontos <= 0:
            raise ValueError("stop_min_pontos tem que ser positivo")
        if stop_max_pontos < stop_min_pontos:
            raise ValueError("stop_max_pontos tem que ser >= stop_min_pontos")
        if atr_multiplo <= 0:
            raise ValueError("atr_multiplo tem que ser positivo")
        if stop_family == "atr" and not atr_serie:
            raise ValueError(
                "stop_family='atr' exige atr_serie pre-computado "
                "(ver atr_m15_causal) -- nunca calculado dentro do on_bar")
        if stop_fixo_pontos <= 0:
            raise ValueError("stop_fixo_pontos tem que ser positivo")
        if alvo_multiplo < 3.0:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo de 3x -- fere a disciplina "
                f"alvo >= 3x o stop do mandato do dono")
        if confirma_pontos < 0:
            raise ValueError("confirma_pontos nao pode ser negativo")
        if buffer_entrada_pontos < 0:
            raise ValueError("buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if symbol is not None:
            self.symbol = symbol
        self.range_minutos = float(range_minutos)
        self.stop_family = stop_family
        self.stop_min_pontos = float(stop_min_pontos)
        self.stop_max_pontos = float(stop_max_pontos)
        self.atr_multiplo = float(atr_multiplo)
        self._atr_serie = atr_serie or {}
        self.stop_fixo_pontos = float(stop_fixo_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.confirma_pontos = float(confirma_pontos)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49) --
        self.stats_bruto = 0
        self.stats_ja_operou_hoje = 0
        self.stats_ordens_emitidas = 0
        self.stats_sem_atr_disponivel = 0

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

    # -- geometria (pura, dado o estado da sessao) ---------------------------
    def _geometria(self, ts: pd.Timestamp) -> tuple[float, float] | None:
        """`(stop_pontos, alvo_pontos)` segundo `self.stop_family`, ou `None`
        se a familia `atr` nao tiver valor disponivel nesta barra (janela de
        burn-in do ATR14-M15 ainda nao fechada -- `stats_sem_atr_disponivel`
        conta esses casos). Alvo = stop x `alvo_multiplo` (>= 3x por
        construcao). Arredondado a` grade de preco do WIN@ (5 pontos)."""
        if self.stop_family == "tecnico":
            assert self._range_hi is not None and self._range_lo is not None
            range_pontos = self._range_hi - self._range_lo
            stop = max(self.stop_min_pontos, min(self.stop_max_pontos, range_pontos))
        elif self.stop_family == "fixo":
            stop = self.stop_fixo_pontos
        else:  # "atr"
            atr_val = self._atr_serie.get(ts)
            if atr_val is None or atr_val != atr_val:  # NaN ou ausente
                return None
            stop = self.atr_multiplo * atr_val
            stop = max(self.stop_min_pontos, stop)
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

        # Transicao de posicao -- estado do INICIO da barra (item 6.48):
        # `positions` ja' reflete qualquer fill desta barra. So' existe 1
        # operacao REAL possivel por pregao nesta geracao (sem fade), entao
        # a transicao vazio->nao-vazio so' pode acontecer uma vez por dia.
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            self._preencheu_hoje = True
        self._tinha_posicao_anterior = tem_posicao_agora

        # (1) os primeiros `range_minutos`: so' olha e mede a faixa.
        if (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos):
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            return []

        # (2) o estado de rompimento (fora_hi/fora_lo) e' SEMPRE atualizado,
        # com posicao aberta ou nao -- item 6.48 (mesma disciplina da G07/G08).
        # `confirma_pontos` desloca o LIMIAR que conta como "fora da faixa"
        # (eixo 3 desta geracao) -- 0 reproduz exatamente o comportamento
        # G07/G08 (primeiro toque alem do nivel).
        if self._range_hi is None or self._range_lo is None:
            return []

        rompeu_alta = bar.close > (self._range_hi + self.confirma_pontos)
        rompeu_baixa = bar.close < (self._range_lo - self.confirma_pontos)

        # Borda NOVA -- transicao de "dentro"/"ja rompido no mesmo sentido
        # sem reentrar" para um rompimento FRESCO. Nao conta de novo barra a
        # barra enquanto o preco so' permanece fora.
        nova_alta = rompeu_alta and not self._fora_hi
        nova_baixa = rompeu_baixa and not self._fora_lo
        self._fora_hi = rompeu_alta
        self._fora_lo = rompeu_baixa

        if not (nova_alta or nova_baixa):
            return []

        # BRUTO: toda borda de rompimento CONFIRMADA (ja' com o limiar de
        # `confirma_pontos` aplicado), ANTES de qualquer filtro de "posicao
        # aberta"/"ja armado"/"ja operou hoje" (item 6.48). Por construcao
        # este contador MUDA entre celulas com `confirma_pontos` diferente
        # -- diferente do eixo stop/alvo, que nao afeta a deteccao.
        self.stats_bruto += 1

        if positions:
            return []
        if self._preencheu_hoje:
            self.stats_ja_operou_hoje += 1
            return []
        if self._armou_hoje:
            return []

        geometria = self._geometria(ts)
        if geometria is None:
            self.stats_sem_atr_disponivel += 1
            return []
        stop_pontos, alvo_pontos = geometria
        buf = self.buffer_entrada_pontos
        if nova_alta:
            limite = bar.close - buf
            self._armou_hoje = True
            self.stats_ordens_emitidas += 1
            return [self._ordem("long", limite, stop_pontos, alvo_pontos,
                                "g13_orb_grade_fina_rompimento_alta")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos,
                            "g13_orb_grade_fina_rompimento_baixa")]
