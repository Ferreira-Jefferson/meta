"""Micro topo/fundo duplo M1 -- único sobrevivente de uma varredura de 189
conceitos técnicos/price-action (catálogo de brainstorm de 2026-09-27, 909
conceitos no total; ver a conversa que gerou este arquivo para o catálogo
completo). Os outros 188 foram implementados, testados no motor real
(WDO@, capital R$375, desenho de execução fechado) e descartados -- ou
nunca lucrativos no filtro grosso, ou (os 4 que passaram nele) refutados na
validação IS/OOS que se segue.

Mesma lógica de topo/fundo duplo clássico, aplicada a SWINGS DE POUCOS
MINUTOS: pivô com janela curta (2 barras) e lookback curto (18 barras).
Entra na quebra da mínima/máxima entre os dois picos/vales (a neckline),
alvo = distância replicada (pico-neckline projetada do lado oposto).

## Status: NÃO CONFIRMADO -- guardado por ser o único candidato genuíno,
## não por ter passado no crivo estatístico do projeto

Validação IS/OOS (`scripts/daytrade/lab_concepts_validacao_5_candidatos_
2026_09_27.py`), capital real R$375, corte declarado ANTES de olhar
qualquer resultado (OOS = 2025-12-09..2026-06-12, nunca visto antes desta
investigação; IS = 2026-06-15..2026-09-15, a janela que o filtro grosso já
tinha usado para escolher este conceito entre os 189):

    janela            trades   liquido R$   win%    IC95%(Wilson)   breakeven
    OOS (cego)           454      +618,06   50,9%   [46,3 ; 55,5]      49,7%
    IS (ja vista)        220      +482,25   53,6%   [47,0 ; 60,1]      51,1%

Veredito nas DUAS janelas: INDEFINIDO -- o breakeven empírico cai DENTRO do
intervalo de confiança, por pouco, nas duas. Bootstrap (5.000 reamostragens
por trade): 68,1% (OOS) e 75,5% (IS) das reamostragens com R$/trade médio
positivo -- não é ruído puro, mas também não é confirmação.

O que separa este conceito dos outros 4 que passaram no filtro grosso
(`CunhaAscendenteDescendente`, `ORBFade`, `UltimateOscillator`,
`GapDeExaustao`, todos descartados): os outros quatro geraram 3 a 6 trades
em 123 pregões no período cego -- amostra pequena demais para significar
qualquer coisa, e mesmo assim perderam dinheiro (veredito NEGATIVO ou
bootstrap <11% positivo). Este gerou 454 trades no MESMO período cego, com
resultado líquido positivo e qualitativamente igual ao da janela que o
escolheu. Não é edge comprovado; é o único dos 189 que sobrou depois de um
teste de verdade.

## Antes de promover ou descartar

Não foi calibrado (parâmetros são os defaults escolhidos por quem
implementou, nenhum sweep de hiperparâmetro). Não tem fila real calibrada
para o padrão de rompimento próprio dele (herda a fila 438/489 genérica do
`backtest.intraday.fidelidade` via `config_for`, calibrada para outro
desenho). Não rodou nem em sombra, nem com dinheiro real. Antes de
qualquer promoção: acumular mais pregão real (o OOS aqui já é grande, mas
mais dado só ajuda a decidir a favor ou contra), e considerar bootstrap por
PREGÃO em vez de por trade (a amostra de 454 trades vem de só 109 pregões
com trade -- os trades dentro do mesmo pregão não são independentes entre
si, e o bootstrap por trade acima pode estar inflando a confiança).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class MicroTopoFundoDuploM1(IntradayStrategy):
    """Topo/fundo duplo em janela curta (poucos minutos)."""

    name: str = "micro_topo_fundo_duplo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_pivo: int = 2
    lookback_barras: int = 18
    tolerancia_topos_ticks: int = 3
    offset_ticks: int = 1
    entrada_ttl_bars: int | None = 40

    _janela_high: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _janela_low: deque = field(default_factory=lambda: deque(maxlen=5), init=False, repr=False)
    _idx: int = field(default=0, init=False, repr=False)
    _historico: deque = field(default_factory=lambda: deque(maxlen=18), init=False, repr=False)
    _pivos: deque = field(default_factory=lambda: deque(maxlen=6), init=False, repr=False)
    _armado: dict | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        janela = 2 * self.janela_pivo + 1
        self._janela_high = deque(maxlen=janela)
        self._janela_low = deque(maxlen=janela)
        self._idx = 0
        self._historico = deque(maxlen=self.lookback_barras)
        self._pivos = deque(maxlen=6)
        self._armado = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        idx = self._idx
        self._idx += 1
        self._historico.append((idx, bar.high, bar.low))
        self._janela_high.append(bar.high)
        self._janela_low.append(bar.low)

        if len(self._janela_high) == self._janela_high.maxlen:
            centro_idx = idx - self.janela_pivo
            centro_high = self._janela_high[self.janela_pivo]
            centro_low = self._janela_low[self.janela_pivo]
            if centro_high == max(self._janela_high):
                self._pivos.append(("alta", centro_idx, centro_high))
            elif centro_low == min(self._janela_low):
                self._pivos.append(("baixa", centro_idx, centro_low))

        limite_lookback = idx - self.lookback_barras
        tol = self.tolerancia_topos_ticks * self.tick_size

        if self._armado is None:
            altas = [p for p in self._pivos if p[0] == "alta" and p[1] >= limite_lookback]
            baixas = [p for p in self._pivos if p[0] == "baixa" and p[1] >= limite_lookback]
            if len(altas) >= 2:
                p1, p2 = altas[-2], altas[-1]
                if abs(p1[2] - p2[2]) <= tol:
                    neckline = min(
                        (lo for i, hi, lo in self._historico if p1[1] < i < p2[1]),
                        default=None,
                    )
                    if neckline is not None:
                        altura = max(p1[2], p2[2]) - neckline
                        if altura >= 4 * self.tick_size:
                            self._armado = {"lado": "short", "nivel": neckline, "altura": altura}
            if self._armado is None and len(baixas) >= 2:
                p1, p2 = baixas[-2], baixas[-1]
                if abs(p1[2] - p2[2]) <= tol:
                    neckline = max(
                        (hi for i, hi, lo in self._historico if p1[1] < i < p2[1]),
                        default=None,
                    )
                    if neckline is not None:
                        altura = neckline - min(p1[2], p2[2])
                        if altura >= 4 * self.tick_size:
                            self._armado = {"lado": "long", "nivel": neckline, "altura": altura}

        if positions or self._armado is None:
            return []

        armado = self._armado
        if armado["lado"] == "short" and bar.close < armado["nivel"]:
            limite = no_tick(armado["nivel"] + self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite + armado["altura"], self.tick_size)
            alvo = limite - armado["altura"]
            self._armado = None
            return [EnterLimit(
                side="short", limit_price=limite, initial_stop=stop,
                initial_target=alvo, quantity=1,
                ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
                exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
            )]
        if armado["lado"] == "long" and bar.close > armado["nivel"]:
            limite = no_tick(armado["nivel"] - self.offset_ticks * self.tick_size, self.tick_size)
            stop = no_tick(limite - armado["altura"], self.tick_size)
            alvo = limite + armado["altura"]
            self._armado = None
            return [EnterLimit(
                side="long", limit_price=limite, initial_stop=stop,
                initial_target=alvo, quantity=1,
                ttl_bars=self.entrada_ttl_bars, exit_split_unit=1,
                exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
            )]
        return []
