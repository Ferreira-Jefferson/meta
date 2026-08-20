"""LiquidSleeves5 — o robo que eu levaria para operacao. Cinco sleeves, uma conta.

O que ele e
-----------
Cinco `LiquidSleeve` (ver `strategy/liquid_sleeve.py`) rodando lado a lado, cada
um dono de um quinto do top-20 mais liquido do dia e de um quinto do capital.
Cada sleeve decide sozinho, com as MESMAS regras do campeao `portfolio_dip2_hw40`
(momentum 12-1, dip de 2%, histerese de 15%, gate de Selic, blackout de
resultados) — o que muda e de onde ele pode escolher e quanto ele carrega.

De onde vem cada decisao de desenho
-----------------------------------
Nada aqui foi escolhido por melhorar o backtest. Cada peca passou num teste
cego e as que nao passaram ficaram de fora:

| peca                          | evidencia                                              |
|-------------------------------|--------------------------------------------------------|
| universo por liquidez na data | vies de selecao valia +17 p.p. de CAGR (`run_walk_forward.py`) |
| 5 sleeves                     | janelas negativas 1/5 -> 0/5, pior 12m -41,9% -> -16,1% |
| parametros CONGELADOS         | tunar no in-sample perdeu em 4 de 6 trilhas (`run_walk_forward_params.py`) |
| nenhum filtro defensivo extra | trava de tendencia, quarentena, stop largo, dip 5%: todos reprovaram |

O preco esta declarado, nao escondido: o CAGR mediano liquido de IR cai de
15,17% (uma conta concentrada) para 9,36%. O IBOV nas mesmas janelas fez 7,45%.

Uma conta so, e nao cinco na corretora
--------------------------------------
O teste que aprovou o desenho somava cinco curvas independentes. Aqui o caixa e
COMPARTILHADO, o que muda uma coisa de verdade: quando um sleeve vende e nao
recompra, o dinheiro dele fica no caixa reservado — `size_hint` divide o caixa
livre pelo numero de sleeves DESCOBERTOS, nao pelo numero de entradas do dia,
justamente para um sleeve nao herdar a fatia do outro. E a unica forma de manter
a proporcao de 1/5 sem o engine saber o que e um sleeve.

A diferenca residual entre esta versao e as cinco contas separadas e medida em
`scripts/run_sleeve_validation.py` — se as duas curvas divergirem, e este
arquivo que esta errado, nao o teste.
"""
from __future__ import annotations

import pandas as pd

from strategy.base import Enter, Exit
from strategy.liquid_sleeve import POOL, LiquidSleeve
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio


