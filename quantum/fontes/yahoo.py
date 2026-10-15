"""Yahoo Finance via yfinance (gratuito): preços diários, proventos e desdobramentos.

Cada ticker vira um CSV bruto em `brutos/yahoo/precos/<TICKER>.csv`, com as
colunas exatamente como o yfinance devolve. Rebaixa a série inteira a cada
atualização: o `Adj Close` muda para TRÁS toda vez que sai um provento novo,
então colar só os dias novos deixaria a série com dois ajustes misturados.

Limitação conhecida: o Yahoo quase não guarda ticker deslistado. Empresas que
saíram da bolsa somem do universo do passado (viés de sobrevivência). O painel
mostra a cobertura por data para isso não ficar escondido.
"""
from __future__ import annotations

import time

import pandas as pd
import yfinance as yf

from .. import config
from . import arquivo

CAMPOS = {"Close": "close", "Adj Close": "adj_close", "Volume": "volume",
          "Dividends": "dividendo", "Stock Splits": "split"}


def _yahoo(ticker: str) -> str:
    return ticker if ticker.startswith("^") else f"{ticker}.SA"


def _arquivo(ticker: str):
    return arquivo.caminho("yahoo", "precos", f"{ticker.replace('^', 'IDX_')}.csv")


def baixar_lote(tickers: list[str], inicio: str = config.INICIO_PRECOS, progresso=print) -> dict[str, pd.DataFrame]:
    """Baixa em lotes; devolve {ticker: DataFrame} e salva cada CSV bruto."""
    saida: dict[str, pd.DataFrame] = {}
    lote = 40
    for i in range(0, len(tickers), lote):
        parte = tickers[i:i + lote]
        for tentativa in range(3):
            try:
                df = yf.download([_yahoo(t) for t in parte], start=inicio, auto_adjust=False,
                                 actions=True, group_by="ticker", threads=True, progress=False)
                break
            except Exception as e:  # yfinance levanta tipos variados em falha de rede
                if tentativa == 2:
                    progresso(f"  yahoo: lote {i // lote + 1} falhou ({e})")
                    df = pd.DataFrame()
                time.sleep(5)
        for t in parte:
            y = _yahoo(t)
            if isinstance(df.columns, pd.MultiIndex) and y in df.columns.get_level_values(0):
                sub = df[y].dropna(subset=["Close"])
                if len(sub):
                    p = _arquivo(t)
                    sub.to_csv(p, index_label="Date")
                    arquivo.registrar(p, "yahoo", f"yfinance:{y}")
                    saida[t] = sub
        progresso(f"  yahoo: {min(i + lote, len(tickers))}/{len(tickers)} tickers, {len(saida)} com dados")
    return saida


def para_tabela(ticker: str, df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns=CAMPOS)[list(CAMPOS.values())].copy()
    out.index = pd.to_datetime(out.index).strftime("%Y-%m-%d")
    out = out.reset_index().rename(columns={"index": "data", "Date": "data"})
    out.insert(0, "ticker", ticker)
    return out


def ler_bruto(ticker: str) -> pd.DataFrame | None:
    p = _arquivo(ticker)
    if not p.exists():
        return None
    return pd.read_csv(p, index_col="Date")
