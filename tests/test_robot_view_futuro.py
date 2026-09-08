"""Testes do ROBÔ DE FUTURO na ficha de day trade (`dashboard/robot_view.py`).

Nasceram junto com a promoção da `wdo_grid_reload_maker` a TOP-1 do pódio
(2026-08-27, ver `strategy/daytrade/registry.py`): até então nenhum robô de
FUTURO (WIN@/WDO@) tinha passado pela ficha do painel, que nasceu inteira
para ação (lote de 100, `capital_minimo_brl = preço x 100 x 2`). Sem os
ajustes cobertos aqui, o form de "novo robô" em `/operacao` mostraria um
caixa mínimo de ~R$1 milhão para 1 contrato de WDO@ (a fórmula de lote de
ação aplicada a um preço de futuro).
"""
from __future__ import annotations

import pytest

from dashboard.robot_view import _asset, _daytrade_assets, _preco_key, capital_minimo_para
from strategy.daytrade.lab.gremah import Gremah
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker


# ---------- capital_minimo_para: margem (futuro) x lote (ação) ------------

def test_capital_minimo_para_acao_e_igual_ao_de_sempre():
    from strategy.daytrade.base import capital_minimo_brl

    assert capital_minimo_para(False, "PMAM3", 0.14) == capital_minimo_brl(0.14)


def test_capital_minimo_para_acao_sem_preco_e_none():
    assert capital_minimo_para(False, "PMAM3", None) is None


def test_capital_minimo_para_futuro_usa_margem_do_perfil_nao_o_preco():
    """WDO@: margem R$150 x MARGIN_BUFFER_FUTUROS (2.0) x
    RESERVA_CAIXA_SEGURANCA (1.25) = R$375 -- e não muda com o preço
    passado, diferente do caminho de ação.

    Era R$300 até 2026-08-28, e esse número mentia: o dimensionamento de
    entrada real usa `contracts_from_capital_com_reserva`, então o robô
    subia no painel com R$300 e tinha TODA ordem recusada por
    `capital_insuficiente`, em silêncio, para sempre. Portão que libera o
    que a camada seguinte recusa é pior que portão nenhum."""
    assert capital_minimo_para(True, "WDO@", 5079.0) == 375.0
    assert capital_minimo_para(True, "WDO@", None) == 375.0
    assert capital_minimo_para(True, "WIN@", 141_000.0) == 250.0


def test_capital_minimo_para_futuro_sem_margem_declarada_e_none(monkeypatch):
    """Perfil de futuro sem `margin_per_contract_brl` (nunca medido ainda)
    mostra a FALTA, nunca inventa um número -- mesmo espírito do `None` de
    ação sem preço salvo."""
    from backtest.intraday import profiles

    class _PerfilSemMargem:
        margin_per_contract_brl = None

    monkeypatch.setattr(profiles, "profile_for", lambda symbol: _PerfilSemMargem())

    assert capital_minimo_para(True, "XYZ@", 1.0) is None


# ---------- _preco_key: caminho sanitizado (regressão) ---------------------

def test_preco_key_de_futuro_usa_o_mesmo_caminho_sanitizado_do_storage():
    """REGRESSAO: antes desta correção, `_preco_key` reconstruía o caminho
    sem sanitizar `@`/`$` -- para `WDO@` isso aponta pra um arquivo que
    nunca existe (`WDO@.parquet` != `WDO_A_.parquet`), `caminho.stat()`
    sempre caía no `except`, e o cache de preço ficava travado em
    `(symbol, 0.0, 0)` para sempre, mesmo com o parquet real presente e
    atualizado."""
    from market_data_intraday.storage import _parquet_path

    symbol, mtime, size = _preco_key("WDO@")

    assert symbol == "WDO@"
    if _parquet_path("WDO@").exists():
        assert mtime > 0.0 and size > 0
    else:
        pytest.skip("data/raw_intraday/WDO_A_.parquet ausente neste ambiente")


# ---------- _daytrade_assets: robô de futuro mostra ticks, não % ----------

def test_daytrade_assets_de_futuro_marca_is_futuro_e_ticks():
    robo = WdoGridReloadMaker()
    (ativo,) = _daytrade_assets(WdoGridReloadMaker, robo)

    assert ativo.symbol == "WDO@"
    assert ativo.is_futuro is True
    assert ativo.profit_ticks == 2
    assert ativo.stop_ticks == 16
    # margem-based, presente mesmo sem preço de minuto salvo. R$375 = margem
    # x buffer x reserva de caixa -- ver
    # `test_capital_minimo_para_futuro_usa_margem_do_perfil_nao_o_preco`.
    assert ativo.min_capital == 375.0
    # não existe "lote" de contrato -- diferente de ação, nunca inventado
    assert ativo.lot_cost is None


def test_daytrade_assets_de_acao_nao_e_afetado_pela_mudanca():
    """REGRESSAO: nenhum campo novo muda o caminho de ação (Gremah)."""
    robo = Gremah()
    ativos = _daytrade_assets(Gremah, robo)

    assert all(a.is_futuro is False for a in ativos)
    assert all(a.profit_ticks is None and a.stop_ticks is None for a in ativos)


def test_asset_futuro_nao_mostra_profit_pct_fabricado():
    """`profit_pct`/`stop_multiplier` chegam 0.0 (default de `getattr`) para
    um robô de futuro -- o campo `is_futuro` existe exatamente para o
    template nunca confundir esse 0.0 com um alvo real de 0%."""
    a = _asset("WDO@", 0.0, 0.0, False, None, None, None, "", is_futuro=True,
               profit_ticks=1, stop_ticks=16)

    assert a.is_futuro is True
    assert a.profit_pct == 0.0  # presente, mas o template não lê isto p/ futuro
    assert a.profit_ticks == 1
