"""`win_busca_lucro_g30_retangulo_ema_corpo` — Geração 30 da busca por EA
lucrativo de day trade do WIN (ver `ORQUESTRACAO.md`).

## Pedido do dono (2026-10-05, depois de olhar o replay da G29)

Olhando uma operação perdedora bem perto da EMA34, o dono perguntou: "será
que se todo o CORPO da vela fechar acima ou abaixo [da EMA] melhora o
resultado?" — ou seja, a G29 só olha o FECHAMENTO contra a EMA; isso deixa
passar velas onde o corpo inteiro (abertura E fechamento) está dos dois
lados da linha (a vela "atravessa" a EMA), um sinal mais fraco/ambíguo do
que uma vela com o corpo inteiro de um só lado.

## O que esta classe faz

Subclasse de `WinBuscaLucroG21Retangulo1000` (mesmo padrão de G26-G29):
nenhuma lógica de detecção/geometria reimplementada. Em vez de comparar só
`bar.close` contra a EMA (G29), compara o CORPO INTEIRO da última vela:
`min(open, close)` e `max(open, close)`. Regra literal: venda só passa se
`max(open, close) <= EMA` (o corpo inteiro, inclusive a ponta mais alta
dele, fica na EMA ou abaixo); compra só passa se `min(open, close) >= EMA`
(o corpo inteiro fica na EMA ou acima). Mais estrita que a G29 por
construção — nunca deixa passar um caso que a G29 bloquearia, mas bloqueia
alguns que a G29 deixava passar (as velas que atravessam a EMA).

Reaproveita a MESMA EMA pré-computada da G29 (`g29_ema34/ema_m1.pkl`,
períodos 21/34/55) -- não recalcula nada.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)
from strategy.daytrade.lab.win_busca_lucro_g29_retangulo_ema34 import (
    PERIODOS_VALIDOS,
    _emas,
)


class WinBuscaLucroG30RetanguloEmaCorpo(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g30_retangulo_ema_corpo"
    version = "1.0.0"

    def __init__(self, periodo: int = 34, **kwargs) -> None:
        if periodo not in PERIODOS_VALIDOS:
            raise ValueError(f"periodo={periodo!r} inválido: {PERIODOS_VALIDOS}")
        super().__init__(**kwargs)
        self.periodo = int(periodo)
        self._ema = _emas()[f"ema{periodo}"]
        self._ultimo_open: float | None = None
        self._ultimo_close: float | None = None

    def _ema_em(self, ts: pd.Timestamp) -> float | None:
        try:
            v = self._ema.at[ts]
        except KeyError:
            return None
        return float(v) if v == v else None

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._ultimo_open = bar.open
        self._ultimo_close = bar.close
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes

        ema = self._ema_em(ts)
        if ema is None:
            return []

        corpo_topo = max(self._ultimo_open, self._ultimo_close)
        corpo_fundo = min(self._ultimo_open, self._ultimo_close)

        filtradas: list[IntradayAction] = []
        for acao in acoes:
            lado = getattr(acao, "side", None)
            if lado is None:
                filtradas.append(acao)
                continue
            # venda: corpo INTEIRO (topo incluído) na EMA ou abaixo.
            # compra: corpo INTEIRO (fundo incluído) na EMA ou acima.
            passa = (corpo_topo <= ema) if lado == "short" else (corpo_fundo >= ema)
            if passa:
                filtradas.append(acao)
        return filtradas
