"""Execucao de ordem, atras de um port.

Regra de fronteira (AGENTS.md #6): um `Broker` executa, NUNCA decide e NUNCA
persiste. Ele muta e devolve a `Order` recebida (`status`, `filled_qty`,
`avg_price`, `fees`, `slippage`, `broker_ref`) — quem grava essa `Order` no
diario e quem atualiza `AccountState` e o RUNTIME, nunca o broker. Motivo:
se o broker tivesse acesso a escrita, um bug de execucao poderia corromper o
diario sem passar pelo unico lugar que sabe como fazer isso direito
(`journal/writer.py`), e o broker deixaria de ser uma peca trocavel (paper
hoje, corretora real amanha) para virar um segundo dono de estado de conta.

Implementacao de producao (`src/`):

  - Corretora real (`live.broker_mt5.MT5Broker`, via pip `MetaTrader5`) fala
    com um terminal MT5 ja aberto na mesma maquina, decide nada, so executa.

Nenhuma classe que preenche sozinha contra um feed (simulacao) mora em
`src/` — isso e, por definicao, um dublê de teste, nunca uma corretora real
(ver `tests/doubles.py::PaperBroker`, movida para la em FEAT-001: mante-la
aqui era o que permitia o dashboard/CLI cair nela por um fallback silencioso
sempre que o modo pedido nao batia com nenhum broker real). Esse e o ponto de
existir o port: nem o runtime nem os robos de `strategy/` precisam mudar uma
linha para trocar de broker — so troca qual `Broker` e instanciado.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.live_models import Order, OrderStatus


class Broker(ABC):
    """Port de execucao. Contrato: recebe uma `Order`, devolve a MESMA
    `Order` mutada com o resultado. Nao guarda historico, nao escreve banco."""

    name: str
    mode: str  # 'mt5' (ver core.live_models.BrokerMode)
    # `True` só em dublês de teste (ex.: `tests/doubles.PaperBroker`) — nunca
    # em broker de produção. `LiveRuntime.__init__` recusa instanciar um
    # dublê apontando para o banco de produção (`core.config.LIVE_DB_PATH`),
    # ver `live/runtime.py` (item 0.3 herdado de FEAT-000).
    is_test_double: bool = False

    @abstractmethod
    def place(self, order: Order) -> Order:
        """Envia a ordem. Muta e devolve `order` com o resultado do envio."""
        raise NotImplementedError

    @abstractmethod
    def poll(self, order: Order) -> Order:
        """Atualiza o status de uma ordem ja enviada. Para brokers sincronos
        (paper), e um no-op que devolve a ordem como esta — o fill ja
        aconteceu em `place`. Para MT5, consulta o terminal — o fill pode
        chegar depois do `place` (ver `live/runtime.py::reconcile_pending_fills`)."""
        raise NotImplementedError

    def cancel(self, order: Order) -> Order:
        """Cancela uma ordem viva. Default: marca `CANCELLED` se ainda nao
        terminal; ordens ja terminais (`is_terminal`) ficam como estao —
        cancelar um fill ja consumado nao desfaz o fill."""
        if not order.is_terminal:
            order.status = OrderStatus.CANCELLED
        return order

    def position_state(self, ticker: str) -> dict:
        """Posicao aberta deste robo em `ticker`, em TRI-ESTADO -- devolve
        `{"ok": bool, "position": dict | None, "note": str}`.

        Existe porque `open_position()` devolve `None` para DUAS coisas que
        nao podem ser confundidas: "perguntei a corretora e nao ha posicao
        nenhuma" e "nao consegui perguntar". Tratar a segunda como a primeira
        e' o erro mais caro que este sistema pode cometer -- e' assim que o
        robo re-arma ordem sobre uma posicao que existe, ou registra uma
        saida que nunca aconteceu. `ok=False` significa exatamente "NAO SEI",
        e quem chama tem de tratar como incerteza, nunca como zero.

        Default do port: pergunta `open_position()` e assume que a resposta
        e' confiavel (`ok=True`). Serve para os dublês de teste, que leem
        estado em memoria e nao tem como falhar na consulta. `MT5Broker`
        sobrescreve com a versao que de fato distingue os dois casos."""
        leitor = getattr(self, "open_position", None)
        if leitor is None:
            return {"ok": True, "position": None,
                    "note": "este broker nao reporta posicao"}
        return {"ok": True, "position": leitor(ticker), "note": ""}

    def margin_required(self, ticker: str, side: str, quantity: int,
                        price: float) -> Optional[float]:
        """Margem em R$ que a corretora exige para abrir esta ordem, ou
        `None` = "este broker nao sabe responder" (nunca "e' de graca").

        Default `None` pelo mesmo motivo de `cash_balance`: so' uma conexao
        de corretora de verdade sabe. Quem chama trata `None` como "nao
        sei", e "nao sei" nunca autoriza nem bloqueia sozinho -- ver
        `IntradayLiveRuntime._check_margem_da_conta`."""
        return None

    def supports_automation(self) -> bool:
        """Se este broker pode operar sem confirmacao humana no meio. Hoje a
        unica implementacao de producao e MT5, que sempre pode: True."""
        return True

    def cash_balance(self) -> Optional[float]:
        """Saldo de caixa segundo uma fonte EXTERNA e independente da conta
        interna (`AccountState.cash`), se este broker tiver uma. Default
        `None`: significa "nao tenta reconciliar deposito contra este
        broker", nunca "saldo zero". So uma conexao de corretora de verdade
        (ver `MT5Broker.cash_balance`) sabe responder isto de fato."""
        return None
