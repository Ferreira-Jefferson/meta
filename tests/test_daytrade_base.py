"""Contrato compartilhado da familia de day trade (`strategy/daytrade/base.py`).

Cobre `capital_minimo_brl`, que saiu de `lab/gremah.py` em 2026-08-22: a regra
"2x o custo de 1 lote" nao e' de UM robo, vale para qualquer robo intradiario
que opere lote padrao sem fracionario -- e `live/intraday_runtime.py` precisa
consultar a MESMA funcao que a ficha exibe e que dimensionou o capital de todo
backtest da tabela de calibracao (AGENTS.md #6: `live/` aplica regra
declarada, nunca inventa a propria).
"""
from __future__ import annotations

import pytest

from strategy.daytrade.base import (
    CAPITAL_MINIMO_EM_LOTES,
    LOTE_PADRAO_B3,
    capital_minimo_brl,
)


def test_capital_minimo_e_o_dobro_do_custo_de_um_lote():
    """Regra do dono, 2026-08-22, com o exemplo que ele deu: PMAM3 a R$0,14
    -> lote de R$14,00 -> minimo R$28,00."""
    assert capital_minimo_brl(0.14) == pytest.approx(28.0)
    assert capital_minimo_brl(3.64) == pytest.approx(728.0)   # CSAN3
    assert capital_minimo_brl(151.95) == pytest.approx(30_390.0)  # CLSC4


def test_capital_minimo_acompanha_o_preco_sem_arredondar():
    """Substituiu (2026-08-22) a regra de arredondar pra cima ao proximo
    multiplo de R$50, que dava folga absurdamente desigual conforme o preco
    (PMAM3 R$14 -> R$50 era 3,6x o lote; CSAN3 R$364 -> R$400, so 1,1x).
    Agora a proporcao e' a MESMA em qualquer preco, e por isso um centavo a
    mais no preco move o minimo -- e' o comportamento pretendido, ja que o
    piso e' reavaliado a cada pregao."""
    assert capital_minimo_brl(1.00) == pytest.approx(200.0)
    assert capital_minimo_brl(1.01) == pytest.approx(202.0)
    for preco in (0.09, 0.5, 3.66, 5.08, 75.09):
        assert capital_minimo_brl(preco) % 50 != 0 or preco in (0.5,)


def test_capital_minimo_usa_o_lote_que_o_robo_de_fato_negocia():
    """`shares_per_lot` nao e' decoracao: quem chama ao vivo passa
    `config.default_quantity` (a quantidade que o robo realmente manda por
    ordem), para o piso cobrir o que sera' comprado -- nao um lote de
    referencia que nao corresponde a ordem."""
    assert capital_minimo_brl(2.00, shares_per_lot=100) == pytest.approx(400.0)
    assert capital_minimo_brl(2.00, shares_per_lot=200) == pytest.approx(800.0)
    assert capital_minimo_brl(2.00) == capital_minimo_brl(2.00, shares_per_lot=LOTE_PADRAO_B3)


def test_constantes_declaradas_batem_com_a_formula():
    """Se alguem mudar `CAPITAL_MINIMO_EM_LOTES` sem querer, isto pega -- a
    formula e as constantes nao podem divergir em silencio."""
    assert CAPITAL_MINIMO_EM_LOTES == pytest.approx(2.0)
    assert LOTE_PADRAO_B3 == 100
    assert capital_minimo_brl(7.0) == pytest.approx(7.0 * LOTE_PADRAO_B3 * CAPITAL_MINIMO_EM_LOTES)
