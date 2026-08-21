"""Testes da camada de cotacao (`live/feed.py`) — sem rede.

Foco: `ParquetCloseFeed` declara o proprio atraso como a idade real do dado
(nao um numero fixo), `ReplayFeed` serve de dublê determinístico para teste, e
`staleness_report` so aponta quem passou do limite. `YFinanceFeed` e testado
sem tocar rede: so o contrato de atraso declarado e o lazy-import. `MT5Feed`
(FEAT-004) e testado com um `MetaTrader5` FALSO injetado em `sys.modules`,
mesma tecnica de `tests/test_live_broker_mt5.py::fake_mt5`.
"""
from __future__ import annotations

import inspect
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from live import feed as feed_mod
from live.feed import MT5Feed, ParquetCloseFeed, QuoteFeed, YFinanceFeed, staleness_report
from core.live_models import Quote, SessionPhase
from tests.doubles import ReplayFeed


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


# ---------- MT5Feed (FEAT-004) ----------------------------------------------

def _make_fake_mt5_feed_module(*, initialize_ok: bool = True, ticks: dict | None = None,
                               last_error=(0, "sem erro")):
    """Fake minimo de `MetaTrader5`, so a superficie usada por `MT5Feed`
    (`initialize`, `symbol_select`, `symbol_info_tick`, `last_error`)."""
    ticks = ticks or {}
    mod = types.ModuleType("MetaTrader5")
    mod.initialize = lambda **kwargs: initialize_ok
    mod.last_error = lambda: last_error
    mod.symbol_select = lambda symbol, enable=True: True
    mod.symbol_info_tick = lambda symbol: ticks.get(symbol)
    return mod


def _tick(*, bid=49.9, ask=50.1, last=None, time=0):
    return types.SimpleNamespace(bid=bid, ask=ask, last=last, time=time)


def test_mt5feed_le_tick_e_declara_atraso_real(monkeypatch):
    now = datetime(2026, 8, 18, 15, 0, 0, tzinfo=timezone.utc)
    # epoch da hora de PAREDE do servidor (Brasilia, UTC-3) — ver comentario
    # em `test_mt5feed_now_fn_injetavel_permite_idade_deterministica`.
    epoch_agora = int((now - timedelta(hours=3)).timestamp())
    tick = _tick(bid=49.9, ask=50.1, last=50.0, time=epoch_agora - 12)
    mod = _make_fake_mt5_feed_module(ticks={"WEGE3": tick})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now)
    quotes = feed.quotes(["WEGE3.SA"])

    assert quotes["WEGE3.SA"].price == pytest.approx(50.0)
    assert quotes["WEGE3.SA"].source == "mt5"
    assert quotes["WEGE3.SA"].delay_seconds == pytest.approx(12.0)
    assert feed.delay_seconds == pytest.approx(12.0)


def test_mt5feed_sem_last_usa_midpoint_bid_ask(monkeypatch):
    now = datetime(2026, 8, 18, 15, 0, 0, tzinfo=timezone.utc)
    tick = _tick(bid=49.9, ask=50.1, last=None, time=int(now.timestamp()))
    mod = _make_fake_mt5_feed_module(ticks={"WEGE3": tick})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now)
    quotes = feed.quotes(["WEGE3.SA"])

    assert quotes["WEGE3.SA"].price == pytest.approx(50.0)  # midpoint (49.9+50.1)/2


def test_mt5feed_symbol_for_remove_sufixo_e_respeita_symbol_map():
    feed = MT5Feed()
    assert feed.symbol_for("WEGE3.SA") == "WEGE3"
    assert feed.symbol_for("PETR4") == "PETR4"

    feed_map = MT5Feed(symbol_map={"WEGE3.SA": "WEGE3F"})
    assert feed_map.symbol_for("WEGE3.SA") == "WEGE3F"
    assert feed_map.symbol_for("PETR4.SA") == "PETR4"


def test_mt5feed_falha_de_conexao_devolve_dict_vazio_e_chama_on_error(monkeypatch):
    mod = _make_fake_mt5_feed_module(initialize_ok=False, last_error=(10004, "terminal nao encontrado"))
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    erros = []
    feed = MT5Feed(on_error=lambda ticker, exc: erros.append((ticker, str(exc))))
    quotes = feed.quotes(["WEGE3.SA"])

    assert quotes == {}
    assert len(erros) == 1
    assert "10004" in erros[0][1]


def test_mt5feed_nao_importa_metatrader5_no_topo_do_modulo():
    import live.feed as feed_module

    source = inspect.getsource(feed_module)
    top_of_file = source.split("class MT5Feed")[0]
    assert "import MetaTrader5" not in top_of_file
    for line in source.splitlines():
        if line.startswith("import MetaTrader5") or line.startswith("from MetaTrader5"):
            pytest.fail(f"import de MetaTrader5 fora de metodo (coluna 0): {line!r}")


