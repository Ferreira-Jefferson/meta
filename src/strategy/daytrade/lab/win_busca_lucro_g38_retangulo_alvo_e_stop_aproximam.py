"""`win_busca_lucro_g38_retangulo_alvo_e_stop_aproximam` — Geração 38
(pergunta do dono, 2026-10-06): sobre o padrão G37 (alvo que se aproxima a
cada 5 velas), o STOP também se aproxima da entrada no mesmo relógio?

A cada passo do alvo (k = quantos passos o alvo já deu), o stop vai para
`stop_fracao_largura - stop_passo*k` x largura, nunca abaixo de `stop_piso`.
Diferente da G35 (stop guiado pelo preço andar a favor): aqui o gatilho é o
TEMPO, o mesmo do alvo. O motor só aceita stop mais protetor; se o preço já
estiver além do stop novo, a próxima vela o executa.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import AdjustStop, AdjustTarget, Bar, IntradayAction, IntradayOpenPosition, no_tick
from strategy.daytrade.lab.win_busca_lucro_g37_retangulo_ema34_alvo_aproxima_congelado_v37 import (
    WinBuscaLucroG37RetanguloEma34AlvoAproximaCongeladoV37,
)


class WinBuscaLucroG38RetanguloAlvoEStopAproximam(WinBuscaLucroG37RetanguloEma34AlvoAproximaCongeladoV37):
    name = "win_busca_lucro_g38_retangulo_alvo_e_stop_aproximam"
    version = "1.0.0"

    def __init__(self, stop_passo: float = 0.05, stop_piso: float = 0.05, **kwargs) -> None:
        super().__init__(**kwargs)
        self.stop_passo = stop_passo
        self.stop_piso = stop_piso

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if self.stop_passo <= 0 or not positions or not any(isinstance(a, AdjustTarget) for a in acoes):
            return acoes
        pos = positions[0]
        k = round((self.alvo_fracao_largura - self._frac_atual) / self.passo_fracao)
        frac = max(self.stop_fracao_largura - self.stop_passo * k, self.stop_piso)
        s = 1.0 if pos.side == "long" else -1.0
        novo = no_tick(pos.entry_price - s * frac * self._largura, self.tick_size)
        if pos.current_stop is None or s * (novo - pos.current_stop) > 0:
            return list(acoes) + [AdjustStop(new_stop=novo)]
        return acoes
