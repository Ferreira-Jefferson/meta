"""Testes de `live/bar_feed.py::MT5BarFeed` — as duas guardas de barra
FECHADA e o fuso do servidor.

O que esta em jogo: alimentar a maquina intradiaria com a barra em FORMACAO
e a versao intradiaria do look-ahead. `bar.high`/`bar.low` do minuto corrente
ainda vao mudar, e e' exatamente neles que stop, alvo e toque de ordem-limite
sao resolvidos — um stop "disparado" pela maxima parcial de um minuto que
ainda nao acabou nunca existiu.

`fetch_m1_recent`/`fetch_m1_range` sao monkeypatchados: nenhum destes testes
toca no terminal MT5.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from core.b3_session import MT5_SERVER_TIMEZONE
from live import bar_feed as bar_feed_mod
from live.bar_feed import MT5BarFeed
from market_data_intraday.mt5_source import DEFAULT_SERVER_UTC_OFFSET_HOURS


def _df(inicio: str, n: int, **extra) -> pd.DataFrame:
    idx = pd.date_range(inicio, periods=n, freq="1min", tz="UTC")
    dados = {
        "open": [10.0 + i * 0.01 for i in range(n)],
        "high": [10.05 + i * 0.01 for i in range(n)],
        "low": [9.95 + i * 0.01 for i in range(n)],
        "close": [10.0 + i * 0.01 for i in range(n)],
        "tick_volume": [100] * n,
    }
    dados.update(extra)
    return pd.DataFrame(dados, index=idx)


def _feed(monkeypatch, df: pd.DataFrame, agora: str, **kwargs) -> MT5BarFeed:
    monkeypatch.setattr(bar_feed_mod, "fetch_m1_recent", lambda *a, **k: df)
    monkeypatch.setattr(bar_feed_mod, "fetch_m1_range", lambda *a, **k: df)
    return MT5BarFeed(
        "PMAM3",
        now_fn=lambda: datetime.fromisoformat(agora).replace(tzinfo=timezone.utc),
        **kwargs,
    )


# ---------- guarda 1: descarta a barra em formacao -------------------------

def test_descarta_a_barra_mais_nova_do_lote(monkeypatch):
    """`copy_rates_from_pos(..., 0, n)` inclui SEMPRE a barra do minuto
    corrente, em formacao."""
    df = _df("2026-08-21 13:00", 5)  # 13:00..13:04
    feed = _feed(monkeypatch, df, "2026-08-21 13:05:30")

    barras = feed.closed_bars_since(None)

    assert [b.ts.strftime("%H:%M") for b in barras] == ["13:00", "13:01", "13:02", "13:03"]


def test_lote_de_uma_barra_so_devolve_nada(monkeypatch):
    """Se o lote so tem a barra em formacao, nao ha barra fechada nenhuma —
    devolver essa unica barra seria entregar exatamente o dado proibido."""
    df = _df("2026-08-21 13:00", 1)
    feed = _feed(monkeypatch, df, "2026-08-21 13:01:30")

    assert feed.closed_bars_since(None) == []


def test_lote_vazio_devolve_lista_vazia_sem_excecao(monkeypatch):
    """Mesmo contrato de `MT5Feed.quotes`: terminal indisponivel nunca levanta,
    devolve vazio — o supervisor precisa sobreviver ao terminal cair."""
    feed = _feed(monkeypatch, pd.DataFrame(), "2026-08-21 13:05:30")
    assert feed.closed_bars_since(None) == []


# ---------- guarda 2: idade minima ----------------------------------------

def test_idade_minima_segura_barra_que_a_guarda_da_ultima_deixaria_passar(monkeypatch):
    """A redundancia entre as duas guardas nao e' decorativa.

    O `time` de uma barra M1 do MT5 e' o instante de ABERTURA dela: a barra
    rotulada 13:02 fecha as 13:03. Se o relogio do servidor estiver ADIANTADO
    do nosso, o lote chega com barras rotuladas no nosso futuro proximo —
    descartar so a ultima deixaria as outras "do futuro" passarem como
    fechadas. Aqui o lote vai ate 13:04 mas ja' sao 13:02:30 para nos: a
    guarda 1 tira 13:04, e a guarda de idade tira 13:03 e 13:02 (nenhuma das
    duas fechou ainda)."""
    df = _df("2026-08-21 13:00", 5)  # 13:00..13:04
    feed = _feed(monkeypatch, df, "2026-08-21 13:02:30")

    barras = feed.closed_bars_since(None)

    assert [b.ts.strftime("%H:%M") for b in barras] == ["13:00", "13:01"]


def test_after_ts_filtra_o_que_ja_foi_entregue(monkeypatch):
    df = _df("2026-08-21 13:00", 6)
    feed = _feed(monkeypatch, df, "2026-08-21 13:06:30")

    barras = feed.closed_bars_since(pd.Timestamp("2026-08-21 13:02", tz="UTC"))

    assert [b.ts.strftime("%H:%M") for b in barras] == ["13:03", "13:04"]


def test_barras_vem_em_ordem_cronologica_mesmo_com_lote_desordenado(monkeypatch):
    """A maquina consome barra a barra, em ORDEM: alimentar fora de ordem
    faria stop/alvo resolverem contra o preco errado."""
    df = _df("2026-08-21 13:00", 5).sample(frac=1.0, random_state=0)
    feed = _feed(monkeypatch, df, "2026-08-21 13:05:30")

    barras = feed.closed_bars_since(None)

    assert [b.ts for b in barras] == sorted(b.ts for b in barras)


# ---------- volume: real_volume vs tick_volume ----------------------------

def test_usa_real_volume_quando_reportado(monkeypatch):
    """Mesma regra do backtest (`engine.bar_from_row`): o MT5 nao devolve
    `volume`, devolve `real_volume` (nem sempre populado) e `tick_volume`."""
    df = _df("2026-08-21 13:00", 3, real_volume=[5_000, 6_000, 7_000])
    feed = _feed(monkeypatch, df, "2026-08-21 13:04:30")

    barras = feed.closed_bars_since(None)

    assert [b.volume for b in barras] == [5_000.0, 6_000.0]


def test_cai_para_tick_volume_quando_real_volume_e_zero(monkeypatch):
    df = _df("2026-08-21 13:00", 3, real_volume=[0, 0, 0])
    feed = _feed(monkeypatch, df, "2026-08-21 13:04:30")

    assert [b.volume for b in feed.closed_bars_since(None)] == [100.0, 100.0]


# ---------- fuso do servidor ----------------------------------------------

def test_offset_reportado_vem_do_fuso_medido_do_servidor(monkeypatch):
    """Um offset errado NAO produz erro nenhum — produz um robo rodando a fase
    errada (ancora fixa vs rolante) e achatando no minuto errado, o dia
    inteiro, em silencio. O numero exposto aqui existe so para o painel
    MOSTRAR qual fuso esta em uso."""
    feed = _feed(monkeypatch, _df("2026-08-21 13:00", 3), "2026-08-21 13:04:30")

    assert feed.offset_hours == pytest.approx(DEFAULT_SERVER_UTC_OFFSET_HOURS)
    assert feed.offset_hours == pytest.approx(3.0)


def test_nao_ha_offset_injetavel_no_feed_de_barras():
    """REGRESSAO: `offset_provider` era o caminho pelo qual um offset INFERIDO
    (da idade aparente de um tick) chegava as barras. Medido em 2026-08-21 no
    terminal real, a inferencia adotou +4.0h onde o certo era +3.0h. Quem
    converte agora e' `mt5_source`, pelo fuso declarado — e conferir o relogio
    passou a IMPEDIR a operacao (`MT5Feed.verify_server_clock`) em vez de
    reescrever o numero em silencio."""
    import inspect

    assinatura = inspect.signature(MT5BarFeed.__init__)
    assert "offset_provider" not in assinatura.parameters


def test_conversao_de_fuso_e_delegada_ao_mt5_source(monkeypatch):
    """O feed de barras nao passa mais offset nenhum ao fetch: `None` (o
    default de `mt5_source`) significa "converta pelo fuso declarado", que e'
    o unico caminho correto quando o fuso pode ter horario de verao."""
    capturado: list = []

    def _fake_recent(symbol, count=None, on_error=None, **kw):
        capturado.append(kw.get("server_utc_offset_hours", "ausente"))
        return _df("2026-08-21 13:00", 3)

    monkeypatch.setattr(bar_feed_mod, "fetch_m1_recent", _fake_recent)
    feed = MT5BarFeed(
        "PMAM3", now_fn=lambda: datetime(2026, 8, 21, 13, 4, 30, tzinfo=timezone.utc)
    )

    feed.closed_bars_since(None)

    assert capturado == ["ausente"]


def _parede_lida_pelo_terminal(limite: datetime) -> datetime:
    """O relogio de parede que o terminal MT5 vai ler do limite entregue.

    Reproduz o que o pacote `MetaTrader5` faz: `.timestamp()` no limite, e o
    terminal trata esse epoch como hora de parede do servidor. Num limite
    tz-aware `.timestamp()` NAO consulta o fuso local; num naive, consulta.
    Mesma tecnica de `tests/test_live_tick_feed.py` — olhar o limite pelos
    OLHOS DO TERMINAL, nao pelo tipo do objeto, e' o unico jeito de um teste
    sem terminal enxergar um deslocamento de janela."""
    return datetime.fromtimestamp(limite.timestamp(), timezone.utc).replace(tzinfo=None)


def test_session_bars_until_pede_a_janela_no_relogio_do_servidor(monkeypatch):
    """REGRESSAO: ate' 2026-09-07 `session_bars_until` mandava `meia_noite ±
    dias` em UTC CRU para `fetch_m1_range` -> `copy_rates_range`, que
    interpreta os limites no relogio do SERVIDOR. A janela chegava 3h
    deslocada. Ficava mascarado pelo alargamento de ±1 dia, mas mascarar nao
    e' corrigir: bastava apertar a janela para o pregao ser cortado no lugar
    errado. Mesma familia do bug que comeu 63 buracos de 3h do parquet
    canonico do WDO@ (`mt5_ticks_source._cursor_paginacao`).

    Com o codigo antigo a parede lida seria 2026-08-20 00:00 / 2026-08-23
    00:00 — o proprio horario UTC, sem conversao."""
    capturado: list = []

    def _fake_range(symbol, start, end, on_error=None, **kw):
        capturado.append((start, end))
        return _df("2026-08-21 13:00", 8)

    monkeypatch.setattr(bar_feed_mod, "fetch_m1_range", _fake_range)
    feed = MT5BarFeed(
        "PMAM3", now_fn=lambda: datetime(2026, 8, 21, 13, 10, tzinfo=timezone.utc)
    )

    feed.session_bars_until(date(2026, 8, 21), pd.Timestamp("2026-08-21 13:05", tz="UTC"))

    start, end = capturado[0]
    # tz-aware nos dois limites: e' o que torna `.timestamp()` independente da
    # maquina que roda o robo (um naive seria resolvido no fuso LOCAL, o que
    # cancelaria a conversao).
    assert start.tzinfo is not None and end.tzinfo is not None
    # 2026-08-21 00:00 UTC menos 1 dia == 2026-08-20 00:00 UTC, que no relogio
    # do servidor (Brasilia) e' 2026-08-19 21:00.
    assert _parede_lida_pelo_terminal(start) == datetime(2026, 8, 19, 21, 0)
    assert _parede_lida_pelo_terminal(end) == datetime(2026, 8, 22, 21, 0)


def test_alargamento_de_um_dia_para_cada_lado_continua_valendo(monkeypatch):
    """O alargamento NAO virou redundante com a correcao de fuso acima, e por
    isso nao foi removido: ele defende contra o dia civil do servidor nao ser
    o dia civil em UTC e contra o fuso declarado divergir do servidor real —
    modos de falha independentes do limite ir na hora errada (mesmo
    raciocinio das defesas mantidas em `live/tick_feed.py`)."""
    capturado: list = []

    def _fake_range(symbol, start, end, on_error=None, **kw):
        capturado.append((start, end))
        return _df("2026-08-21 13:00", 8)

    monkeypatch.setattr(bar_feed_mod, "fetch_m1_range", _fake_range)
    feed = MT5BarFeed(
        "PMAM3", now_fn=lambda: datetime(2026, 8, 21, 13, 10, tzinfo=timezone.utc)
    )

    feed.session_bars_until(date(2026, 8, 21), pd.Timestamp("2026-08-21 13:05", tz="UTC"))

    start, end = capturado[0]
    assert end - start == pd.Timedelta(days=3)
    # a sessao pedida (00:00..24:00 de 2026-08-21 em Brasilia) cabe FOLGADA
    # dentro da janela, com pelo menos meio dia de sobra de cada lado.
    abre = pd.Timestamp("2026-08-21 00:00", tz=MT5_SERVER_TIMEZONE)
    fecha = pd.Timestamp("2026-08-22 00:00", tz=MT5_SERVER_TIMEZONE)
    p_start = pd.Timestamp(_parede_lida_pelo_terminal(start), tz=MT5_SERVER_TIMEZONE)
    p_end = pd.Timestamp(_parede_lida_pelo_terminal(end), tz=MT5_SERVER_TIMEZONE)
    assert p_start <= abre - pd.Timedelta(hours=12)
    assert p_end >= fecha + pd.Timedelta(hours=12)


# ---------- semente do warm start ----------------------------------------

def test_session_bars_until_recorta_o_pregao_e_respeita_o_limite(monkeypatch):
    """Material do `warm_start_calibration`: da abertura ate a ultima barra
    fechada, so do pregao pedido."""
    df = pd.concat([
        _df("2026-08-20 19:50", 3),   # pregao anterior (a janela pedida ao
                                      # terminal e' alargada de proposito)
        _df("2026-08-21 13:00", 8),   # 13:00..13:07
    ])
    feed = _feed(monkeypatch, df, "2026-08-21 13:10:00")

    barras = feed.session_bars_until(date(2026, 8, 21),
                                     pd.Timestamp("2026-08-21 13:05", tz="UTC"))

    assert [b.ts.strftime("%H:%M") for b in barras] == [
        "13:00", "13:01", "13:02", "13:03", "13:04", "13:05",
    ]


def test_session_bars_until_nao_descarta_a_barra_do_proprio_limite(monkeypatch):
    """Ordem das operacoes importa: se o recorte por `until_ts` viesse ANTES
    de descartar a barra em formacao, a ultima barra do recorte seria jogada
    fora como "em formacao" sem ser — e a calibracao perderia um minuto de
    dado real a cada chamada."""
    df = _df("2026-08-21 13:00", 8)
    feed = _feed(monkeypatch, df, "2026-08-21 13:10:00")

    barras = feed.session_bars_until(date(2026, 8, 21),
                                     pd.Timestamp("2026-08-21 13:03", tz="UTC"))

    assert barras[-1].ts.strftime("%H:%M") == "13:03"


def test_session_bars_until_sem_dado_devolve_vazio(monkeypatch):
    feed = _feed(monkeypatch, pd.DataFrame(), "2026-08-21 13:10:00")
    assert feed.session_bars_until(date(2026, 8, 21),
                                   pd.Timestamp("2026-08-21 13:05", tz="UTC")) == []
