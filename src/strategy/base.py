"""Interface Strategy — event-driven, adaptativa.

Cada robô recebe o gatilho (o bar atual + estado da carteira) e devolve **ações
declarativas** que o engine executa: `Enter`, `Exit`, `AdjustStop`. Assim cada
estratégia é dona da sua própria política de entrada, saída e ajuste de stop
(fixo, trailing por ATR, canal Donchian, banda mediana etc.) — o engine só
coordena calendário, custos, sizing e diário.

Contrato:
- `initialize(panels, ibov)` é chamado uma vez com todo o histórico do universo.
  O robô pré-calcula os indicadores que quiser e guarda como estado.
- `on_bar(date, open_positions, cash_available)` é chamado a cada pregão.
  O robô devolve `list[Action]` — pode devolver lista vazia (rebalance mensal ignora
  os outros dias).
- As ações são **enfileiradas** pelo engine: `Enter`/`Exit` executam na abertura
  do próximo pregão (anti-look-ahead); `AdjustStop` é aplicado imediatamente
  (custo zero, só atualiza o stop registrado).
- Stops disparam intra-bar: se `low[D] <= current_stop`, o engine emite um
  `Exit(reason=STOP)` automático no próprio dia — sem esperar a decisão do robô.

Este contrato é portável a MQL5: `initialize()` vira `OnInit`, `on_bar()` vira
`OnTick` com timeframe D1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Union

import pandas as pd

from core.models import ExitReason


@dataclass
class OpenPosition:
    """Snapshot da posição vista pelo robô no momento do `on_bar`."""

    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    quantity: int
    current_stop: float | None
    bars_held: int
    metadata: dict = field(default_factory=dict)


@dataclass
class Enter:
    """Ação: abrir posição comprada.

    - `initial_stop`: preço absoluto onde o robô quer parar caso o trade vire.
      Se `None`, o engine assume que não há stop e a posição só será fechada
      por `Exit` explícito.
    - `size_hint`: fração do caixa disponível a alocar (0..1). Se `None`,
      o engine aplica o default (caixa dividido pelos slots livres).
    - `metadata`: livre para o robô salvar contexto (ex.: banda no dia da
      entrada, ATR estimado). Fica preservado em `OpenPosition.metadata` para
      o robô consultar em `on_bar`.
    - `reason`: qual REGRA do robô disparou esta compra, em código curto
      (`"dip_rank"`, `"dip_rank1_rotation"`). Existe por simetria com
      `Exit.reason`: sem ele o diário sabe explicar toda venda e nenhuma
      compra, e a pergunta "por que este papel neste dia?" fica sem resposta
      seis meses depois. Fica em `live_intents.reason`; os NÚMEROS que
      acompanham a regra (rank, score, distância da máxima) vão em
      `metadata`, que o runtime copia para `live_intents.payload`.

      String e não enum de propósito: `ExitReason` é fechado porque as saídas
      são poucas e comuns a todos os robôs, mas cada estratégia entra por um
      motivo próprio, e um enum central obrigaria a editar `core/` a cada robô
      novo — exatamente o acoplamento que a regra 2 do AGENTS.md evita.
    """

    ticker: str
    initial_stop: float | None = None
    size_hint: float | None = None
    metadata: dict | None = None
    reason: str = ""


@dataclass
class Exit:
    """Ação: fechar posição. Deve levar um `ExitReason` para o diário."""

    ticker: str
    reason: ExitReason


@dataclass
class AdjustStop:
    """Ação: mover o stop registrado para `new_stop`.

    O engine só aceita se `new_stop >= current_stop` (stop nunca desce).
    Custo zero — é uma atualização de estado.
    """

    ticker: str
    new_stop: float


Action = Union[Enter, Exit, AdjustStop]


class Strategy(ABC):
    """Interface event-driven que todos os robôs implementam."""

    name: str
    version: str
    # Universo próprio do robô. Se None, engine usa WATCHLIST default.
    # Permite robôs experimentais escolherem seus tickers (setor bancário,
    # universo largo, etc.) sem mexer nos canonicals.
    universe_tickers: tuple[str, ...] | None = None

    # Lista branca (class attribute) dos atributos privados que precisam
    # sobreviver a um restart do processo ao vivo — ver `state()`/`restore()`
    # abaixo. Vazia por default: a maioria dos robôs não tem nada que precise
    # sobreviver a um restart (indicadores são recalculados por
    # `initialize()`). Só entra aqui o que MUDA a decisão futura e não pode
    # ser recomputado do histórico — ex.: `BuyTheDip._pending_rebalance`, o
    # adiamento de rotação por blackout de resultados. Nunca usar
    # `vars(self)` cru em `state()`: a família dip guarda `_scores`/
    # `_dist_from_high` (`dict[str, pd.Series]`), não serializáveis em JSON
    # e recalculados a cada `initialize()` — não precisam e não podem
    # sobreviver a um restart.
    _stateful_keys: tuple[str, ...] = ()

    # ---------------------------------------------------------------- ficha
    # FICHA TÉCNICA — documentação, nunca decisão. Nada aqui é lido por
    # `on_bar`; quem lê é `strategy/registry.py`, para a página do robô
    # (`/strategies/<key>`) poder dizer em prosa o que o código faz. Ficam na
    # CLASSE (e não num dicionário no dashboard) por um motivo só: assim a
    # explicação e a regra explicada moram no mesmo arquivo e divergem juntas
    # — uma tabela de textos em `dashboard/` envelheceria em silêncio no dia
    # em que alguém mudasse a regra aqui.
    #
    # São HERDADAS como qualquer atributo de classe: uma subclasse que não
    # declara nada mostra a ficha da mãe (correto — ela opera as mesmas
    # regras). Quem muda uma peça declara a lista INTEIRA, tipicamente
    # somando à da mãe (`entry_rules = Mae.entry_rules + ("...",)`), para o
    # que a subclasse acrescenta ficar explícito na leitura do código.
    #
    # Convenção de texto: uma frase por item, `crase` para nome de
    # parâmetro/arquivo (virá `<code>` na tela). Sem HTML cru.
    #
    # TEXTO PARA HUMANO, NÃO PARA QUEM LÊ CÓDIGO
    # ------------------------------------------
    # `tagline`/`plain_summary`/`plain_example` são a versão que o DONO DO
    # CAPITAL lê na página do robô. Existem porque a primeira versão desta
    # ficha reaproveitava o docstring da classe, e o docstring é escrito para
    # outra audiência: ele fala de hipótese a priori, de refutação, de
    # `kwargs.setdefault`, de datas de promoção. Tudo isso importa para quem
    # mexe no código e é ruído para quem só quer saber o que o robô faz com o
    # dinheiro dele.
    #
    # Regras de escrita (o docstring continua livre para ser técnico):
    #   - sem nome de parâmetro, de classe ou de arquivo — números e prazos
    #     de verdade no lugar ("2% abaixo da máxima de 8 semanas", não
    #     "`dip_pct` abaixo da máxima de `high_window`");
    #   - números REAIS deste robô, conferidos, não os da classe-base;
    #   - `plain_example` é um caso concreto em passos, com valores que o
    #     robô produziria de fato.
    # Declarar na FOLHA (o robô operável), nunca numa classe-base: uma
    # classe-base não sabe com que números a folha vai rodar, e um número
    # errado na tela é pior que número nenhum.
    tagline: str = ""                       # uma frase: o que ele faz
    plain_summary: tuple[str, ...] = ()     # parágrafos de prosa
    plain_example: tuple[str, ...] = ()     # um caso concreto, em passos

    watched_signals: tuple[str, ...] = ()   # o que o robô calcula e observa
    entry_rules: tuple[str, ...] = ()       # quando e por que compra
    exit_rules: tuple[str, ...] = ()        # quando e por que vende
    sizing_rules: tuple[str, ...] = ()      # quanto compra, e o que custa
    # Descrição de um parâmetro do `__init__`, por nome. Mesclado ao longo do
    # MRO (a classe mais derivada ganha) por `registry.declared_params()`.
    param_docs: dict[str, str] = {}
    # Parâmetros que NÃO aparecem na ficha. Para encanamento: caminho de
    # arquivo, chave de modo interno, nome que só faz sentido para quem leu a
    # classe. Continuam existindo e continuam configuráveis — só não são
    # oferecidos como se fossem uma decisão de investimento.
    param_hidden: tuple[str, ...] = ()
    # Parâmetros cujo valor é FRAÇÃO e deve ser lido como percentual na ficha
    # (`0.02` -> "2%"). É propriedade da UNIDADE do parâmetro, não do valor,
    # então pode ser declarado na classe-base sem risco de mentir numa
    # subclasse. Sem isto, a ficha mostrava "0.02" e deixava para o leitor
    # adivinhar se eram 2% ou 0,02%.
    param_pct: tuple[str, ...] = ()

    def initialize(self, panels: dict[str, pd.DataFrame], ibov: pd.DataFrame) -> None:
        """Pré-calcula indicadores sobre o histórico completo.

        Chamado uma vez pelo engine antes do loop de datas. O robô deve
        guardar `panels`, `ibov` e quaisquer indicadores derivados como
        atributos de instância para consultar em `on_bar`.

        Implementação padrão vazia — robôs sem estado podem simplesmente
        computar tudo em `on_bar` (não recomendado por performance).
        """

    @abstractmethod
    def on_bar(
        self,
        date: pd.Timestamp,
        open_positions: dict[str, OpenPosition],
        cash_available: float,
    ) -> list[Action]:
        """Decisão do dia. Devolve ações declarativas ao engine."""

    def on_missed_bars(self, missed: list[pd.Timestamp]) -> None:
        """Estes pregões passaram SEM que `on_bar` fosse chamado. O que fazer?

        Existe porque ao vivo o processo pode estar fora do ar no fecho — e aí
        a decisão daquele pregão não atrasa, ela se PERDE: um robô que só
        rebalanceia no último pregão do mês perde a rotação do mês inteiro.
        No backtest isto nunca acontece (o loop visita todo pregão), então o
        ambiente ao vivo precisa de um jeito de contar o que faltou.

        Quem decide o que um pregão perdido significa é a ESTRATÉGIA, nunca
        `live/` (regra 6 do AGENTS.md): o ambiente só REPORTA o fato. Um robô
        que decide todo dia não deve nada e o default aqui é não fazer nada;
        um robô de cadência mensal pode querer marcar a rotação como devida.

        Não é execução atrasada e não conflita com a regra 7: nada decidido
        naquele fecho antigo é executado. O que a estratégia pode fazer é
        pedir para DECIDIR DE NOVO no próximo pregão, com o dado desse
        pregão — se o sinal não fizer mais sentido, não faz mais sentido, e a
        decisão nova dirá isso. Mesmo mecanismo que a família dip já usa para
        o blackout de resultados, que o backtest exercita.

        Default no-op de propósito: um robô que não implementa isto continua
        se comportando exatamente como antes.
        """

    def state(self) -> dict:
        """Estado a persistir para sobreviver a um restart do processo ao vivo.

        Genérico sobre `_stateful_keys` (lista branca), de propósito: NUNCA
        `vars(self)` cru — ver o comentário em `_stateful_keys` para o
        motivo (indicadores não-serializáveis que não deveriam sobreviver a
        restart de qualquer forma, porque `initialize()` os recalcula).
        Mesma convenção de `backtest.withdrawal.WithdrawalPolicy.state()`.

        `getattr(..., None)` com default (correção pós-review, tentativa 1):
        sem ele, uma subclasse que declare `_stateful_keys` com um atributo
        criado fora de `__init__` (ex.: só na primeira chamada de `on_bar`)
        levantaria `AttributeError` aqui no meio de um `save_account` — o
        mesmo cuidado que `restore()` logo abaixo já tinha.
        """
        return {k: getattr(self, k, None) for k in self._stateful_keys}

    def restore(self, state: dict) -> None:
        """Reidrata o estado devolvido por `state()`.

        Ignora silenciosamente qualquer chave fora de `_stateful_keys` —
        estado de uma versão diferente da estratégia (ou de outro robô, ver
        `live.runtime._restore_robot_state`) não pode contaminar esta
        instância. Normaliza lista→tupla (o caminho real de persistência
        passa por JSON, que não tem tipo tupla — mesmo cuidado de
        `CircuitBreaker.restore()`/`WithdrawalPolicy.restore()`) e COAGE o
        tipo pelo valor atual do atributo (bool/int/float): sem isso,
        `_pending_rebalance` persistido como a string `"false"` seria
        truthy em Python e dispararia rotação fora de hora.
        """
        for k, v in state.items():
            if k not in self._stateful_keys:
                continue
            if isinstance(v, list):
                v = tuple(v)
            default = getattr(self, k, None)
            if isinstance(default, bool):
                # `bool("false")` é `True` em Python (string não-vazia) — o
                # motivo exato do achado C2. Interpreta a string pelo seu
                # conteúdo; qualquer valor não-string cai no `bool()` normal.
                v = v.strip().lower() not in ("false", "0", "") if isinstance(v, str) else bool(v)
            elif isinstance(default, int):
                v = int(v)
            elif isinstance(default, float):
                v = float(v)
            setattr(self, k, v)
