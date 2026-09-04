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
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
from strategy.daytrade.registry import list_daytrade_robots, symbols_for_robot


# ---------- o robo declara, o ambiente obedece -----------------------------

def test_robo_tick_recebe_feed_de_negocio_a_negocio():
    """`GremahTick` foi eliminada em 2026-09-04 (ver o comentario no topo de
    `strategy/daytrade/registry.py`) -- este teste cobria o mesmo dispatch por
    `feed_kind` (nao por nome de classe), e `WdoGridReloadMaker` (tambem
    `feed_kind = "tick"`) prova a mesma cobertura sem depender da classe
    removida."""
    feed = feed_for(WdoGridReloadMaker())

    assert isinstance(feed, MT5TickFeed)
    assert feed.symbol == "WDO@"


def test_wdo_grid_reload_maker_recebe_feed_de_negocio_a_negocio():
    """REGRESSAO: `feed_kind` desta classe era "m1" (herdado de quando o
    modulo so' tinha a checagem de sanidade em M1) e foi corrigido para
    "tick" em 2026-08-27 -- o numero validado (R$148,89/pregao, 89% de
    retencao OOS) e' o de leitura tick; rodar em M1 reproduziria o numero
    inflado pelo artefato de `_exit_fill_price`, nao o validado."""
    feed = feed_for(WdoGridReloadMaker())

    assert isinstance(feed, MT5TickFeed)
    assert feed.symbol == "WDO@"


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

def test_podio_declarado_2026_09_04():
    """Decisao do dono, 2026-08-27: `wdo_grid_reload_maker` promovido a
    TOP-1 (unico candidato de day trade com confirmacao OOS que sustenta --
    89% de retencao IS->OOS, 30/30 blocos de 4 pregoes positivos).

    Decisao do dono, 2026-08-28: `copa_win` entra como TOP-2 apos
    recalibracao de `alvo_vol`/`stop_vol` confirmada em OOS (o par (19,12)
    MELHOROU fora da amostra, R$54,86 -> R$61,80/pregao).

    Decisao do dono, 2026-09-04: `gremah_tick` ELIMINADA (venceu em 0 de 9
    simbolos contra `gremah` M1, tanto no historico completo quanto no
    protocolo IS/OOS em PMAM3/KLBN3) -- o podio cai de 4 para 3 robos. Ver o
    comentario sobre `_ROBOTS` em `strategy/daytrade/registry.py`."""
    robos = list_daytrade_robots()

    assert [r.key for r in robos] == [
        "wdo_grid_reload_maker", "copa_win", "gremah",
    ]
    assert [r.rank for r in robos] == [1, 2, 3]
    assert [r.feed_kind for r in robos] == ["tick", "m1", "m1"]
    assert [r.is_futuro for r in robos] == [True, True, False]


def test_gremah_cobre_os_nove_simbolos_confirmados():
    """Eram 10 ativos ate' 2026-08-26, quando a CLSC4 saiu do conjunto
    calibrado: ela imprime preco em 18,4 barras M1 por pregao (contra 217-427
    dos outros) e exige R$15.130 de caixa contra R$658-810 deles -- nao havia
    giro que sustentasse um robo maker ali, e ela era negativa em 48 de 48
    celulas de geometria nos dois motores da familia (M1 e tick). A `gremah`
    (motor M1, unico sobrevivente da familia desde 2026-09-04) mede os
    mesmos nove."""
    assert len(symbols_for_robot("gremah")) == 9
