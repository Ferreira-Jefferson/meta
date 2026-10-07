"""`win_busca_lucro_g41_retangulo_zera_cedo` — Geração 41 (pedido do dono,
2026-10-06): sobre o padrão G37, encerrar o dia mais cedo (ex. 17:00) em vez
de ficar posicionado até perto do fechamento.

`hora_zerar` (HH:MM, horário de Brasília da base M1): a última vela que
fecha antes desse horário dispara `Exit` (a mercado na abertura da vela das
HH:MM -- mesma saída da zeragem do EA). Novas entradas param `ttl_barras`
velas antes, para nenhuma limite pendente preencher depois do corte.
`hora_zerar=None` = padrão G37 sem corte próprio.

PADRÃO ATUAL desde 2026-10-06 (decisão do dono): `hora_zerar="17:00"` sobre o
G37 (retângulo + EMA34 + alvo que se aproxima). Porte MQL5:
`mt5/WinRetanguloEma34.mq5` v1.04.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

from strategy.daytrade.base import Bar, Exit, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g37_retangulo_ema34_alvo_aproxima_congelado_v37 import (
    WinBuscaLucroG37RetanguloEma34AlvoAproximaCongeladoV37,
)


class WinBuscaLucroG41RetanguloZeraCedoCongeladoV41(WinBuscaLucroG37RetanguloEma34AlvoAproximaCongeladoV37):
    name = "win_busca_lucro_g41_retangulo_zera_cedo_congelado_v41"
    version = "1.0.0"

    def __init__(self, hora_zerar: str | None = "17:00", **kwargs) -> None:
        super().__init__(**kwargs)
        if hora_zerar is None:
            self._corte = None
        else:
            h, m = (int(x) for x in hora_zerar.split(":"))
            self._corte = h * 60 + m

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if self._corte is None:
            return acoes
        minuto = ts.hour * 60 + ts.minute
        if positions:
            if minuto >= self._corte - 1:
                return [Exit(reason="g41_zera_cedo")]
            return acoes
        if minuto >= self._corte - self.ttl_barras - 1:
            return [a for a in acoes if getattr(a, "side", None) is None]
        return acoes
