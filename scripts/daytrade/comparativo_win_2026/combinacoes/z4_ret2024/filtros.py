# -*- coding: utf-8 -*-
"""Z4: filtros de ENTRADA pre-registrados (etapa 2). Valores escolhidos olhando so' 2024 (diagnostico.md).
Cada filtro recebe o contexto calculado por port_z4.Contexto.calcula no instante em que a ordem seria armada
(t_arm = fim da vela M15 de decisao) e devolve True para ARMAR, False para nao armar (o EA tenta de novo na vela seguinte).
  hora_arm       = hora de t_arm em horas decimais (servidor)
  faixa_dia_atrd = (maxima - minima do pregao, M1 fechadas ate' t_arm) / ATR14 D1 dos pregoes anteriores
"""


def f1_decisao_a_partir_10h(c):
    """Nao arma com decisao antes das 10:00. A janela de 20 velas M15 e' quase toda do pregao anterior e a abertura
    (gap, leilao, primeira hora) nao respeita a faixa de ontem. 2024: decisoes 9:30-9:59 = 23 ops, -969, 10% acerto."""
    return c["hora_arm"] >= 10.0


def f2_decisao_a_partir_12h(c):
    """Nao arma com decisao antes das 12:00 (manha inteira; a janela atravessa a noite ate' ~14h).
    2024: decisao < 12h = 73 ops, -1.231; >= 12h = 62 ops, +170."""
    return c["hora_arm"] >= 12.0


def f3_dia_ja_andou(c):
    """So' arma se o pregao ja' andou: amplitude do dia ate' a decisao >= 0,5 ATR D1. Com o dia comprimido a expansao
    que falta tende a vir depois, e o stop (0,45 x largura, curto em ano de baixa volatilidade) e' atropelado.
    2024: quartis de amplitude -14,6 / -20,7 / -6,2 / +5,3 / -3,0 R$/op (quintis); corte no meio (0,5)."""
    return c["faixa_dia_atrd"] >= 0.5


def f4_manha_sem_amplitude(c):
    """Bloqueia so' a combinacao: decisao antes das 12:00 E amplitude do dia ate' a decisao < 0,5 ATR D1.
    2024: essa celula = -1.147; o resto do ano = +86."""
    return not (c["hora_arm"] < 12.0 and c["faixa_dia_atrd"] < 0.5)


FILTROS = {
    "f1": f1_decisao_a_partir_10h,
    "f2": f2_decisao_a_partir_12h,
    "f3": f3_dia_ja_andou,
    "f4": f4_manha_sem_amplitude,
}
