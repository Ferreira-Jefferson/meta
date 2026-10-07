from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from social_arbitrage.deteccao_reddit import Mencao, buscar_mencoes
from social_arbitrage.deteccao_trends import SinalTendencia, consultar_interesse


# ---------------------------------------------------------------------------
# Reddit -- fakes de HTTP servindo Atom/RSS, nunca rede real
# ---------------------------------------------------------------------------

_ATOM_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
{entradas}
</feed>"""

_ENTRADA_TEMPLATE = """<entry>
<title>{titulo}</title>
<link href="{url}" />
<published>{publicado}</published>
</entry>"""


def _feed_atom(entradas: list[tuple[str, str, str]]) -> bytes:
    """`entradas`: lista de (titulo, url, publicado_iso)."""
    xml_entradas = "\n".join(_ENTRADA_TEMPLATE.format(titulo=t, url=u, publicado=p) for t, u, p in entradas)
    return _ATOM_TEMPLATE.format(entradas=xml_entradas).encode("utf-8")


class _RespostaFake:
    def __init__(self, content: bytes, status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _ClienteHTTPFake:
    def __init__(self, feeds: dict[str, bytes] | None = None):
        self._feeds = feeds or {}
        self.chamadas_get = []

    def get(self, url, **kwargs):
        self.chamadas_get.append((url, kwargs))
        partes = url.split("/")
        subreddit = partes[partes.index("r") + 1]
        return _RespostaFake(self._feeds.get(subreddit, _feed_atom([])))


def test_buscar_mencoes_retorna_mencoes_de_cada_subreddit():
    fake = _ClienteHTTPFake(feeds={
        "investimentos": _feed_atom([
            ("Havaianas sumiu do mercado", "https://reddit.com/r/investimentos/comments/abc/", "2026-09-20T10:00:00+00:00"),
        ]),
        "farialimabets": _feed_atom([]),
    })
    mencoes = buscar_mencoes("Havaianas", ("investimentos", "farialimabets"), cliente=fake, pausa_segundos=0.0)
    assert len(mencoes) == 1
    [m] = mencoes
    assert isinstance(m, Mencao)
    assert m.subreddit == "investimentos"
    assert m.termo_buscado == "Havaianas"
    assert m.criado_em.tzinfo is not None


def test_buscar_mencoes_preserva_acentos():
    fake = _ClienteHTTPFake(feeds={
        "investimentos": _feed_atom([
            ("Alpargatas perde valor de mercado nesta 2ª", "https://reddit.com/x/", "2026-09-20T10:00:00+00:00"),
        ]),
    })
    [m] = buscar_mencoes("Alpargatas", ("investimentos",), cliente=fake, pausa_segundos=0.0)
    assert m.titulo.endswith("2ª")


def test_buscar_mencoes_propaga_erro_http_sem_engolir():
    class _ClienteQuebrado(_ClienteHTTPFake):
        def get(self, url, **kwargs):
            return _RespostaFake(b"", status=429)

    with pytest.raises(RuntimeError):
        buscar_mencoes("Havaianas", ("investimentos",), cliente=_ClienteQuebrado(), pausa_segundos=0.0)


def test_buscar_mencoes_pausa_entre_subreddits(monkeypatch):
    pausas = []
    monkeypatch.setattr("social_arbitrage.deteccao_reddit.time.sleep", lambda s: pausas.append(s))
    fake = _ClienteHTTPFake()
    buscar_mencoes("Havaianas", ("a", "b", "c"), cliente=fake, pausa_segundos=2.5)
    assert pausas == [2.5, 2.5]


# ---------------------------------------------------------------------------
# Google Trends -- fake do cliente pytrends
# ---------------------------------------------------------------------------

class _ClienteTrendsFake:
    def __init__(self, serie: list[int], termo: str):
        self._serie = serie
        self._termo = termo

    def build_payload(self, termos, *, geo, timeframe):
        assert termos == [self._termo]

    def interest_over_time(self) -> pd.DataFrame:
        return pd.DataFrame({self._termo: self._serie})


def test_consultar_interesse_calcula_razao_pico():
    # 8 pontos de media=10, ultimo ponto=40 -> razao=4.0, em_pico True
    serie = [10] * 8 + [40]
    sinal = consultar_interesse("Havaianas", cliente=_ClienteTrendsFake(serie, "Havaianas"))
    assert isinstance(sinal, SinalTendencia)
    assert sinal.interesse_atual == 40
    assert sinal.media_movel_recente == pytest.approx(10.0)
    assert sinal.razao_pico == pytest.approx(4.0)
    assert sinal.em_pico is True


def test_consultar_interesse_sem_pico_quando_estavel():
    serie = [10] * 9
    sinal = consultar_interesse("Havaianas", cliente=_ClienteTrendsFake(serie, "Havaianas"))
    assert sinal.razao_pico == pytest.approx(1.0)
    assert sinal.em_pico is False


def test_consultar_interesse_lanca_quando_serie_vazia():
    class _ClienteVazio:
        def build_payload(self, termos, *, geo, timeframe):
            pass

        def interest_over_time(self):
            return pd.DataFrame()

    with pytest.raises(RuntimeError):
        consultar_interesse("termo-sem-dado", cliente=_ClienteVazio())


def test_consultar_interesse_lanca_quando_serie_curta_demais():
    with pytest.raises(RuntimeError):
        consultar_interesse("Havaianas", janela_media_semanas=8, cliente=_ClienteTrendsFake([10, 20, 30], "Havaianas"))
