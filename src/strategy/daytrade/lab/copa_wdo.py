"""`copa_wdo` — grade maker de alta frequencia no minidolar (WDO),
desenhada para a Copa BTG Trader.

## Por que GIRO aqui, e ROMPIMENTO no WIN

Mesma tarifa, instrumentos opostos. R$0,50 de round-trip por contrato vale:

| | tarifa por round-trip | em ticks do ativo | alvo minimo que se paga |
|---|---|---|---|
| WIN (tick 5 pts = R$1,00) | 2,5 pontos | **0,50 tick** | 2 ticks |
| WDO (tick 0,5 pt = R$5,00) | 0,05 ponto | **0,10 tick** | 1 tick |

No WDO um alvo de UM tick (R$5,00/contrato) sobra 90% depois do custo. E' o
regime em que giro alto se paga — e' o mesmo desenho maker que a familia
`gremah` valida em acao, aqui com a economia do minidolar. No WIN esse mesmo
alvo nasce negativo (ver `copa_win.py`).

O que o WDO tem de escasso e' MOVIMENTO: range diario mediano de 49,3 pontos
(~99 ticks) contra 2.968 pontos (~594 ticks) do WIN — 177 pregoes medidos.
Nao ha' movimento sobrando para perseguir, o que reforca a mesma conclusao:
aqui o robo ESPERA parado (maker) em vez de pagar spread para entrar.

## Onde o teto de contratos morde de verdade

A entrada e' dividida em `pecas` filhos independentes (`EnterLimit.
split_quantities`). Cada filho que preenche vira uma posicao SEPARADA, com
stop e alvo proprios — pedido do dono em 2026-08-24, ja no motor. E' isto que
faz o teto (`max_open_contracts`) ser uma restricao ativa e nao decorativa: o
filho que nao couber no teto e' recusado por inteiro e contabilizado
(`IntradaySessionMachine.ordens_recusadas_por_teto`, portao G5).

## Tudo reinicia no pregao

A ancora, a grade, o alvo e o stop saem exclusivamente das barras de HOJE.
`WDO@` rola de vencimento TODO MES (~9 emendas na janela salva) — mais que o
dobro do WIN — e nenhum nivel de preco pode atravessar essa costura.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    EnterLimit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    no_tick,
)


def dividir_em_pecas(quantidade: int, pecas: int) -> tuple[int, ...]:
    """Reparte `quantidade` em ate `pecas` pedacos inteiros o mais iguais
    possivel, sem perder nem inventar contrato: `sum(...) == quantidade`
    sempre (o motor NAO redistribui sozinho, ver `EnterLimit.split_quantities`).

    `dividir_em_pecas(7, 3) -> (3, 2, 2)`. Quantidade menor que `pecas` vira
    `quantidade` pedacos de 1 -- pedir 5 pedacos de 3 contratos nao produz
    pedaco de zero contrato."""
    pecas = max(1, min(int(pecas), int(quantidade)))
    base, resto = divmod(int(quantidade), pecas)
    return tuple(base + (1 if i < resto else 0) for i in range(pecas))


class CopaWdo(IntradayStrategy):
    """Ordem-limite parada a `entrada_ticks` da referencia, dividida em pecas
    independentes; alvo e stop em ticks; lados alternados a cada rodada.

    Ancora HIBRIDA, o mesmo desenho medido da `gremah`: a abertura do pregao
    nas primeiras `ancora_fixa_barras` barras, o preco corrente depois. Uma
    ancora presa na abertura vai ficando longe demais conforme o dia anda e
    para de ser tocada; uma ancora sempre rolante persegue o preco desde o
    primeiro minuto, quando a abertura ainda e' a referencia boa."""

    name = "copa_wdo"
    version = "0.1"
    symbol = "WDO@"
    # Entrada E saida por alvo sao ordens PARADAS no nivel -- o desenho
    # inteiro e' nao pagar spread. Stop e flatten continuam a mercado (sao
    # urgencia, nao escolha).
    target_fills_as_maker = True
    feed_kind = "m1"
    #: Pernas MAKER por round-trip: DUAS (entrada e alvo, as duas paradas no
    #: nivel). Por isso este desenho e' o mais exposto ao portao G7 -- ver
    #: `CopaWin.pernas_maker`.
    pernas_maker = 2

    def __init__(
        self,
        teto_contratos: int,
        symbol: str = "WDO@",
        tick_size: float = 0.5,
        point_value_brl: float = 10.0,
        fracao_entrada: float = 1.0,
        pecas: int = 2,
        entrada_ticks: float = 2.0,
        alvo_ticks: float = 2.0,
        stop_ticks: float = 6.0,
        ttl_barras: int = 10,
        ancora_fixa_barras: int = 120,
        aquecimento_barras: int = 5,
        max_rodadas_dia: int = 60,
        perda_max_dia_pontos: float | None = None,
    ):
        """`teto_contratos`: teto de contratos SIMULTANEOS da competicao.
        Obrigatorio e sem default -- ver `copa_win.CopaWin.__init__`.

        `fracao_entrada`: quantos contratos por rodada, como fracao do teto.
        Default `1.0` (ocupa o teto inteiro) porque no WDO o teto e' pequeno
        (5 em 2025) e as pecas ja dao a granularidade; o robo NUNCA le 4 nem 5.

        `pecas`: em quantos filhos independentes a entrada e' dividida. Cada
        filho tem stop/alvo proprios e so' preenche se houver volume real
        para ele sozinho -- e' o que torna o teto uma restricao ativa.

        `entrada_ticks`: distancia da ordem parada ate a referencia.
        `alvo_ticks`/`stop_ticks`: alvo e stop, em ticks, a partir do preco de
        entrada. No WDO o tick vale R$5,00/contrato e o custo e' R$0,50 --
        por isso alvo de 1-2 ticks e' economicamente viavel aqui.

        `ttl_barras`: barras que a ordem parada espera antes de o motor
        cancela-la. O robo so' re-arma depois disso, sincronizado com o motor
        -- re-armar a cada barra substituiria a propria ordem sem parar,
        e ela nunca completaria o prazo de espera.

        `ancora_fixa_barras`: barras iniciais em que a referencia e' a
        ABERTURA do pregao; depois passa a ser o preco corrente.

        `max_rodadas_dia`: teto de rodadas (uma rodada = uma ordem armada) por
        pregao.

        `perda_max_dia_pontos`: perda-limite do pregao em pontos por contrato
        do teto. `None` desliga -- e' hipotese a MEDIR, nao premissa."""
        if teto_contratos < 1:
            raise ValueError(
                f"copa_wdo: `teto_contratos` tem de ser >= 1, veio {teto_contratos!r}. "
                "O teto e' entrada de configuracao (as regras da Copa podem mudar "
                "antes de 14/09/2026), nunca constante no codigo."
            )
        self.symbol = symbol
        self.teto_contratos = int(teto_contratos)
        self.tick_size = float(tick_size)
        self.point_value_brl = float(point_value_brl)
        self.fracao_entrada = float(fracao_entrada)
        self.pecas = int(pecas)
        self.entrada_ticks = float(entrada_ticks)
        self.alvo_ticks = float(alvo_ticks)
        self.stop_ticks = float(stop_ticks)
        self.ttl_barras = int(ttl_barras)
        self.ancora_fixa_barras = int(ancora_fixa_barras)
        self.aquecimento_barras = int(aquecimento_barras)
        self.max_rodadas_dia = int(max_rodadas_dia)
        self.perda_max_dia_pontos = perda_max_dia_pontos

        self._abertura: float | None = None
        self._barras_hoje = 0
        self._rodadas_hoje = 0
        self._proximo_lado = "long"
        self._tinha_posicao = False
        # Barras desde que a ordem foi armada. `None` = nenhuma ordem em pe'.
        # Espelha `IntradaySessionMachine.resting_limit_bars_waited` de fora:
        # a estrategia nao enxerga o estado do motor, entao conta o mesmo
        # prazo por conta propria para nao re-armar antes da hora.
        self._espera: int | None = None
        self._encerrado_hoje = False

    # ---------- tamanho: sempre fracao do teto ----------------------------

    @property
    def quantidade_por_rodada(self) -> int:
        return max(1, round(self.teto_contratos * self.fracao_entrada))

    @property
    def perda_max_dia_brl(self) -> float | None:
        if self.perda_max_dia_pontos is None:
            return None
        return abs(self.perda_max_dia_pontos) * self.point_value_brl * self.teto_contratos

    # ---------- ciclo do pregao -------------------------------------------

    def on_session_start(self, session_date) -> None:
        self._abertura = None
        self._barras_hoje = 0
        self._rodadas_hoje = 0
        self._proximo_lado = "long"
        self._tinha_posicao = False
        self._espera = None
        self._encerrado_hoje = False

    # ---------- decisao ----------------------------------------------------

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._barras_hoje += 1
        if self._abertura is None:
            self._abertura = bar.open

        if positions:
            # Com posicao aberta o motor ignora `EnterLimit` nova; qualquer
            # filho ainda sem preencher continua valendo por conta propria.
            self._tinha_posicao = True
            self._espera = None
            return []

        if self._tinha_posicao:
            # Acabou de zerar: alterna o lado da proxima rodada. Alternar
            # (em vez de insistir no mesmo lado) e' o que impede a grade de
            # virar uma aposta direcional disfarcada depois de uma sequencia.
            self._tinha_posicao = False
            self._proximo_lado = "short" if self._proximo_lado == "long" else "long"

        if self._encerrado_hoje:
            return []

        limite = self.perda_max_dia_brl
        if limite is not None and session_pnl_brl <= -limite:
            self._encerrado_hoje = True
            return []

        if self._espera is not None:
            self._espera += 1
            if self._espera < self.ttl_barras:
                return []   # ordem ainda viva no motor -- nao substituir
            self._espera = None

        if self._barras_hoje <= self.aquecimento_barras:
            return []
        if self._rodadas_hoje >= self.max_rodadas_dia:
            return []

        referencia = (self._abertura if self._barras_hoje <= self.ancora_fixa_barras
                      else bar.close)
        return [self._armar(referencia)]

    def _armar(self, referencia: float) -> EnterLimit:
        self._rodadas_hoje += 1
        self._espera = 0
        passo = self.entrada_ticks * self.tick_size
        alvo = self.alvo_ticks * self.tick_size
        stop = self.stop_ticks * self.tick_size
        quantidade = self.quantidade_por_rodada
        if self._proximo_lado == "long":
            preco = no_tick(referencia - passo, self.tick_size)
            initial_target = no_tick(preco + alvo, self.tick_size)
            initial_stop = no_tick(preco - stop, self.tick_size)
        else:
            preco = no_tick(referencia + passo, self.tick_size)
            initial_target = no_tick(preco - alvo, self.tick_size)
            initial_stop = no_tick(preco + stop, self.tick_size)
        return EnterLimit(
            side="long" if self._proximo_lado == "long" else "short",
            limit_price=preco,
            initial_stop=initial_stop,
            initial_target=initial_target,
            quantity=quantidade,
            split_quantities=dividir_em_pecas(quantidade, self.pecas),
            ttl_bars=self.ttl_barras,
            metadata={"rodada": self._rodadas_hoje, "referencia": referencia},
            reason=f"grade_{self._proximo_lado}",
        )
