"""Testes de `market_data_intraday` — sem terminal MT5 real, mesma tecnica
de `tests/test_live_feed.py` (MetaTrader5 FALSO injetado em `sys.modules`).
"""
from __future__ import annotations

import inspect
import sys
import types
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from core.b3_session import MT5_SERVER_TIMEZONE, server_utc_offset_hours
from market_data_intraday import mt5_source, mt5_ticks_source, storage


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

    mt5_source.fetch_m1_recent("PMAM3", count=200_000)

    assert all(c <= mt5_source.MAX_BARS_PER_REQUEST for c in pedidos)


def test_fetch_m1_recent_devolve_dataframe_indexado_por_tempo(monkeypatch):
    rates = [_rate(1_700_000_000 + i * 60) for i in range(5)]
    mod = _make_fake_mt5_module(rates=rates)
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    df = mt5_source.fetch_m1_recent("PMAM3", count=5)

    assert len(df) == 5
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing


def test_fetch_falha_de_conexao_devolve_dataframe_vazio_e_chama_on_error(monkeypatch):
    mod = _make_fake_mt5_module(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    erros = []
    df = mt5_source.fetch_m1_recent("PMAM3", on_error=lambda k, e: erros.append((k, e)))

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

    df = mt5_source.fetch_m1_full_history("PMAM3")

    assert len(df) == total
    assert df.index.is_monotonic_increasing
    assert not df.index.has_duplicates


def test_fetch_m1_full_history_sem_dado_devolve_vazio(monkeypatch):
    mod = _make_fake_mt5_module(rates=[])
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    df = mt5_source.fetch_m1_full_history("PMAM3")

    assert df.empty


def test_symbol_economics_mapeia_campos(monkeypatch):
    info = types.SimpleNamespace(point=1.0, trade_contract_size=1.0, trade_tick_size=5.0, trade_tick_value=1.0)
    mod = _make_fake_mt5_module(symbol_info=info)
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    econ = mt5_source.symbol_economics("PMAM3")

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


# ---------- fuso do TICK: rota compartilhada vs. `tz_localize("UTC")` cru ----

# Campos NOMEADOS que `copy_ticks_*` devolve (structured array), na mesma
# disciplina de `_RATE_DTYPE` acima: `pd.DataFrame(ticks)` so preserva os
# nomes de coluna se o fake reproduzir o dtype real.
_TICK_DTYPE = np.dtype([
    ("time", "i8"), ("bid", "f8"), ("ask", "f8"), ("last", "f8"),
    ("volume", "u8"), ("time_msc", "i8"), ("flags", "u4"), ("volume_real", "f8"),
])


def _ticks_array(paredes: list[str], preco: float = 5432.5) -> np.ndarray:
    """Ticks cujo `time_msc` e' a hora de PAREDE do servidor -- que e' o que
    o terminal de verdade entrega (ver `core/b3_session.py`)."""
    linhas = []
    for s in paredes:
        msc = int(pd.Timestamp(s).value // 1_000_000)  # naive de proposito
        linhas.append((msc // 1000, 0.0, 0.0, preco, 1, msc, 0, 1.0))
    return np.array(linhas, dtype=_TICK_DTYPE)


def _fake_mt5_ticks(ticks_arr):
    mod = types.ModuleType("MetaTrader5")
    mod.COPY_TICKS_TRADE = 2
    mod.initialize = lambda **kwargs: True
    mod.last_error = lambda: (0, "sem erro")
    mod.symbol_select = lambda symbol, enable=True: True
    mod.copy_ticks_range = lambda symbol, start, end, flags: ticks_arr
    return mod


def test_fetch_ticks_range_converte_parede_do_servidor_para_utc(monkeypatch):
    """`time_msc` e' hora de PAREDE do servidor MT5 (= Brasilia, medido em
    `core/b3_session.py`), NUNCA UTC. Rotular direto com
    `tz_localize("UTC")` -- o atalho que em 2026-09-04 deslocou em 3h todo
    `entry_ts`/`exit_ts` de uma analise de MFE/MAE do WDO F1 e a fez nao
    bater com os fills reais de `db/live.sqlite` -- erra em exatamente
    `server_utc_offset_hours()` horas.

    Este teste compara as DUAS rotas sobre o mesmo tick, para o atalho
    voltar a passar despercebido nunca mais."""
    abertura_parede = "2026-09-04 09:00:00.123"  # abertura do pregao do WDO
    monkeypatch.setitem(sys.modules, "MetaTrader5", _fake_mt5_ticks(_ticks_array([abertura_parede])))

    df = mt5_ticks_source.fetch_ticks_range("WDO@", object(), object())

    cru = pd.Timestamp(abertura_parede).tz_localize("UTC")  # o metodo ERRADO
    esperado = pd.Timestamp(abertura_parede, tz=MT5_SERVER_TIMEZONE).tz_convert("UTC")
    assert len(df) == 1
    assert df.index[0] == esperado
    assert df.index[0] - cru == pd.Timedelta(hours=server_utc_offset_hours())
    assert df.index[0] != cru  # o atalho e' DETECTAVEL, nao um no-op


# ---------- fuso no LIMITE PEDIDO: a paginacao de historico completo --------

def _parede_lida_pelo_terminal(limite) -> pd.Timestamp:
    """O relogio de parede que o terminal MT5 vai ler do limite entregue.

    Reproduz o que o pacote `MetaTrader5` faz: `.timestamp()` no limite, e o
    terminal trata esse epoch como hora de parede do servidor. Num limite
    tz-aware `.timestamp()` NAO consulta o fuso local; num naive, consulta —
    e e' exatamente por isso que um cursor naive deslocava a paginacao.
    Mesma tecnica de `tests/test_live_tick_feed.py`."""
    return pd.Timestamp(datetime.fromtimestamp(limite.timestamp(), timezone.utc)
                        .replace(tzinfo=None))


def _fake_mt5_ticks_paginado(paredes: list[str], capturado: list, teto: int = 20):
    """Fake de `copy_ticks_from` que se comporta como o TERMINAL, nao como o
    pacote: le o limite recebido pelos olhos de `.timestamp()` e devolve os
    proximos `count` negocios a partir dessa PAREDE. E' o unico jeito de um
    teste sem terminal enxergar o deslocamento — olhando o tipo do objeto o
    bug e' invisivel.

    `teto` corta o loop se a paginacao deixar de progredir: o `while True` de
    `fetch_ticks_full_history` nao tem limite proprio, e um teste que trava e'
    pior que um teste que falha."""
    todos = sorted(pd.Timestamp(s) for s in paredes)

    def _copy_ticks_from(symbol, cursor, count, flags):
        capturado.append(cursor)
        if len(capturado) > teto:
            return _ticks_array([])
        parede = _parede_lida_pelo_terminal(cursor)
        janela = [t for t in todos if t >= parede][:count]
        return _ticks_array([str(t) for t in janela])

    mod = types.ModuleType("MetaTrader5")
    mod.COPY_TICKS_TRADE = 2
    mod.initialize = lambda **kwargs: True
    mod.last_error = lambda: (0, "sem erro")
    mod.symbol_select = lambda symbol, enable=True: True
    mod.copy_ticks_from = _copy_ticks_from
    return mod


#: pregao sintetico de 11 negocios, um por minuto, na PAREDE do servidor.
_PREGAO_SINTETICO = [f"2026-09-01 09:{m:02d}:00" for m in range(11)]


def test_paginacao_nao_perde_negocio_na_troca_de_pagina(monkeypatch):
    """REGRESSAO do bug que comeu 63 buracos de 3h do `WDO_A_.parquet`.

    Ate' 2026-09-07 o cursor de paginacao era um `datetime` NAIVE com a
    parede do servidor. O pacote `MetaTrader5` chama `.timestamp()` no
    limite, e `.timestamp()` de um naive e' resolvido no fuso da MAQUINA —
    entao cada troca de pagina pedia a partir de `cursor + 3h` nesta maquina
    (Brasilia), pulando ate' 3h de negocio em CADA borda de pagina, sem
    levantar erro nenhum. Medido no parquet canonico do WDO@: 63 lacunas de
    exatamente 180min, uma a cada ~198.500 linhas.

    O teste pagina de 4 em 4 sobre 11 negocios (3 bordas) e exige os 11 de
    volta. Com o cursor antigo a 2a pagina cairia 3h a frente do pregao
    inteiro, voltaria vazia, e o historico pararia nos 4 primeiros."""
    monkeypatch.setattr(mt5_ticks_source, "MAX_TICKS_PER_REQUEST", 4)
    capturado: list = []
    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        _fake_mt5_ticks_paginado(_PREGAO_SINTETICO, capturado))

    df = mt5_ticks_source.fetch_ticks_full_history("WDO@")

    paredes = df.index.tz_convert(MT5_SERVER_TIMEZONE).strftime("%H:%M:%S").tolist()
    assert paredes == [f"09:{m:02d}:00" for m in range(11)]
    assert len(capturado) >= 3  # de fato houve troca de pagina


def test_cursor_de_paginacao_chega_ao_terminal_na_parede_pedida(monkeypatch):
    """O mesmo bug visto pelo LIMITE em vez de pelo resultado, e sem depender
    do fuso da maquina que roda a suite: o cursor tem de ser tz-aware (e' o
    que torna `.timestamp()` independente da maquina) e o epoch entregue tem
    de valer a parede do ULTIMO negocio da pagina anterior — nao ela mais o
    offset local."""
    monkeypatch.setattr(mt5_ticks_source, "MAX_TICKS_PER_REQUEST", 4)
    capturado: list = []
    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        _fake_mt5_ticks_paginado(_PREGAO_SINTETICO, capturado))

    mt5_ticks_source.fetch_ticks_full_history("WDO@")

    assert all(c.tzinfo is not None for c in capturado)
    # 1a chamada parte do genesis; da 2a em diante, do ultimo tick da pagina
    # anterior (09:03, 09:06, 09:09 — paginas de 4 com 1 tick de sobreposicao).
    assert _parede_lida_pelo_terminal(capturado[0]) == pd.Timestamp("2000-01-01 00:00")
    assert [_parede_lida_pelo_terminal(c) for c in capturado[1:4]] == [
        pd.Timestamp("2026-09-01 09:03"),
        pd.Timestamp("2026-09-01 09:06"),
        pd.Timestamp("2026-09-01 09:09"),
    ]


def test_genesis_e_tz_aware():
    """Aqui o naive era INOFENSIVO (2000-01-01 deslocado 3h continua antes de
    qualquer tick real), mas um naive escapando para a API do MT5 e' o padrao
    que este modulo nao pode mais ter em lugar nenhum — foi um naive
    "inofensivo" ao lado de um naive letal que fez o segundo passar
    despercebido por meses."""
    assert mt5_ticks_source._GENESIS.tzinfo is not None


def test_fetch_ticks_range_offset_explicito_bate_com_a_conversao_pelo_fuso(monkeypatch):
    """`server_utc_offset_hours=None` (o default) converte pelo FUSO; passar
    o escalar do momento tem de dar o mesmo instante hoje. Sao caminhos
    diferentes dentro de `_ticks_to_df`, e a razao de o default ser o fuso e'
    que so ele continua certo se o horario de verao brasileiro voltar."""
    parede = "2026-09-04 15:30:45.500"
    monkeypatch.setitem(sys.modules, "MetaTrader5", _fake_mt5_ticks(_ticks_array([parede])))

    pelo_fuso = mt5_ticks_source.fetch_ticks_range("WDO@", object(), object())
    pelo_escalar = mt5_ticks_source.fetch_ticks_range(
        "WDO@", object(), object(), server_utc_offset_hours=server_utc_offset_hours(),
    )

    assert pelo_fuso.index[0] == pelo_escalar.index[0]


# ---------- storage.merge_m1 --------------------------------------------------

def _df(timestamps, closes):
    idx = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True), name="time")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=idx)


