# -*- coding: utf-8 -*-
"""`WinBuscaLucroG14PortfolioOrbCross` -- Geracao 14 da busca por um EA
lucrativo do WIN (`ORQUESTRACAO.md`): a QUARTA e ultima alavanca do mandato
do coordenador -- portfolio/ALTERNANCIA entre duas familias ja medidas desta
busca, nao soma de risco.

## A pergunta desta geracao

A R$250 so' cabe 1 contrato (`contracts_from_capital_operacional` nunca
libera o 2o sem a pilha cheia -- CLAUDE.md, "Capital inicial: sempre o
minimo real"). Entao "portfolio" aqui NAO pode ser "duas posicoes
simultaneas com capital separado" -- e' ALTERNANCIA de qual estrategia PODE
disparar, compartilhando o MESMO caixa SEQUENCIALMENTE (nunca 2 posicoes
abertas ao mesmo tempo -- se uma esta aberta, OU pendente, a outra espera).

A G8 (ORB momentum, rompimento da faixa de abertura, win%~37%, payoff 3x)
morreu no OOS-1 com 5 derrotas seguidas logo no inicio da janela -- caixa
cruzou a margem de R$100 vindo de R$250 na 3a operacao, p_ruina(MC) do IS ja
previa ~25% de chance disso acontecer. A G4 (confirmacao cruzada WIN x WDO,
estado anomalo, win%~35%, payoff 3x) passou o gate LITERAL (liquido>0 nas
duas janelas) mas NAO VALIDOU com folga (IC95 cruza o breakeven empirico nas
duas janelas, concentracao piora de 59% para 240% do IS pro OOS-1). A
pergunta: se as duas familias tendem a ter sequencias de perdas em momentos
DIFERENTES (nao correlacionadas), rodar as duas como uma CESTA (qualquer uma
pode disparar, OU logico, nao E) pode DILUIR a probabilidade de ruina mesmo
que nenhuma das duas sozinha tenha edge validado -- porque ruina e' sobre a
SEQUENCIA de perdas CONSECUTIVAS, e se as perdas de uma nao coincidem com as
da outra, a sequencia COMBINADA tem menos rajadas longas do mesmo lado.

## Composicao -- OU logico, nao E

Esta classe NAO reimplementa a deteccao de nenhuma das duas familias: ela
IMPORTA as duas funcoes puras (`estado_anomalo_cruzado` da G4, passada ao
construtor como series pre-computadas, mesmo padrao da G4/G12) e replica,
lado a lado, EXATAMENTE a mesma logica de deteccao/geometria de
`WinBuscaLucroG08OrbSobrevivencia` (sinal A) e `WinBuscaLucroG04CrossWdo`
(sinal B) -- nao subclasse de nenhuma das duas (mesmo motivo de toda esta
busca: cada geracao congela seu proprio modulo, uma edicao futura de G04/G08
nunca pode afetar, silenciosamente, o resultado ja registrado desta
geracao).

A cada barra, o rompimento ORB e' checado PRIMEIRO; so' se o ORB NAO disparou
NESTA MESMA BARRA e' que o sinal cruzado e' considerado -- **prioridade
declarada: ORB vence empate** (os dois sinais raramente coincidem na mesma
barra -- ORB dispara na transicao de rompimento da faixa, cruzado dispara na
borda de uma anomalia de correlacao; quando coincidem, o ORB e' o sinal mais
simples/direto desta busca e fica com a prioridade). Nunca duas ordens
emitidas na mesma chamada de `on_bar`.

## O portao compartilhado -- nunca 2 posicoes, nunca 2 ordens pendentes

O motor so' guarda UMA ordem-limite pendente por vez (`resting_limit`) --
devolver uma `EnterLimit` nova enquanto outra esta pendente SUBSTITUI a
anterior em silencio. Para as duas familias nunca brigarem pelo mesmo slot,
esta classe mantem um UNICO estado de pendencia compartilhado,
`_ordem_pendente_origem` (`None`/`"orb"`/`"cross"`): nenhuma familia arma
ordem nova enquanto `_ordem_pendente_origem is not None` OU existe posicao
aberta. O estado e' resolvido (voltando a `None`) em tres pontos: fill (a
posicao abre -- `positions` transita vazio->nao-vazio), `on_order_expired` e
`on_order_rejected` (o motor nao diz qual ordem expirou/foi rejeitada, mas
so' pode existir uma pendente por vez, entao nao ha' ambiguidade).

## Disciplinas HERDADAS, declaradas, nao uniformizadas a forca

As duas familias tem disciplinas de reentrada DIFERENTES na geracao de
origem, e esta classe preserva as duas, nao inventa uma terceira:

- **ORB (G7/G8): "sem fade"** -- no maximo 1 operacao REAL do ORB por
  pregao (`_orb_preencheu_hoje`), mesmo depois que a posicao fechar. Se o
  ORB ja' operou hoje, so' o sinal cruzado pode disparar pelo resto do dia.
- **Cruzado (G4): sem teto diario** -- pode reentrar no MESMO pregao depois
  que uma posicao (de QUALQUER origem) fechar e o portao compartilhado
  estiver livre de novo, a mesma disciplina que a G4 sempre teve.

A pernada maior (R43, filtro de tendencia do sinal B) e a medicao da faixa
de abertura (sinal A) sao atualizadas em TODA barra, com ou sem posicao
aberta/pendente -- item 6.48 (estado nunca fica preso atras do portao de
emissao).

## Rastreio de origem por trade

O motor (`IntradayTrade`) nao carrega o `reason` da ordem de entrada. Esta
classe mantem `self.origem_por_entry_ts: dict[pd.Timestamp, str]`,
preenchido no momento do FILL (`positions[0].entry_ts` -> `"orb"` ou
`"cross"`) -- o harness casa `trade.entry_ts` contra este dict depois do
backtest para separar a sequencia combinada por familia de origem (p_ruina,
correlacao diaria, etc.), sem precisar que o motor saiba nada sobre
"familias".

## Desenho de execucao e capital -- identicos a toda a linha (CLAUDE.md, FECHADO)

`EnterLimit` com `ttl_bars` (nunca `Enter` a mercado); alvo por ordem-limite
real fatiada, SEM prazo; `anchor_exits_at_fill=True`; so' o STOP e' a
mercado; `target_fills_as_maker=True`; alvo sempre >= 3x o stop nas DUAS
geometrias (ValueError se nao). Fila do WIN@ NAO calibrada (premissa
otimista declarada pelo harness). Capital real R$250, 1 contrato fixo,
NUNCA 2 posicoes simultaneas (ver portao acima).
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG14PortfolioOrbCross"]

#: Pernada maior (R43) -- filtro de tendencia do sinal B, identico a G1-G4.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (CLAUDE.md, "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela -- definicao congelada em
    `REGRAS.md`, identica a R43/G1-G4. Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


class WinBuscaLucroG14PortfolioOrbCross(IntradayStrategy):
    """Cesta de DUAS familias desta busca -- ORB momentum (G8) e confirmacao
    cruzada WIN x WDO (G4) -- em OU logico, alternando sobre o MESMO caixa
    (nunca 2 posicoes/ordens simultaneas). Geracao 14 (alavanca 4 do
    mandato do coordenador: portfolio/alternancia)."""

    name = "win_busca_lucro_g14_portfolio_orb_cross"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        wdo_anomalo: pd.Series,
        wdo_direcao: pd.Series,
        symbol: str | None = None,
        # -- geometria ORB (sinal A, vencedor da G8/G13) --------------------
        orb_range_minutos: float = 5.0,
        orb_stop_min_pontos: float = 50.0,
        orb_stop_max_pontos: float = 140.0,
        orb_alvo_multiplo: float = 3.0,
        orb_buffer_entrada_pontos: float = 20.0,
        # -- geometria cruzado (sinal B, vencedor da G4) --------------------
        cross_direcao_aposta: str = "continuacao",
        cross_pernada_pontos: float = PERNADA_PONTOS,
        cross_stop_pontos: float = 150.0,
        cross_alvo_multiplo: float = 3.0,
        cross_buffer_entrada_pontos: float = 30.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        if orb_range_minutos <= 0:
            raise ValueError("orb_range_minutos tem que ser positivo")
        if orb_stop_min_pontos <= 0:
            raise ValueError("orb_stop_min_pontos tem que ser positivo")
        if orb_stop_max_pontos < orb_stop_min_pontos:
            raise ValueError("orb_stop_max_pontos tem que ser >= orb_stop_min_pontos")
        if orb_alvo_multiplo < 3.0:
            raise ValueError(
                f"orb_alvo_multiplo={orb_alvo_multiplo} abaixo de 3x -- fere a "
                f"disciplina alvo >= 3x o stop do mandato do dono")
        if orb_buffer_entrada_pontos < 0:
            raise ValueError("orb_buffer_entrada_pontos nao pode ser negativo")
        if cross_direcao_aposta not in ("continuacao", "reversao"):
            raise ValueError(f"cross_direcao_aposta={cross_direcao_aposta!r} invalido "
                              "-- 'continuacao' ou 'reversao'")
        if cross_pernada_pontos <= 0:
            raise ValueError("cross_pernada_pontos tem que ser positivo")
        if cross_stop_pontos <= 0:
            raise ValueError("cross_stop_pontos tem que ser positivo")
        if cross_alvo_multiplo < 3.0:
            raise ValueError(
                f"cross_alvo_multiplo={cross_alvo_multiplo} abaixo de 3x -- fere a "
                f"disciplina alvo >= 3x o stop do mandato do dono")
        if cross_buffer_entrada_pontos < 0:
            raise ValueError("cross_buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if symbol is not None:
            self.symbol = symbol

        self._wdo_anomalo = wdo_anomalo.to_dict() if isinstance(wdo_anomalo, pd.Series) else dict(wdo_anomalo)
        self._wdo_direcao = wdo_direcao.to_dict() if isinstance(wdo_direcao, pd.Series) else dict(wdo_direcao)

        self.orb_range_minutos = float(orb_range_minutos)
        self.orb_stop_min_pontos = float(orb_stop_min_pontos)
        self.orb_stop_max_pontos = float(orb_stop_max_pontos)
        self.orb_alvo_multiplo = float(orb_alvo_multiplo)
        self.orb_buffer_entrada_pontos = float(orb_buffer_entrada_pontos)

        self.cross_direcao_aposta = cross_direcao_aposta
        self.cross_pernada_pontos = float(cross_pernada_pontos)
        self.cross_stop_pontos = float(cross_stop_pontos)
        self.cross_alvo_multiplo = float(cross_alvo_multiplo)
        self.cross_buffer_entrada_pontos = float(cross_buffer_entrada_pontos)

        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49) --
        self.stats_bruto_orb = 0
        self.stats_bruto_cross = 0
        self.stats_orb_ja_operou_hoje = 0
        self.stats_cross_contra_tendencia = 0
        self.stats_cross_perdeu_empate_pra_orb = 0
        self.stats_ordens_emitidas_orb = 0
        self.stats_ordens_emitidas_cross = 0

        #: `entry_ts` (do FILL, = `IntradayOpenPosition.entry_ts`) -> "orb"/
        #: "cross" -- o harness casa contra `trade.entry_ts` depois do
        #: backtest (ver docstring do modulo).
        self.origem_por_entry_ts: dict[pd.Timestamp, str] = {}

        self._reset_sessao()

    # -- estado por sessao ---------------------------------------------------
    def _reset_sessao(self) -> None:
        # ORB (sinal A)
        self._open_ts: pd.Timestamp | None = None
        self._range_hi: float | None = None
        self._range_lo: float | None = None
        self._fora_hi = False
        self._fora_lo = False
        self._orb_preencheu_hoje = False
        # cruzado (sinal B) -- pernada maior (R43), nunca atravessa sessao
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        self._anomalo_anterior = False
        self._hist: deque[Bar] = deque(maxlen=4)
        # compartilhado
        self._tinha_posicao_anterior = False
        self._ordem_pendente_origem: str | None = None

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._ordem_pendente_origem = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._ordem_pendente_origem = None

    # -- geometria ORB (pura, identica a G08) ---------------------------------
    def _geometria_orb(self) -> tuple[float, float]:
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        stop = max(self.orb_stop_min_pontos, min(self.orb_stop_max_pontos, range_pontos))
        stop = round(stop / self.tick_size) * self.tick_size
        alvo = round((stop * self.orb_alvo_multiplo) / self.tick_size) * self.tick_size
        return float(stop), float(alvo)

    def _ordem_orb(self, side: str, limite: float, stop_pontos: float,
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

    # -- pernada maior (R43, identica a G04) ----------------------------------
    def _atualiza_perna(self, p: float) -> None:
        if self._origem is None:
            self._origem = p
            self._extremo = p
            return
        s = self._direcao
        if s is None:
            if p - self._origem >= self.cross_pernada_pontos:
                self._direcao = 1
                self._extremo = p
            elif self._origem - p >= self.cross_pernada_pontos:
                self._direcao = -1
                self._extremo = p
            return
        if s == 1:
            if p > self._extremo:
                self._extremo = p
            elif self._extremo - p >= self.cross_pernada_pontos:
                self._origem = self._extremo
                self._direcao = -1
                self._extremo = p
        else:
            if p < self._extremo:
                self._extremo = p
            elif p - self._extremo >= self.cross_pernada_pontos:
                self._origem = self._extremo
                self._direcao = 1
                self._extremo = p

    def _monta_entrada_cross(self, direcao_entrada: int, bar: Bar) -> IntradayAction | None:
        buf = self.cross_buffer_entrada_pontos
        if direcao_entrada == 1:
            lado = "long"
            limite = bar.close - buf
            stop = limite - self.cross_stop_pontos
            alvo = limite + self.cross_alvo_multiplo * self.cross_stop_pontos
        else:
            lado = "short"
            limite = bar.close + buf
            stop = limite + self.cross_stop_pontos
            alvo = limite - self.cross_alvo_multiplo * self.cross_stop_pontos

        limite = no_tick(limite, self.tick_size)
        if lado == "long" and limite >= bar.close:
            return None
        if lado == "short" and limite <= bar.close:
            return None

        return EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=f"g14_cross_{self.cross_direcao_aposta}_s{self.cross_stop_pontos:.0f}_a{self.cross_alvo_multiplo:.0f}x",
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
        self._hist.append(bar)

        # -- transicao de posicao (estado do INICIO da barra, item 6.48) ----
        # `positions` ja' reflete qualquer fill desta barra.
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            origem = self._ordem_pendente_origem
            if positions:
                self.origem_por_entry_ts[positions[0].entry_ts] = origem or "desconhecida"
            if origem == "orb":
                self._orb_preencheu_hoje = True
            self._ordem_pendente_origem = None
        self._tinha_posicao_anterior = tem_posicao_agora

        # -- sinal A (ORB): a faixa de abertura e' SEMPRE medida/atualizada,
        # com ou sem posicao/pendencia (item 6.48, identico a G08). ---------
        dentro_da_faixa = (ts - self._open_ts) < pd.Timedelta(minutes=self.orb_range_minutos)
        if dentro_da_faixa:
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            nova_alta = nova_baixa = False
        else:
            if self._range_hi is None or self._range_lo is None:
                nova_alta = nova_baixa = False
            else:
                rompeu_alta = bar.close > self._range_hi
                rompeu_baixa = bar.close < self._range_lo
                nova_alta = rompeu_alta and not self._fora_hi
                nova_baixa = rompeu_baixa and not self._fora_lo
                self._fora_hi = rompeu_alta
                self._fora_lo = rompeu_baixa

        if nova_alta or nova_baixa:
            self.stats_bruto_orb += 1

        # -- sinal B (cruzado): pernada maior SEMPRE atualizada (identico a
        # G04, "nao condicionado a pode_armar"). -----------------------------
        for p in _caminho_da_barra(bar):
            self._atualiza_perna(p)

        anomalo_agora = bool(self._wdo_anomalo.get(ts, False))
        direcao_sinal = int(self._wdo_direcao.get(ts, 0))
        disparo_novo_cross = anomalo_agora and not self._anomalo_anterior
        self._anomalo_anterior = anomalo_agora
        if disparo_novo_cross and direcao_sinal != 0:
            self.stats_bruto_cross += 1

        # -- portao compartilhado: nunca 2 posicoes, nunca 2 pendentes ------
        pode_emitir = (not tem_posicao_agora) and self._ordem_pendente_origem is None
        ja_emitiu_nesta_barra = False
        acoes: list[IntradayAction] = []

        # (1) ORB tem PRIORIDADE declarada no empate (ver docstring). -------
        orb_disparou_aqui = False
        if nova_alta or nova_baixa:
            if self._orb_preencheu_hoje:
                self.stats_orb_ja_operou_hoje += 1
            elif pode_emitir:
                stop_pontos, alvo_pontos = self._geometria_orb()
                buf = self.orb_buffer_entrada_pontos
                if nova_alta:
                    limite = bar.close - buf
                    acao = self._ordem_orb("long", limite, stop_pontos, alvo_pontos,
                                            "g14_orb_rompimento_alta")
                else:
                    limite = bar.close + buf
                    acao = self._ordem_orb("short", limite, stop_pontos, alvo_pontos,
                                            "g14_orb_rompimento_baixa")
                acoes.append(acao)
                self._ordem_pendente_origem = "orb"
                self.stats_ordens_emitidas_orb += 1
                ja_emitiu_nesta_barra = True
                orb_disparou_aqui = True

        # (2) cruzado -- so' considerado se o ORB NAO disparou NESTA barra. -
        if disparo_novo_cross and direcao_sinal != 0:
            direcao_entrada = direcao_sinal if self.cross_direcao_aposta == "continuacao" else -direcao_sinal
            if self._direcao != direcao_entrada:
                self.stats_cross_contra_tendencia += 1
            elif orb_disparou_aqui:
                self.stats_cross_perdeu_empate_pra_orb += 1
            elif pode_emitir and not ja_emitiu_nesta_barra:
                acao = self._monta_entrada_cross(direcao_entrada, bar)
                if acao is not None:
                    acoes.append(acao)
                    self._ordem_pendente_origem = "cross"
                    self.stats_ordens_emitidas_cross += 1

        return acoes
