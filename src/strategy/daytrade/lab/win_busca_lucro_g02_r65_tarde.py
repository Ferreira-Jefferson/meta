# -*- coding: utf-8 -*-
"""`WinBuscaLucroG02R65` -- Geracao 2 da busca por um EA lucrativo do WIN.

Mandato do dono (2026-10-04/2026-10-05, `ORQUESTRACAO.md`): a Geracao 1
testou R65 (M15 rompe so' a EMA9 com H1 alinhado) sob um portao de horario
herdado de R61 (`<11h/12h` ajustado DST) e teve ZERO sinais no IS inteiro --
nao por falta de gatilho (383 rompimentos de EMA9-M15 em 122 dias), mas
porque a conjuncao "M15 so' EMA9" + "H1 alinhado" + "a favor da pernada"
raramente amadurece antes do meio-dia; a maioria das ocorrencias que passam
todos os filtros nasce **a tarde** (12:59-17:59, achado descritivo da G1).

Esta classe testa R65 como HIPOTESE PROPRIA: nenhum portao de horario
herdado. A janela em que o robo pode ARMAR uma ordem e' um PARAMETRO a
descobrir no IS (jan-jun/2026) -- "sem filtro", "so' manha", "so' tarde",
"dia todo exceto o fim do pregao" sao so' QUATRO valores possiveis deste
mesmo parametro, nao quatro robos diferentes.

O UNICO filtro de direcao mantido como principio INEGOCIAVEL do dono (nao
como parametro a testar): nunca entrar CONTRA a pernada de 750 pontos em
curso (R43, zigzag causal sobre o CAMINHO da vela -- alta: minima->maxima;
baixa: maxima->minima, definicao CONGELADA em 2026-10-04).

## Gatilho -- R65 (M15 rompe so' a EMA9, H1 alinhado)

Identico a' Geracao 1 (EMAs mantidas POR DENTRO do robo via agregacao causal
de M1 em M15/H1, atravessando a sessao -- nao resetam em
`on_session_start`; ver a nota longa da G1 sobre por que isto e' deliberado:
a janela de busca deste robo pode ir ate' o fim do pregao, mas o motivo
original ainda vale -- um EMA9 de H1 reiniciado a cada pregao nunca teria
amostra).

"Rompe so' a EMA9, nao a EMA21": o FECHAMENTO do M15 fica estritamente ENTRE
as duas EMAs (`ema9 < close < ema21` para alta, invertido para baixa).
Disparo por BORDA (so' na primeira vez que o M15 fechado entra nesta zona).

"H1 alinhado": fechamento do H1 do MESMO LADO da EMA9 do H1.

## Janela de horario -- PARAMETRO (nao portao fixo)

`janela_inicio`/`janela_fim` (strings `"HH:MM"`, hora local B3) delimitam
quando este robo pode EMITIR a ordem-limite do R65. O ESTADO do gatilho
(EMA9/EMA21/H1, deteccao de borda) continua sendo atualizado em TODA barra,
dentro ou fora da janela -- so' a EMISSAO da ordem e' filtrada. Isto
preserva o comportamento medido pela G1: uma borda que amadurece fora da
janela fica CONSUMIDA (nao re-arma s'o porque a janela abriu depois), exatamente
como o gatilho funciona na pratica (o estado "dentro da zona EMA9-EMA21" nao
"espera" o horario -- ele existe ou nao em cada fechamento de M15).

## Direcao -- NUNCA contra a pernada de 750 em curso (R43)

Mesmo zigzag causal da G1, reiniciado a cada pregao (`on_session_start`) --
a serie continua `WIN@` tem saltos de rolagem que nao podem atravessar a
sessao disfarcados de movimento real.

## Stop -- DUAS familias, PARAMETRO a escolher no IS

1. **Tecnico** (`familia_stop="tecnico"`): extremo das ultimas
   `barras_stop_tecnico` velas M1 antes da entrada -- identico a' G1.
2. **Proporcional/ATR** (`familia_stop="atr"`): `atr_multiplo` x ATR do M15
   (media movel SIMPLES do true range das ultimas `atr_periodo_m15` barras
   M15 fechadas -- NAO Wilder, escolha simples e documentada; aquecida
   causalmente, atravessa a sessao pelo mesmo motivo das EMAs). `risco =
   atr_multiplo * atr_m15`; sem ATR aquecido ainda, nao arma.

Em QUALQUER familia, o alvo e' `alvo_multiplo * risco` (`alvo_multiplo >=
3.0`, obrigatorio -- disciplina do dono "alvo sempre >= 3x o stop").

## Execucao -- o desenho fechado, sem excecao (CLAUDE.md)

Entrada so' por `EnterLimit` (reteste do nivel da EMA9 do M15 -- o desenho
fechado do projeto proibe ordem a mercado mesmo numa entrada de rompimento)
com `ttl_bars` obrigatorio; alvo so' como ordem-limite real fatiada
(`exit_split_unit`), SEM prazo (`exit_ttl_bars=None`); so' o stop e' a
mercado; `anchor_exits_at_fill=True`; `target_fills_as_maker=True`.
Conferencia MECANICA antes de armar (limite de venda so' descansa ACIMA do
preco corrente, de compra so' ABAIXO).

## Fila -- WIN@ nao tem fidelidade calibrada

Mesma ressalva da G1/`WinRetangulo`: toda medicao desta classe roda com
`queue_ahead_qty=0`/`exit_queue_ahead_qty=0` (preenche no toque), premissa
OTIMISTA declarada, identica nas duas janelas.

## Capital e dimensionamento

1 contrato FIXO (`quantity=1`, sem escala por caixa) -- dimensionamento
dinamico fica para geracao futura. O motor aplica o teto por margem
(`contracts_from_capital_operacional`) por cima de qualquer jeito.
"""
from __future__ import annotations

