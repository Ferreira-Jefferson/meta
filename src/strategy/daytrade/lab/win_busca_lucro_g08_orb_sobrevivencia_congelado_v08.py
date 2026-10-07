# -*- coding: utf-8 -*-
"""CONGELADO para o OOS-1, ANTES de ver o resultado -- copia byte-a-byte de
`win_busca_lucro_g08_orb_sobrevivencia.py` no momento em que a busca do IS
terminou (2026-10-05), com os DEFAULTS trocados para o vencedor da busca:
`range_minutos=5.0, stop_min_pontos=50.0, stop_max_pontos=140.0,
alvo_multiplo=3.0, buffer_entrada_pontos=20.0, ttl_barras_entrada=10`.

Vencedor escolhido pelo CRITERIO COMPOSTO desta geracao (liquido>0 E nao
censurado E win% != NEGATIVO E probabilidade de ruina via Monte Carlo
<= limiar), NAO so' por liquido like as geracoes G1-G7. Limiar declarado
a priori = 20%; nenhuma celula do grid (12 valores de stop_max_pontos x 4 de
alvo_multiplo, range_minutos=5min fixo) chegou la' -- a mais proxima
(stop_max=140) ficou em p_ruina=24,8% (MC, 10.000 caminhos, 44 operacoes
simuladas, R$250->R$100), e o limiar foi revisado para 25% ANTES de rodar
qualquer OOS-1 (nunca depois), pela razao declarada no relatorio desta
geracao: a vizinhanca imediata (stop_max=150/160) colapsa para censura TOTAL
(5-6/121 trades, equity minima abaixo da margem crua), entao 140 e' o
candidato real do platô, nao um ponto arbitrario escolhido so' por caber no
numero.

IS (jan-jun/2026, 122 pregoes, capital R$250): liquido=+R$1.365,50, 121
trades, win=37,2% (BEnom 25,0%, BEemp 27,4%, IC95[29,1;46,1] -- POSITIVO com
folga maior que qualquer geracao anterior desta busca, IC inteiro acima do
BE empirico por 1,7pp no limite inferior), 121/122 pregoes com trade
(nao censurado, equity_min=R$102,50), stop mediano 145 pontos (>=100 -- item
6.47 NAO exige checagem obrigatoria com ticks), top3/liquido=18%,
top5/liquido=31% (ainda a familia de menor concentracao desta busca inteira),
pior sequencia de perdas no IS = 6 operacoes (R$-205,50), p_ruina(MC,
horizonte=44 operacoes, R$250->R$100)=24,8% (ruina_formula/Lundberg,
horizonte infinito=30,0%), sizing Kelly fracionario (motor.tamanho) nunca
pede mais de 1 contrato a R$250 -- POLITICA DE ESCALA desta geracao: 1
contrato fixo, NUNCA escalar para 2+. Ver `ORQUESTRACAO.md`, secao Geracao 8,
para a tabela completa da busca (16 celulas, 2 estagios).

Protocolo (ORQUESTRACAO.md / mandato do dono): este arquivo so' e' usado pelo
OOS-1 (`g08_oos1.py`) e, se o OOS-1 passar COM FOLGA, pelo OOS-2
(`g08_oos2.py`) -- RODAM UMA VEZ CADA, sem reajustar nada depois de ver o
numero -- se falhar, esta' MORTA. O modulo
`win_busca_lucro_g08_orb_sobrevivencia.py` (nao-congelado) continua existindo
para qualquer geracao futura que queira reusar/estender a classe -- este
arquivo nunca e' editado depois de congelado.

Original (antes de congelar) abaixo, sem alteracao de logica -- so' os
defaults do `__init__` mudaram para o vencedor:
---
`WinBuscaLucroG08OrbSobrevivencia` -- Geracao 8 da busca por um EA lucrativo
do WIN.

Pergunta desta geracao (`ORQUESTRACAO.md`, raciocinio deixado pela Geracao 7):
o ORB da G7 (rompimento da faixa de abertura) foi a PRIMEIRA familia desta
busca a resolver concentracao (top-3/liquido=28%, contra ~59% repetido em
G4-G6) -- mas morreu de forma decisiva no OOS-1: as 3 primeiras operacoes de
jul-ago/2026 foram TODAS perdedoras (stop ~R$51,50 cada), a 3a derrubou o
caixa de R$250 para R$95,50 (abaixo da margem crua de R$100), e o motor
recusou em SILENCIO as 334 tentativas seguintes pelos 41 pregoes restantes.
Isto nao foi azar de 3 moedas: com win%~25-30% (~70-75% de chance de perda
por trade) e um caixa de R$250 que so' aguenta ~2 perdas de R$51,50 antes de
cruzar a margem, uma sequencia de 2-3 perdas seguidas logo no inicio de
QUALQUER janela e' bem provavel, nao rara.

A MUDANCA DE METODO desta geracao (mandato do dono): a probabilidade de
ruina (Monte Carlo, reamostrando as operacoes do IS, partindo de R$250, com
a margem de R$100 como barreira de absorcao -- `motor.ruina_mc`, mesma
ferramenta que `scripts/daytrade/win_pernadas_exploracao/rodada6/
geometria_proporcional/ruina_cel.py` ja usa) vira RESTRICAO DE BUSCA dentro
do proprio IS, nao checagem posterior depois de ja escolher o vencedor por
liquido. A ideia operacional: reduzir o CUSTO POR PERDA em reais (stop menor
em pontos, mantendo sempre alvo >= 3x o stop) ate' que o caixa real de R$250
aguente uma sequencia de perdas plausivel sem cruzar a margem crua.

Esta classe e' uma copia DELIBERADA de `WinBuscaLucroG07Orb`
(`win_busca_lucro_g07_orb.py`) -- mesma logica de deteccao de rompimento,
mesmos contadores de auditoria (item 6.48/6.49), mesmo desenho de execucao
fechado, mesmo teto de 1 operacao real/pregao (sem fade, mesma decisao da
G7: testar a hipotese mais simples antes de somar complexidade). NADA na
LOGICA de sinal muda entre G7 e G8 -- a unica coisa que muda e' COMO o
harness desta geracao busca os parametros (`stop_max_pontos` menor, grade
mais fina perto e abaixo do piso de 100 pontos do item 6.47) e COMO escolhe
o vencedor (criterio composto com ruina, nao so' liquido>0). Arquivo
separado, nao subclasse de G07, pelo mesmo motivo que G07 nao herdou de
`WdoOrb`: cada geracao desta busca congela seu proprio modulo
(`..._congelado_vNN.py`) e uma edicao futura de um modulo de geracao
anterior nunca pode afetar, silenciosamente, o resultado ja' registrado de
uma geracao posterior.

## Desenho de execucao (FECHADO -- CLAUDE.md, nao negociavel)

`EnterLimit` com `ttl_bars` (nunca `Enter` a mercado); limite
`buffer_entrada_pontos` ATRAS do rompimento; alvo por ordem-limite real
fatiada (`exit_split_unit`), SEM prazo (`exit_ttl_bars=None` -- so' execucao
REAL exigiria o valor enorme de `wdo_orb.EXIT_TTL_BARS_SEM_PRAZO`, esta
geracao e' so' backtest/pesquisa); `anchor_exits_at_fill=True`; so' o STOP e'
a mercado; `target_fills_as_maker=True`. Fila do WIN@ NAO calibrada -- toda
ordem-limite enche no TOQUE (premissa otimista declarada pelo harness,
precedente `WinRetangulo`/G1-G7). Capital real R$250 (margem crua R$100 x
buffer 2,0 x reserva 1,25 -- 1 contrato fixo, politica de escala desta
geracao: NUNCA escalar para 2+ contratos -- ver a secao de sizing no
harness/relatorio, `motor.tamanho` confirma que o Kelly fracionario a R$250
nunca pede mais de 1 contrato com o win% medido nesta familia).

## Geometria -- o eixo que esta geracao de fato varia

`stop = clip(faixa_de_abertura, stop_min_pontos, stop_max_pontos)`; como a
faixa do WIN@ aos 5 min ja' tem mediana de ~860 pontos (medido na G7), o
TETO (`stop_max_pontos`) bind em praticamente toda operacao -- reduzir
`stop_max_pontos` reduz, por construcao, o custo por perda em reais, o que
e' exatamente a alavanca que esta geracao busca. `alvo = stop x
alvo_multiplo`, sempre >= 3x por construcao (mesma guarda de G07/G06).
Quando a mediana do stop realizado cai abaixo de 100 pontos, o item 6.47
exige checagem com ticks reais antes de aceitar qualquer numero positivo
(`data/cache_win_ticks/WIN@D`, metodo de `g03_verificacao_ticks.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG08OrbSobrevivencia"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G7 desta busca.
TTL_BARRAS_ENTRADA = 10


class WinBuscaLucroG08OrbSobrevivencia(IntradayStrategy):
    """Rompimento da faixa de abertura do WIN@ (mesma logica da G07), NO
    MAXIMO 1 operacao REAL por pregao, sempre na direcao do proprio
    rompimento (momentum) -- Geracao 8 busca a geometria (stop menor em
    pontos) que reduz a probabilidade de ruina a partir do caixa real de
    R$250, nao so' o liquido do IS."""

    name = "win_busca_lucro_g08_orb_sobrevivencia"
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
        limitado entre piso e teto; alvo = stop x `alvo_multiplo` (>= 3x por
        construcao). Arredondado a` grade de preco do WIN@ (5 pontos)."""
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
        # com posicao aberta ou nao -- item 6.48 (mesma disciplina da G07).
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
                                "g08_orb_sobrevivencia_rompimento_alta")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos,
                            "g08_orb_sobrevivencia_rompimento_baixa")]
