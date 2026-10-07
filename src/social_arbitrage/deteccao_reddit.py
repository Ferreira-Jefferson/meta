"""Conector Reddit -- busca marcas/termos em subreddits BR, dado bruto para
alimentar `thesis.Fase.DETECTADA` (a decisao de abrir tese continua manual --
ver `scripts/social_arbitrage_monitorar.py`).

## RSS, nao a API JSON -- e por que

Testado ao vivo em 2026-09-27: o endpoint JSON sem autenticacao
(`reddit.com/r/.../search.json`) devolve **403** -- exigiria cadastro de app
OAuth, que o dono decidiu nao fazer. O feed **RSS/Atom** do mesmo mecanismo
de busca (`reddit.com/r/.../search.rss`) devolve **200 com resultado real**,
sem credencial nenhuma -- confirmado com uma thread genuina sobre Alpargatas
(ALPA4)/Havaianas retornada de verdade nesse teste. RSS e' um formato de
publicacao que o Reddit ainda serve abertamente (nao e' burlar bloqueio, e'
usar canal que a propria plataforma disponibiliza).

Duas limitacoes reais deste caminho, medidas ao vivo, nao hipoteticas:

  * **Taxa de acesso mais apertada e imprevisivel que a API OAuth.** Duas
    chamadas seguidas sem pausa ja devolveram 429; com ~20-30s de intervalo,
    voltou a funcionar. Por isso `buscar_mencoes` aceita `pausa_segundos`
    entre subreddits (default 3s) -- e o chamador (`social_arbitrage_
    monitorar.py`) ainda deve espacar entre MARCAS tambem.
  * **Sem `score`/upvotes.** O Atom do Reddit nao inclui essa informacao
    (so' a API OAuth tem) -- `Mencao` nao tem esse campo aqui.

Parse via `resposta.content` (bytes), nunca `.text`: `requests` as vezes
adivinha a codificacao errada a partir dos headers, e o XML ja declara a
propria codificacao (`ET.fromstring` sobre bytes respeita isso direto).
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import requests

_NS = {"atom": "http://www.w3.org/2005/Atom"}

_USER_AGENT = "social-arbitrage-detector/0.1 (uso pessoal, pesquisa nao-comercial, ver social_arbitrage/deteccao_reddit.py)"


class _HTTPClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class Mencao:
    """Um resultado de busca -- dado BRUTO, nao uma tese. So' vira
    `thesis.Evidencia`/`Thesis` depois de uma decisao humana."""

    subreddit: str
    titulo: str
    url: str
    criado_em: datetime
    termo_buscado: str


def _parsear_entrada(entrada: ET.Element, subreddit: str, termo: str) -> Mencao | None:
    titulo_el = entrada.find("atom:title", _NS)
    link_el = entrada.find("atom:link", _NS)
    publicado_el = entrada.find("atom:published", _NS)
    if titulo_el is None or titulo_el.text is None or link_el is None or publicado_el is None or publicado_el.text is None:
        return None
    return Mencao(
        subreddit=subreddit,
        titulo=titulo_el.text,
        url=link_el.get("href", ""),
        criado_em=datetime.fromisoformat(publicado_el.text),
        termo_buscado=termo,
    )


def buscar_mencoes(
    termo: str,
    subreddits: tuple[str, ...],
    *,
    cliente: _HTTPClient | None = None,
    limite_por_subreddit: int = 25,
    pausa_segundos: float = 3.0,
) -> list[Mencao]:
    """Busca `termo` (marca/produto) em cada um de `subreddits` via RSS
    publico -- sem credencial. Falha de rede/HTTP propaga
    (`raise_for_status`) -- nunca vira lista vazia silenciosa, que seria
    indistinguivel de "nao achou nada". Uma pausa de `pausa_segundos` entre
    CADA subreddit (nao so' entre marcas -- ver a nota de rate-limit na
    docstring do modulo)."""
    cliente = cliente or requests
    mencoes: list[Mencao] = []
    for i, subreddit in enumerate(subreddits):
        if i > 0:
            time.sleep(pausa_segundos)
        resposta = cliente.get(
            f"https://www.reddit.com/r/{subreddit}/search.rss",
            params={"q": termo, "restrict_sr": 1, "sort": "new", "limit": limite_por_subreddit},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        resposta.raise_for_status()
        raiz = ET.fromstring(resposta.content)
        for entrada in raiz.findall("atom:entry", _NS):
            mencao = _parsear_entrada(entrada, subreddit, termo)
            if mencao is not None:
                mencoes.append(mencao)
    return mencoes
