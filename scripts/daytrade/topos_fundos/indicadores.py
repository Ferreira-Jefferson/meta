"""Médias móveis e osciladores (funções puras sobre séries; só barras fechadas)."""
import numpy as np
import pandas as pd


def mms(s, n):
    return s.rolling(n).mean()


def mme(s, n):
    return s.ewm(span=n, adjust=False).mean()


def inclinacao(m, barras=3):
    """+1 subindo, -1 caindo: média agora contra a média de `barras` atrás."""
    return np.sign(m - m.shift(barras))


def estocastico(b, n=14, suav=3):
    """%K lento: (close - mínima de n) / (máxima de n - mínima de n), suavizado por `suav`."""
    ll, hh = b.low.rolling(n).min(), b.high.rolling(n).max()
    return (100 * (b.close - ll) / (hh - ll).replace(0, np.nan)).rolling(suav).mean()


def tendencia(close, rapida=9, media=21, lenta=34):
    """+1 alta (close > MME lenta e MME rápida > MME média), -1 baixa (espelho), 0 neutro."""
    r, m, l = mme(close, rapida), mme(close, media), mme(close, lenta)
    up = (close > l) & (r > m)
    dn = (close < l) & (r < m)
    return pd.Series(np.where(up, 1, np.where(dn, -1, 0)), index=close.index)
