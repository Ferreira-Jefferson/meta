"""Testes de `market_data_intraday` — sem terminal MT5 real, mesma tecnica
de `tests/test_live_feed.py` (MetaTrader5 FALSO injetado em `sys.modules`).
"""
from __future__ import annotations

import inspect
import sys
import types

import numpy as np
import pandas as pd
import pytest

from market_data_intraday import mt5_source, storage


# MT5 devolve um numpy structured array com estes campos NOMEADOS (verificado
# contra o terminal real da Clear, 2026-08-20) -- `pd.DataFrame(rates)` só
# preserva os nomes de coluna se `rates` for este tipo, nao uma lista de
# tuplas simples. O fake precisa reproduzir isso para o teste valer algo.
_RATE_DTYPE = np.dtype([
    ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
    ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8"),
])


def _rate(t: int, o=100.0, h=101.0, l=99.0, c=100.5, tick_volume=10, spread=1, real_volume=0):
    return (t, o, h, l, c, tick_volume, spread, real_volume)


def _rates_array(rows: list[tuple]) -> np.ndarray:
    return np.array(rows, dtype=_RATE_DTYPE)


def _make_fake_mt5_module(*, initialize_ok=True, rates=None, symbol_info=None, last_error=(0, "sem erro")):
    """Fake minimo, so a superficie usada por `mt5_source.py`."""
    rates_arr = _rates_array(rates if rates is not None else [])
    mod = types.ModuleType("MetaTrader5")
    mod.TIMEFRAME_M1 = 1
    mod.initialize = lambda **kwargs: initialize_ok
    mod.last_error = lambda: last_error
    mod.symbol_select = lambda symbol, enable=True: True
    mod.copy_rates_range = lambda symbol, timeframe, start, end: rates_arr
    mod.copy_rates_from_pos = lambda symbol, timeframe, start_pos, count: (
        rates_arr[start_pos:start_pos + count] if start_pos < len(rates_arr) else _rates_array([])
    )
    mod.symbol_info = lambda symbol: symbol_info
    return mod


# ---------- fetch_m1_recent / fetch_m1_range ---------------------------------

def test_fetch_m1_recent_nunca_pede_mais_que_o_maximo(monkeypatch):
    """Regressao do off-by-one medido contra o terminal real da Clear:
    pedir exatamente 100000 barras falha com 'Invalid params'; o modulo
    nunca deve pedir mais que `MAX_BARS_PER_REQUEST` (99999)."""
    pedidos = []
    rates = [_rate(i) for i in range(10)]
    mod = _make_fake_mt5_module(rates=rates)
    original = mod.copy_rates_from_pos

    def _spy(symbol, timeframe, start_pos, count):
        pedidos.append(count)
        return original(symbol, timeframe, start_pos, count)

    mod.copy_rates_from_pos = _spy
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    mt5_source.fetch_m1_recent("WIN@", count=200_000)

    assert all(c <= mt5_source.MAX_BARS_PER_REQUEST for c in pedidos)


def test_fetch_m1_recent_devolve_dataframe_indexado_por_tempo(monkeypatch):
    rates = [_rate(1_700_000_000 + i * 60) for i in range(5)]
    mod = _make_fake_mt5_module(rates=rates)
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    df = mt5_source.fetch_m1_recent("WIN@", count=5)

    assert len(df) == 5
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing


