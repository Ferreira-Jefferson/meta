# -*- coding: utf-8 -*-
"""Pre-computa (uma vez, offline) 3 TIPOS de media movel do WIN@ M1, em 5
periodos -- 21/34/55/68/100 -- pedido do dono: "verifique se faz diferenca
mudar o tipo de MM pra simples, exponencial, aritmetica" + testes com 2 MMs
(34+68, 34+100) e 3 MMs (34+68+100).

Nota de nomenclatura: "media aritmetica" e "media simples" sao o MESMO
calculo (SMA) em finance -- nao sao dois tipos diferentes. Os 3 tipos de
verdade, calculados aqui:
  - sma: media simples / aritmetica (janela deslizante, peso igual).
  - ema: exponencial (ja' usada em G29-G32, peso maior no recente).
  - wma: media movel ponderada LINEAR (peso cresce linear do mais antigo
    pro mais recente dentro da janela -- meio caminho entre SMA e EMA).

Todas causais (so' usam o passado: `rolling`/`ewm` padrao do pandas).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

OUT = Path(__file__).parent / "mm_m1.pkl"
PERIODOS = (21, 34, 55, 68, 100)


def wma(serie: pd.Series, periodo: int) -> pd.Series:
    pesos = np.arange(1, periodo + 1, dtype=float)
    return serie.rolling(periodo).apply(lambda x: np.dot(x, pesos) / pesos.sum(), raw=True)


def main() -> None:
    win = g05b.carrega_win()
    close = win["close"]
    out = {}
    for p in PERIODOS:
        out[f"sma{p}"] = close.rolling(p).mean()
        out[f"ema{p}"] = close.ewm(span=p, adjust=False).mean()
        out[f"wma{p}"] = wma(close, p)
        print(f"período {p} pronto", flush=True)
    df = pd.DataFrame(out)
    df.to_pickle(OUT)
    print(f"Salvo em {OUT} ({len(df)} linhas, {OUT.stat().st_size/1_048_576:.2f} MB)")
    print(df.tail(2))


if __name__ == "__main__":
    main()