def test_merge_m1_idempotente(tmp_path):
    novo = _df(["2026-01-01 10:00", "2026-01-01 10:01"], [100.0, 101.0])

    merged1, n1 = storage.merge_m1("PMAM3", novo, data_dir=tmp_path)
    merged2, n2 = storage.merge_m1("PMAM3", novo, data_dir=tmp_path)

    assert n1 == 2
    assert n2 == 0  # segunda vez, mesmas barras -> 0 genuinamente novas
    assert len(merged2) == 2
    pd.testing.assert_frame_equal(merged1, merged2)


def test_merge_m1_novo_vence_em_timestamp_sobreposto(tmp_path):
    velho = _df(["2026-01-01 10:00"], [100.0])
    storage.merge_m1("PMAM3", velho, data_dir=tmp_path)

    corrigido = _df(["2026-01-01 10:00"], [999.0])
    merged, n_novos = storage.merge_m1("PMAM3", corrigido, data_dir=tmp_path)

    assert merged.loc[pd.Timestamp("2026-01-01 10:00", tz="UTC"), "close"] == pytest.approx(999.0)
    assert n_novos == 0  # timestamp nao e novo, so foi corrigido


def test_merge_m1_resgata_barra_antiga_ausente_do_fetch_novo(tmp_path):
    """A janela do servidor MT5 rola para frente -- uma barra que a sessao
    anterior salvou e que o fetch de hoje nao consegue mais pedir tem que
    sobreviver ao merge, nunca ser apagada."""
    velho = _df(["2025-12-01 10:00", "2025-12-01 10:01"], [50.0, 51.0])
    storage.merge_m1("PMAM3", velho, data_dir=tmp_path)

    novo_apenas_recente = _df(["2026-08-20 10:00"], [200.0])
    merged, n_novos = storage.merge_m1("PMAM3", novo_apenas_recente, data_dir=tmp_path)

    assert len(merged) == 3
    assert pd.Timestamp("2025-12-01 10:00", tz="UTC") in merged.index
    assert n_novos == 1


