"""`win_busca_lucro_g36_retangulo_ema34_stop_largo` — Geração 36 (CURIOSIDADE
do dono, 2026-10-06): e se, em vez de apertar o stop (G35, piorou), o stop
for AFASTADO? Alvo fica parado em 0,90x a largura.

ATENÇÃO: com stop > 0,45x o alvo deixa de ser 2x o stop -- fura o piso do
mandato (`MULTIPLO_MINIMO`=2). Por isso esta classe baixa o piso para
1,0x (stop sempre MENOR que o alvo; perda>=ganho continua proibido) e é
teste de curiosidade, não candidata.

`passo_barras=None`: stop fixo em `stop_fracao_largura`.
`passo_barras=N`: stop "que se afasta" -- começa em `stop_inicial` (0,45x) e
abre +`passo_fracao` x largura a cada N velas fechadas desde o fill, até
`stop_fracao_largura` (o teto). O motor nunca afrouxa stop nativo, então o
stop NATIVO fica no teto (proteção de catástrofe) e o nível que se afasta é
checado no FECHAMENTO da vela: fechou além dele -> sai a mercado na abertura
seguinte (`Exit`).
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import Bar, Exit, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g29_retangulo_ema34_congelado_v29 import (
    WinBuscaLucroG29RetanguloEma34CongeladoV29,
)


class WinBuscaLucroG36RetanguloEma34StopLargo(WinBuscaLucroG29RetanguloEma34CongeladoV29):
    name = "win_busca_lucro_g36_retangulo_ema34_stop_largo"
    version = "1.0.0"
    MULTIPLO_MINIMO = 1.0

    def __init__(self, passo_barras: int | None = None, stop_inicial: float = 0.45,
                 passo_fracao: float = 0.10, **kwargs) -> None:
        super().__init__(**kwargs)
        if self.stop_fracao_largura >= self.alvo_fracao_largura:
            raise ValueError("stop >= alvo: perda>=ganho é proibido")
        self.passo_barras = passo_barras
        self.stop_inicial = stop_inicial
        self.passo_fracao = passo_fracao
        self._pos_id = None
        self._largura = None
        self._barras = 0

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not positions:
            self._pos_id = None
            return acoes
        if self.passo_barras is None:
            return acoes
        pos = positions[0]
        if self._pos_id != pos.entry_ts:
            self._pos_id = pos.entry_ts
            self._largura = abs(pos.entry_price - pos.current_stop) / self.stop_fracao_largura
            self._barras = 0
        if ts <= pos.entry_ts:
            return acoes
        self._barras += 1
        frac = min(self.stop_inicial + self.passo_fracao * (self._barras // self.passo_barras),
                   self.stop_fracao_largura)
        s = 1.0 if pos.side == "long" else -1.0
        nivel = pos.entry_price - s * frac * self._largura
        if s * (bar.close - nivel) <= 0:
            return list(acoes) + [Exit(reason=f"g36_stop_que_se_afasta_{frac:.2f}")]
        return acoes
