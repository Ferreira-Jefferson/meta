"""Carga de dados para a varredura Raschke (I/O isolado do nucleo).

Fontes:
  * WIN@D / WDO@D (CSV M5/M1 exportado do MT5, ajuste por diferenca) -> M5/M15/H1/D1
  * acoes B3 diarias (data/raw/*.parquet, yfinance, ajustadas por adj_close)
  * indices / ETFs / Bitcoin: puxados do MT5 da Rico (cache em data/raschke/)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .nucleo import Barras, Custo

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raschke"
CSV_WIN_M5 = RAIZ / "data" / "wdo-mt5" / "WIN@D_M5_202110010900_202610011715.csv"
CSV_WDO_M1 = RAIZ / "data" / "wdo-mt5" / "WDO@D_M1_202109290900_202609291020.csv"

#: Corte IS/OOS unico para todos os ativos (entrada do trade antes = IS).
CORTE_OOS = pd.Timestamp("2024-07-01")


def _csv_mt5(p: Path) -> pd.DataFrame:
    d = pd.read_csv(p, sep="\t")
    d.columns = [c.strip("<>").lower() for c in d.columns]
    idx = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")
    d = d.set_index(idx)[["open", "high", "low", "close"]].astype(float)
    d.columns = ["o", "h", "l", "c"]
    return d.sort_index()


def _resample(d: pd.DataFrame, regra: str) -> pd.DataFrame:
    # janelas alinhadas ao inicio do pregao (09:00) -> origin do dia
    r = d.resample(regra, origin="start_day", offset="9h" if regra.endswith("h") else "0min").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    return r


def para_barras(d: pd.DataFrame, intraday: bool, barras_por_hora: int = 12) -> tuple[Barras, pd.DatetimeIndex]:
    idx = d.index
    dias = idx.strftime('%Y%m%d').astype(int).to_numpy()
    minuto = (idx.hour * 60 + idx.minute).to_numpy()
    b = Barras(d["o"].to_numpy(), d["h"].to_numpy(), d["l"].to_numpy(), d["c"].to_numpy(),
               dias, minuto, intraday, barras_por_hora)
    return b, idx


def intraday_futuro(simbolo: str, tf: str) -> tuple[Barras, pd.DatetimeIndex]:
    """tf em {'M5','M15','H1'}; pregao 09:00-18:20, sem dado fora."""
    base = _csv_mt5(CSV_WIN_M5) if simbolo == "WIN" else _csv_mt5(CSV_WDO_M1)
    if simbolo == "WDO":
        base = _resample(base, "5min")
    base = base[(base.index.hour * 60 + base.index.minute) < 18 * 60 + 20]
    if tf == "M5":
        d, bph = base, 12
    elif tf == "M15":
        d, bph = _resample(base, "15min"), 4
    else:
        d, bph = _resample(base, "1h"), 1
    return para_barras(d, True, bph)


def diario_futuro(simbolo: str) -> tuple[Barras, pd.DatetimeIndex]:
    base = _csv_mt5(CSV_WIN_M5) if simbolo == "WIN" else _csv_mt5(CSV_WDO_M1)
    d = base.groupby(base.index.normalize()).agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    return para_barras(d, False)


def diario_acao(ticker: str) -> tuple[Barras, pd.DatetimeIndex] | None:
    p = RAIZ / "data" / "raw" / f"{ticker}.parquet"
    if not p.exists():
        return None
    f = pd.read_parquet(p)
    fator = (f["adj_close"] / f["close"]).to_numpy()
    d = pd.DataFrame({"o": f["open"].to_numpy() * fator, "h": f["high"].to_numpy() * fator,
                      "l": f["low"].to_numpy() * fator, "c": f["adj_close"].to_numpy()},
                     index=pd.DatetimeIndex(f.index)).dropna()
    d = d[(d["h"] >= d["l"]) & (d["l"] > 0)]
    return para_barras(d, False)


def diario_mt5(simbolo: str) -> tuple[Barras, pd.DatetimeIndex] | None:
    """D1 do MT5 da Rico, em cache parquet (rode `atualizar_cache_mt5` antes)."""
    p = CACHE / f"{simbolo.replace('@', '_')}_D1.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p)
    return para_barras(d, False)


def atualizar_cache_mt5(simbolos: list[str], anos_inicio: int = 2015) -> None:
    import datetime as dt

    import MetaTrader5 as mt5

    CACHE.mkdir(parents=True, exist_ok=True)
    mt5.initialize()
    for s in simbolos:
        mt5.symbol_select(s, True)
        r = mt5.copy_rates_range(s, mt5.TIMEFRAME_D1, dt.datetime(anos_inicio, 1, 1), dt.datetime(2026, 10, 5))
        if r is None or len(r) == 0:
            print(s, "sem dado", flush=True)
            continue
        d = pd.DataFrame(r)
        d.index = pd.to_datetime(d["time"], unit="s").dt.normalize()
        d = d[["open", "high", "low", "close"]]
        d.columns = ["o", "h", "l", "c"]
        d.to_parquet(CACHE / f"{s.replace('@', '_')}_D1.parquet")
        print(s, len(d), d.index[0].date(), flush=True)


def liquidas(n: int = 60, janela: int = 250) -> list[str]:
    """Acoes mais liquidas (financeiro medio diario nos ultimos `janela` pregoes)."""
    pontos = []
    for p in (RAIZ / "data" / "raw").glob("*_SA.parquet"):
        t = p.stem
        if t.startswith("_"):
            continue
        f = pd.read_parquet(p)
        if len(f) < 1500 or pd.Timestamp(f.index[-1]) < pd.Timestamp("2026-06-01"):
            continue
        pontos.append((float((f["close"] * f["volume"]).tail(janela).mean()), t))
    pontos.sort(reverse=True)
    return [t for _, t in pontos[:n]]


def custo_futuro(simbolo: str, tf: str) -> Custo:
    if simbolo == "WIN":
        return Custo(tick=5.0, valor_ponto=0.20, qty=1, fee_brl=0.50)
    return Custo(tick=0.5, valor_ponto=10.0, qty=1, fee_brl=0.50)


def custo_acao(preco_ref: float) -> Custo:
    """Lote padrao 100; B3: ~0,035% por lado; deslize 1 tick (R$0,01)."""
    return Custo(tick=0.01, valor_ponto=1.0, qty=100, fee_brl=0.0, pct_lado=0.00035)
