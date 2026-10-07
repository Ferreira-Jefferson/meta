# -*- coding: utf-8 -*-
"""`WinBuscaLucroG20CrossWdoFreq` -- copia CONGELADA (Geracao 20) da mesma
classe de execucao da G17 (`WinBuscaLucroG17CrossWdoCapital1000`), SEM
NENHUMA mudanca de codigo/comportamento -- so' renomeada para esta geracao
ter seu proprio arquivo congelado, independente do ciclo de vida do arquivo
da G17.

## Por que esta geracao nao precisou de classe nova

A Geracao 20 ataca a CONCENTRACAO temporal do sinal cruzado WIN x WDO (G4/
G17) pela FREQUENCIA do gatilho, nao pelo tamanho da aposta (G19 ja mostrou
que graduar por magnitude PIORA a concentracao -- ver ORQUESTRACAO.md). A
alavanca e' baixar o `quantil` de `estado_anomalo_cruzado` (funcao pura da
G4, ja aceita `quantil` como parametro) para capturar mais episodios -- a
classe de execucao (`alvo_multiplo` em grade {2x..5x}, capital de teste
R$1.000, execucao fechada) ja era exatamente a da G17, sem precisar de
nenhuma alteracao.

## Vencedor do IS (congelado ANTES do OOS-1, ver `g20_vencedor_diagnostico.py`)

`quantil=0,60` (baixado de 0,75 da G17), `janela_min=20`, `direcao_aposta=
continuacao`, `stop_pontos=150`, `alvo_multiplo=3,0`, `buffer_entrada_
pontos=30`, capital de teste R$1.000. IS (jan-jun/2026, 122 pregoes):
liquido=+R$2.166,00, 324 trades, win=32,7% (BEemp=27,1%, IC95[27,8;38,0]
POSITIVO por 0,7pp), 95/122 pregoes com trade (so' 27 sem trade -- contra
62/125 pregoes com trade da G17), top3/liquido=38,5%, top5/liquido=58,4%
(dramaticamente menor que os 56,3%/77,0% da G17), p_ruina(MC)=1,6%.

## O resto -- identico a` G17/G4/linha inteira (CLAUDE.md, execucao fechada)

Entrada so' `EnterLimit` com `ttl_barras_entrada` obrigatorio, limite
`buffer_entrada_pontos` pontos atras do fechamento. Stop e alvo em PONTOS
fixos. Alvo so' como ordem-limite real fatiada (`exit_split_unit`), SEM
prazo; so' o stop e' a mercado; `anchor_exits_at_fill=True`;
`target_fills_as_maker=True`. Sempre a favor da pernada maior do WIN (R43,
principio inegociavel, sem parametro que desligue). Fila WIN@ nao calibrada
(`queue_ahead_qty=0`), premissa otimista declarada, identica a` linha
inteira. Piso `alvo_multiplo>=2,0x` (nunca <=1x) intacto e INEGOCIAVEL.
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)
# Reaproveitada por IMPORT direto -- mesma funcao pura da G4, agora chamada
# com quantil=0,60 pelo harness (nao reimplementada aqui).
from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import (  # noqa: F401
    estado_anomalo_cruzado,
)

#: Limiar da pernada maior (zigzag causal sobre o caminho da vela, R43).
#: Nao e' parametro desta geracao -- o mesmo valor usado em G1-G19.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Dias INTEIROS de historico, estritamente anteriores ao dia corrente,
#: exigidos antes do quantil causal comecar a valer -- identico a` G4.
MIN_DIAS_BURN_IN = 20
#: Piso INEGOCIAVEL da grade (decisao do dono, 2026-10-05): alvo/stop nunca
#: pode cair para <=1x (perder>=ganhar e' proibido).
ALVO_MULTIPLO_MINIMO = 2.0


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela -- definicao CONGELADA em
    `REGRAS.md`, identica a` usada em R43/R65/R57/G4. Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


class WinBuscaLucroG20CrossWdoFreq(IntradayStrategy):
    """Opera o WIN@ quando WIN@ e WDO@ andam, por uma janela curta, na MESMA
    direcao (estado ANOMALO cruzado, reaproveitado da G4, agora com quantil
    mais baixo para capturar mais episodios). WDO entra so' como FILTRO/
    GATILHO (nunca como posicao). Sempre a favor da pernada maior do WIN
    (R43, principio inegociavel) -- Geracao 20 da busca por um EA lucrativo
    do WIN (`ORQUESTRACAO.md`), copia CONGELADA e sem mudanca de codigo da
    classe de execucao da G17."""

    name = "win_busca_lucro_g20_cross_wdo_freq"
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
        direcao_aposta: str = "continuacao",
        pernada_pontos: float = PERNADA_PONTOS,
        stop_pontos: float = 150.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 30.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        if direcao_aposta not in ("continuacao", "reversao"):
            raise ValueError(f"direcao_aposta={direcao_aposta!r} invalido -- "
                              "'continuacao' ou 'reversao'")
        if pernada_pontos <= 0:
            raise ValueError("pernada_pontos tem que ser positivo")
        if stop_pontos <= 0:
            raise ValueError("stop_pontos tem que ser positivo")
        if alvo_multiplo < ALVO_MULTIPLO_MINIMO:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo do piso de "
                f"{ALVO_MULTIPLO_MINIMO}x -- perder>=ganhar e' proibido "
                f"(principio inegociavel do dono, mesmo com o mandato "
                f"relaxado de 2026-10-05)")
        if buffer_entrada_pontos < 0:
            raise ValueError("buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if quantity < 1:
            raise ValueError("quantity tem que ser >= 1")
        if symbol is not None:
            self.symbol = symbol
        self._wdo_anomalo = wdo_anomalo.to_dict() if isinstance(wdo_anomalo, pd.Series) else dict(wdo_anomalo)
        self._wdo_direcao = wdo_direcao.to_dict() if isinstance(wdo_direcao, pd.Series) else dict(wdo_direcao)
        self.direcao_aposta = direcao_aposta
        self.pernada_pontos = float(pernada_pontos)
        self.stop_pontos = float(stop_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (licao da G2/G4 / item 6.48) --
        self.stats_bruto = 0
        self.stats_contra_tendencia = 0
        self.stats_ordens_emitidas = 0

        self._reset_sessao()

    # -- estado por sessao --------------------------------------------------
    def _reset_sessao(self) -> None:
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        self._anomalo_anterior = False
        self._espera: int | None = None
        self._hist: deque[Bar] = deque(maxlen=4)

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
            reason=f"g20_cross_wdo_{self.direcao_aposta}_s{self.stop_pontos:.0f}_a{self.alvo_multiplo:.1f}x",
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

        # Decide ANTES de atualizar qualquer estado se este robo PODE armar
        # uma ordem nova nesta barra -- com o `_espera` que existia no INICIO
        # da barra (licao da Geracao 2/4 / item 6.48).
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

        for p in _caminho_da_barra(bar):
            self._atualiza_perna(p)

        anomalo_agora = bool(self._wdo_anomalo.get(ts, False))
        direcao_sinal = int(self._wdo_direcao.get(ts, 0))
        disparo_novo = anomalo_agora and not self._anomalo_anterior
        self._anomalo_anterior = anomalo_agora

        if not (disparo_novo and direcao_sinal != 0):
            return []

        self.stats_bruto += 1
        direcao_entrada = direcao_sinal if self.direcao_aposta == "continuacao" else -direcao_sinal

        if self._direcao != direcao_entrada:
            self.stats_contra_tendencia += 1
            return []

        if not pode_armar:
            return []

        acao = self._monta_entrada(direcao_entrada, bar)
        if acao is None:
            return []
        self.stats_ordens_emitidas += 1
        return [acao]
