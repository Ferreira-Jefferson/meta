"""`win_busca_lucro_g33_retangulo_multiplas_mm` — Geração 33 da busca por EA
lucrativo de day trade do WIN (ver `ORQUESTRACAO.md`).

## Pedido do dono (2026-10-05)

"Teste com mais MM, verifique se faz diferença mudar o tipo de MM pra
simples, exponencial, aritmética, etc. Testes com duas MM em períodos
diferentes (34+68, 34+100). Teste com 3 MM em períodos diferentes
(34+68+100)."

Nota: "média aritmética" e "média simples" são o MESMO cálculo (SMA) em
finanças — não dois tipos. Os 3 tipos de verdade testados (`g33_prep.py`):
`sma` (simples/aritmética), `ema` (exponencial, usada em G29-G32), `wma`
(ponderada linear — meio caminho entre as duas).

## O que esta classe faz

Generaliza a regra da G29 (só fechamento) para N médias em vez de 1:
compra só passa se o fechamento está NA OU ACIMA de TODAS as médias da
lista; venda só se está na ou abaixo de TODAS. Uma lista com 1 média
reproduz exatamente a G29 (serve para comparar tipo sem mudar mais nada);
2 ou 3 médias testam se EXIGIR CONCORDÂNCIA entre escalas ajuda.

`mms`: lista de pares `(tipo, periodo)`, ex. `[("ema", 34)]` (G29),
`[("ema", 34), ("ema", 68)]` (2 médias), `[("ema", 34), ("ema", 68),
("ema", 100)]` (3 médias). Médias pré-computadas em
`g33_multiplas_mm/mm_m1.pkl` (períodos 21/34/55/68/100, tipos sma/ema/wma).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)

PKL = Path(__file__).resolve().parents[4] / "scripts" / "daytrade" / "win_pernadas_exploracao" \
    / "ea_busca_lucro" / "g33_multiplas_mm" / "mm_m1.pkl"

TIPOS_VALIDOS = ("sma", "ema", "wma")
PERIODOS_VALIDOS = (21, 34, 55, 68, 100)

_CACHE: dict = {}


def _mms() -> pd.DataFrame:
    if "df" not in _CACHE:
        _CACHE["df"] = pd.read_pickle(PKL)
    return _CACHE["df"]


class WinBuscaLucroG33RetanguloMultiplasMM(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g33_retangulo_multiplas_mm"
    version = "1.0.0"

    def __init__(self, mms: list[tuple[str, int]] = (("ema", 34),), **kwargs) -> None:
        if not mms:
            raise ValueError("mms vazio: precisa de pelo menos 1 média")
        for tipo, periodo in mms:
            if tipo not in TIPOS_VALIDOS:
                raise ValueError(f"tipo={tipo!r} inválido: {TIPOS_VALIDOS}")
            if periodo not in PERIODOS_VALIDOS:
                raise ValueError(f"periodo={periodo!r} inválido: {PERIODOS_VALIDOS}")
        super().__init__(**kwargs)
        self.mms = tuple(mms)
        df = _mms()
        self._series = [df[f"{tipo}{periodo}"] for tipo, periodo in self.mms]
        self._ultimo_close: float | None = None

    def _valores_em(self, ts: pd.Timestamp) -> list[float] | None:
        vals = []
        for s in self._series:
            try:
                v = s.at[ts]
            except KeyError:
                return None
            if v != v:
                return None
            vals.append(float(v))
        return vals

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._ultimo_close = bar.close
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes

        vals = self._valores_em(ts)
        if vals is None:
            return []

        filtradas: list[IntradayAction] = []
        for acao in acoes:
            lado = getattr(acao, "side", None)
            if lado is None:
                filtradas.append(acao)
                continue
            if lado == "long":
                passa = all(self._ultimo_close >= v for v in vals)
            else:
                passa = all(self._ultimo_close <= v for v in vals)
            if passa:
                filtradas.append(acao)
        return filtradas
