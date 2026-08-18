"""Testes da camada de cotacao (`live/feed.py`) — sem rede.

Foco: `ParquetCloseFeed` declara o proprio atraso como a idade real do dado
(nao um numero fixo), `ReplayFeed` serve de dublê determinístico para teste, e
`staleness_report` so aponta quem passou do limite. `YFinanceFeed` e testado
sem tocar rede: so o contrato de atraso declarado e o lazy-import.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from live.feed import ParquetCloseFeed, QuoteFeed, ReplayFeed, YFinanceFeed, staleness_report
from core.live_models import Quote


def _save_panel(path: Path, ticker: str, last_close: float, last_date: str) -> None:
    idx = pd.DatetimeIndex([pd.Timestamp("2026-08-10"), pd.Timestamp(last_date)], name="date")
    df = pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [10.5, 11.5],
            "low": [9.5, 10.5],
            "close": [10.2, last_close],
            "volume": [1000, 2000],
        },
        index=idx,
    )
    safe = ticker.replace("^", "_").replace(".", "_")
    df.to_parquet(path / f"{safe}.parquet")


def test_parquet_close_feed_le_ultimo_close(tmp_path):
    _save_panel(tmp_path, "TEST3.SA", last_close=42.0, last_date="2026-08-14")
    now = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)
    feed = ParquetCloseFeed(data_dir=tmp_path, now_fn=lambda: now)

    quotes = feed.quotes(["TEST3.SA"])

    assert quotes["TEST3.SA"].price == pytest.approx(42.0)
    assert quotes["TEST3.SA"].source == "parquet"


def test_parquet_close_feed_delay_cresce_com_a_idade(tmp_path):
    _save_panel(tmp_path, "TEST3.SA", last_close=42.0, last_date="2026-08-14")

    now_perto = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)
    feed_perto = ParquetCloseFeed(data_dir=tmp_path, now_fn=lambda: now_perto)
    feed_perto.quotes(["TEST3.SA"])
    delay_perto = feed_perto.delay_seconds

    now_longe = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
    feed_longe = ParquetCloseFeed(data_dir=tmp_path, now_fn=lambda: now_longe)
    feed_longe.quotes(["TEST3.SA"])
    delay_longe = feed_longe.delay_seconds

    assert delay_longe > delay_perto
    # dado de ontem (barra em 2026-08-14 00:00) => ~1 dia de atraso declarado
    now_ontem = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
    feed_ontem = ParquetCloseFeed(data_dir=tmp_path, now_fn=lambda: now_ontem)
    feed_ontem.quotes(["TEST3.SA"])
    assert feed_ontem.delay_seconds == pytest.approx(86400.0, rel=0.01)


def test_parquet_close_feed_ticker_inexistente_fica_ausente(tmp_path):
    _save_panel(tmp_path, "TEST3.SA", last_close=42.0, last_date="2026-08-14")
    feed = ParquetCloseFeed(data_dir=tmp_path)

    quotes = feed.quotes(["TEST3.SA", "NAOEXISTE3.SA"])

    assert "TEST3.SA" in quotes
    assert "NAOEXISTE3.SA" not in quotes


def test_parquet_close_feed_convenience_quote(tmp_path):
    _save_panel(tmp_path, "TEST3.SA", last_close=42.0, last_date="2026-08-14")
    feed = ParquetCloseFeed(data_dir=tmp_path)

    assert feed.quote("TEST3.SA").price == pytest.approx(42.0)
    assert feed.quote("NAOEXISTE3.SA") is None


def test_replay_feed_round_trip():
    feed = ReplayFeed()
    ts = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    feed.set("WEGE3.SA", 55.5, ts=ts)

    quotes = feed.quotes(["WEGE3.SA"])
    assert quotes["WEGE3.SA"].price == pytest.approx(55.5)
    assert quotes["WEGE3.SA"].ts == ts
    assert quotes["WEGE3.SA"].source == "replay"
    assert feed.delay_seconds == 0.0
    assert feed.is_realtime is True


def test_replay_feed_advance_consome_fila():
    feed = ReplayFeed()
    feed.queue("WEGE3.SA", [(50.0, None), (51.0, None)])

    q1 = feed.advance("WEGE3.SA")
    q2 = feed.advance("WEGE3.SA")
    q3 = feed.advance("WEGE3.SA")

    assert q1.price == pytest.approx(50.0)
    assert q2.price == pytest.approx(51.0)
    assert q3 is None
    # a cotacao corrente fica no ultimo valor avancado
    assert feed.quote("WEGE3.SA").price == pytest.approx(51.0)


def test_staleness_report_so_marca_quem_passou_do_limite():
    now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    fresco = Quote(ticker="A.SA", price=10.0, ts=now - timedelta(seconds=5), source="replay")
    velho = Quote(ticker="B.SA", price=20.0, ts=now - timedelta(seconds=500), source="replay")

    report = staleness_report({"A.SA": fresco, "B.SA": velho}, now=now, max_age_seconds=60.0)

    assert "A.SA" not in report
    assert "B.SA" in report
    assert report["B.SA"] == pytest.approx(500.0)


def test_yfinance_feed_declara_atraso_de_15_minutos_e_nao_e_realtime():
    feed = YFinanceFeed()
    assert feed.delay_seconds == 900.0
    assert feed.is_realtime is False


def test_yfinance_feed_nao_importa_yfinance_no_topo_do_modulo():
    import live.feed as feed_module

    source = inspect.getsource(feed_module)
    top_of_file = source.split("class YFinanceFeed")[0]
    assert "import yfinance" not in top_of_file


def test_yfinance_feed_falha_de_rede_devolve_dict_vazio_e_chama_on_error(monkeypatch):
    import sys
    import types

    erros = []

    class _TickerBoom:
        def __init__(self, ticker):
            raise ConnectionError("sem rede")

    fake_yf = types.ModuleType("yfinance")
    fake_yf.Ticker = _TickerBoom
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    feed = YFinanceFeed(on_error=lambda ticker, exc: erros.append((ticker, str(exc))))
    quotes = feed.quotes(["WEGE3.SA", "RADL3.SA"])

    assert quotes == {}
    assert len(erros) == 2


def test_quotefeed_e_abstrata():
    with pytest.raises(TypeError):
        QuoteFeed()
