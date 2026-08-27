"""Testes de `live/intraday_feed.py::feed_for` e do PODIO de day trade.

O que esta em jogo: a granularidade do dado e' propriedade do ROBO, nao
escolha de quem monta o ambiente. Os dois chamadores que sobem um robo de day
trade (`scripts/run_live.py::build_intraday` e
`dashboard/live_service.py::_build_intraday_runtime`) tem de chegar no MESMO
feed para o mesmo robo — foi passando um parametro parecido a mao, por
chamador, que o robo ao vivo ja' acabou com modelo de custo diferente do robo
validado (ver `IntradayStrategy.target_fills_as_maker`).
"""
from __future__ import annotations

import pytest

from live.bar_feed import MT5BarFeed
from live.intraday_feed import feed_for
from live.tick_feed import MT5TickFeed
from strategy.daytrade.lab.gremah import Gremah
from strategy.daytrade.lab.gremah_tick import GremahTick
from strategy.daytrade.registry import list_daytrade_robots, symbols_for_robot


# ---------- o robo declara, o ambiente obedece -----------------------------

def test_gremah_tick_recebe_feed_de_negocio_a_negocio():
    feed = feed_for(GremahTick())

    assert isinstance(feed, MT5TickFeed)
    assert feed.symbol == "PMAM3"


def test_gremah_recebe_feed_de_barra_m1():
    feed = feed_for(Gremah())

    assert isinstance(feed, MT5BarFeed)


def test_feed_kind_desconhecido_falha_alto_em_vez_de_cair_no_m1():
    """Sem default silencioso: um robo cujos parametros de tempo foram medidos
    numa granularidade, rodando na outra, e' um robo DIFERENTE do validado — e
    o erro nao apareceria em lugar nenhum ate o extrato."""
    class _RoboTorto(Gremah):
        name = "robo_torto"
        feed_kind = "m5"

    with pytest.raises(ValueError, match="feed_kind"):
        feed_for(_RoboTorto())


def test_os_dois_montadores_de_runtime_usam_a_mesma_fabrica():
    """REGRESSAO: enquanto cada chamador instanciava `MT5BarFeed` direto, um
    robo novo de outra granularidade entraria em producao lendo M1 num dos dois
    caminhos e tick no outro, sem ninguem notar."""
    import inspect

    from dashboard import live_service
    import scripts.run_live as run_live

    for fonte in (inspect.getsource(live_service._build_intraday_runtime),
                  inspect.getsource(run_live.build_intraday)):
        assert "feed_for(" in fonte
        assert "MT5BarFeed(" not in fonte
        assert "MT5TickFeed(" not in fonte


# ---------- o podio declarado ----------------------------------------------

def test_gremah_tick_e_o_top1_e_gremah_o_top2():
    """Decisao do dono, 2026-08-22. A ordem do registry E' o podio — ver o
    comentario sobre `_ROBOTS` em `strategy/daytrade/registry.py` para por que
    ela e' declarada e nao calculada."""
    robos = list_daytrade_robots()

    assert [r.key for r in robos] == ["gremah_tick", "gremah"]
    assert [r.rank for r in robos] == [1, 2]
    assert [r.feed_kind for r in robos] == ["tick", "m1"]


def test_o_painel_so_oferece_ativo_medido_em_tick():
    """O painel so' oferece ativo com medicao propria em tick.

    Eram 10 ate' 2026-08-26, quando a CLSC4 saiu do conjunto calibrado: ela
    imprime preco em 18,4 barras M1 por pregao (contra 217-427 dos outros) e
    exige R$15.130 de caixa contra R$658-810 deles -- nao havia giro que
    sustentasse um robo maker ali, e ela era negativa em 48 de 48 celulas de
    geometria nos dois motores. Ver `gremah_tick.py`, acima de
    `TICK_CONFIRMED_SYMBOLS`."""
    assert symbols_for_robot("gremah_tick") == (
        "PMAM3", "BMGB4", "KLBN3", "LPSB3", "DASA3", "KLBN4", "PCAR3", "CSAN3",
        "GRND3",
    )
    # A `gremah` acompanha: sao os mesmos nove, medidos em M1.
    assert len(symbols_for_robot("gremah")) == 9
