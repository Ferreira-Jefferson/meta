# -*- coding: utf-8 -*-
"""`WinBuscaLucroG09OrbFade` -- Geracao 9 da busca por um EA lucrativo do WIN.

Pergunta desta geracao (`ORQUESTRACAO.md`, raciocinio deixado pela Geracao 8):
a familia ORB/momentum (G7, G8) nunca encontrou geometria com p_ruina baixa o
bastante -- mesmo a MELHOR (G8, stop_max=140) ficou em 24,8% de probabilidade
de ruina a partir do caixa real de R$250, porque o win% geometricamente baixo
(25-37%, imposto pelo mandato alvo>=3x) deixa sequencias de 2-5 perdas NADA
raras. A saida logica: buscar win% estruturalmente MAIOR com o MESMO piso de
payoff (alvo=3x) -- um win% de 40-55% sobraria folga de caixa suficiente para
tornar sequencias longas de perda muito mais raras, por CONSTRUCAO, nao por
ajuste fino de stop.

O candidato: FADE da FALHA do rompimento da abertura -- o oposto do momentum
puro de G7/G8. `WdoOrb` (producao, WDO@) ja opera um fade (`fade_rompimento_
oposto`) com win% mais alto que o breakout puro, mas usa `alvo_multiplo=1.5`
em producao -- este arquivo NAO reusa esse valor (fere o mandato desta busca,
que exige >=3x sempre) e a logica de deteccao tambem e' diferente: `WdoOrb`
dispara o fade so' DEPOIS que a 1a operacao do dia (momentum) ja fechou, e o
2o rompimento (lado OPOSTO) e' o proprio gatilho de entrada. Esta geracao NAO
tem perna de momentum nenhuma -- o unico trade real do dia, se houver, E' o
fade da FALHA do primeiro rompimento, nunca uma entrada a favor dele.

## Definicao operacional de "falha do rompimento" (parametro `falha_n_barras`)

Depois que o preco fecha fora da faixa de abertura (rompimento), a classe
observa uma JANELA de ate' `falha_n_barras` barras M1 seguintes e declara
FALHA por qualquer um dos dois caminhos (o que vier primeiro):

  (a) REVERSAO -- o preco fecha de volta DENTRO da faixa (`close <= range_hi`
      para rompimento de alta, `close >= range_lo` para o de baixa) antes do
      fim da janela;
  (b) ESTAGNACAO -- o preco nao faz uma NOVA extremidade (maxima mais alta
      para rompimento de alta, minima mais baixa para o de baixa) durante
      `falha_n_barras` barras consecutivas depois do rompimento -- ou seja, o
      movimento parou de se estender, mesmo sem reverter de volta pra dentro.

Se nenhuma das duas ocorrer dentro da janela (o rompimento ESTENDEU uma nova
extremidade a cada passo e nunca reverteu ate' o fim da janela), o episodio e'
encerrado como "momentum que continuou" -- SEM entrada (esta geracao nao tem
perna de momentum) -- e a classe volta a vigiar por um rompimento NOVO (so'
conta como novo depois que o preco voltar pra dentro da faixa e romper de
novo, ou romper o lado oposto).

So' um episodio e' vigiado por vez (preco so' pode estar fora de um dos dois
lados por barra). No MAXIMO 1 operacao REAL por pregao -- mesma decisao de
G7/G8 (testar a hipotese mais simples antes de somar complexidade, e e' o
desenho que, por construcao, ja resolveu concentracao nessas duas geracoes:
amostra PREGOES distintos, nunca reentra no mesmo dia).

## Geometria

`stop_pontos = clip(|extremo_do_episodio - preco_de_entrada| + stop_buffer_
pontos, stop_min_pontos, stop_max_pontos)` -- o stop fica no extremo que o
rompimento alcancou (onde a tese de fade estaria errada), mais uma folga
pequena (`stop_buffer_pontos`), com o MESMO piso/teto em pontos que G7/G8
usam para poder buscar a geometria e aplicar o item 6.47 se o stop mediano
sair curto. `alvo_pontos = stop_pontos x alvo_multiplo`, SEMPRE >= 3x por
construcao (guarda no `__init__`, mesma disciplina de G07/G08).

## Desenho de execucao (FECHADO -- CLAUDE.md, nao negociavel)

`EnterLimit` com `ttl_bars` (nunca `Enter` a mercado); limite
`buffer_entrada_pontos` na direcao que da' preco melhor para quem entra
CONTRA o rompimento (mesma convencao de offset de G07/G08, so' que a entrada
e' no lado OPOSTO ao lado do rompimento); alvo por ordem-limite real fatiada
(`exit_split_unit`), SEM prazo (`exit_ttl_bars=None` -- esta geracao e' so'
backtest/pesquisa, nao execucao real; o valor enorme de producao
`wdo_orb.EXIT_TTL_BARS_SEM_PRAZO` so' seria exigido se este robo um dia virar
candidato real); `anchor_exits_at_fill=True`; so' o STOP e' a mercado;
`target_fills_as_maker=True`. Fila do WIN@ NAO calibrada -- toda ordem-limite
enche no TOQUE (premissa otimista declarada pelo harness, precedente
`WinRetangulo`/G1-G8). Capital real R$250, 1 contrato fixo (politica desta
busca: nunca escalar para 2+, ver `motor.tamanho`/G8).

Arquivo NOVO, nao subclasse/copia de `WdoOrb` nem de G07/G08 -- a logica de
sinal (deteccao de FALHA, nao de rompimento) e' estruturalmente diferente o
bastante para nao justificar heranca, mesma razao pela qual G07 nao herdou de
`WdoOrb` e G08 nao herdou de G07.
"""
from __future__ import annotations

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG09OrbFade"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G8 desta busca.
TTL_BARRAS_ENTRADA = 10


