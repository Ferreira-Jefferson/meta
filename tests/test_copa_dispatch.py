"""`Copa` — o despachante por ativo.

Decisao do dono (2026-08-24): o robo tem de entender QUAL ativo foi
selecionado e usar a melhor estrategia para aquele ativo. Estes testes
travam as duas metades disso: cada simbolo cai na classe certa, e simbolo
sem estrategia propria LEVANTA em vez de herdar a de outro ativo.
"""
from __future__ import annotations

import pytest

from strategy.daytrade.base import IntradayStrategy
from strategy.daytrade.lab.copa import Copa
from strategy.daytrade.lab.copa_wdo import CopaWdo
from strategy.daytrade.lab.copa_win import CopaWin


def test_cada_simbolo_cai_na_classe_certa():
    assert isinstance(Copa(symbol="WIN@", teto_contratos=12), CopaWin)
    assert isinstance(Copa(symbol="WDO@", teto_contratos=4), CopaWdo)


def test_simbolo_sem_estrategia_propria_levanta():
    """Mesma postura de `Gremah`/`GremahTick` com simbolo sem calibracao: a
    estrategia NAO transfere entre ativos, porque a economia de cada
    instrumento e' outra (R$0,50 de round-trip e' meio tick no WIN e um
    decimo de tick no WDO)."""
    with pytest.raises(ValueError) as erro:
        Copa(symbol="BIT@", teto_contratos=25)
    assert "BIT@" in str(erro.value)
    assert "WIN@" in str(erro.value)     # a mensagem diz o que existe


def test_todo_robo_da_familia_e_uma_IntradayStrategy():
    for symbol, teto in (("WIN@", 12), ("WDO@", 4)):
        assert isinstance(Copa(symbol=symbol, teto_contratos=teto), IntradayStrategy)


def test_simbolos_lista_os_ativos_com_estrategia_propria():
    assert Copa.simbolos() == ("WIN@", "WDO@")


# ---------- o teto e' ENTRADA, nunca constante ------------------------------

@pytest.mark.parametrize("symbol,teto", [("WIN@", 4), ("WIN@", 12), ("WIN@", 15),
                                         ("WIN@", 20), ("WDO@", 2), ("WDO@", 5),
                                         ("WDO@", 8)])
def test_o_teto_viaja_intacto_para_o_robo_escolhido(symbol, teto):
    assert Copa(symbol=symbol, teto_contratos=teto).teto_contratos == teto


def test_a_exposicao_escala_com_o_teto_sem_alterar_codigo():
    """O portao G6 do plano (P&L no teto oficial >= P&L no teto de teste) so'
    faz sentido se o robo DIMENSIONA pelo teto. Os numeros de 2025 (WIN 15 /
    WDO 5) podem mudar antes de 14/09/2026."""
    expostos = [Copa(symbol="WIN@", teto_contratos=t, fracao_entrada=0.5)
                .quantidade_por_entrada for t in (4, 12, 15, 20)]
    assert expostos == [2, 6, 8, 10]

    expostos_wdo = [Copa(symbol="WDO@", teto_contratos=t, fracao_entrada=1.0)
                    .quantidade_por_rodada for t in (2, 4, 5, 8)]
    assert expostos_wdo == [2, 4, 5, 8]


def test_parametros_da_varredura_passam_adiante_para_o_construtor():
    """E' assim que a grade de parametros funciona sem precisar saber qual
    classe esta do outro lado."""
    win = Copa(symbol="WIN@", teto_contratos=12, alvo_vol=3.5, janela_rompimento=42)
    assert win.alvo_vol == 3.5 and win.janela_rompimento == 42

    wdo = Copa(symbol="WDO@", teto_contratos=4, alvo_ticks=1.0, pecas=4)
    assert wdo.alvo_ticks == 1.0 and wdo.pecas == 4


def test_parametro_inexistente_levanta_em_vez_de_ser_ignorado():
    """Uma grade com nome de parametro errado seria uma varredura inteira
    rodando o default sem ninguem perceber."""
    with pytest.raises(TypeError):
        Copa(symbol="WIN@", teto_contratos=12, parametro_que_nao_existe=1)


# ---------- a familia fica FORA do podio de day trade -----------------------

def test_copa_nao_entra_no_registry_de_day_trade():
    """Outro instrumento, outra metrica: um robo de mini-futuro medido em R$
    liquido com capital NOCIONAL nao e' comparavel a um robo de acao medido em
    retorno sobre caixa real. Misturar os dois no mesmo podio seria a
    comparacao desonesta que este projeto evita."""
    from strategy.daytrade.registry import list_daytrade_robots

    chaves = {r.key for r in list_daytrade_robots()}
    assert "copa_win" not in chaves and "copa_wdo" not in chaves
