"""Quando um robô de day trade em operação deve AVISAR que já dá para abrir um
robô novo em outro ativo.

É só um aviso. Nada aqui abre robô, move dinheiro ou toca em conta: a função
devolve "sugira o ativo X" ou `None`, e quem decide continua sendo o dono, no
painel. A regra mora em `strategy/` (e não em `live/`) pela regra 6 do
AGENTS.md — `live/` aplica regra declarada, nunca inventa a própria.

A REGRA, E DE ONDE ELA VEIO
---------------------------
Escolhida pelo dono em 2026-08-22 depois de quatro variantes medidas em dado
de minuto real (PMAM3 + 9 ativos calibrados, 2025-12-16..2026-08-21). Em
todas, o robô que dispara NÃO paga nada — o capital do robô novo é aporte novo
do dono; o robô em operação só sinaliza a hora.

    avisa quando:  caixa − já_aportado_nos_outros
                   ≥ capital_mínimo(candidato) + capital_mínimo(próprio)

O termo `já_aportado_nos_outros` é o que o dono chamou de "abater o dinheiro do
que já foi aberto", e é o que faz a barra SUBIR a cada robô novo. Sem ele, a
mesma conta requalifica na hora para o candidato seguinte e a fila inteira
nasce no mesmo dia: na medição, uma PMAM3 com R$1.111 disparou três robôs de
uma vez, pedindo R$2.054 do bolso do dono numa tacada. Com o abatimento, os
mesmos quatro aportes se espalharam por abril, junho, junho e julho.

As quatro variantes, para o número não se perder (bolso -> caixa final):

    A) ordem calibrada,  sem abatimento    R$2.924 -> R$10.379   3,5x   5 robôs
    B) mais barato 1º,   sem abatimento    R$5.650 -> R$14.383   2,5x   9 robôs
    C) ordem calibrada,  COM abatimento    R$2.640 -> R$ 9.566   3,6x   5 robôs
    D) mais barato 1º,   COM abatimento    R$5.468 -> R$11.935   2,2x   9 robôs

O dono escolheu **C**. O motivo não foi o resultado (A e C empatam na prática):
foi a assimetria quando o período NÃO se repete — A mandaria colocar R$2.054 no
pior momento possível, C mandaria R$760.

A ORDEM DA FILA É DE QUEM CHAMA
-------------------------------
`avaliar_sugestao` recebe `candidatos` já ordenados e obedece: ela nunca pula
para "o próximo que caberia". Isso tem uma consequência conhecida e aceita na
ordem calibrada (lucro OOS decrescente, `gremah.calibrated_setups()`): o sexto
da fila é a CLSC4, que exige ~R$30.000, então as sugestões PARAM ali mesmo
havendo ativos baratos atrás dela. Foi o comportamento medido em C, e é o que
o dono escolheu. Não é um beco: o painel deixa abrir qualquer ativo na mão a
qualquer momento — a fila governa só o que o robô SUGERE.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from strategy.daytrade.base import LOTE_PADRAO_B3, capital_minimo_brl


@dataclass(frozen=True)
class Candidato:
    """Um ativo que o robô poderia operar, com o preço de hoje."""

    symbol: str
    preco_atual: float
    shares_per_lot: int = LOTE_PADRAO_B3

    @property
    def capital_minimo_brl(self) -> float:
        return capital_minimo_brl(self.preco_atual, self.shares_per_lot)


@dataclass(frozen=True)
class Sugestao:
    """O aviso a mostrar ao dono."""

    symbol: str
    #: Quanto o dono precisa aportar para abrir este robô (o mínimo do ativo).
    required_brl: float
    #: Caixa da conta que avisou, no momento do aviso.
    cash_brl: float
    #: Caixa menos o já aportado nos outros robôs — o número que de fato
    #: cruzou a barra. Guardado para a mensagem poder explicar o porquê.
    disponivel_brl: float


def avaliar_sugestao(
    caixa_brl: float,
    preco_proprio: float,
    candidatos: Sequence[Candidato],
    ja_aportado_brl: float = 0.0,
    shares_per_lot: int = LOTE_PADRAO_B3,
) -> Sugestao | None:
    """O primeiro candidato da fila que esta conta já banca, ou `None`.

    `caixa_brl`: caixa da conta que está avaliando.
    `preco_proprio`: preço de HOJE do ativo que ela já opera — o mínimo dela
    depende dele e muda todo pregão.
    `candidatos`: ativos AINDA NÃO alocados, na ordem em que devem ser
    sugeridos (quem filtra o que já roda é o chamador, que é quem sabe —
    `dashboard.slots.symbols_in_use`).
    `ja_aportado_brl`: soma do capital que o dono já pôs nos OUTROS robôs de
    day trade. É o abatimento descrito na docstring do módulo.

    Devolve `None` na esmagadora maioria das avaliações — o aviso é um evento
    raro, não uma rotina. Também devolve `None` (em vez de levantar) com preço
    ausente ou zerado: falta de preço não é motivo para derrubar o robô que
    está operando.
    """
    if preco_proprio <= 0 or not candidatos:
        return None
    # SÓ o primeiro da fila é avaliado — a fila é estrita e nunca pula para "o
    # próximo que caberia" (ver a docstring do módulo). Um `for` aqui daria a
    # impressão errada de que os demais têm chance nesta rodada.
    candidato = candidatos[0]
    if candidato.preco_atual <= 0:
        return None  # sem preço hoje o custo é desconhecido: a fila espera
    disponivel = float(caixa_brl) - max(0.0, float(ja_aportado_brl))
    meu_minimo = capital_minimo_brl(preco_proprio, shares_per_lot)
    necessario = candidato.capital_minimo_brl
    if disponivel < necessario + meu_minimo:
        return None
    return Sugestao(
        symbol=candidato.symbol,
        required_brl=necessario,
        cash_brl=float(caixa_brl),
        disponivel_brl=disponivel,
    )
