"""Conector Google Trends (via `pytrends`) -- interesse de busca por termo no
Brasil, para detectar pico ANTES do mercado notar. Sem credencial nenhuma
(nao ha API oficial do Google para isto -- `pytrends` le a mesma interface
publica que trends.google.com mostra no navegador), mas por ser nao-oficial
pode ser bloqueado/instavel sob uso intenso -- espace as chamadas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


class _ClienteTrends(Protocol):
    def build_payload(self, termos: list[str], *, geo: str, timeframe: str) -> None: ...
    def interest_over_time(self) -> pd.DataFrame: ...


@dataclass(frozen=True)
class SinalTendencia:
    """`razao_pico` > 1 indica interesse ACIMA do normal recente -- e' o
    numero a olhar, nao `interesse_atual` sozinho (que o Trends ja normaliza
    de 0 a 100 por si so' e nao diz se e' alto PARA AQUELE termo)."""

    termo: str
    interesse_atual: int
    media_movel_recente: float
    razao_pico: float

    @property
    def em_pico(self) -> bool:
        """Heuristica simples (limiar 2.0 = interesse atual pelo menos o
        DOBRO da media recente), documentada aqui porque NUNCA foi calibrada
        contra um resultado real (n=0 medido) -- trate como ponto de partida
        ajustavel, nao como threshold validado."""
        return self.razao_pico >= 2.0


def consultar_interesse(
    termo: str,
    *,
    geo: str = "BR",
    janela_media_semanas: int = 8,
    cliente: _ClienteTrends | None = None,
) -> SinalTendencia:
    """Interesse de busca de `termo` nas ultimas ~12 semanas (`timeframe`
    fixo em "today 3-m" -- e' o que o Trends agrega em pontos SEMANAIS,
    granularidade diaria so' aparece em janelas menores que 3 meses e
    complicaria a media movel sem ganho real aqui), contra a media das
    `janela_media_semanas` anteriores ao ultimo ponto.

    `RuntimeError` quando o Trends nao devolve dado (termo raro demais para
    ter serie, geo invalido, ou bloqueio de taxa) -- nunca um sinal
    fabricado (`razao_pico=0` seria indistinguivel de "interesse zero de
    verdade")."""
    if cliente is None:
        from pytrends.request import TrendReq
        cliente = TrendReq(hl="pt-BR", tz=180)
    cliente.build_payload([termo], geo=geo, timeframe="today 3-m")
    df = cliente.interest_over_time()
    if df.empty or termo not in df.columns:
        raise RuntimeError(
            f"Google Trends nao devolveu serie para termo={termo!r} geo={geo!r} -- "
            f"termo raro demais, geo invalido, ou bloqueio de taxa do pytrends."
        )
    serie = df[termo]
    if len(serie) < janela_media_semanas + 1:
        raise RuntimeError(
            f"serie de {termo!r} tem so' {len(serie)} pontos -- precisa de pelo menos "
            f"{janela_media_semanas + 1} para a media movel de {janela_media_semanas} semanas."
        )
    interesse_atual = int(serie.iloc[-1])
    media_movel = float(serie.iloc[-(janela_media_semanas + 1):-1].mean())
    razao = (interesse_atual / media_movel) if media_movel > 0 else float("inf")
    return SinalTendencia(
        termo=termo, interesse_atual=interesse_atual,
        media_movel_recente=media_movel, razao_pico=razao,
    )