class LiquidSleeves5(DipTop1Portfolio):
    """Cinco sleeves liquidos disjuntos, 20% do capital em cada, numa conta so."""

    name = "liquid_sleeves5"
    version = "1.0"
    # Fora do ranking desde 2026-08-20 — nao por ter perdido, mas por ter
    # vencido: este desenho VIROU o campeao, e `strategy/liquid_champion.py`
    # herda dele sem mudar uma linha de comportamento. Deixar os dois no podio
    # poria a mesma curva em duas posicoes e daria a impressao de que o campeao
    # bateu um rival, quando bateria a si mesmo. A classe continua sendo a base
    # do campeao e da variante `liquid_flow5`.
    candidate = False
    universe_tickers = POOL

    # `_owner` precisa sobreviver a restart: e o que diz de qual sleeve e cada
    # posicao aberta. Sem ele, apos um restart o robo reatribuiria as posicoes
    # pelo criterio de elegibilidade do dia e poderia dar duas posicoes ao mesmo
    # sleeve — mudando o tamanho de tudo em seguida.
    _stateful_keys = ("_pending_rebalance", "_owner")

    def __init__(
        self,
        sleeve_count: int = 5,
        universe_n: int = 20,
        liquidity_window: int = 252,
        refresh_months: int = 12,
        min_history_days: int = 504,
        evict_on_refresh: bool = False,
        **kwargs,
    ):
        # Os parametros de UNIVERSO sao nomeados aqui em vez de viajarem dentro
        # de `**kwargs`: `BuyTheDip.__init__` (a raiz da familia) tem assinatura
        # fechada e levanta TypeError em qualquer chave que nao conheca. O que
        # sobra em `kwargs` sao os parametros de SINAL (dip_pct, high_window,
        # lookback...), que vao para os dois lados de proposito — o robo e os
        # cinco sleeves precisam operar com as mesmas regras.
        super().__init__(**kwargs)
        self.sleeve_count = sleeve_count
        self._sleeves = [
            self._make_sleeve(
                sleeve_index=i,
                sleeve_count=sleeve_count,
                universe_n=universe_n,
                liquidity_window=liquidity_window,
                refresh_months=refresh_months,
                min_history_days=min_history_days,
                evict_on_refresh=evict_on_refresh,
                **kwargs,
            )
            for i in range(sleeve_count)
        ]
        self._owner: dict[str, int] = {}

    def _make_sleeve(self, **kwargs) -> LiquidSleeve:
        """Fabrica de sleeve — ponto de extensao para variantes do universo.

        Existe para que uma variante (ex.: `strategy/liquid_flow5.py`, universo
        continuo com histerese de rank) troque APENAS a regra de universo e
        herde intacta toda a composicao de caixa e posse deste arquivo, que e a
        parte dificil de acertar e a que nao tem motivo para divergir.
        """
        return LiquidSleeve(**kwargs)

    # ------------------------------------------------------------------ setup

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        for s in self._sleeves:
            s.initialize(panels, ibov)

    # ------------------------------------------------------------------ decisao

    def _owner_of(self, ticker: str, date) -> int:
        """De qual sleeve e esta posicao.

        Consulta a memoria primeiro (`_owner`), porque um papel comprado quando
        pertencia ao sleeve 2 continua sendo do sleeve 2 mesmo depois de sair do
        top-20 — e o sleeve 2 que tem de manda-lo embora. O fallback por
        elegibilidade so existe para posicao encontrada sem dono (restart com
        estado perdido, ou carteira pre-existente ao ligar o robo).
        """
        if ticker in self._owner:
            return self._owner[ticker]
        for i, s in enumerate(self._sleeves):
            if s.is_eligible(ticker, date):
                return i
        return 0

    def on_bar(self, date, open_positions, cash_available):
        owner = {t: self._owner_of(t, date) for t in open_positions}
        self._owner = dict(owner)

        others: list = []
        enters: list[Enter] = []
        for i, sleeve in enumerate(self._sleeves):
            mine = {t: p for t, p in open_positions.items() if owner[t] == i}
            for act in sleeve.on_bar(date, mine, cash_available):
                if isinstance(act, Enter):
                    self._owner[act.ticker] = i
                    enters.append(act)
                else:
                    others.append(act)

        exiting = {owner[a.ticker] for a in others if isinstance(a, Exit) and a.ticker in owner}
        for a in others:
            if isinstance(a, Exit):
                self._owner.pop(a.ticker, None)

        if enters:
            invested_after = {owner[t] for t in open_positions} - exiting
            idle = max(len(enters), self.sleeve_count - len(invested_after))
            # `1/(idle-k)` divide o caixa livre em `idle` fatias iguais mesmo o
            # engine consumindo o caixa entrada a entrada: a k-esima compra pega
            # 1/(idle-k) do que sobrou, que e exatamente 1/idle do caixa inicial.
            for k, act in enumerate(enters):
                act.size_hint = 1.0 / float(idle - k)

        return others + enters

    def on_missed_bars(self, missed) -> None:
        """Repassa aos cinco sleeves — eles sao quem tem cadencia mensal.

        Mesmo motivo de `state()`/`restore()` logo abaixo: os sleeves sao
        objetos internos e nenhum mecanismo generico enxerga dentro deles. Sem
        este repasse, um pregao de fim de mes perdido deixaria a rotacao devida
        no objeto de fora — que nao rebalanceia nada por conta propria, porque
        `on_bar` delega tudo aos sleeves — e os cinco voltariam achando que nao
        tem nada pendente. O robo ficaria um mes inteiro sem rotacao sem que
        nenhum sinal disso aparecesse.
        """
        super().on_missed_bars(missed)
        for s in self._sleeves:
            s.on_missed_bars(missed)

    # ------------------------------------------------------------------ estado

    def state(self) -> dict:
        """Estado do robo + o `_pending_rebalance` de cada sleeve.

        Os sleeves sao objetos internos e o mecanismo generico de
        `_stateful_keys` nao enxerga dentro deles. Sem esta serializacao, um
        restart no meio de um blackout de resultados perderia a rotacao adiada
        de todos os cinco — cada um voltaria achando que nao tem nada pendente.
        """
        base = super().state()
        base["_sleeve_pending"] = [bool(s._pending_rebalance) for s in self._sleeves]
        return base

    def restore(self, state: dict) -> None:
        pending = state.get("_sleeve_pending")
        super().restore(state)
        if isinstance(pending, (list, tuple)) and len(pending) == len(self._sleeves):
            for s, v in zip(self._sleeves, pending):
                s._pending_rebalance = bool(v)
        if isinstance(self._owner, (list, tuple)):  # defesa: JSON pode ter virado lista
            self._owner = {}
