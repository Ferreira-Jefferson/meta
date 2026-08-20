"""Painel de indicadores e `MarketSnapshot` — fonte UNICA para backtest e live.

Este modulo nasceu de uma extracao: `_enrich`/`_snapshot` moravam privados
dentro de `backtest/engine.py` e so o backtest gravava contexto de sinal
(`signal_snapshots`). Quando a operacao ao vivo passou a registrar o mesmo
contexto (tabela `live_signal_snapshots`), duplicar o calculo seria o pior
resultado possivel: o objetivo INTEIRO de anotar o snapshot ao vivo e poder
comparar "o que o robo viu no dia da compra real" com "o que o backtest viu
naquela mesma situacao". Duas implementacoes de MM200 que divergem por um
`min_periods` tornam essa comparacao mentira — e uma mentira dificil de
detectar, porque os numeros ficam PARECIDOS, nao errados na cara.

Entao mora aqui, em `core/`, porque e genuinamente compartilhado (regra 5 do
AGENTS.md): `backtest/` (feature) e `live/` (orquestracao) importam os dois
daqui, e nenhuma das duas camadas recalcula nada por conta propria.

Nao ha decisao aqui — nada neste modulo escolhe comprar ou vender. E leitura
de mercado transformada em numero, o que mantem o registro ao vivo dentro da
regra 6 do AGENTS.md ("nenhuma regra de decisao em `live/`"): o runtime pode
chamar isto para ANOTAR sem virar dono de nenhuma regra.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.indicators import (
    atr,
    cross_up,
    days_since_last_true,
    historical_volatility,
    ifr,
    rolling_correlation,
    rolling_high,
    rolling_low,
    sma,
)
from core.models import MarketSnapshot

# Nomes das colunas que `enrich_features` anexa. Exportado porque quem chama
# `snapshot_from_row` precisa saber que a linha tem de vir de um DataFrame
# enriquecido — passar uma linha OHLCV crua nao levanta erro, so devolve um
# snapshot cheio de zeros (ver o default de `_f`), que e exatamente o tipo de
# dado silenciosamente inutil que o diario nao deve acumular.
FEATURE_COLUMNS: tuple[str, ...] = (
    "mm20", "mm50", "mm200", "mm50_over_mm200_pct", "days_since_cross",
    "ifr14", "atr14", "hvol30", "high_52w", "low_52w", "dist_from_high",
    "dist_from_low", "volume_avg20", "volume_vs_avg20", "ibov_close",
    "ibov_mm200", "ibov_above_mm200", "ibov_trend_strength", "corr_ibov_60d",
)


def enrich_features(df: pd.DataFrame, ibov: pd.DataFrame) -> pd.DataFrame:
    """Anexa as colunas de indicadores usadas para preencher o `MarketSnapshot`.

    `df` e o OHLCV de UM ticker; `ibov` e o painel do benchmark, reindexado
    para o calendario de `df` com `ffill` (o benchmark pode ter pregao que o
    papel nao teve, e vice-versa). Devolve uma copia — nunca muta a entrada.
    """
    close = df["close"]
    out = df.copy()
    out["mm20"] = sma(close, 20)
    out["mm50"] = sma(close, 50)
    out["mm200"] = sma(close, 200)
    out["mm50_over_mm200_pct"] = out["mm50"] / out["mm200"] - 1.0

    cross_events = cross_up(out["mm50"], out["mm200"])
    out["days_since_cross"] = days_since_last_true(cross_events)
    out["ifr14"] = ifr(close, 14)
    out["atr14"] = atr(df["high"], df["low"], close, 14)
    out["hvol30"] = historical_volatility(close, 30)
    out["high_52w"] = rolling_high(close, 252)
    out["low_52w"] = rolling_low(close, 252)
    out["dist_from_high"] = close / out["high_52w"] - 1.0
    out["dist_from_low"] = close / out["low_52w"] - 1.0
    out["volume_avg20"] = df["volume"].rolling(20, min_periods=20).mean()
    out["volume_vs_avg20"] = df["volume"] / out["volume_avg20"]

    ibov_close = ibov["close"].reindex(df.index).ffill()
    out["ibov_close"] = ibov_close
    out["ibov_mm200"] = sma(ibov_close, 200)
    out["ibov_above_mm200"] = ibov_close > out["ibov_mm200"]
    out["ibov_trend_strength"] = ibov_close / out["ibov_mm200"] - 1.0
    out["corr_ibov_60d"] = rolling_correlation(
        close.pct_change(), ibov_close.pct_change(), 60
    )
    return out


def snapshot_from_row(row: pd.Series) -> MarketSnapshot:
    """Uma linha do DataFrame enriquecido -> `MarketSnapshot`.

    NaN vira 0.0 de proposito: o snapshot e registro de auditoria, e uma
    linha faltando (papel com menos de 200 pregoes, por exemplo) nao pode
    derrubar a gravacao do trade que de fato aconteceu.
    """
    def _f(k, default=0.0):
        v = row.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        return float(v) if not isinstance(v, bool) else bool(v)

    return MarketSnapshot(
        close=_f("close"),
        volume=_f("volume"),
        volume_vs_avg20=_f("volume_vs_avg20"),
        mm20=_f("mm20"),
        mm50=_f("mm50"),
        mm200=_f("mm200"),
        mm50_over_mm200_pct=_f("mm50_over_mm200_pct"),
        days_since_cross=int(row.get("days_since_cross") or 0),
        ifr14=_f("ifr14"),
        atr14=_f("atr14"),
        historical_vol_30d=_f("hvol30"),
        distance_from_52w_high_pct=_f("dist_from_high"),
        distance_from_52w_low_pct=_f("dist_from_low"),
        ibov_close=_f("ibov_close"),
        ibov_mm200=_f("ibov_mm200"),
        ibov_above_mm200=bool(row.get("ibov_above_mm200") or False),
        ibov_trend_strength=_f("ibov_trend_strength"),
        correlation_with_ibov_60d=_f("corr_ibov_60d"),
    )
