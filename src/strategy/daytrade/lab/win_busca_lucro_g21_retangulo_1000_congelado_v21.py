"""`win_busca_lucro_g21_retangulo_1000` — Geração 21 da busca por EA lucrativo
de day trade do WIN (`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`,
ver `ORQUESTRACAO.md`).

## Por que esta geração existe

A G16 (ANTES da mudança de mandato de 2026-10-05, ainda a capital R$250 e
`alvo_fracao_largura >= 3x stop_fracao_largura` obrigatório) adaptou a lógica
de DETECÇÃO de lateralização do `WinRetangulo` (produção, win%~45%, payoff
real 1,6:1, piso de capital R$1.100) para esta busca, e morreu de forma
MECANICISTA: 18 de 18 células (`stop_fracao∈{0,15..0,50}` × `alvo_mult∈
{3x,4x,5x}`) foram negativas e censuradas a R$250. O raciocínio da G16 — nunca
testado até aqui — era que o stop 0,50×largura / alvo 0,80×largura (razão
1,6:1) da produção não é arbitrário: é o único ponto onde o stop fica FORA da
banda de ruído que o próprio padrão de retângulo usa para se qualificar como
retângulo (contenção ≥95% com banda q90/q10, tolerância 0,20×largura de
"toque" na borda). Forçar `alvo≥3×stop` obrigava apertar o stop para DENTRO
dessa banda (onde é varrido antes de reverter) ou esticar o alvo além do
alcance histórico do retângulo (n cai a quase zero).

A decisão do dono de 2026-10-05 (ver `ORQUESTRACAO.md`, "MUDANÇA DE MANDATO")
abre a grade de alvo/stop para `{2x, 2,5x, 3x, 4x, 5x}` em vez de só "≥3x"
fixo (piso nunca ≤1×, perda≥ganho continua proibido) e sobe o capital de teste
para R$1.000. Esta geração testa se 2× e 2,5× — muito mais perto da razão
real de produção (1,6:1) do que 3× jamais poderia — permitem um stop que
ainda fica (ou quase fica) fora da banda de ruído do padrão, resolvendo o
impasse mecanicista da G16.

## O que é reaproveitado e o que é redesenhado

**Reaproveitado, por import direto, não reimplementado:** `detecta_retangulo`
(função pura de `strategy.daytrade.lab.win_retangulo` — topo/piso por
quantil, toques mínimos, visitas, cruzamentos do meio, contenção, contração,
deriva) e as constantes de "morte do retângulo" (`MARGEM_MORTE`/
`BARRAS_MORTE`/`LARGURA_MINIMA_TICKS`). Nenhum critério de FORMA do retângulo
foi alterado — idêntico à G16.

**Redesenhado, só o piso do múltiplo:** esta classe generaliza os mesmos dois
parâmetros da G16 (`alvo_fracao_largura`, `stop_fracao_largura`) mas impõe no
construtor `alvo_fracao_largura >= 2.0 × stop_fracao_largura` (em vez de
3,0×) — o novo piso do mandato (2026-10-05), não mais o antigo "sempre ≥3×".

## Capital e execução

Capital de teste **R$1.000** (substitui o R$250 da G16, autorização do dono
só para esta busca). `quantidade=1` SEMPRE — nunca escala por caixa. Esta é
uma escolha DECLARADA, não uma suposição: a G19 desta mesma busca (sizing
Kelly fracionário sobre o payoff REALIZADO de duas famílias de sinal
diferentes, ORB e cruzado WIN×WDO) mediu que o Kelly fracionário a R$1.000
nunca pediu mais de 1 contrato em nenhum balde testado — mas isso foi medido
para OUTRAS famílias de sinal, não para esta geometria de retângulo, e por
isso não é assumido aqui sem dizer: `_dimensiona()` não existe nesta classe,
e caso uma célula vencedora desta geração mostre folga de capital suficiente
para justificar escalar, isso é trabalho da G22, não desta.

Desenho de execução idêntico à linha inteira: `EnterLimit` com `ttl_barras`,
alvo só como ordem-limite real fatiada (`target_fills_as_maker=True`), âncora
no preço de fill (`anchor_exits_at_fill=True`), só o stop a mercado. Fila
WIN@ zero nos dois lados (não calibrada — premissa otimista declarada, mesmo
precedente de toda a linha G1-G20 e do próprio `WinRetangulo`).

## Fila ALÉM da borda oposta — bandeira declarada, não resolvida aqui

Idêntica à ressalva da G16: ao mirar além da borda oposta do retângulo, o
nível do alvo pode ser um nível raramente visitado — exatamente o modo de
morte que matou a família maker do WDO F1 por fila. Como `WIN@` não tem
fidelidade calibrada, essa degradação não aparece no backtest — é uma
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


class WinBuscaLucroG21Retangulo1000(IntradayStrategy):
    """Entra por ordem-limite no MEIO de um retângulo (detecção reaproveitada
    de `WinRetangulo`), com geometria de alvo/stop redesenhada para
    `alvo_fracao_largura >= 2x stop_fracao_largura` (piso do mandato
    2026-10-05) e capital de teste R$1.000, 1 contrato fixo (G21)."""

    name = "win_busca_lucro_g21_retangulo_1000"
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

    #: Piso do mandato 2026-10-05 — substitui o 3,0 da G16.
    MULTIPLO_MINIMO = 2.0

    def __init__(
        self,
        symbol: str | None = None,
        janela_barras: int = 20,
        largura_minima_pontos: float = 328.0,
        alvo_fracao_largura: float = 1.00,
        stop_fracao_largura: float = 0.50,
        ttl_barras: int = 10,
        quantidade: int = 1,
        tolerancia_borda: float = 0.20,
        risco_maximo_brl: float | None = None,
    ) -> None:
        """`janela_barras=20`/`tolerancia_borda=0,20`/`largura_minima_pontos=328`
        — herdados do `WinRetangulo` CONGELADO sem retune, idêntico à G16:
        esta geração testa a geometria de entrada/saída, não a detecção de
        forma (que é a mesma função pura importada).

        `alvo_fracao_largura`/`stop_fracao_largura` — fração da LARGURA do
        retângulo, medida a partir do centro (`meio`), igual à convenção do
        `WinRetangulo` e da G16. A validação abaixo é o que muda em relação à
        G16: o piso do múltiplo cai de 3,0× para `MULTIPLO_MINIMO=2,0×`
        (mandato 2026-10-05) — nunca ≤1× (perda≥ganho continua proibido).

        `risco_maximo_brl=None` desliga o teto de risco por operação — mesmo
        raciocínio da G16: não foi medido para R$1.000, herdar o número da
        produção (R$80, medido para o piso de R$1.100) seria arbitrário. A
        restrição de sobrevivência é a probabilidade de ruína via Monte Carlo
        sobre o P&L real.
        """
        if janela_barras < 6:
            raise ValueError(
                f"janela_barras={janela_barras} é curto demais: o espalhamento "
                f"exige W/3 barras entre a primeira e a última visita de cada borda")
        if alvo_fracao_largura <= 0 or stop_fracao_largura <= 0:
            raise ValueError("alvo e stop têm de ser distâncias positivas")
        if alvo_fracao_largura < self.MULTIPLO_MINIMO * stop_fracao_largura:
            raise ValueError(
                f"alvo_fracao_largura={alvo_fracao_largura} < "
                f"{self.MULTIPLO_MINIMO}x stop_fracao_largura={stop_fracao_largura} "
                f"(mínimo exigido: {self.MULTIPLO_MINIMO * stop_fracao_largura}) — "
                f"o piso do mandato 2026-10-05 exige alvo>={self.MULTIPLO_MINIMO}x o "
                f"stop (perda>=ganho continua proibido; ORQUESTRACAO.md, "
                f"'MUDANÇA DE MANDATO')")
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
                "quantidade != 1: esta geração testa capital de R$1.000 com 1 "
                "contrato fixo (escolha DECLARADA, não assumida — ver docstring "
                "do módulo), nunca escala")
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
            reason=f"g21_retangulo_W{self.janela_barras}_L{largura:.0f}",
        )]