def test_mt5feed_now_fn_injetavel_permite_idade_deterministica(monkeypatch):
    """Dois `tick.time` diferentes com o MESMO `now_fn` fixo provam que a
    idade e CALCULADA (nao uma constante) e independe do relogio real da
    maquina rodando o teste."""
    now_fixo = datetime(2026, 8, 18, 15, 0, 0, tzinfo=timezone.utc)
    # `tick.time` e a hora de PAREDE do servidor (Brasilia, UTC-3), nao UTC —
    # entao o epoch de referencia de um tick "agora" e `now - 3h`. Montar o
    # fake com o epoch de UTC direto simularia um servidor 3h adiantado (e
    # acenderia, com razao, o alarme de tick no futuro).
    epoch_agora = int((now_fixo - timedelta(hours=3)).timestamp())
    tick_fresco = _tick(last=50.0, time=epoch_agora - 5)
    tick_velho = _tick(last=50.0, time=epoch_agora - 400)
    mod = _make_fake_mt5_feed_module(ticks={"AAA": tick_fresco, "BBB": tick_velho})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now_fixo)
    quotes = feed.quotes(["AAA.SA", "BBB.SA"])

    assert quotes["AAA.SA"].delay_seconds == pytest.approx(5.0)
    assert quotes["BBB.SA"].delay_seconds == pytest.approx(400.0)
    assert quotes["BBB.SA"].delay_seconds != quotes["AAA.SA"].delay_seconds


# ---------- MT5Feed: offset declarado + conferencia do relogio -------------
#
# `tick.time` do MetaTrader5 e o relogio do SERVIDOR do terminal, nao UTC. Nos
# fakes abaixo, para simular isso, construimos o "tick.time" cru a partir do
# horario LOCAL do servidor, mas rotulado como UTC (exatamente o jeito errado
# que `datetime.fromtimestamp(tick.time, tz=utc)` interpreta o valor antes da
# correcao).
#
# A AUTOCALIBRACAO do offset foi REMOVIDA em 2026-08-21 (ver docstring de
# `MT5Feed`): ela inferia o offset da idade aparente do tick mais novo, e essa
# inferencia e ambigua por construcao — "tick de 1h atras" e "fuso 1h errado"
# dao o mesmo numero. Estes testes cobrem o que ficou no lugar: offset vindo do
# fuso declarado e medido, e uma conferencia que so acusa quando ha prova.

def _epoch_rotulado_utc(ano, mes, dia, hora, minuto, segundo=0) -> int:
    """Epoch de um horario LOCAL do servidor, como se fosse UTC (o jeito
    'errado' que o pacote MetaTrader5 devolve em `tick.time`)."""
    return int(datetime(ano, mes, dia, hora, minuto, segundo, tzinfo=timezone.utc).timestamp())


def test_mt5feed_usa_o_offset_do_fuso_declarado(monkeypatch):
    """Cenario da medicao real (terminal conectado, pregao aberto): agora UTC
    18:41:20, relogio do servidor 15:41:20 -> +3h, que e exatamente o offset do
    fuso declarado em `core.b3_session`. WEGE3/CSMG3 frescos, EMAE4 parado ha
    ~521s (papel iliquido, atraso genuino) — e o atraso de cada um sai em
    SEGUNDOS, nao nas ~3h que o bug de fuso produzia."""
    now_utc = datetime(2026, 8, 20, 18, 41, 20, tzinfo=timezone.utc)
    tick_wege3 = _tick(last=50.0, time=_epoch_rotulado_utc(2026, 8, 20, 15, 41, 19))
    tick_csmg3 = _tick(last=15.0, time=_epoch_rotulado_utc(2026, 8, 20, 15, 41, 20))
    tick_emae4 = _tick(last=3.0, time=_epoch_rotulado_utc(2026, 8, 20, 15, 32, 39))
    mod = _make_fake_mt5_feed_module(
        ticks={"WEGE3": tick_wege3, "CSMG3": tick_csmg3, "EMAE4": tick_emae4}
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now_utc)
    quotes = feed.quotes(["WEGE3.SA", "CSMG3.SA", "EMAE4.SA"])

    assert feed.server_utc_offset_hours == pytest.approx(3.0)
    assert feed.offset_source == "fuso_declarado"
    assert quotes["WEGE3.SA"].delay_seconds == pytest.approx(1.0, abs=1.0)
    assert quotes["CSMG3.SA"].delay_seconds == pytest.approx(0.0, abs=1.0)
    assert quotes["EMAE4.SA"].delay_seconds == pytest.approx(521.0, abs=1.0)
    assert feed.server_clock_alarm is None


