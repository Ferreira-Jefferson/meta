# -*- coding: utf-8 -*-
"""`WinBuscaLucroG17CrossWdoCapital1000` -- Geracao 17 da busca por um EA
lucrativo do WIN.

## Mudanca de mandato (dono, 2026-10-05), so' para esta busca

Depois de 16 geracoes mortas pela mesma restricao estrutural (capital R$250
+ `alvo>=3x` -> win% baixo -> sequencia de perdas quebra o caixa, ver a
sintese da G16 em `ORQUESTRACAO.md`), o dono abriu DUAS portas:

1. Capital de teste = **R$1.000** (nao R$250 -- excecao explicita, so' nesta
   busca, nao muda a regra geral do resto do repo).
2. `alvo_multiplo` vira GRADE **{2x, 2,5x, 3x, 4x, 5x}** em vez de fixo
   `>=3x`. O piso nunca cai para <=1x (perder>=ganhar continua proibido,
   principio inegociavel do dono) -- so' o MINIMO aceitavel caiu de 3x para
   2x.

## O que foi reaproveitado, por import direto (mandato explicito: "pode
importar")

`estado_anomalo_cruzado` (funcao pura module-level de
`win_busca_lucro_g04_cross_wdo`, j=20min/q=0,75/continuacao ja identificados
como o melhor ponto no IS original) -- REIMPORTADA, nao reimplementada. A
estrutura geral da classe (pernada maior R43 como filtro de tendencia
inegociavel, `EnterLimit` com buffer de entrada, execucao fechada) tambem e'
a mesma da G4 -- esta classe e' uma copia deliberada com UMA mudanca de
contrato: o piso de `alvo_multiplo` cai de 3,0 para 2,0 (o resto da
disciplina -- nunca <=1x -- fica intacto e INEGOCIAVEL, sem parametro que
desligue).

## Por que uma classe nova em vez de so' baixar o `if` da G4

A classe da G4 (`WinBuscaLucroG04CrossWdo`) e' citada e comparada em varias
geracoes seguintes (G5/G12/G14/G15/G16) com o contrato `alvo_multiplo>=3,0`
-- mudar o ValueError dela in-place mudaria silenciosamente a garantia que
essas geracoes ja documentaram sobre ela. Uma classe nova e' o jeito de abrir
a grade 2x/2,5x sem alterar nenhum comportamento ja registrado.

## Capital -- unica mudanca de TESTE, nao de estrategia

A classe em si nao muda de tamanho: `quantity=1` FIXO (mesma decisao de
G1-G4/G16 -- "isola o efeito do alvo/stop primeiro", dimensionamento
dinamico fica para a G19). O que muda e' o `initial_capital`/`cash_brl` que
o HARNESS (`g17_base.py`) passa ao `config_for` -- R$1.000 em vez de R$250 --
e por isso o motor (`contracts_from_capital_operacional`) so' bloqueia uma
entrada por falta de caixa bem mais tarde na sequencia de perdas. A margem
CRUA do WIN@ nao muda (R$100/contrato, sempre) -- so' o COLCHAO antes dela.

## O resto -- identico a` G4/linha inteira (CLAUDE.md, execucao fechada)

Entrada so' `EnterLimit` com `ttl_barras_entrada` obrigatorio, limite
`buffer_entrada_pontos` pontos atras do fechamento. Stop e alvo em PONTOS
fixos. Alvo so' como ordem-limite real fatiada (`exit_split_unit`), SEM
prazo; so' o stop e' a mercado; `anchor_exits_at_fill=True`;
`target_fills_as_maker=True`. Sempre a favor da pernada maior do WIN (R43,
principio inegociavel, sem parametro que desligue). Fila WIN@ nao calibrada
(`queue_ahead_qty=0`), premissa otimista declarada, identica a` G4.
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)
# Reaproveitada por IMPORT direto -- mandato explicito da G17, nao
# reimplementada (j=20min/q=0,75/continuacao ja identificados na G4).
from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import (  # noqa: F401
    estado_anomalo_cruzado,
)

#: Limiar da pernada maior (zigzag causal sobre o caminho da vela, R43).
#: Nao e' parametro desta geracao -- o mesmo valor usado em G1-G4/G16.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Dias INTEIROS de historico, estritamente anteriores ao dia corrente,
#: exigidos antes do quantil causal comecar a valer -- identico a` G4.
MIN_DIAS_BURN_IN = 20
#: Piso INEGOCIAVEL da grade desta geracao (decisao do dono, 2026-10-05):
#: alvo/stop nunca pode cair para <=1x (perder>=ganhar e' proibido).
ALVO_MULTIPLO_MINIMO = 2.0


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela -- definicao CONGELADA em
    `REGRAS.md`, identica a` usada em R43/R65/R57/G4. Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


class WinBuscaLucroG17CrossWdoCapital1000(IntradayStrategy):
    """Opera o WIN@ quando WIN@ e WDO@ andam, por uma janela curta, na MESMA
    direcao (estado ANOMALO cruzado, reaproveitado da G4). WDO entra so'
    como FILTRO/GATILHO (nunca como posicao). Sempre a favor da pernada
    maior do WIN (R43, principio inegociavel) -- Geracao 17 da busca por um
    EA lucrativo do WIN (`ORQUESTRACAO.md`), capital de teste R$1.000 e
    `alvo_multiplo` liberado para a grade {2x,2,5x,3x,4x,5x}."""

    name = "win_busca_lucro_g17_cross_wdo_capital1000"
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
            reason=f"g17_cross_wdo_{self.direcao_aposta}_s{self.stop_pontos:.0f}_a{self.alvo_multiplo:.1f}x",
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
