"""`win_busca_lucro_g27_retangulo_tendencia_maior` — Geração 27 da busca por
EA lucrativo de day trade do WIN (`scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/`, ver `ORQUESTRACAO.md`).

## Por que esta geração existe

A G26 testou um filtro de tendência CRU (sinal de `close[-1]-close[-W]`) e
não se confirmou no OOS-1. O dono pediu então algo mais estrutural, nas
palavras dele: "ver em M15 ou H1 se o retângulo de M1 é um recuo de
tendência num gráfico maior" — ou seja, não um drift genérico, mas uma
medida de tendência de verdade no tempo gráfico maior, para ver se o
retângulo de 20 minutos é só uma PAUSA dentro de um movimento maior (e
nesse caso operar a favor desse movimento) em vez de um drift arbitrário.

Reaproveita, sem reimplementar, as 3 medidas de tendência JÁ VALIDADAS como
causais na Fase 2 desta busca (`rodada5/tendencia/base.py`, usadas nas
regras R43-R47 de `REGRAS.md`):
  - `i_m15`: inclinação da EMA20 amostrada em M15 (sobe/desce/plana).
  - `i_h1` : idem em H1.
  - `i_leg`: direção da pernada de 750 pts em curso (zigzag intra-vela M1).

Pré-computadas uma vez por `g27_prep.py` em
`g27_tendencia_m15h1/tendencia_m15_h1_leg.pkl` (DataFrame indexado por
Timestamp M1, causal -- cada linha só usa dados até aquele instante).

## O que esta classe faz

Subclasse de `WinBuscaLucroG21Retangulo1000`, mesmo padrão da G26: nenhuma
lógica de detecção/geometria reimplementada, só intercepta a ação
`EnterLimit` do pai e descarta quando o lado conflita com a tendência
escolhida. `medida` ∈ {"i_m15", "i_h1", "i_leg", "m15_h1"} -- a última exige
CONCORDÂNCIA entre M15 e H1 (os dois concordam e não-zero) para contar como
tendência clara; discorda ou algum neutro => tendência=0.

`estrito=False` (default): tendência neutra (0) deixa passar os dois
lados -- só bloqueia quando há tendência OPOSTA clara. `estrito=True`: só
entradas com tendência a favor clara passam.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)

PKL = Path(__file__).resolve().parents[4] / "scripts" / "daytrade" / "win_pernadas_exploracao" \
    / "ea_busca_lucro" / "g27_tendencia_m15h1" / "tendencia_m15_h1_leg.pkl"

MEDIDAS_VALIDAS = ("i_m15", "i_h1", "i_leg", "m15_h1")

_CACHE: dict = {}


def _tendencias() -> pd.DataFrame:
    if "df" not in _CACHE:
        _CACHE["df"] = pd.read_pickle(PKL)
    return _CACHE["df"]


class WinBuscaLucroG27RetanguloTendenciaMaior(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g27_retangulo_tendencia_maior"
    version = "1.0.0"

    def __init__(self, medida: str = "i_m15", estrito: bool = False, **kwargs) -> None:
        if medida not in MEDIDAS_VALIDAS:
            raise ValueError(f"medida={medida!r} inválida: {MEDIDAS_VALIDAS}")
        super().__init__(**kwargs)
        self.medida = medida
        self.estrito = bool(estrito)
        df = _tendencias()
        if medida == "m15_h1":
            m15, h1 = df["i_m15"], df["i_h1"]
            self._serie = ((m15 == h1) & (m15 != 0)).astype(int) * m15
        else:
            self._serie = df[medida]

    def _tendencia(self, ts: pd.Timestamp) -> int:
        try:
            v = self._serie.at[ts]
        except KeyError:
            return 0
        return int(v) if v == v else 0

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes

        tendencia = self._tendencia(ts)
        filtradas: list[IntradayAction] = []
        for acao in acoes:
            lado = getattr(acao, "side", None)
            if lado is None:
                filtradas.append(acao)
                continue
            sinal_lado = 1 if lado == "long" else -1
            if self.estrito:
                passa = (tendencia == sinal_lado)
            else:
                passa = (tendencia == 0) or (tendencia == sinal_lado)
            if passa:
                filtradas.append(acao)
        return filtradas
