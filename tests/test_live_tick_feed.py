"""Testes de `live/tick_feed.py::MT5TickFeed` — o feed de NEGOCIO A NEGOCIO
que todo robo `feed_kind="tick"` consome ao vivo (`WdoGridReloadMaker` hoje;
`GremahTick` tambem consumia ate' ser eliminada em 2026-09-04).

O que esta em jogo, e por que os invariantes sao OPOSTOS aos de
`test_live_bar_feed.py`: uma barra M1 e' um agregado que continua mudando ate'
o minuto acabar, entao o feed de barras tem de descartar a mais nova e exigir
60s de idade. Um tick de negocio ja' aconteceu — descartar o mais recente
jogaria fora um preco real, e esperar 60s atrasaria o robo por nada. Este
arquivo prova que a segunda politica esta em vigor aqui, e nao a primeira.

`fetch_ticks_range` e' monkeypatchado: nenhum destes testes toca no terminal.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from core.b3_session import MT5_SERVER_TIMEZONE
from live import tick_feed as tick_feed_mod
from live.tick_feed import MT5TickFeed


def _ticks(inicio: str, n: int, freq: str = "1s", preco: float = 10.0) -> pd.DataFrame:
    idx = pd.date_range(inicio, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "bid": [preco - 0.01] * n,
        "ask": [preco + 0.01] * n,
        "last": [preco + i * 0.01 for i in range(n)],
        "volume": [100] * n,
        "volume_real": [0] * n,
        "flags": [0] * n,
    }, index=idx)


def _feed(monkeypatch, df: pd.DataFrame, agora: str, capturado: list | None = None):
    def _fake(symbol, start, end, on_error=None, **kw):
        if capturado is not None:
            capturado.append((start, end, kw))
        return df

    monkeypatch.setattr(tick_feed_mod, "fetch_ticks_range", _fake)
    return MT5TickFeed(
        "PMAM3",
        now_fn=lambda: datetime.fromisoformat(agora).replace(tzinfo=timezone.utc),
    )


# ---------- o tick mais novo NAO e' descartado -----------------------------

def test_entrega_o_negocio_mais_recente_sem_esperar_o_minuto_fechar(monkeypatch):
    """A guarda central do feed M1 seria um BUG aqui: um negocio nao se forma,
    acontece. Segurar o mais novo por 60s custaria exatamente a vantagem que
    justifica um robo `feed_kind="tick"` (`WdoGridReloadMaker` hoje) preferir
    este feed ao M1."""
    df = _ticks("2026-08-21 13:00:00", 5)  # 13:00:00..13:00:04
    feed = _feed(monkeypatch, df, "2026-08-21 13:00:05")

    barras = feed.closed_bars_since(None)

    assert [b.ts.strftime("%H:%M:%S") for b in barras] == [
        "13:00:00", "13:00:01", "13:00:02", "13:00:03", "13:00:04",
    ]


def test_um_unico_negocio_ja_e_entregue(monkeypatch):
    """Contraste direto com `test_lote_de_uma_barra_so_devolve_nada` do feed
    M1: la o lote de um era so' a barra em formacao, aqui e' um negocio real."""
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 1), "2026-08-21 13:00:01")

    assert len(feed.closed_bars_since(None)) == 1


def test_barra_degenerada_tem_o_mesmo_preco_nos_quatro_campos(monkeypatch):
    """E' o que apaga a ambiguidade stop-vs-alvo que o M1 tem por construcao:
    com `high == low`, o motor so' pode resolver um dos dois."""
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 1, preco=9.37),
                 "2026-08-21 13:00:01")

    bar = feed.closed_bars_since(None)[0]

    assert bar.open == bar.high == bar.low == bar.close == pytest.approx(9.37)


# ---------- guardas que CONTINUAM valendo ----------------------------------

def test_tick_rotulado_no_futuro_nao_passa(monkeypatch):
    """Nao e' a guarda de "em formacao" disfarcada: e' a defesa contra relogio
    de servidor divergente. Um offset errado nao levanta erro nenhum — so' faz
    o robo rodar a fase errada do dia inteiro."""
    df = _ticks("2026-08-21 13:00:00", 5)
    feed = _feed(monkeypatch, df, "2026-08-21 13:00:02")

    barras = feed.closed_bars_since(None)

    assert [b.ts.strftime("%H:%M:%S") for b in barras] == [
        "13:00:00", "13:00:01", "13:00:02",
    ]