def test_mt5feed_nao_adota_offset_de_tick_parado(monkeypatch):
    """REGRESSAO do bug medido em 2026-08-21 no terminal real da Rico.

    Um unico papel iliquido, com o ultimo negocio de ~1h atras, faz a idade
    aparente do tick cru ser de 4h. A autocalibracao antiga arredondava isso
    para +4h COM RESIDUO PEQUENO — aceitava a calibracao e deslocava o dia
    inteiro do robo (fase da ancora, minuto do flatten). O offset agora vem do
    fuso e nao se move.

    O atraso reportado, esse sim, tem de ficar grande: e isso que faz
    `staleness_report` recusar decisao sobre dado velho, que e a defesa certa
    para este caso.
    """
    now_utc = datetime(2026, 8, 21, 21, 42, 44, tzinfo=timezone.utc)
    # relogio do servidor: 18:42:44. Ultimo negocio do papel: 17:42:44 (1h atras).
    tick_parado = _tick(last=0.13, time=_epoch_rotulado_utc(2026, 8, 21, 17, 42, 44))
    mod = _make_fake_mt5_feed_module(ticks={"PMAM3": tick_parado})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now_utc)
    quotes = feed.quotes(["PMAM3.SA"])

    assert feed.server_utc_offset_hours == pytest.approx(3.0)  # NAO virou 4.0
    assert quotes["PMAM3.SA"].delay_seconds == pytest.approx(3600.0, abs=2.0)
    # tick velho nao e prova de relogio errado — e indistinguivel de iliquidez.
    assert feed.server_clock_alarm is None


def test_mt5feed_offset_explicito_vence_o_fuso_declarado(monkeypatch):
    """`server_utc_offset_hours` explicito e respeitado tal qual — e o escape
    para quem mediu outro offset (troca de corretora/servidor)."""
    now_utc = datetime(2026, 8, 18, 15, 0, 0, tzinfo=timezone.utc)
    tick = _tick(last=50.0, time=int(now_utc.timestamp()))
    mod = _make_fake_mt5_feed_module(ticks={"WEGE3": tick})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now_utc, server_utc_offset_hours=-3.0)
    quotes = feed.quotes(["WEGE3.SA"])

    assert feed.server_utc_offset_hours == pytest.approx(-3.0)
    assert feed.offset_source == "explicito"
    # offset explicito -3h aplicado ao tick "cru" desloca o tick 3h para
    # TRAS -> atraso de 3h, mesmo o tick sendo cru-identico a `now`.
    assert quotes["WEGE3.SA"].delay_seconds == pytest.approx(3 * 3600.0)


def test_mt5feed_acusa_tick_no_futuro(monkeypatch):
    """Tick ADIANTADO e a unica prova incondicional de que o offset aplicado
    esta grande demais: nenhum atraso de dado faz um tick chegar do futuro.
    Cenario: servidor na verdade em UTC-2, offset declarado +3h -> o tick
    aparece 1h a frente."""
    now_utc = datetime(2026, 8, 20, 18, 41, 20, tzinfo=timezone.utc)
    tick = _tick(last=50.0, time=_epoch_rotulado_utc(2026, 8, 20, 16, 41, 20))
    mod = _make_fake_mt5_feed_module(ticks={"WEGE3": tick})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    erros = []
    feed = MT5Feed(now_fn=lambda: now_utc, on_error=lambda t, e: erros.append((t, str(e))))
    feed.quotes(["WEGE3.SA"])

    assert feed.server_clock_alarm is not None
    assert "FUTURO" in feed.server_clock_alarm
    assert any(ticker == "relogio" for ticker, _ in erros)
    # o offset NAO e corrigido sozinho: quem decide o que fazer e quem opera.
    assert feed.server_utc_offset_hours == pytest.approx(3.0)


def test_mt5feed_tick_levemente_adiantado_nao_acusa(monkeypatch):
    """Dessincronia normal de relogio (NTP, latencia) nao pode acender alarme:
    senao o robo pararia por ruido de segundos."""
    now_utc = datetime(2026, 8, 20, 18, 41, 20, tzinfo=timezone.utc)
    tick = _tick(last=50.0, time=_epoch_rotulado_utc(2026, 8, 20, 15, 42, 20))  # 60s a frente
    mod = _make_fake_mt5_feed_module(ticks={"WEGE3": tick})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now_utc)
    feed.quotes(["WEGE3.SA"])

    assert feed.server_clock_alarm is None