def test_fetch_falha_de_conexao_devolve_dataframe_vazio_e_chama_on_error(monkeypatch):
    mod = _make_fake_mt5_module(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    erros = []
    df = mt5_source.fetch_m1_recent("WIN@", on_error=lambda k, e: erros.append((k, e)))

    assert df.empty
    assert len(erros) == 1
    assert "10004" in str(erros[0][1])


def test_fetch_m1_full_history_pagina_ate_lote_menor_que_o_maximo(monkeypatch):
    """Simula profundidade REAL maior que um unico pedido de 99999 barras --
    a paginacao deve percorrer 2 paginas e nao parar na primeira."""
    total = mt5_source.MAX_BARS_PER_REQUEST + 5
    rates = [_rate(1_700_000_000 + i * 60) for i in range(total)]
    mod = _make_fake_mt5_module(rates=rates)
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    df = mt5_source.fetch_m1_full_history("WIN@")

    assert len(df) == total
    assert df.index.is_monotonic_increasing
    assert not df.index.has_duplicates


def test_fetch_m1_full_history_sem_dado_devolve_vazio(monkeypatch):
    mod = _make_fake_mt5_module(rates=[])
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    df = mt5_source.fetch_m1_full_history("WIN@")

    assert df.empty


def test_symbol_economics_mapeia_campos(monkeypatch):
    info = types.SimpleNamespace(point=1.0, trade_contract_size=1.0, trade_tick_size=5.0, trade_tick_value=1.0)
    mod = _make_fake_mt5_module(symbol_info=info)
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    econ = mt5_source.symbol_economics("WIN@")

    assert econ is not None
    assert econ.trade_tick_size == pytest.approx(5.0)
    assert econ.trade_tick_value == pytest.approx(1.0)


def test_symbol_economics_simbolo_inexistente_devolve_none(monkeypatch):
    mod = _make_fake_mt5_module(symbol_info=None)
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    assert mt5_source.symbol_economics("NAOEXISTE") is None


def test_mt5_source_nao_importa_metatrader5_no_topo_do_modulo():
    source = inspect.getsource(mt5_source)
    for line in source.splitlines():
        if line.startswith("import MetaTrader5") or line.startswith("from MetaTrader5"):
            pytest.fail(f"import de MetaTrader5 fora de metodo (coluna 0): {line!r}")


# ---------- storage.merge_m1 --------------------------------------------------

def _df(timestamps, closes):
    idx = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True), name="time")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=idx)


def test_merge_m1_idempotente(tmp_path):
    novo = _df(["2026-01-01 10:00", "2026-01-01 10:01"], [100.0, 101.0])

    merged1, n1 = storage.merge_m1("WIN@", novo, data_dir=tmp_path)
    merged2, n2 = storage.merge_m1("WIN@", novo, data_dir=tmp_path)

    assert n1 == 2
    assert n2 == 0  # segunda vez, mesmas barras -> 0 genuinamente novas
    assert len(merged2) == 2
    pd.testing.assert_frame_equal(merged1, merged2)


def test_merge_m1_novo_vence_em_timestamp_sobreposto(tmp_path):
    velho = _df(["2026-01-01 10:00"], [100.0])
    storage.merge_m1("WIN@", velho, data_dir=tmp_path)

    corrigido = _df(["2026-01-01 10:00"], [999.0])
    merged, n_novos = storage.merge_m1("WIN@", corrigido, data_dir=tmp_path)

    assert merged.loc[pd.Timestamp("2026-01-01 10:00", tz="UTC"), "close"] == pytest.approx(999.0)
    assert n_novos == 0  # timestamp nao e novo, so foi corrigido


def test_merge_m1_resgata_barra_antiga_ausente_do_fetch_novo(tmp_path):
    """A janela do servidor MT5 rola para frente -- uma barra que a sessao
    anterior salvou e que o fetch de hoje nao consegue mais pedir tem que
    sobreviver ao merge, nunca ser apagada."""
    velho = _df(["2025-12-01 10:00", "2025-12-01 10:01"], [50.0, 51.0])
    storage.merge_m1("WIN@", velho, data_dir=tmp_path)

    novo_apenas_recente = _df(["2026-08-20 10:00"], [200.0])
    merged, n_novos = storage.merge_m1("WIN@", novo_apenas_recente, data_dir=tmp_path)

    assert len(merged) == 3
    assert pd.Timestamp("2025-12-01 10:00", tz="UTC") in merged.index
    assert n_novos == 1


def test_load_m1_sem_parquet_devolve_vazio(tmp_path):
    assert storage.load_m1("WIN@", data_dir=tmp_path).empty