def test_after_ts_filtra_o_que_ja_foi_entregue(monkeypatch):
    df = _ticks("2026-08-21 13:00:00", 6)
    feed = _feed(monkeypatch, df, "2026-08-21 13:00:10")

    barras = feed.closed_bars_since(pd.Timestamp("2026-08-21 13:00:02", tz="UTC"))

    assert [b.ts.strftime("%H:%M:%S") for b in barras] == [
        "13:00:03", "13:00:04", "13:00:05",
    ]


def test_terminal_indisponivel_devolve_vazio_sem_excecao(monkeypatch):
    """Mesmo contrato de `MT5BarFeed`: o supervisor tem de sobreviver ao
    terminal cair. Vazio tambem e' o caso NORMAL num papel iliquido."""
    feed = _feed(monkeypatch, pd.DataFrame(), "2026-08-21 13:00:10")
    assert feed.closed_bars_since(None) == []


def test_ordem_cronologica_mesmo_com_lote_desordenado(monkeypatch):
    df = _ticks("2026-08-21 13:00:00", 8).sample(frac=1.0, random_state=0)
    feed = _feed(monkeypatch, df, "2026-08-21 13:00:20")

    barras = feed.closed_bars_since(None)

    assert [b.ts for b in barras] == sorted(b.ts for b in barras)


# ---------- fuso: a janela pedida vai no relogio do SERVIDOR ---------------

def test_limites_da_janela_sao_convertidos_para_o_relogio_do_servidor(monkeypatch):
    """`copy_ticks_range` interpreta os limites que recebe no relogio do
    SERVIDOR, nao em UTC — pedir "desde 13:00 UTC" sem converter pediria, na
    verdade, 13:00 de Brasilia: tres horas de dado no lugar errado.

    `after_ts` aqui e' de dois dias atras (mais longe que
    `_SAFE_FETCH_LOOKBACK`), de proposito: e' o unico jeito de testar a
    conversao de fuso do LIMITE PEDIDO sem o piso de seguranca (ver
    `test_janela_estreita_e_alargada_para_alcancar_o_piso_seguro` abaixo)
    substituir `after_ts` antes que a conversao aconteca."""
    capturado: list = []
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 3),
                 "2026-08-21 13:00:10", capturado=capturado)

    feed.closed_bars_since(pd.Timestamp("2026-08-19 13:00:00", tz="UTC"))

    start, _end, _kw = capturado[0]
    esperado = (datetime(2026, 8, 19, 13, 0, tzinfo=timezone.utc)
                .astimezone(MT5_SERVER_TIMEZONE).replace(tzinfo=None))
    # Ate' 2026-09-07 este teste exigia `start.tzinfo is None`, afirmando que
    # o naive impedia o pacote `MetaTrader5` de reinterpretar o limite. E' o
    # contrario: `.timestamp()` de um naive e' resolvido no fuso da MAQUINA,
    # o que CANCELA a conversao acima (ver `tick_feed._limite_servidor`). O
    # limite certo e' o relogio de parede do servidor ROTULADO como UTC.
    assert start.tzinfo == timezone.utc
    assert start.replace(tzinfo=None) == esperado
    assert start.hour == 10  # 13:00 UTC == 10:00 em Brasilia


def _parede_lida_pelo_terminal(limite: datetime) -> datetime:
    """O relogio de parede que o terminal MT5 vai ler do limite entregue.

    Reproduz o que o pacote `MetaTrader5` faz: `.timestamp()` no limite, e o
    terminal trata esse epoch como hora de parede do servidor. Num limite
    tz-aware `.timestamp()` nao consulta o fuso local; num naive, consulta —
    e e' exatamente por isso que o naive deslocava a janela."""
    return datetime.fromtimestamp(limite.timestamp(), timezone.utc).replace(tzinfo=None)