# ---------- verify_server_clock: o teste que resolve o caso ambiguo --------

def _feed_com_tick_de_referencia(monkeypatch, now_utc, idade_segundos):
    """`MT5Feed` cujo papel de REFERENCIA tem um tick com a idade pedida."""
    parede = now_utc - timedelta(hours=3) - timedelta(seconds=idade_segundos)
    tick = _tick(last=44.0, time=int(parede.replace(tzinfo=timezone.utc).timestamp()))
    mod = _make_fake_mt5_feed_module(ticks={"PETR4": tick})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)
    return MT5Feed(now_fn=lambda: now_utc)


def test_verify_server_clock_acusa_tick_velho_do_papel_liquido_com_pregao_aberto(monkeypatch):
    """Dentro do continuo o papel de REFERENCIA negocia todo minuto. Um tick
    dele com 1h de idade nao tem a desculpa de iliquidez — e prova de que o
    relogio do servidor nao esta no fuso declarado."""
    now_utc = datetime(2026, 8, 20, 16, 0, 0, tzinfo=timezone.utc)  # 13:00 Brasilia
    feed = _feed_com_tick_de_referencia(monkeypatch, now_utc, idade_segundos=3600)
    monkeypatch.setattr(feed_mod.clock, "phase", lambda *a, **k: SessionPhase.OPEN)

    alarme = feed.verify_server_clock()

    assert alarme is not None
    assert "referencia" in alarme
    assert feed.server_clock_alarm == alarme


def test_verify_server_clock_nao_acusa_fora_do_continuo(monkeypatch):
    """Com o mercado FECHADO todo tick esta velho por definicao — foi
    exatamente assim que a autocalibracao antiga errou. Aqui a conferencia por
    atraso simplesmente nao roda."""
    now_utc = datetime(2026, 8, 20, 21, 42, 44, tzinfo=timezone.utc)
    feed = _feed_com_tick_de_referencia(monkeypatch, now_utc, idade_segundos=3600)
    monkeypatch.setattr(feed_mod.clock, "phase", lambda *a, **k: SessionPhase.POST_CLOSE)

    assert feed.verify_server_clock() is None


def test_verify_server_clock_nao_acusa_com_tick_fresco(monkeypatch):
    now_utc = datetime(2026, 8, 20, 16, 0, 0, tzinfo=timezone.utc)
    feed = _feed_com_tick_de_referencia(monkeypatch, now_utc, idade_segundos=2)
    monkeypatch.setattr(feed_mod.clock, "phase", lambda *a, **k: SessionPhase.OPEN)

    assert feed.verify_server_clock() is None


def test_verify_server_clock_sem_tick_nenhum_nao_conclui(monkeypatch):
    """Terminal sem o papel de referencia disponivel nao e prova de nada — nao
    pode acender alarme nem dar um OK falso."""
    mod = _make_fake_mt5_feed_module(ticks={})
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)
    feed = MT5Feed(now_fn=lambda: datetime(2026, 8, 20, 16, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(feed_mod.clock, "phase", lambda *a, **k: SessionPhase.OPEN)

    assert feed.verify_server_clock() is None


def test_mt5feed_ticker_atrasado_entre_frescos_continua_velho_apos_correcao(monkeypatch):
    """O objetivo do fix e fazer o limite de `staleness_report` voltar a
    significar alguma coisa, NAO desligar a deteccao de atraso real: um
    ticker genuinamente parado (EMAE4, ~521s) no meio de tickers frescos tem
    de continuar marcado como velho por `staleness_report` DEPOIS da
    correcao do offset."""
    now_utc = datetime(2026, 8, 20, 18, 41, 20, tzinfo=timezone.utc)
    tick_wege3 = _tick(last=50.0, time=_epoch_rotulado_utc(2026, 8, 20, 15, 41, 19))
    tick_csmg3 = _tick(last=15.0, time=_epoch_rotulado_utc(2026, 8, 20, 15, 41, 20))
    tick_emae4 = _tick(last=3.0, time=_epoch_rotulado_utc(2026, 8, 20, 15, 32, 39))
    mod = _make_fake_mt5_feed_module(
        ticks={"WEGE3": tick_wege3, "CSMG3": tick_csmg3, "EMAE4": tick_emae4}
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", mod)

    feed = MT5Feed(now_fn=lambda: now_utc)
    quotes = feed.quotes(["WEGE3.SA", "CSMG3.SA", "EMAE4.SA"])

    report = staleness_report(quotes, now=now_utc, max_age_seconds=300.0)

    assert "EMAE4.SA" in report
    assert "WEGE3.SA" not in report
    assert "CSMG3.SA" not in report


