"""`win_busca_lucro_g16_retangulo_250` — Geração 16 da busca por EA lucrativo
de day trade do WIN (`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`,
ver `ORQUESTRACAO.md`).

## Por que esta geração existe

G1-G10 (famílias de sinal) e G11-G15 (alavancas do coordenador sobre as
famílias de momentum/breakout/ORB) convergiram, de forma consistente, para o
mesmo teto estrutural: alvo≥3× exige win% baixo, win% baixo produz sequências
de perda plausíveis que o capital real de R$250 (1 contrato) não aguenta —
G13 mediu um penhasco isolado (nenhum platô em 79 células), G14/G15 mostraram
que nem portfólio/alternância nem orçamento de exposição resolvem a ruína
porque o caixa nunca é dividido, é reexposto a cada disparo.

A G13 e a G15 identificaram, mas não testaram, o único ângulo genuinamente
diferente: uma família de **win% MAIS ALTO e variância MAIS BAIXA**, ao
estilo do `WinRetangulo` (`strategy.daytrade.lab.win_retangulo`, já em
PRODUÇÃO real, win%~45%, payoff ~1,6:1, piso de capital R$1.100). Nem o
win%/payoff nem o capital do `WinRetangulo` cabem DIRETAMENTE no mandato
desta busca (alvo≥3×, capital R$250) — esta geração testa se a lógica de
DETECÇÃO de lateralização sobrevive a uma geometria redesenhada para caber.

## O que é reaproveitado e o que é redesenhado

**Reaproveitado, por import direto, não reimplementado:** `detecta_retangulo`
(função pura module-level de `strategy.daytrade.lab.win_retangulo` — topo/
piso por quantil, toques mínimos, visitas, cruzamentos do meio, contenção,
contração, deriva) e as constantes de "morte do retângulo"
(`MARGEM_MORTE`/`BARRAS_MORTE`/`LARGURA_MINIMA_TICKS`). Nenhum critério de
FORMA do retângulo foi alterado — a pergunta desta geração é só sobre a
geometria de ENTRADA/SAÍDA sobre um retângulo já detectado do mesmo jeito.

**Redesenhado:** a geometria de entrada/saída. O `WinRetangulo` de produção
entra no CENTRO do retângulo (`meio`), mira 0,80× a largura ALÉM do centro
(o que atravessa a borda oposta por 0,30× a largura) e para no stop a
0,50× a largura do centro (exatamente na borda oposta) — payoff 1,6:1. Essa
geometria, testada como está, falha o mandato desta busca por construção
(1,6:1 < 3:1). Esta classe generaliza os DOIS parâmetros
(`alvo_fracao_largura`, `stop_fracao_largura`) e **impõe no construtor**
`alvo_fracao_largura >= 3 × stop_fracao_largura` — o desenho de execução
fechado deste projeto (CLAUDE.md, "nunca alvo perto de 1 tick"/"alvo sempre
≥3× o stop") vira validação estrutural, não convenção de busca.

Isso cobre as duas rotas que o mandato da G16 sugeriu, com UM parâmetro:
reduzir `stop_fracao_largura` abaixo de 0,50 (stop TÉCNICO, aquém da borda
oposta, em vez do stop original que vai até ela) empurra o múltiplo
alvo/stop para cima sem mudar `alvo_fracao_largura`; subir
`alvo_fracao_largura` bem além de 0,80 (mirar 1,5-3× a largura a partir do
centro) faz o mesmo na outra direção. A busca no IS varre as duas.

## Capital e execução — sem herdar nada da produção

`quantidade=1` SEMPRE — nunca escala por caixa (diferente do `WinRetangulo`,
cujo `_dimensiona` supõe um piso de R$1.100; a R$250 cabe exatamente 1
contrato e nenhuma escada de margem adicional faz sentido aqui). Desenho de
execução idêntico à linha inteira: `EnterLimit` com `ttl_barras`, alvo só
como ordem-limite real fatiada (`target_fills_as_maker=True`), âncora no
preço de fill (`anchor_exits_at_fill=True`), só o stop a mercado. Fila WIN@
zero nos dois lados (não calibrada — premissa otimista declarada, mesmo
precedente de toda a linha G1-G15 e do próprio `WinRetangulo`).

## Fila ALÉM da borda oposta — bandeira declarada, não resolvida aqui

O `WinRetangulo` de produção argumenta que a entrada (limite na linha do
meio) é barata de fila porque é um nível que o preço visita muito. O MESMO
argumento NÃO vale automaticamente para o alvo desta geração: ao mirar bem
além da borda oposta (abordagem "alvo grande"), o nível do alvo pode ser um
nível raramente visitado — exatamente o modo de morte que matou a família
maker do WDO F1 por fila (ver CLAUDE.md, "Maker ENCERRADA"). Como `WIN@` não
tem fidelidade calibrada, essa degradação **não aparece no backtest** — é uma
bandeira a declarar na linha do resultado, não algo que o número já cobre.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)
from strategy.daytrade.lab.win_retangulo import (
    BARRAS_MORTE, LARGURA_MINIMA_TICKS, MARGEM_MORTE, detecta_retangulo,
)


class WinBuscaLucroG16Retangulo250(IntradayStrategy):
    """Entra por ordem-limite no MEIO de um retângulo (detecção reaproveitada
    de `WinRetangulo`), com geometria de alvo/stop REDESENHADA para
    `alvo >= 3x stop` e capital real de R$250, 1 contrato fixo (mandato G16)."""

    name = "win_busca_lucro_g16_retangulo_250"
    version = "1.0.0"
    symbol = "WIN@"
    is_futuro = True
    #: Alvo é ordem-limite REAL parada no livro (nunca `tp` nativo).
    target_fills_as_maker = True
    #: A entrada é limite, então a âncora no preço realmente obtido vale de
    #: verdade (robô que entra a mercado trataria isto como no-op silencioso
    #: — item 4.23 de `LICOES_DE_PRODUCAO.md`).
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        janela_barras: int = 20,
        largura_minima_pontos: float = 328.0,
        alvo_fracao_largura: float = 1.50,
        stop_fracao_largura: float = 0.25,
        ttl_barras: int = 10,
        quantidade: int = 1,
        tolerancia_borda: float = 0.20,
        risco_maximo_brl: float | None = None,
    ) -> None:
        """`janela_barras=20`/`tolerancia_borda=0,20` — herdados do
        `WinRetangulo` CONGELADO sem retune: esta geração testa a geometria
        de entrada/saída, não a detecção de forma (que é a mesma função pura
        importada). `largura_minima_pontos=328` — idem, é o filtro de
        ESTRUTURA DE MERCADO do retângulo original (terço superior da largura
        medida no IS daquela geração), independente do capital ou da
        geometria de alvo/stop — não há razão a priori para o capital de
        R$250 mudar o que CONTA como retângulo válido, só o que se faz com
        ele depois de detectado.

        `alvo_fracao_largura`/`stop_fracao_largura` — fração da LARGURA do
        retângulo, medida a partir do centro (`meio`), igual à convenção do
        `WinRetangulo`. A validação abaixo é o que torna esta classe
        estruturalmente diferente da produção: nunca aceita um par que não
        bata `alvo >= 3x stop` (CLAUDE.md, desenho de execução fechado).

        `risco_maximo_brl=None` desliga o teto de risco por operação (ao
        contrário do `WinRetangulo`, que tem um teto medido para o piso de
        R$1.100 — aqui o teto não foi medido para R$250 e herdar o número de
        lá seria arbitrário; a restrição de sobrevivência desta geração é a
        probabilidade de ruína via Monte Carlo sobre o P&L real, não um teto
        de risco por trade adivinhado).
        """
        if janela_barras < 6:
            raise ValueError(
                f"janela_barras={janela_barras} é curto demais: o espalhamento "
                f"exige W/3 barras entre a primeira e a última visita de cada borda")
        if alvo_fracao_largura <= 0 or stop_fracao_largura <= 0:
            raise ValueError("alvo e stop têm de ser distâncias positivas")
        if alvo_fracao_largura < 3.0 * stop_fracao_largura:
            raise ValueError(
                f"alvo_fracao_largura={alvo_fracao_largura} < 3x "
                f"stop_fracao_largura={stop_fracao_largura} "
                f"(mínimo exigido: {3.0 * stop_fracao_largura}) — o desenho de "
                f"execução desta busca exige alvo>=3x o stop (CLAUDE.md, "
                f"ORQUESTRACAO.md mandato da Geração 16)")
        if ttl_barras is None or ttl_barras <= 0:
            # Ordem-limite de entrada SEM prazo espera até o fim do pregão e
            # preenche horas depois do sinal (medido: 269,7 min) — não é o
            # trade que a estratégia pediu.
            raise ValueError(
                "ttl_barras é obrigatório: limite de entrada sem prazo vira "
                "ordem esquecida no livro")
        if symbol is not None:
            self.symbol = symbol
        self.janela_barras = int(janela_barras)
        self.largura_minima_pontos = float(largura_minima_pontos)
        self.alvo_fracao_largura = float(alvo_fracao_largura)
        self.stop_fracao_largura = float(stop_fracao_largura)
        self.ttl_barras = int(ttl_barras)
        if not 0 < tolerancia_borda < 0.5:
            raise ValueError(
                f"tolerancia_borda={tolerancia_borda} fora de (0; 0,5): acima "
                f"de 0,5 as duas bordas se encontram no meio")
        self.tolerancia_borda = float(tolerancia_borda)
        self.risco_maximo_brl = (
            float(risco_maximo_brl) if risco_maximo_brl is not None else float("inf"))
        self.quantidade = int(quantidade)
        if self.quantidade != 1:
            raise ValueError(
                "quantidade != 1: esta geração testa o capital mínimo real de "
                "R$250 (1 contrato fixo), nunca escala — ver docstring do módulo")
        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size
        self.valor_do_ponto_brl = economia.point_value_brl
        self._reset_sessao()

    # -- estado --------------------------------------------------------
    def _reset_sessao(self) -> None:
        # 3xW barras: W para a janela do detector, 2W para a amplitude
        # anterior que o teste de CONTRAÇÃO consome.
        self._hist: deque[Bar] = deque(maxlen=3 * self.janela_barras + 2)
        self._retangulo: dict | None = None
        self._fora_seguidas = 0
        self._barras_esperando: int | None = None

    def on_session_start(self, session_date) -> None:
        """Zera TUDO — nenhum nível de preço atravessa a virada do `WIN@`
        (série contínua com emenda de rolagem, mesmo motivo do `WinRetangulo`)."""
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._barras_esperando = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._barras_esperando = None

    # -- detecção (reaproveitada, não reimplementada) -------------------
    def _janelas(self):
        W = self.janela_barras
        h = list(self._hist)
        recente = h[-W:]
        anterior = h[-3 * W:-W]
        return (
            np.array([b.high for b in recente], dtype=float),
            np.array([b.low for b in recente], dtype=float),
            np.array([b.close for b in recente], dtype=float),
            float(max(b.high for b in anterior) - min(b.low for b in anterior)),
        )

    def _tenta_detectar(self) -> None:
        if len(self._hist) < 3 * self.janela_barras:
            return
        high, low, close, amplitude_anterior = self._janelas()
        ret = detecta_retangulo(high, low, close, amplitude_anterior,
                                 tolerancia=self.tolerancia_borda)
        if ret is None:
            return
        if ret["largura"] < LARGURA_MINIMA_TICKS * self.tick_size:
            return
        if ret["largura"] < self.largura_minima_pontos:
            return
        risco = (self.stop_fracao_largura * ret["largura"]
                 * self.valor_do_ponto_brl)
        if risco > self.risco_maximo_brl:
            return
        self._retangulo = ret
        self._fora_seguidas = 0

    def _morreu(self, bar: Bar) -> bool:
        r = self._retangulo
        margem = MARGEM_MORTE * r["largura"]
        if bar.close > r["topo"] + margem or bar.close < r["piso"] - margem:
            self._fora_seguidas += 1
            return self._fora_seguidas >= BARRAS_MORTE
        self._fora_seguidas = 0
        return False

    # -- loop ------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)

        if self._retangulo is not None and self._morreu(bar):
            self._retangulo = None
            self._barras_esperando = None
        if self._retangulo is None:
            self._tenta_detectar()
            if self._retangulo is None:
                return []

        if positions:
            self._barras_esperando = None
            return []

        if self._barras_esperando is not None:
            self._barras_esperando += 1
            if self._barras_esperando < self.ttl_barras:
                return []
            self._barras_esperando = None

        r = self._retangulo
        meio, largura = r["meio"], r["largura"]
        if bar.close < meio:
            lado = "short"
            alvo = meio - self.alvo_fracao_largura * largura
            stop = meio + self.stop_fracao_largura * largura
        elif bar.close > meio:
            lado = "long"
            alvo = meio + self.alvo_fracao_largura * largura
            stop = meio - self.stop_fracao_largura * largura
        else:
            return []

        # Conferência MECÂNICA: uma limite do lado errado é ordem a mercado
        # disfarçada, proibida pelo desenho de execução deste projeto.
        limite = no_tick(meio, self.tick_size)
        if lado == "short" and limite <= bar.close:
            return []
        if lado == "long" and limite >= bar.close:
            return []

        self._barras_esperando = 0
        return [EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantidade,
            ttl_bars=self.ttl_barras,
            reason=f"g16_retangulo_W{self.janela_barras}_L{largura:.0f}",
        )]
