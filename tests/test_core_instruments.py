"""`core.instruments` e' a FONTE DA VERDADE da economia de um instrumento --
valor do ponto, passo de preco e margem por contrato.

Ela subiu para `core/` em 2026-09-09 porque duas features precisavam dos
MESMOS numeros e nao podiam se importar (AGENTS.md, regra 1): o perfil
economico (`backtest.intraday.profiles`) e o catalogo de robos
(`strategy.daytrade.registry`). Ate entao o registry REDIGITAVA WDO@
10,0/150,0 e WIN@ 0,20/100,0, e o que impedia a divergencia era um teste de
amarracao -- rede, nao conserto.

Os testes deste arquivo cobrem a fonte. A amarracao dos consumidores nela
mora em `tests/test_intraday_profiles.py`.
"""
from __future__ import annotations

import pytest

from core.instruments import (
    ACAO_B3_POINT_VALUE_BRL,
    ACAO_B3_PRICE_TICK_SIZE,
    FUTUROS,
    InstrumentEconomics,
    economics_for,
)


def test_economia_declarada_dos_dois_minis_da_b3():
    """Os numeros que a operacao real usa hoje. Mudar qualquer um destes
    muda P&L, dimensionamento e grade de ordem ao mesmo tempo -- entao eles
    ficam escritos tambem aqui, fora do modulo, para a troca ser
    deliberada."""
    win = economics_for("WIN@")
    assert win.point_value_brl == pytest.approx(0.20)
    assert win.price_tick_size == pytest.approx(5.0)
    assert win.margin_per_contract_brl == pytest.approx(100.0)

    wdo = economics_for("WDO@")
    assert wdo.point_value_brl == pytest.approx(10.0)
    assert wdo.price_tick_size == pytest.approx(0.5)
    assert wdo.margin_per_contract_brl == pytest.approx(150.0)


def test_valor_do_tick_e_derivado_nunca_declarado():
    """Tres numeros -- ponto, tick e valor do tick -- so' que dois deles
    determinam o terceiro. Declarar os tres deixaria dois livres para
    contradizer o outro, que e' a doenca que esta tabela cura."""
    assert economics_for("WDO@").tick_value_brl == pytest.approx(5.0)
    assert economics_for("WIN@").tick_value_brl == pytest.approx(1.0)


@pytest.mark.parametrize(
    "campo", ["point_value_brl", "price_tick_size", "margin_per_contract_brl"]
)
@pytest.mark.parametrize("invalido", [None, 0.0, -1.0])
def test_economia_incompleta_e_recusada_na_fonte(campo, invalido):
    """Os tres campos ja custaram incidente (itens 5.7/5.19 e o de
    2026-08-28, que zerou a conta). O guard mora AQUI, na fonte, e nao em
    cada consumidor: um instrumento novo declarado pela metade nao chega a
    virar perfil nem kwargs de robo."""
    validos = dict(symbol="XXX@", point_value_brl=10.0, price_tick_size=0.5,
                   margin_per_contract_brl=150.0)
    validos[campo] = invalido
    with pytest.raises(ValueError, match=campo):
        InstrumentEconomics(**validos)


def test_instrumento_desconhecido_levanta_em_vez_de_chutar():
    """Assumir a economia de outro contrato e' o erro de 10x que esta tabela
    existe para impedir -- entao nao ha default silencioso."""
    with pytest.raises(KeyError, match="ZZZ@"):
        economics_for("ZZZ@")


def test_acao_nao_entra_na_tabela_de_futuros():
    """Toda acao da B3 em lote padrao tem a MESMA economia (1 ponto =
    R$1,00, passo de R$0,01, sem margem por contrato) -- uma linha por papel
    seria dez linhas identicas, e a primeira que alguem editasse sozinha
    viraria a divergencia de sempre."""
    assert ACAO_B3_POINT_VALUE_BRL == 1.0
    assert ACAO_B3_PRICE_TICK_SIZE == 0.01
    with pytest.raises(KeyError):
        economics_for("PMAM3")


def test_toda_entrada_da_tabela_esta_completa_e_se_identifica():
    """Vale para o que vier depois, nao so' para WIN@/WDO@: a chave do
    dicionario e o `symbol` da entrada tem de ser a mesma coisa, senao a
    mensagem de erro de `config_for` (que usa o `symbol`) apontaria o
    operador para um instrumento diferente do que ele pediu."""
    assert FUTUROS, "premissa: ha instrumento declarado"
    for chave, econ in FUTUROS.items():
        assert econ.symbol == chave, f"{chave}: entrada se identifica como {econ.symbol!r}"
        assert econ.point_value_brl > 0 and econ.price_tick_size > 0
        assert econ.margin_per_contract_brl > 0


def test_core_nao_importa_nada_do_projeto():
    """Regra de camada (AGENTS.md): `core/` nao importa feature nenhuma. Se
    esta tabela importasse `backtest`/`strategy` para "conferir", ela
    deixaria de poder ser a fonte dos dois."""
    import inspect

    from core import instruments

    fonte = inspect.getsource(instruments)
    for proibido in ("import backtest", "import strategy", "import market_data",
                     "import journal", "import live", "import dashboard"):
        assert proibido not in fonte, f"core.instruments importa feature: {proibido!r}"