def test_limite_chega_ao_terminal_como_a_parede_pedida_e_nao_deslocado(monkeypatch):
    """Regressao do bug latente corrigido em 2026-09-07: o limite era naive, e
    `.timestamp()` de um naive e' resolvido no fuso da MAQUINA — o que
    cancelava a conversao para o relogio do servidor e fazia a janela pedida
    andar +3h nesta maquina (medido: pedir naive 12:00 devolveu negocios de
    15:00 de parede).

    O teste olha o limite pelos olhos do terminal, nao pelo tipo do objeto: o
    epoch entregue tem de valer a hora de BRASILIA do instante UTC pedido.
    Com o codigo antigo o epoch valia o proprio horario UTC."""
    capturado: list = []
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 3),
                 "2026-08-21 13:00:10", capturado=capturado)

    feed.closed_bars_since(pd.Timestamp("2026-08-19 13:00:00", tz="UTC"))

    start, end, _kw = capturado[0]
    # tz-aware nos dois limites: e' o que torna `.timestamp()` independente
    # da maquina que roda o robo.
    assert start.tzinfo is not None and end.tzinfo is not None
    # 13:00 UTC == 10:00 em Brasilia, que e' o relogio do servidor.
    assert _parede_lida_pelo_terminal(start) == datetime(2026, 8, 19, 10, 0)
    # limite superior: "agora" (13:00:10 UTC) + `_FUTURE_MARGIN` (2min).
    assert _parede_lida_pelo_terminal(end) == datetime(2026, 8, 21, 10, 2, 10)


def test_session_bars_until_tambem_pede_a_janela_no_relogio_do_servidor(monkeypatch):
    """A outra porta de entrada do mesmo `_fetch` — o warm start. A janela e'
    alargada em um dia para cada lado (o recorte do pregao e' feito depois,
    sobre o index ja' corrigido), mas o alargamento e' folga, nao licenca para
    pedir a janela na hora errada."""
    capturado: list = []
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 3),
                 "2026-08-21 13:10:00", capturado=capturado)

    feed.session_bars_until(date(2026, 8, 21), pd.Timestamp("2026-08-21 13:05", tz="UTC"))

    start, end, _kw = capturado[0]
    # meia-noite UTC de 2026-08-21, menos 1 dia == 2026-08-20 00:00 UTC,
    # que em Brasilia e' 2026-08-19 21:00.
    assert _parede_lida_pelo_terminal(start) == datetime(2026, 8, 19, 21, 0)
    assert _parede_lida_pelo_terminal(end) == datetime(2026, 8, 22, 21, 0)


def test_janela_estreita_e_alargada_para_alcancar_o_piso_seguro(monkeypatch):
    """Bug medido 2026-08-24 (Rico/XP): `copy_ticks_range` com `date_from`
    DENTRO do pregao de hoje devolveu negocios incompletos ou ZERO neste
    terminal, mesmo com negocios reais dentro da janela pedida -- sem
    excecao nenhuma, entao a `gremah_tick` ficou o pregao inteiro sem ver
    UMA barra. `after_ts` recente (ou `None`, cold start) nao pode mais
    resultar numa janela mais estreita que `_SAFE_FETCH_LOOKBACK`."""
    capturado: list = []
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 3),
                 "2026-08-21 13:00:10", capturado=capturado)

    feed.closed_bars_since(pd.Timestamp("2026-08-21 13:00:05", tz="UTC"))

    start, _end, _kw = capturado[0]
    pedido = (datetime(2026, 8, 21, 13, 0, 5, tzinfo=timezone.utc)
              .astimezone(MT5_SERVER_TIMEZONE).replace(tzinfo=None))
    # `.replace(tzinfo=None)`: o limite passou a ser tz-aware em 2026-09-07
    # (ver `tick_feed._limite_servidor`); o NUMERO de parede comparado aqui
    # e' o mesmo de antes — o piso de seguranca nao mudou.
    assert start.replace(tzinfo=None) < pedido - timedelta(hours=23)


def test_conversao_de_volta_e_delegada_ao_mt5_ticks_source(monkeypatch):
    """Nao passa offset explicito: `None` (o default de `mt5_ticks_source`)
    significa "converta pelo FUSO declarado", o unico caminho correto se o fuso
    do servidor um dia voltar a ter horario de verao."""
    capturado: list = []
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 3),
                 "2026-08-21 13:00:10", capturado=capturado)

    feed.closed_bars_since(None)

    _start, _end, kw = capturado[0]
    assert "server_utc_offset_hours" not in kw


def test_offset_reportado_vem_do_fuso_medido(monkeypatch):
    feed = _feed(monkeypatch, _ticks("2026-08-21 13:00:00", 3), "2026-08-21 13:00:10")
    assert feed.offset_hours == pytest.approx(3.0)