import datetime as _dt
from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

#: Limiar da pernada "oficial" (R43) -- zigzag sobre o caminho da vela.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (meio da faixa 5-15 barras sugerida --
#: nunca `None`, ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Periodos das EMAs do R65.
EMA_RAPIDA_M15 = 9
EMA_LENTA_M15 = 21
EMA_H1 = 9
#: Default da familia tecnica (velas M1 que definem o extremo).
BARRAS_STOP_TECNICO = 10
#: Default da familia ATR (periodo do M15, multiplo do risco).
ATR_PERIODO_M15 = 14
ATR_MULTIPLO = 1.0
#: Multiplo do risco que vira alvo -- ponto medio-BAIXO da faixa "5-10x" do
#: mandato do dono, ajustavel dentro de [3, ...) mas nunca abaixo de 3x.
ALVO_MULTIPLO = 5.0


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela, na ordem em que o preco
    provavelmente passou por eles -- definicao CONGELADA em `REGRAS.md`:
    vela de alta (fecha >= abre) anda minima->maxima; vela de baixa anda
    maxima->minima. Pura (so' le o `Bar` recebido)."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


def _parse_hhmm(texto: str) -> _dt.time:
    h, m = texto.split(":")
    return _dt.time(int(h), int(m))


class WinBuscaLucroG02R65(IntradayStrategy):
    """R65 (M15 so' EMA9, H1 alinhado, a favor da pernada de 750) como
    hipotese PROPRIA -- Geracao 2 da busca por um EA lucrativo do WIN
    (`ORQUESTRACAO.md`). Janela de horario e familia de stop sao PARAMETROS,
    nao portoes herdados."""

    name = "win_busca_lucro_g02_r65_tarde"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        pernada_pontos: float = PERNADA_PONTOS,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        ema_rapida_m15: int = EMA_RAPIDA_M15,
        ema_lenta_m15: int = EMA_LENTA_M15,
        ema_h1: int = EMA_H1,
        janela_inicio: str = "00:00",
        janela_fim: str = "23:59",
        familia_stop: str = "tecnico",
        barras_stop_tecnico: int = BARRAS_STOP_TECNICO,
        atr_periodo_m15: int = ATR_PERIODO_M15,
        atr_multiplo: float = ATR_MULTIPLO,
        alvo_multiplo: float = ALVO_MULTIPLO,
        quantity: int = 1,
    ) -> None:
        if familia_stop not in ("tecnico", "atr"):
            raise ValueError(f"familia_stop={familia_stop!r} invalido: use 'tecnico' ou 'atr'")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)"
            )
        if alvo_multiplo < 3.0:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo de 3x -- fere a disciplina "
                f"alvo >= 3x o stop do mandato do dono"
            )
        if symbol is not None:
            self.symbol = symbol
        self.pernada_pontos = float(pernada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.ema_rapida_m15 = int(ema_rapida_m15)
        self.ema_lenta_m15 = int(ema_lenta_m15)
        self.ema_h1 = int(ema_h1)
        self.janela_inicio = _parse_hhmm(janela_inicio)
        self.janela_fim = _parse_hhmm(janela_fim)
        self.familia_stop = familia_stop
        self.barras_stop_tecnico = int(barras_stop_tecnico)
        self.atr_periodo_m15 = int(atr_periodo_m15)
        self.atr_multiplo = float(atr_multiplo)
        self.alvo_multiplo = float(alvo_multiplo)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size
        self.valor_do_ponto_brl = economia.point_value_brl

        # -- EMAs/ATR do R65: atravessam a sessao (ver docstring do modulo) --
        self._ema9_m15: float | None = None
        self._ema21_m15: float | None = None
        self._ema9_h1: float | None = None
        self._m15_estado_anterior: str | None = None
        self._m15_prev_close: float | None = None
        self._tr_m15_hist: deque[float] = deque(maxlen=self.atr_periodo_m15)
        self._atr_m15: float | None = None

        self._reset_sessao()

    # -- EMA incremental -------------------------------------------------
    @staticmethod
    def _ema_update(anterior: float | None, preco: float, periodo: int) -> float:
        if anterior is None:
            return preco
        alfa = 2.0 / (periodo + 1)
        return alfa * preco + (1.0 - alfa) * anterior

    # -- janela de horario (PARAMETRO, nao portao fixo) -------------------
    def _dentro_da_janela(self, ts: pd.Timestamp) -> bool:
        t = ts.time()
        return self.janela_inicio <= t <= self.janela_fim

    # -- estado por sessao --------------------------------------------------
    def _reset_sessao(self) -> None:
        self._hist: deque[Bar] = deque(maxlen=max(self.barras_stop_tecnico, 1) + 2)
        # zigzag da pernada (R43) -- reseta a cada pregao, ver docstring.
        self._zz_origem: float | None = None
        self._zz_extremo: float | None = None
        self._zz_direcao: int | None = None
        # acumulador do M15 corrente (fecha a cada ts.minute % 15 == 14)
        self._m15_high: float | None = None
        self._m15_low: float | None = None
        self._m15_estado_anterior = None
        self._h1_close_atual: float | None = None
        # ordem pendente (uma por vez)
        self._espera: int | None = None

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._espera = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._espera = None

    # -- zigzag da pernada (R43) ---------------------------------------------
    def _zz_atualiza(self, p: float) -> None:
        if self._zz_origem is None:
            self._zz_origem = p
            self._zz_extremo = p
            return
        if self._zz_direcao is None:
            if p - self._zz_origem >= self.pernada_pontos:
                self._zz_direcao = 1
                self._zz_extremo = p
            elif self._zz_origem - p >= self.pernada_pontos:
                self._zz_direcao = -1
                self._zz_extremo = p
            return
        if self._zz_direcao == 1:
            if p > self._zz_extremo:
                self._zz_extremo = p
            elif self._zz_extremo - p >= self.pernada_pontos:
                self._zz_origem = self._zz_extremo
                self._zz_direcao = -1
                self._zz_extremo = p
        else:
            if p < self._zz_extremo:
                self._zz_extremo = p
            elif p - self._zz_extremo >= self.pernada_pontos:
                self._zz_origem = self._zz_extremo
                self._zz_direcao = 1
                self._zz_extremo = p

    # -- R65: M15 rompe so' a EMA9, H1 alinhado ------------------------------
    def _atualiza_m15_h1(self, ts: pd.Timestamp, bar: Bar, pode_armar: bool) -> list[IntradayAction]:
        """Atualiza EMAs/ATR/estado do M15-H1 em TODA barra (a deteccao de
        borda nao pode esperar o robo estar livre para armar, ver docstring
        do modulo); so' tenta EMITIR uma ordem nova quando `pode_armar` --
        ou seja, sem posicao aberta e sem ordem-limite ja pendente de uma
        barra anterior.

        ATENCAO -- bug encontrado e corrigido ao testar esta classe
        (2026-10-05): a G1 (`win_busca_lucro_g01_consolidado.py`) chamava o
        equivalente desta funcao ANTES de checar `_espera`, e `_avalia_r65`
        setava `_espera=0` internamente ao armar -- o proprio `on_bar`
        enxergava `_espera is not None` JA' nesta mesma barra (acabara de
        ser setado) e descartava a acao que tinha acabado de criar. Isso
        FAZIA a condicao "R65 nunca emite ordem" ser estrutural, independente
        de qualquer portao de horario -- nao so' o motivo descrito na G1
        (a conjuncao amadurecer a tarde). Aqui o CALCULO do estado roda
        sempre; a EMISSAO so' acontece se `pode_armar` for `True`, decidido
        pelo `on_bar` ANTES desta chamada, com o valor de `_espera` que
        existia no INICIO da barra -- nunca o que esta funcao acabou de
        setar."""
        if self._m15_high is None:
            self._m15_high, self._m15_low = bar.high, bar.low
        else:
            self._m15_high = max(self._m15_high, bar.high)
            self._m15_low = min(self._m15_low, bar.low)

        acoes: list[IntradayAction] = []
        if ts.minute % 15 == 14:
            fechamento_m15 = bar.close
            # -- ATR do M15 (simples, causal) ANTES de atualizar EMAs: o true
            # range desta barra M15 usa o fechamento ANTERIOR do M15.
            if self._m15_prev_close is not None:
                tr = max(
                    self._m15_high - self._m15_low,
                    abs(self._m15_high - self._m15_prev_close),
                    abs(self._m15_low - self._m15_prev_close),
                )
                self._tr_m15_hist.append(tr)
                if len(self._tr_m15_hist) >= self.atr_periodo_m15:
                    self._atr_m15 = sum(self._tr_m15_hist) / len(self._tr_m15_hist)
            self._m15_prev_close = fechamento_m15
            self._ema9_m15 = self._ema_update(self._ema9_m15, fechamento_m15, self.ema_rapida_m15)
            self._ema21_m15 = self._ema_update(self._ema21_m15, fechamento_m15, self.ema_lenta_m15)
            self._m15_high = None
            self._m15_low = None
            acoes = self._avalia_r65(ts, bar, fechamento_m15, pode_armar)
        if ts.minute == 59:
            self._ema9_h1 = self._ema_update(self._ema9_h1, bar.close, self.ema_h1)
            self._h1_close_atual = bar.close
        return acoes

    def _risco_tecnico(self, estado: str, nivel: float) -> float | None:
        if len(self._hist) < self.barras_stop_tecnico:
            return None
        ultimas = list(self._hist)[-self.barras_stop_tecnico:]
        if estado == "long":
            stop_tecnico = min(b.low for b in ultimas)
            risco = nivel - stop_tecnico
        else:
            stop_tecnico = max(b.high for b in ultimas)
            risco = stop_tecnico - nivel
        if risco <= 0:
            return None
        return stop_tecnico

    def _avalia_r65(self, ts: pd.Timestamp, bar: Bar, fechamento_m15: float,
                     pode_armar: bool) -> list[IntradayAction]:
        if self._ema9_m15 is None or self._ema21_m15 is None or self._ema9_h1 is None:
            return []
        ema9, ema21 = self._ema9_m15, self._ema21_m15
        if ema9 < fechamento_m15 < ema21:
            estado = "long"
        elif ema21 < fechamento_m15 < ema9:
            estado = "short"
        else:
            estado = "fora"
        disparou = estado in ("long", "short") and estado != self._m15_estado_anterior
        self._m15_estado_anterior = estado
        if not disparou:
            return []
        # H1 alinhado: fechamento do H1 do mesmo lado da EMA9 do H1.
        alinhado_long = self._h1_close_atual is not None and self._h1_close_atual > self._ema9_h1
        alinhado_short = self._h1_close_atual is not None and self._h1_close_atual < self._ema9_h1
        if estado == "long" and not alinhado_long:
            return []
        if estado == "short" and not alinhado_short:
            return []
        # R43 -- nunca contra a pernada de 750 em curso (principio INEGOCIAVEL).
        sentido_pernada = self._zz_direcao
        if sentido_pernada is None:
            return []
        if estado == "long" and sentido_pernada != 1:
            return []
        if estado == "short" and sentido_pernada != -1:
            return []
        # janela de horario -- PARAMETRO, filtra so' a EMISSAO da ordem (o
        # estado/borda acima ja' foi consumido independente da janela).
        if not self._dentro_da_janela(ts):
            return []
        # ja' ha' posicao aberta OU ordem pendente de uma barra anterior --
        # o estado/borda acima fica CONSUMIDO do mesmo jeito (nao re-arma
        # quando a janela/posicao liberar de novo), mas nao emite ordem
        # nova agora. Ver a nota longa em `_atualiza_m15_h1` sobre o bug que
        # isto evita.
        if not pode_armar:
            return []

        nivel = no_tick(ema9, self.tick_size)
        lado = estado
        if self.familia_stop == "tecnico":
            stop_bruto = self._risco_tecnico(estado, nivel)
            if stop_bruto is None:
                return []
        else:
            if self._atr_m15 is None:
                return []
            risco_atr = self.atr_multiplo * self._atr_m15
            if risco_atr <= 0:
                return []
            stop_bruto = (nivel - risco_atr) if lado == "long" else (nivel + risco_atr)

        if lado == "long":
            risco = nivel - stop_bruto
            if risco <= 0:
                return []
            alvo = nivel + self.alvo_multiplo * risco
        else:
            risco = stop_bruto - nivel
            if risco <= 0:
                return []
            alvo = nivel - self.alvo_multiplo * risco

        if lado == "long" and nivel >= bar.close:
            return []
        if lado == "short" and nivel <= bar.close:
            return []
        self._espera = 0
        return [EnterLimit(
            side=lado,
            limit_price=nivel,
            initial_stop=no_tick(stop_bruto, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=f"r65_reteste_ema{self.ema_rapida_m15}_{self.familia_stop}",
        )]

    # -- loop -----------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)
        for p in _caminho_da_barra(bar):
            self._zz_atualiza(p)

        # Decide ANTES de atualizar o estado do M15/H1 se este robo PODE
        # armar uma ordem nova nesta barra -- com o `_espera` que existia no
        # INICIO da barra, nunca um valor que `_atualiza_m15_h1` ainda vai
        # setar mais abaixo (ver a nota longa no metodo sobre o bug que isto
        # corrige).
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

        acoes_r65 = self._atualiza_m15_h1(ts, bar, pode_armar)
        return acoes_r65 if pode_armar else []