def test_load_m1_sem_parquet_devolve_vazio(tmp_path):
    assert storage.load_m1("PMAM3", data_dir=tmp_path).empty


# ---------- "nada novo" vs. "nao consegui ler" (incidente 2026-09-08) -------
#
# 44,8 min de cegueira do terminal ficaram indistinguiveis de um papel parado
# porque `resultado is None or len(resultado) == 0 -> DataFrame()` engolia os
# dois casos no mesmo `return`, sem chamar `on_error`. Os tres testes abaixo
# fixam a fronteira MEDIDA no terminal real (Rico-PRD build 6182, 2026-09-08):
# `None` e vazio-com-`last_error`-negativo sao FALHA; vazio com
# `last_error() == (1, 'Success')` e' o caso NORMAL e nao pode virar alarme.

def _fake_mt5_ticks_com_erro(resultado, last_error):
    mod = types.ModuleType("MetaTrader5")
    mod.COPY_TICKS_TRADE = 2
    mod.initialize = lambda **kwargs: True
    mod.last_error = lambda: last_error
    mod.symbol_select = lambda symbol, enable=True: True
    mod.copy_ticks_range = lambda symbol, start, end, flags: resultado
    return mod


def test_fetch_ticks_range_reporta_quando_o_terminal_devolve_none(monkeypatch):
    """`copy_ticks_range` -> `None` e' o sinal INEQUIVOCO de leitura falhada
    (medido: simbolo inexistente devolve None com last_error (-4, 'Not
    found')). Antes de 2026-09-08 virava DataFrame vazio silencioso."""
    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        _fake_mt5_ticks_com_erro(None, (-4, "Terminal: Not found")))
    erros = []

    df = mt5_ticks_source.fetch_ticks_range(
        "WDO@", object(), object(), on_error=lambda k, e: erros.append((k, str(e))))

    assert df.empty
    assert len(erros) == 1
    assert erros[0][0] == "WDO@"
    assert "copy_ticks_range" in erros[0][1] and "-4" in erros[0][1]