class WinBuscaLucroG09OrbFade(IntradayStrategy):
    """Fade da FALHA do rompimento da faixa de abertura do WIN@ -- NUNCA opera
    a favor do rompimento (sem perna de momentum), no MAXIMO 1 operacao REAL
    por pregao. Geracao 9 busca win% estruturalmente maior que a familia
    momentum (G7/G8), mantendo alvo >= 3x o stop."""

    name = "win_busca_lucro_g09_orb_fade"
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
        falha_n_barras: int = 5,
        stop_min_pontos: float = 50.0,
        stop_max_pontos: float = 250.0,
        stop_buffer_pontos: float = 20.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        if range_minutos <= 0:
            raise ValueError("range_minutos tem que ser positivo")
        if falha_n_barras is None or falha_n_barras <= 0:
            raise ValueError("falha_n_barras tem que ser um inteiro positivo")
        if stop_min_pontos <= 0:
            raise ValueError("stop_min_pontos tem que ser positivo")
        if stop_max_pontos < stop_min_pontos:
            raise ValueError("stop_max_pontos tem que ser >= stop_min_pontos")
        if stop_buffer_pontos < 0:
            raise ValueError("stop_buffer_pontos nao pode ser negativo")
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
        self.range_minutos = float(range_minutos)
        self.falha_n_barras = int(falha_n_barras)
        self.stop_min_pontos = float(stop_min_pontos)
        self.stop_max_pontos = float(stop_max_pontos)
        self.stop_buffer_pontos = float(stop_buffer_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49) --
        #: toda vez que um rompimento FRESCO comeca a ser vigiado (episodio novo).
        self.stats_bruto_rompimento = 0
        #: toda vez que uma FALHA e' confirmada (reversao ou estagnacao),
        #: ANTES de qualquer filtro de posicao/ja-operou/ja-armado.
        self.stats_bruto_falha = 0
        self.stats_ja_operou_hoje = 0
        self.stats_ordens_emitidas = 0

        self._reset_sessao()

    # -- estado por sessao ----------------------------------------------------
    def _reset_sessao(self) -> None:
        self._open_ts: pd.Timestamp | None = None
        self._range_hi: float | None = None
        self._range_lo: float | None = None
        self._fora_hi = False
        self._fora_lo = False
        #: episodio de rompimento sendo vigiado: "alta" / "baixa" / None.
        self._episodio_lado: str | None = None
        self._episodio_barras = 0
        self._episodio_extremo: float | None = None
        self._episodio_barras_sem_novo_extremo = 0
        self._armou_hoje = False
        self._preencheu_hoje = False
        self._tinha_posicao_anterior = False

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    # -- geometria (pura) -------------------------------------------------------
    def _geometria(self, limite: float, extremo: float) -> tuple[float, float]:
        """`(stop_pontos, alvo_pontos)` -- stop sai da distancia do preco de
        ENTRADA ate' o extremo que o rompimento alcancou (onde a tese de fade
        estaria errada), mais uma folga pequena, limitado entre piso e teto;
        alvo = stop x `alvo_multiplo` (>= 3x por construcao). Arredondado a`
        grade de preco do WIN@."""
        dist = abs(extremo - limite) + self.stop_buffer_pontos
        stop = max(self.stop_min_pontos, min(self.stop_max_pontos, dist))
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

    # -- loop -------------------------------------------------------------------
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
        # operacao REAL possivel por pregao nesta geracao (sem fade de fade),
        # entao a transicao vazio->nao-vazio so' pode acontecer 1x por dia.
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

        # (2) estado de rompimento -- SEMPRE atualizado (item 6.48), com ou
        # sem episodio ativo, com ou sem posicao aberta.
        rompeu_alta = bar.close > self._range_hi
        rompeu_baixa = bar.close < self._range_lo
        nova_alta = rompeu_alta and not self._fora_hi
        nova_baixa = rompeu_baixa and not self._fora_lo
        self._fora_hi = rompeu_alta
        self._fora_lo = rompeu_baixa

        falha_confirmada = False
        lado_rompimento: str | None = None
        extremo_falha: float | None = None

        # (3) episodio JA ativo: processa esta barra antes de considerar
        # qualquer rompimento novo (so' 1 episodio vigiado por vez).
        if self._episodio_lado is not None:
            self._episodio_barras += 1
            if self._episodio_lado == "alta":
                if bar.close <= self._range_hi:
                    falha_confirmada = True
                else:
                    novo_extremo = max(self._episodio_extremo, bar.high)
                    if novo_extremo > self._episodio_extremo:
                        self._episodio_extremo = novo_extremo
                        self._episodio_barras_sem_novo_extremo = 0
                    else:
                        self._episodio_barras_sem_novo_extremo += 1
                    if self._episodio_barras_sem_novo_extremo >= self.falha_n_barras:
                        falha_confirmada = True
            else:  # "baixa"
                if bar.close >= self._range_lo:
                    falha_confirmada = True
                else:
                    novo_extremo = min(self._episodio_extremo, bar.low)
                    if novo_extremo < self._episodio_extremo:
                        self._episodio_extremo = novo_extremo
                        self._episodio_barras_sem_novo_extremo = 0
                    else:
                        self._episodio_barras_sem_novo_extremo += 1
                    if self._episodio_barras_sem_novo_extremo >= self.falha_n_barras:
                        falha_confirmada = True

            if falha_confirmada:
                self.stats_bruto_falha += 1
                lado_rompimento = self._episodio_lado
                extremo_falha = self._episodio_extremo
                self._episodio_lado = None
            elif self._episodio_barras >= self.falha_n_barras:
                # janela esgotou SEM falha -- o rompimento estendeu (momentum
                # que continuou). Episodio encerrado sem trade; volta a
                # vigiar por um rompimento NOVO (precisa reverter pra dentro
                # da faixa e romper de novo, ou romper o lado oposto).
                self._episodio_lado = None

        # (4) sem episodio ativo: um rompimento FRESCO comeca a ser vigiado.
        elif nova_alta:
            self.stats_bruto_rompimento += 1
            self._episodio_lado = "alta"
            self._episodio_barras = 0
            self._episodio_extremo = bar.high
            self._episodio_barras_sem_novo_extremo = 0
        elif nova_baixa:
            self.stats_bruto_rompimento += 1
            self._episodio_lado = "baixa"
            self._episodio_barras = 0
            self._episodio_extremo = bar.low
            self._episodio_barras_sem_novo_extremo = 0

        if not falha_confirmada:
            return []

        # (5) falha confirmada: tenta emitir a entrada CONTRARIA ao lado do
        # rompimento que falhou -- so' se nao houver posicao/ordem no caminho.
        if positions:
            return []
        if self._preencheu_hoje:
            self.stats_ja_operou_hoje += 1
            return []
        if self._armou_hoje:
            return []

        buf = self.buffer_entrada_pontos
        if lado_rompimento == "alta":
            # rompimento de ALTA falhou -> fade VENDIDO. Limite ACIMA do
            # preco corrente (mesma convencao de entrada curta de G07/G08).
            side = "short"
            limite = bar.close + buf
            reason = "g09_fade_falha_rompimento_alta"
        else:
            side = "long"
            limite = bar.close - buf
            reason = "g09_fade_falha_rompimento_baixa"

        stop_pontos, alvo_pontos = self._geometria(limite, extremo_falha)
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem(side, limite, stop_pontos, alvo_pontos, reason)]
