"""Fade do GAP overnight do WDO@ (fechamento[d-1] -> abertura[d]), restrito a
gaps PEQUENOS/MEDIOS -- estagio 2 (motor real) de uma hipotese medida em
correlacao bruta (estagio 1, 2026-09-27, sem motor):

  * `scripts/daytrade/wdo_gap_proprio_padrao_2026_09_27.py` -- 18 celulas
    testando se o gap prediz DIRECAO do pregao. 0/18 sobrevivem Bonferroni.
  * `scripts/daytrade/wdo_gap_padrao_nao_linear_2026_09_27.py` -- 28 celulas
    de padroes nao-lineares. 3/28 sobrevivem, a mais forte: fill-rate do gap
    (o preco volta a tocar o fechamento anterior DENTRO do proprio pregao) e'
    89,2% para gaps PEQUENOS (tercil) contra 41,5% para gaps GRANDES
    (diff=0,477, p=0,00005).

Essa diferenca e' PROVAVELMENTE em boa parte mecanica (quanto mais perto o
gap esta' do fechamento anterior, mais facil o ruido normal do pregao tocar
aquele nivel de volta -- e' como probabilidade de toque de uma opcao, nao
necessariamente edge). Toque nao e' o mesmo que "um trade REAL captura isso
sem ser stopado antes" -- e' exatamente essa lacuna que este arquivo mede,
no motor de verdade (custo, fila, execucao fechada), nao mais em correlacao
bruta.

## A hipotese

Na abertura do pregao, se o gap cair no tercil "pequeno" ou "medio" (a
classificacao vem de FORA -- ver `elegivel`/`prev_close_px` abaixo -- porque
decidir o tercil exige a distribuicao de MUITOS pregoes, informacao que uma
estrategia `strategy/` pura nao pode ter, AGENTS.md regra 2), entra CONTRA o
gap (fade) mirando o fechamento anterior como alvo:

  * gap para CIMA (abriu acima do fechamento de ontem) -> fade SHORT,
    apostando que o preco volta para baixo ate' o fechamento anterior;
  * gap para BAIXO -> fade LONG, apostando que o preco volta para cima.

Uma unica operacao por pregao, decidida na PRIMEIRA barra (que e' a abertura
real -- base de tick, barra degenerada `open=high=low=close`).

## Piso do alvo -- a proibicao do T1 (CLAUDE.md) aplicada a um alvo VARIAVEL

Aqui o alvo nao e' um numero fixo do robo, e' a distancia ate' o fechamento
anterior -- e essa distancia pode ser pequena o bastante para chegar perto
de 1 tick, que e' proibido para qualquer robo `target_fills_as_maker=True`
neste projeto (fila real calibrada em `backtest/intraday/fidelidade.py`
mostra que ate' alvo NORMAL pena pra preencher; 1 tick e' o nivel mais
disputado do livro). `alvo_min_ticks` (default 4) e' o piso: um dia cujo
gap de' um alvo menor que isso NAO opera, mesmo estando no tercil elegivel.
Decisao documentada, nao medida -- mesmo estatuto de outros pisos deste
projeto (`MARGIN_BUFFER_FUTUROS`, `RESERVA_CAIXA_SEGURANCA`) ate' existir
dado real para calibrar.

## O DESENHO DE EXECUCAO (CLAUDE.md, "O desenho de execucao e' FECHADO") --
sem excecao, igual `wdo_orb.WdoOrb` (ver aquele arquivo para a medicao que
justifica cada peca):

  * entrada por `EnterLimit` parada no livro, nunca `Enter` a mercado --
    offset de `offset_ticks` NA DIRECAO do gap (espera uma pequena extensao
    antes de fadear, mesma logica de `WdoOrb._ordem`);
  * a ordem de entrada tem prazo (`entrada_ttl_bars`, em BARRAS -- base de
    tick, ~336 barras/minuto, NUNCA leia isto como tempo sem calibrar; o
    harness de backtest reporta o atraso REALIZADO em minutos);
  * alvo por ordem-limite REAL fatiada (`exit_split_unit=1`), SEM prazo
    (`EXIT_TTL_BARS_SEM_PRAZO`, nunca `None`) -- nunca `tp` nativo;
  * `anchor_exits_at_fill=True`: stop e alvo ancoram no preco REALMENTE
    preenchido;
  * stop a MERCADO -- excecao unica.

## O que este arquivo NAO decide

Nao escolhe os cortes de tercil (isso e' do harness de backtest, que tem
acesso a' distribuicao de MUITOS pregoes -- olhar so' o pregao de hoje seria
look-ahead E a estrategia teria de deixar de ser pura). Nao escolhe stop:
`stop_ticks` e' derivado do `alvo_ticks` pela razao `razao_alvo_stop`
(default 1,5 -- reaproveita o MESMO multiplo ja medido/promovido em
`WdoOrb.alvo_multiplo`, mesmo instrumento e mesmo desenho de execucao, em
vez de inventar um numero novo sem medicao), limitado entre
`stop_min_ticks`/`stop_max_ticks`.

## Como o gap de CADA dia chega ate' aqui, permanecendo PURA

`elegivel`/`prev_close_px` (campos simples, um valor so') servem para rodar
UM pregao isolado (o pregao vira o construtor inteiro). Para uma janela de
MUITOS pregoes num unico `run_intraday_backtest` continuo (capital que
carrega de um dia pro outro, em vez de resetado por pregao), o harness pode
passar `gap_por_dia` -- um dict pronto `{date: (elegivel, prev_close_px)}`,
computado inteiramente FORA (precisa da distribuicao de muitos pregoes para
os tercis, que uma estrategia pura nao pode calcular sozinha). `on_session_
start` so' faz uma BUSCA nesse dict pelo `session_date` que o motor ja' lhe
da' -- e' consulta em memoria a um dado ja' pronto, nao I/O (AGENTS.md regra
2 continua respeitada), mesmo espirito dos hooks `seed_daily_volatility`/
`seed_typical_trade_size` que ja' injetam contexto multi-dia calculado por
fora."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    Side,
)

#: Mesma constante/mesmo motivo de `wdo_orb.EXIT_TTL_BARS_SEM_PRAZO`: a
#: limite do alvo fica parada ate' o mercado PAGAR, nunca sai a mercado por
#: impaciencia. NUNCA `None` -- `None` no motor significa "sem fatia com
#: prazo" (comportamento antigo) e em execucao REAL levantaria erro.
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class WdoGapFade(IntradayStrategy):
    """Fade do gap overnight do WDO@, restrito a gaps pequenos/medios -- ate'
    1 operacao por pregao, mirando o fechamento anterior."""

    name: str = "wdo_gap_fade"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    #: alvo e' ordem-limite REAL parada no livro, nao `tp` nativo.
    target_fills_as_maker: bool = True
    #: stop/alvo ancoram no preco REALMENTE preenchido.
    anchor_exits_at_fill: bool = True
    #: medido em base de TICK (barra degenerada).
    feed_kind: str = "tick"
    is_futuro: bool = True

    tick_size: float = 0.5

    #: Decidido de FORA (ver a docstring do modulo): este pregao caiu no
    #: tercil pequeno/medio de |gap|? `False` = nunca opera hoje, qualquer
    #: que seja a barra.
    elegivel: bool = False
    #: Fechamento do pregao ANTERIOR -- o ALVO desta operacao. `None` =
    #: sem dado (primeiro pregao do historico carregado) -- nunca opera.
    prev_close_px: float | None = None
    #: Alternativa a `elegivel`/`prev_close_px` para uma janela de MUITOS
    #: pregoes num unico `run_intraday_backtest` continuo -- ver a secao
    #: "Como o gap de CADA dia chega ate' aqui" da docstring do modulo.
    #: `{date: (elegivel, prev_close_px)}`. `None` (default) = usa os dois
    #: campos simples acima (modo de 1 pregao so').
    gap_por_dia: dict | None = None

    #: 0 = limite NO preco de abertura; N = N ticks NA DIRECAO do gap
    #: (espera uma pequena extensao antes de fadear -- mesma logica de
    #: `wdo_orb.WdoOrb._ordem`: limite = referencia - sinal*offset).
    offset_ticks: int = 2
    #: Prazo da ordem de ENTRADA parada no livro, EM BARRAS -- ver a nota
    #: longa em `wdo_orb.WdoOrb.entrada_ttl_bars` sobre por que barra nao e'
    #: tempo em base de tick. Reaproveita o mesmo numero medido la' como
    #: ponto de partida (o harness deste arquivo reporta o atraso REALIZADO
    #: em minutos, nunca o prazo nominal).
    entrada_ttl_bars: int | None = 5000

    #: Piso do alvo em ticks -- ver a secao "Piso do alvo" da docstring do
    #: modulo (proibicao do T1, CLAUDE.md). Um dia cujo |gap| de' menos que
    #: isto de distancia ate' o fechamento anterior NAO opera, mesmo elegivel.
    alvo_min_ticks: int = 4
    #: stop = round(alvo_ticks / razao_alvo_stop), limitado entre stop_min/
    #: stop_max_ticks. 1,5 reaproveita o multiplo ja medido/promovido em
    #: `wdo_orb.WdoOrb.alvo_multiplo` (mesmo instrumento, mesmo desenho de
    #: execucao) em vez de inventar um numero novo sem medicao.
    razao_alvo_stop: float = 1.5
    stop_min_ticks: int = 10
    stop_max_ticks: int = 60

    quantity: int = 1

    _decidiu: bool = field(default=False, init=False, repr=False)
    _bloqueado: bool = field(default=False, init=False, repr=False)
    _lado: Side | None = field(default=None, init=False, repr=False)
    _alvo_ticks: int | None = field(default=None, init=False, repr=False)
    _stop_ticks: int | None = field(default=None, init=False, repr=False)
    _preco_referencia: float | None = field(default=None, init=False, repr=False)
    _armou: bool = field(default=False, init=False, repr=False)
    _preencheu: bool = field(default=False, init=False, repr=False)
    #: resolvidos em `on_session_start` -- de `gap_por_dia[session_date]`
    #: quando presente, senao dos campos simples `elegivel`/`prev_close_px`.
    _elegivel_hoje: bool = field(default=False, init=False, repr=False)
    _prev_close_hoje: float | None = field(default=None, init=False, repr=False)

    # ---------------- ciclo ------------------------------------------------

    def on_session_start(self, session_date) -> None:
        self._decidiu = False
        self._bloqueado = False
        self._lado = None
        self._alvo_ticks = None
        self._stop_ticks = None
        self._preco_referencia = None
        self._armou = False
        self._preencheu = False
        if self.gap_por_dia is not None:
            self._elegivel_hoje, self._prev_close_hoje = self.gap_por_dia.get(
                session_date, (False, None))
        else:
            self._elegivel_hoje, self._prev_close_hoje = self.elegivel, self.prev_close_px

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """Recusa por teto/capital: a ordem morreu, o robo pode tentar de novo
        com a MESMA geometria (mesmo espirito de `wdo_orb.WdoOrb`)."""
        self._armou = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        """Prazo estourado: idem -- sem isto o robo ficaria CEGO, achando
        para sempre que tem ordem viva no livro (o mesmo bug corrigido em
        `wdo_orb.WdoOrb.on_order_expired`, item 4.25 de LICOES_DE_PRODUCAO.md)."""
        self._armou = False

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        # --- (1) primeira barra do pregao: decide a geometria de hoje ------
        if not self._decidiu:
            self._decidiu = True
            self._preco_referencia = bar.close
            if not self._elegivel_hoje or self._prev_close_hoje is None:
                self._bloqueado = True
            else:
                gap_ticks = (bar.close - self._prev_close_hoje) / self.tick_size
                alvo_ticks = int(round(abs(gap_ticks)))
                if gap_ticks == 0 or alvo_ticks < self.alvo_min_ticks:
                    self._bloqueado = True
                else:
                    self._lado = "short" if gap_ticks > 0 else "long"
                    self._alvo_ticks = alvo_ticks
                    self._stop_ticks = int(max(
                        self.stop_min_ticks,
                        min(self.stop_max_ticks, round(alvo_ticks / self.razao_alvo_stop)),
                    ))

        if self._bloqueado:
            return []

        # --- (2) posicao aberta: nada a fazer, so' o motor (stop/alvo/
        # achatamento de fim de pregao) decide daqui pra frente ------------
        if positions:
            self._preencheu = True
            return []

        # --- (3) sem posicao: arma a entrada UMA vez (ou de novo se a
        # ordem anterior morreu por prazo/recusa) ---------------------------
        if self._preencheu or self._armou:
            return []
        self._armou = True
        return [self._ordem()]

    # ---------------- auxiliares (puros) -----------------------------------

    def _ordem(self) -> EnterLimit:
        sinal = 1.0 if self._lado == "long" else -1.0
        off = self.offset_ticks * self.tick_size
        limite = self._preco_referencia - sinal * off
        return EnterLimit(
            side=self._lado,
            limit_price=limite,
            initial_stop=limite - sinal * self._stop_ticks * self.tick_size,
            initial_target=self._prev_close_hoje,
            quantity=self.quantity,
            ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason="gap_fade",
        )