def test_fetch_ticks_range_reporta_vazio_com_last_error_negativo(monkeypatch):
    """Vazio NAO e' prova de mercado parado: se o pacote deixou codigo de erro
    negativo em `last_error()`, a leitura falhou."""
    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        _fake_mt5_ticks_com_erro(_ticks_array([]), (-10000, "Internal fail")))
    erros = []

    df = mt5_ticks_source.fetch_ticks_range(
        "WDO@", object(), object(), on_error=lambda k, e: erros.append((k, str(e))))

    assert df.empty
    assert len(erros) == 1
    assert "-10000" in erros[0][1]


def test_fetch_ticks_range_nao_alarma_com_janela_legitimamente_vazia(monkeypatch):
    """A outra metade da fronteira, e a mais importante: madrugada sem
    negocio devolve array vazio com `last_error() == (1, 'Success')`. Alarmar
    aqui transformaria papel parado em erro e o alarme viraria ruido."""
    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        _fake_mt5_ticks_com_erro(_ticks_array([]), (1, "Success")))
    erros = []

    df = mt5_ticks_source.fetch_ticks_range(
        "WDO@", object(), object(), on_error=lambda k, e: erros.append((k, str(e))))

    assert df.empty
    assert erros == []


def test_fetch_m1_recent_reporta_quando_o_terminal_devolve_none(monkeypatch):
    """Mesma fronteira no caminho M1. Nunca foi visto cegar, mas o `return`
    que engolia era identico -- ver `feedback_audit_all_instances_of_pattern`
    na memoria do projeto."""
    mod = _make_fake_mt5_module(last_error=(-1, "Terminal: fail"))
    mod.copy_rates_from_pos = lambda symbol, timeframe, start_pos, count: None
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)
    erros = []

    df = mt5_source.fetch_m1_recent("WIN@", on_error=lambda k, e: erros.append((k, str(e))))

    assert df.empty
    assert len(erros) == 1
    assert "copy_rates_from_pos" in erros[0][1]