def test_atraso_nominal_e_zero_contra_os_60s_do_feed_m1(monkeypatch):
    """O painel reporta este numero. Anunciar 60s aqui esconderia justamente a
    diferenca entre os dois robos."""
    from live.bar_feed import MT5BarFeed

    assert MT5TickFeed.nominal_delay_seconds == 0.0
    assert MT5BarFeed.nominal_delay_seconds == 60.0


# ---------- semente do warm start -----------------------------------------

def test_session_bars_until_recorta_o_pregao_e_respeita_o_limite(monkeypatch):
    """Material do `warm_start_calibration` quando o robo liga no meio do
    pregao: da abertura ate' o limite, so' do pregao pedido."""
    df = pd.concat([
        _ticks("2026-08-20 19:50:00", 3),   # pregao anterior (a janela pedida
                                            # ao terminal e' alargada de proposito)
        _ticks("2026-08-21 13:00:00", 8),
    ])
    feed = _feed(monkeypatch, df, "2026-08-21 13:10:00")

    barras = feed.session_bars_until(
        date(2026, 8, 21), pd.Timestamp("2026-08-21 13:00:03", tz="UTC"))

    assert [b.ts.strftime("%H:%M:%S") for b in barras] == [
        "13:00:00", "13:00:01", "13:00:02", "13:00:03",
    ]


def test_session_bars_until_sem_dado_devolve_vazio(monkeypatch):
    feed = _feed(monkeypatch, pd.DataFrame(), "2026-08-21 13:10:00")
    assert feed.session_bars_until(
        date(2026, 8, 21), pd.Timestamp("2026-08-21 13:05", tz="UTC")) == []


# ---------- "nada novo" vs. "nao consegui ler" (incidente 2026-09-08) -------

def _feed_com_falha(monkeypatch, agora: str, falhar: list[bool]):
    """Feed cujo `fetch_ticks_range` chama `on_error` (e devolve vazio) nas
    leituras marcadas em `falhar` -- exatamente o que
    `mt5_ticks_source._falha_de_leitura` passou a fazer quando o terminal
    devolve `None`/vazio-com-erro."""
    passos = {"n": 0}

    def _fake(symbol, start, end, on_error=None, **kw):
        i = passos["n"]
        passos["n"] += 1
        if i < len(falhar) and falhar[i] and on_error is not None:
            on_error(symbol, RuntimeError("copy_ticks_range devolveu None (last_error=(-4, 'x'))"))
        return pd.DataFrame()

    monkeypatch.setattr(tick_feed_mod, "fetch_ticks_range", _fake)
    return MT5TickFeed(
        "WDO@",
        now_fn=lambda: datetime.fromisoformat(agora).replace(tzinfo=timezone.utc),
    )


def test_leitura_falhada_fica_visivel_apesar_da_lista_vazia(monkeypatch):
    """O buraco de 44,8 min de 2026-09-08 foi invisivel porque
    `closed_bars_since` devolve lista vazia nos DOIS casos -- papel parado e
    terminal cego. O contrato "vazio, nunca excecao" nao mudou; a falha agora
    viaja por fora dele."""
    feed = _feed_com_falha(monkeypatch, "2026-09-08 14:20:00", [True])

    assert feed.closed_bars_since(None) == []
    assert feed.falha_de_leitura is not None
    assert "copy_ticks_range" in feed.falha_de_leitura


def test_janela_legitimamente_vazia_nao_marca_falha(monkeypatch):
    """A outra metade: mercado sem negocio novo devolve vazio SEM falha. Se
    esta assercao cair, o alarme dispara todo passo de papel parado e vira
    ruido -- que e' o modo de falha do item 6.15."""
    feed = _feed_com_falha(monkeypatch, "2026-09-08 14:20:00", [False])

    assert feed.closed_bars_since(None) == []
    assert feed.falha_de_leitura is None


def test_falha_apaga_sozinha_na_leitura_seguinte(monkeypatch):
    """Alarme que nao apaga sozinho e' alarme que ninguem le: a marca vale
    pela leitura ATUAL, nunca por uma de cinco minutos atras."""
    feed = _feed_com_falha(monkeypatch, "2026-09-08 14:20:00", [True, False])

    feed.closed_bars_since(None)
    assert feed.falha_de_leitura is not None
    feed.closed_bars_since(None)
    assert feed.falha_de_leitura is None
