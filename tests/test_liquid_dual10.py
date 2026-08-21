"""Estrutura do `liquid_dual10` -- 10 sleeves, duas faixas de liquidez, sinal congelado.

So testes de ESTRUTURA (rapidos, sem rodar backtest): a composicao das duas
faixas, que o sinal permanece identico ao campeao (o que garante que nada
alem do universo mudou) e que `sleeve_count`/`rank_offset` nao podem ser
sobrescritos -- sao fixos neste desenho (ver docstring de `liquid_dual10.py`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_dual10 import LiquidDual10
from strategy.liquid_sleeve import LiquidSleeve


# ------------------------------------------------------------- composicao


def test_dual10_tem_dez_sleeves():
    bot = LiquidDual10()
    assert bot.sleeve_count == 10
    assert len(bot._sleeves) == 10
    assert all(isinstance(s, LiquidSleeve) for s in bot._sleeves)


def test_cinco_primeiros_sleeves_no_top20_cinco_ultimos_na_faixa_21_40():
    bot = LiquidDual10()
    offsets = [s.rank_offset for s in bot._sleeves]
    assert offsets[:5] == [0, 0, 0, 0, 0]
    assert offsets[5:] == [20, 20, 20, 20, 20]


def test_cada_faixa_e_fatiada_por_rodizio_i_de_5_dentro_dela():
    """NAO e [i::10] sobre 40 nomes -- cada faixa tem seu proprio 0..4."""
    bot = LiquidDual10()
    top20, faixa2140 = bot._sleeves[:5], bot._sleeves[5:]
    assert [s.sleeve_index for s in top20] == [0, 1, 2, 3, 4]
    assert [s.sleeve_index for s in faixa2140] == [0, 1, 2, 3, 4]
    assert all(s.sleeve_count == 5 for s in bot._sleeves), (
        "sleeve_count de cada sleeve individual tem de ser 5 (fatia dentro da "
        "faixa), mesmo com bot.sleeve_count == 10")


def test_rank_offset_da_segunda_faixa_acompanha_universe_n():
    """offset da 2a faixa e o universe_n, nao um 20 fixo -- generaliza a faixa seguinte."""
    bot = LiquidDual10(universe_n=10)
    offsets = [s.rank_offset for s in bot._sleeves]
    assert offsets[:5] == [0, 0, 0, 0, 0]
    assert offsets[5:] == [10, 10, 10, 10, 10]
    assert all(s.universe_n == 10 for s in bot._sleeves)


# ------------------------------------------------------------------ sinal


def test_sinal_dos_dez_sleeves_e_identico_ao_campeao():
    """Sinal congelado: dip_pct/high_window/lookback nao podem divergir do campeao.

    E o que garante que a peca nova e SO universo (top-20 + faixa 21-40), nunca
    um grau de liberdade novo de sinal escondido dentro dos sleeves.
    """
    referencia = LiquidChampion()
    bot = LiquidDual10()
    for attr in ("dip_pct", "high_window", "lookback"):
        assert getattr(bot, attr) == getattr(referencia, attr), attr
        for s in bot._sleeves:
            assert getattr(s, attr) == getattr(referencia, attr), attr


def test_universo_de_cada_sleeve_bate_com_os_parametros_do_campeao():
    bot = LiquidDual10()
    for s in bot._sleeves:
        assert s.liquidity_window == 252
        assert s.refresh_months == 12
        assert s.min_history_days == 504
        assert s.evict_on_refresh is False


# --------------------------------------------------------- parametros fixos


@pytest.mark.parametrize("kw", [{"sleeve_count": 4}, {"rank_offset": 5}])
def test_override_de_sleeve_count_ou_rank_offset_levanta_typeerror(kw):
    with pytest.raises(TypeError):
        LiquidDual10(**kw)


# ------------------------------------------------------------------- estado


def test_state_devolve_dez_itens_de_sleeve_pending():
    bot = LiquidDual10()
    st = bot.state()
    assert len(st["_sleeve_pending"]) == 10


def test_restore_volta_com_os_dez_sleeves_marcados():
    bot = LiquidDual10()
    bot._sleeves[3]._pending_rebalance = True
    bot._sleeves[7]._pending_rebalance = True

    outro = LiquidDual10()
    outro.restore(bot.state())

    marcados = [s._pending_rebalance for s in outro._sleeves]
    assert marcados == [False, False, False, True, False, False, False, True, False, False]


# -------------------------------------------------------------- candidatura


def test_dual10_e_candidato():
    """Promovido em 2026-08-20 -- ver docstring de LiquidDual10."""
    assert LiquidDual10.candidate is True
    assert LiquidDual10().candidate is True


# ------------------------------------------------- teto de posicoes do engine


def test_teto_de_cinco_posicoes_e_parte_do_desenho_do_dual10():
    """10 sleeves disputam 5 vagas -- e isso NAO e acidente, e o desenho medido.

    `max_concurrent_positions` e um teto do ENGINE (`backtest/sizing.py::
    has_free_slot`, o mesmo que `live/runtime.py` aplica), nao da estrategia.
    O campeao tem 5 sleeves e nunca encosta nele; o dual10 tem 10 e encosta
    sempre. Consequencia medida no holdout de 48 janelas: exposicao media de
    43,9% (contra 76,3% do campeao), porque cada sleeve dimensiona 1/10 do
    caixa e so 5 entradas cabem -- ~50% do patrimonio fica em caixa por
    construcao. Parte relevante do MaxDD de -17,0% (contra -34,4% do campeao)
    vem dai.

    Soltar o teto para 10 da um robo DIFERENTE e pior no que importa: capital
    final maior (R$ 6.067 contra R$ 5.412 na janela FULL) mas MaxDD de -28,1%
    contra -16,9%. Ou seja, mudar este default nao "conserta" o dual10 --
    troca o robo aprovado por outro que nunca passou pelo holdout.

    Este teste existe para que essa troca nunca aconteca em silencio.
    """
    assert BacktestConfig().max_concurrent_positions == 5, (
        "O default de max_concurrent_positions mudou. O liquid_dual10 foi "
        "medido e promovido com teto 5 e 10 sleeves; com outro teto ele vira "
        "outro robo. Re-rodar scripts/run_dual10_holdout.py antes de aceitar."
    )
    assert LiquidDual10().sleeve_count == 10
    assert LiquidChampion().sleeve_count == 5, (
        "O campeao precisa continuar com 5 sleeves para o teto NAO apertar "
        "nele -- e o que torna a comparacao dual10 x campeao interpretavel."
    )
