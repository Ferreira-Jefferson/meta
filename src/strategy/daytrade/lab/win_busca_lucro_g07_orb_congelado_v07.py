# -*- coding: utf-8 -*-
"""CONGELADO para o OOS-1, ANTES de ver o resultado -- copia byte-a-byte de
`win_busca_lucro_g07_orb.py` no momento em que a busca do IS terminou
(2026-10-05), com os DEFAULTS trocados para o vencedor da busca:
`range_minutos=5.0, stop_min_pontos=100.0, stop_max_pontos=250.0,
alvo_multiplo=5.0, buffer_entrada_pontos=20.0, ttl_barras_entrada=10`.

IS (jan-jun/2026, 122 pregoes, capital R$250): liquido=+R$2.685,50, 121
trades, win=24,8% (BEnom 16,7%, BEemp 17,4%, IC95[18,0;33,2] -- POSITIVO, mas
por margem apertada, 0,6pp acima do BE empirico), 121/122 pregoes com trade,
top3/liquido=28%, top5/liquido=46%, stop mediano 255 pontos (>=100 -- item
6.47 nao exige checagem obrigatoria com ticks), equity minima R$132,00 (nao
censurado). Ver `ORQUESTRACAO.md`, secao Geracao 7, para a tabela completa dos
3 estagios de busca.

Protocolo (ORQUESTRACAO.md / mandato do dono): este arquivo so' e' usado pelo
OOS-1 (`g07_oos1.py`), RODA UMA VEZ, sem reajustar nada depois de ver o
numero -- se falhar, esta' MORTA. O modulo `win_busca_lucro_g07_orb.py`
(nao-congelado) continua existindo para qualquer geracao futura que queira
reusar/estender a classe -- este arquivo nunca e' editado depois de congelado.

Original (antes de congelar) abaixo, sem alteracao de logica -- so' os
defaults do `__init__` mudaram para o vencedor:
---
`WinBuscaLucroG07Orb` -- Geracao 7 da busca por um EA lucrativo do WIN.

Pergunta desta geracao (`ORQUESTRACAO.md`, raciocinio deixado pela Geracao 6):
as Geracoes 4-6 esgotaram a familia "continuacao da pernada maior sob gatilho
de regime/volatilidade/cross-market" -- tres geracoes seguidas batendo no
mesmo sintoma (concentracao top-3/liquido) por tres angulos diferentes sem
resolve-lo e evidencia de que a causa e' estrutural (resíduo pequeno entre
bruto-ganho e bruto-perda), nao o desenho do robo. A instrucao para a G7 foi
explicita: abandonar essa familia e testar um gatilho de natureza
ESTRUTURALMENTE DIFERENTE -- nao magnitude, nao cross-market, nao pernada de
750 pontos.

Esta geracao adapta `strategy.daytrade.lab.wdo_orb.WdoOrb` (ORB -- Opening
Range Breakout -- do mini-dolar, JA EM PRODUCAO real, mesmo motor/desenho de
execucao) para o mini-indice (WIN@). E' uma familia diferente de tudo testado
em G1-G6: a faixa de abertura dos primeiros `range_minutos` do pregao define
sozinha o nivel de entrada E a geometria de stop -- nao depende de pernada de
750 pontos, de regime de volatilidade, nem de confirmacao cruzada com o WDO.

## O que NAO foi copiado do `WdoOrb` (decisao desta geracao, nao default
## silencioso)

1. **`alvo_multiplo` >= 3,0 sempre** -- o `WdoOrb` em producao usa 1,5x (ver a
   docstring dele para a medicao que levou a esse numero). O mandato desta
   busca (`ORQUESTRACAO.md`) e' mais estrito: "perder de colherinha, ganhar
   de balde", alvo sempre >= 3x o stop. `__init__` levanta `ValueError` se
   `alvo_multiplo < 3.0` -- mesma guarda que `WinBuscaLucroG06AmplitudeTeto`
   ja' usa.
2. **Sem FADE do rompimento oposto.** O `WdoOrb` so' chegou a um veredito
   estatisticamente POSITIVO depois de somar uma segunda entrada (o fade) --
   mas o fade tambem e' o que levanta o teto de reentradas por pregao para
   ate' 3 operacoes/dia, e as Geracoes 5-6 desta busca (WIN) ja' mostraram que
   reentrar no MESMO pregao nao resolve concentracao (e pode piorar, G6 N=3).
   Esta geracao testa a hipotese MAIS SIMPLES primeiro -- rompimento puro, NO
   MAXIMO 1 operacao REAL por pregao -- antes de somar complexidade. Fade fica
   como direcao em aberto para a G8 SE esta geracao passar o portao.
3. **Direcao = so' MOMENTUM (a favor do proprio rompimento), sem condicionar
   pela pernada maior (R43).** O proprio rompimento da faixa JA' define a
   direcao local -- e' o argumento do mandato desta geracao ("nao e'
   obrigatorio que o ORB cite R43 explicitamente se o proprio rompimento da
   faixa JA define a direcao"). Nao filtra por R43 em nenhum lugar: diferente
   de G1/G4/G5/G6, esta classe nem aceita parametro de pernada.
4. **Stop em PONTOS, nao em ticks de WDO.** O WIN@ tem geometria de range MUITO
   maior que o WDO@ -- medido no IS (jan-jun/2026, 122 pregoes): a faixa dos
   primeiros 5 minutos ja' tem mediana de 860 pontos (p10 502, p90 1.402); aos
   15 min, mediana 1.102 (p10 645, p90 1.824); aos 30 min, mediana 1.292 (p10
   745, p90 2.023). Isto e' uma ORDEM DE GRANDEZA acima do piso de 100 pontos
   do item 6.47 -- o teto (`stop_max_pontos`) bind MUITO mais frequentemente
   que o piso (`stop_min_pontos`), o oposto do regime do WDO@ (onde o piso
   mordia mais). O stop mediano desta geracao fica, por construcao, bem acima
   de 100 pontos -- NAO deve exigir checagem obrigatoria de ticks (item 6.47),
   mas o harness confere mesmo assim (protocolo do mandato).

## Desenho de execucao (FECHADO -- CLAUDE.md, nao negociavel)

`EnterLimit` com `ttl_bars` (nunca `Enter` a mercado); limite `buffer_entrada
_pontos` ATRAS do rompimento (espera o recuo, mesmo espirito do `offset_ticks`
do `WdoOrb` e do `buffer_entrada_pontos` de G4/G5/G6); alvo por ordem-limite
real fatiada (`exit_split_unit`), SEM prazo (`exit_ttl_bars=None`, mesma
convencao de G1-G6 desta busca -- so' execucao REAL exigiria o valor enorme
de `wdo_orb.EXIT_TTL_BARS_SEM_PRAZO`, e esta geracao e' so' backtest/pesquisa);
`anchor_exits_at_fill=True`; so' o STOP e' a mercado; `target_fills_as_maker
=True`. Fila do WIN@ NAO calibrada -- toda ordem-limite enche no TOQUE
(premissa otimista declarada pelo harness, precedente `WinRetangulo`/G1-G6).
Capital real R$250 (margem crua R$100 x buffer 2,0 x reserva 1,25 = R$250
exatos -- 1 contrato fixo, `quantity_e_unidade=False`).

## Contadores de auditoria (licao do item 6.48/6.49)

`stats_bruto`: toda BORDA NOVA de rompimento (transicao de "dentro da faixa"
para "fora", em qualquer direcao) -- contada ANTES de qualquer filtro de
"ja' armado"/"ja' operou hoje". Nao e' contagem por BARRA (preco pode ficar
fora da faixa por dezenas de barras seguidas sem gerar borda nova nenhuma) --
e' contagem por OCORRENCIA do gatilho, a mesma semantica de `disparo_novo` em
`WinBuscaLucroG06AmplitudeTeto`. `stats_ja_operou_hoje`: borda nova descartada
so' porque o pregao ja' teve 1 operacao REAL aberta (teto de 1/dia).
`stats_ordens_emitidas`: ordens que de fato viraram `EnterLimit`.

## Decisao de REARME apos ordem morta

Uma `EnterLimit` que expira por prazo (`on_order_expired`) ou e' recusada
(`on_order_rejected`) zera `_armou_hoje` -- mas isso SO' permite uma nova
tentativa quando uma BORDA NOVA ocorrer de novo (preco reentrou na faixa e
rompeu outra vez), nunca no proximo bar so' porque o preco continua fora da
faixa (diferente do `WdoOrb`, que rearma barra-a-barra enquanto o preco segue
rompido). Decisao desta geracao: evitar "perseguir" o rompimento indefinida-
mente bar-a-bar, que inflaria `stats_ordens_emitidas` sem acrescentar
observacao independente nenhuma (mesmo espirito do item 6.49).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG07Orb"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G6 desta busca.
TTL_BARRAS_ENTRADA = 10


class WinBuscaLucroG07Orb(IntradayStrategy):
    """Rompimento da faixa de abertura do WIN@, NO MAXIMO 1 operacao REAL por
    pregao, sempre na direcao do proprio rompimento (momentum) -- Geracao 7 da
    busca por um EA lucrativo do WIN (`ORQUESTRACAO.md`)."""

    name = "win_busca_lucro_g07_orb"
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
        stop_min_pontos: float = 100.0,
        stop_max_pontos: float = 250.0,
        alvo_multiplo: float = 5.0,
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
        # com posicao aberta ou nao -- item 6.48: o estado nao pode parar de
        # ser recalculado so' porque a ACAO esta bloqueada. Uma primeira
        # versao desta classe retornava cedo demais quando `positions` nao
        # era vazio, congelando `_fora_hi`/`_fora_lo` com o valor de ANTES da
        # entrada -- o preco podia reentrar e romper a faixa de novo varias
        # vezes enquanto a posicao do dia ainda estava aberta, e a borda
        # "nova" subsequente, computada so' depois que a posicao fechava,
        # saia contaminada pelo estado congelado (bruto variava so' por causa
        # do TAMANHO DO STOP mudar quanto tempo a posicao ficava aberta --
        # emit/bruto chegou a divergir entre celulas que deviam ter o MESMO
        # bruto por construcao). A emissao continua bloqueada por posicao/
        # armado/ja-operou-hoje logo abaixo -- so' o CALCULO do estado deixou
        # de ser condicional.
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
            # Posicao do dia ainda aberta (so' pode acontecer se o teto de 1
            # trade/dia nao tiver disparado ainda por algum motivo de
            # ordenacao -- defensivo). Nao decide nada aqui, so' o motor.
            return []
        if self._preencheu_hoje:
            self.stats_ja_operou_hoje += 1
            return []
        if self._armou_hoje:
            # Ja' ha' uma ordem pendente nesta mesma direcao -- nao substitui.
            return []

        stop_pontos, alvo_pontos = self._geometria()
        buf = self.buffer_entrada_pontos
        if nova_alta:
            limite = bar.close - buf
            self._armou_hoje = True
            self.stats_ordens_emitidas += 1
            return [self._ordem("long", limite, stop_pontos, alvo_pontos,
                                "g07_orb_rompimento_alta")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos,
                            "g07_orb_rompimento_baixa")]
