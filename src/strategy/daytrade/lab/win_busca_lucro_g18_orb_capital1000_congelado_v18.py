# -*- coding: utf-8 -*-
"""`WinBuscaLucroG18OrbCapital1000` (CONGELADO v18) -- Geracao 18 da busca
por um EA lucrativo do WIN.

CONGELADO ANTES do OOS-1 (jul-ago/2026) com o vencedor do IS: stop_max_pontos
=140, alvo_multiplo=3.0, range_minutos=5.0, buffer_entrada_pontos=20.0,
stop_min_pontos=50.0, capital de teste R$1.000. Nunca editar este arquivo
depois do OOS -- qualquer mudanca de parametro/logica vira uma geracao nova.

## Mandato (dono, 2026-10-05), mesma porta aberta da G17 -- agora sobre o ORB

A G17 testou as duas portas (capital de teste R$1.000 + grade de
`alvo_multiplo` ate' 2,0x) sobre o sinal de confirmacao cruzada WIN x WDO
(G4) e achou: capital maior resolve a RUINA por sequencia de perdas de forma
dramatica (Monte Carlo 35,3%->0,3%, mesma geometria/mesmos trades), mas NAO
resolve a CONCENTRACAO temporal do sinal (o gatilho dispara em rajadas
dentro de poucos pregoes de regime forte -- top3/liquido piorou para 383%
no OOS-1, PIOR que a R$250). A pergunta desta geracao: o ORB (G8/G13) --
que dispara no MAXIMO 1x/pregao por construcao, nunca em rajada dentro do
MESMO dia, diferente do estado anomalo cruzado que pode reentrar varias
vezes no mesmo pregao favoravel -- tem o MESMO modo de falha de concentracao,
ou e' estruturalmente menos concentrado? A G13 ja mediu, a R$250, um
PENHASCO isolado (stop_max=140/alvo=3x sobrevive, stop_max=150+ ou alvo=4x+
colapsam em censura total de capital) -- o precedente da G17 (comparacao
isolada mostrando que capital maior derruba ruina de forma dramatica SEM
mudar nenhum trade) sugere que o mesmo penhasco pode deixar de existir a
R$1.000, porque o caixa aguenta a mesma sequencia de perdas que cruzava a
margem a R$250.

## O que foi reaproveitado por IMPORT/copia deliberada (mandato explicito:
## "reaproveite a deteccao de rompimento ORB da G8/G13 -- pode importar")

A deteccao de rompimento (faixa de abertura de `range_minutos` minutos,
rompimento fresco = transicao de "dentro"/"ja rompido sem reentrar" para
rompimento NOVO, no maximo 1 operacao REAL por pregao, sempre na direcao do
proprio rompimento -- momentum, sem fade) e' IDENTICA a
`WinBuscaLucroG08OrbSobrevivencia` (`win_busca_lucro_g08_orb_sobrevivencia.py`),
que por sua vez e' copia deliberada de G07. NADA na logica de sinal muda
entre G8 e esta geracao -- a UNICA mudanca de contrato e' o piso de
`alvo_multiplo`, que cai de 3,0 para 2,0 (nunca <=1x -- perder>=ganhar
continua proibido, principio inegociavel do dono, sem parametro que
desligue). Mesma razao da G17 para nao editar o modulo anterior in-place:
`WinBuscaLucroG08OrbSobrevivencia` e' citada com o contrato `alvo_multiplo
>= 3,0` em G08/G13 (e os numeros la' publicados dependem desse contrato) --
uma classe NOVA e' o jeito de abrir a grade 2x/2,5x sem alterar, nem de
leve, nenhum resultado ja registrado.

## Capital -- mudanca de TESTE, nao de estrategia

A classe em si nao muda de tamanho (`quantity=1` fixo por default, mesma
decisao de G1-G17 -- "isola o efeito do alvo/stop primeiro", dimensionamento
dinamico fica para a G19). O que muda e' o `initial_capital`/`cash_brl` que
o HARNESS (`g18_base.py`) passa ao `config_for` -- R$1.000 em vez de R$250 --
e por isso o motor (`contracts_from_capital_operacional`) so' bloqueia uma
entrada por falta de caixa bem mais tarde na sequencia de perdas. A margem
CRUA do WIN@ nao muda (R$100/contrato, sempre) -- so' o colchao antes dela.

## Desenho de execucao (FECHADO -- CLAUDE.md, nao negociavel)

`EnterLimit` com `ttl_bars` (nunca `Enter` a mercado); limite
`buffer_entrada_pontos` ATRAS do rompimento; alvo por ordem-limite real
fatiada (`exit_split_unit`), SEM prazo (`exit_ttl_bars=None`); `anchor_exits_
at_fill=True`; so' o STOP e' a mercado; `target_fills_as_maker=True`. Fila do
WIN@ NAO calibrada -- toda ordem-limite enche no TOQUE (premissa otimista
declarada pelo harness, precedente G1-G17).

## Geometria -- os dois eixos que esta geracao varia

`stop = clip(faixa_de_abertura, stop_min_pontos, stop_max_pontos)` (teto
quase sempre bind, mesmo achado de G7/G8/G13: a faixa do WIN@ aos 5min tem
mediana ~860pts). `alvo = stop x alvo_multiplo`, piso >= 2,0x (nunca <=1x).
Quando a mediana do stop realizado cai abaixo de 100 pontos, o item 6.47
exige checagem com ticks reais antes de aceitar qualquer numero positivo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG18OrbCapital1000"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G17 desta busca.
TTL_BARRAS_ENTRADA = 10

#: Piso INEGOCIAVEL da grade desta geracao (decisao do dono, 2026-10-05,
#: mesma porta aberta da G17): alvo/stop nunca pode cair para <=1x (perder
#: >= ganhar e' proibido, sem parametro que desligue).
ALVO_MULTIPLO_MINIMO = 2.0


class WinBuscaLucroG18OrbCapital1000(IntradayStrategy):
    """Rompimento da faixa de abertura do WIN@ (logica IDENTICA a` G07/G08),
    NO MAXIMO 1 operacao REAL por pregao, sempre na direcao do proprio
    rompimento (momentum) -- Geracao 18 reabre o piso de `alvo_multiplo` para
    2,0x (porta da G17) e testa capital de teste R$1.000 (harness), para
    checar se o penhasco de ruina que a G8/G13 mediram a R$250 (stop_max=140/
    alvo=3x isolado, cercado de colapso total) sobrevive ao caixa maior, e se
    a concentracao temporal do ORB (gatilho no maximo 1x/pregao por
    construcao) e' estruturalmente menor que a do sinal cruzado WIN x WDO da
    G17 (que piorou para 383% no OOS-1)."""

    name = "win_busca_lucro_g18_orb_capital1000"
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
        stop_max_pontos: float = 250.0,
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
        self.range_minutos = float(range_minutos)
        self.stop_min_pontos = float(stop_min_pontos)
        self.stop_max_pontos = float(stop_max_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49) --
        self.stats_bruto = 0
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

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    # -- geometria (pura) -----------------------------------------------------
    def _geometria(self) -> tuple[float, float]:
        """`(stop_pontos, alvo_pontos)` -- stop sai do tamanho da faixa,
        limitado entre piso e teto; alvo = stop x `alvo_multiplo` (>= 2x por
        construcao, piso da G17/G18). Arredondado a` grade de preco do WIN@
        (5 pontos)."""
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
        # "posicao aberta"/"ja armado"/"ja operou hoje" (item 6.48).
        self.stats_bruto += 1

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
                                "g18_orb_capital1000_rompimento_alta")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos,
                            "g18_orb_capital1000_rompimento_baixa")]
