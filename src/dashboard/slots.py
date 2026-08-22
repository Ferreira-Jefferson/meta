"""Quais vagas de operação existem AGORA — as estáticas do catálogo mais as
de day trade que o dono criou no painel.

Existe como módulo próprio (e não dentro de `live_control`/`live_service`)
porque é a única peça que precisa cruzar `core.config` (a forma de um slot)
com `journal.live_store` (quais contas existem). `core/` não pode importar
feature nenhuma (regra 1 do AGENTS.md), então a lista completa não tem como
morar lá; e as duas peças que a consomem — quem sobe processo
(`live_control`) e quem monta a página (`app`/`live_service`) — precisariam
duplicá-la.

O QUE DEFINE UM SLOT DE DAY TRADE
---------------------------------
Uma linha em `live_accounts` com `symbol` preenchido. O id da conta é o id do
slot (`dt-<robô>-<ativo>`) e carrega robô e ativo dentro de si, então o
processo filho (`scripts/run_live.py --slot dt-gremah-pmam3`) reconstrói tudo
que precisa a partir do argumento — sem ler este módulo, sem depender de o
dashboard estar de pé.

A conta é a fonte de verdade, e não o arquivo de estado dos processos
(`db/live_process.json`), por uma razão de contabilidade: um robô PARADO
continua dono do ativo dele, porque o caixa dele está lá. Um ativo só volta a
ficar livre quando a conta é removida.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.config import Slot, daytrade_slot, ordered_slots, slot_by_id
from journal import live_store


@dataclass(frozen=True)
class SlotAccount:
    """Um slot e a conta dele, já resolvidos juntos — o par que quase todo
    chamador quer (o slot sozinho não sabe o caixa; a conta sozinha não sabe
    o `magic` nem a cadência)."""

    slot: Slot
    #: `None` só no swing antes de o dono informar caixa pela primeira vez.
    #: Todo slot de day trade tem conta por construção (ela é o que o cria).
    account: Optional[object] = None


def daytrade_slots(conn) -> list[Slot]:
    """Slots de day trade existentes, na ordem em que foram criados.

    Uma conta com `symbol` cujo NOME não é um id de slot válido é ignorada em
    silêncio de propósito: pode ser resíduo de migração ou linha criada à mão
    no SQLite, e derrubar a página inteira (`KeyError`) por causa dela deixaria
    o dono sem painel justamente quando ele precisa consertar o banco.
    """
    resultado: list[Slot] = []
    for conta in live_store.accounts_with_symbol(conn):
        try:
            slot = slot_by_id(conta.name)
        except KeyError:
            continue
        if not slot.is_intraday:
            continue
        # O que vale é o que está GRAVADO na conta, não o que o id sugere: se
        # os dois divergirem (id montado com um robô, conta gravada com
        # outro), a conta manda — é ela que tem o dinheiro.
        #
        # `ValueError` = o robô gravado não cabe num id de slot (tem hífen, ou
        # está vazio). Acontece com linha antiga/corrompida, e NÃO pode derrubar
        # a página: fica-se com o slot derivado do id, e o robô inexistente
        # aparece como erro no cartão dele (`_slot_ctx` degrada num `KeyError`
        # do registry, com o nome do robô no banner) em vez de num 500 que
        # esconde todos os outros robôs.
        if conta.investment_robot and conta.investment_robot != slot.robot_key:
            try:
                slot = daytrade_slot(conta.investment_robot, conta.symbol)
            except ValueError:
                pass
        resultado.append(slot)
    return resultado


def all_slots(conn=None) -> list[Slot]:
    """Todos os slots do painel, day trade primeiro (`Slot.order`).

    `conn=None` abre e fecha uma conexão própria — conveniência para os
    chamadores que só querem a lista. Quem já está dentro de uma transação
    passa a sua, para não abrir uma segunda conexão no mesmo SQLite.
    """
    if conn is None:
        with live_store.live_journal() as own:
            return all_slots(own)
    slots = [*daytrade_slots(conn), *ordered_slots()]
    # Ordena SÓ por `order`, e o desempate é a ordem de entrada — `sorted` é
    # estável, e `daytrade_slots` já vem em ordem de criação (`ORDER BY id`).
    #
    # Havia um `s.id` no desempate, e ele era um bug de tela: todo slot de day
    # trade tem `order == 0`, então o desempate valia SEMPRE e ordenava os
    # robôs em ordem alfabética do id. Abrir KLBN4 depois de PMAM3 colocava o
    # novo ACIMA do antigo, e a lista deixava de contar a história de como o
    # dono chegou nela. Ordem de criação, mais recente por último
    # (pedido do dono, 2026-08-22).
    return sorted(slots, key=lambda s: s.order)


def symbols_in_use(conn=None) -> dict[str, str]:
    """`{ativo: id_do_slot}` de todo ativo já alocado a um robô de day trade.

    É o que responde as duas perguntas do pedido de 2026-08-22: o painel
    desenha a bolinha e desabilita o ativo já usado, e a regra de sugestão
    (`strategy.daytrade.enxame`) sabe o que NÃO oferecer. Inclui robô parado —
    ver docstring do módulo.
    """
    if conn is None:
        with live_store.live_journal() as own:
            return symbols_in_use(own)
    return {slot.symbol: slot.id for slot in daytrade_slots(conn) if slot.symbol}
