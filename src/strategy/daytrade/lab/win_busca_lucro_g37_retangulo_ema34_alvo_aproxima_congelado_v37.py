"""`win_busca_lucro_g37_retangulo_ema34_alvo_aproxima` — Geração 37
(curiosidade do dono, 2026-10-06): alvo que se APROXIMA da entrada com o
tempo. Começa em `alvo_fracao_largura` (0,90x) e encolhe `passo_fracao` x
largura a cada `passo_barras` velas fechadas desde o fill, até `alvo_piso`
(0,50x -- sempre acima do stop de 0,45x: perda>=ganho continua proibido).
Stop fixo. O alvo é ordem-limite real e `AdjustTarget` o reprecifica de
verdade, então não há a distorção de "checar no fechamento" da G36.

PADRÃO ATUAL desde 2026-10-06 (decisão do dono): `passo_barras=5`,
`passo_fracao=0,10`, `alvo_piso=0,50`, sobre G21+EMA34 com stop 0,45 e alvo
inicial 0,90. Porte MQL5: `mt5/WinRetanguloEma34.mq5` v1.03.
`passo_barras=None` reproduz o padrão anterior (G29, alvo parado).
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import AdjustTarget, Bar, IntradayAction, IntradayOpenPosition, no_tick
from strategy.daytrade.lab.win_busca_lucro_g29_retangulo_ema34_congelado_v29 import (
    WinBuscaLucroG29RetanguloEma34CongeladoV29,
)


class WinBuscaLucroG37RetanguloEma34AlvoAproximaCongeladoV37(WinBuscaLucroG29RetanguloEma34CongeladoV29):
    name = "win_busca_lucro_g37_retangulo_ema34_alvo_aproxima_congelado_v37"
    version = "1.0.0"

    def __init__(self, passo_barras: int | None = 5, passo_fracao: float = 0.10,
                 alvo_piso: float = 0.50, **kwargs) -> None:
        super().__init__(**kwargs)
        if alvo_piso <= self.stop_fracao_largura:
            raise ValueError("alvo_piso <= stop: perda>=ganho é proibido")
        self.passo_barras = passo_barras
        self.passo_fracao = passo_fracao
        self.alvo_piso = alvo_piso
        self._pos_id = None
        self._largura = None
        self._barras = 0
        self._frac_atual = None

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not positions:
            self._pos_id = None
            return acoes
        if self.passo_barras is None:
            return acoes
        pos = positions[0]
        if pos.current_target is None:
            return acoes
        if self._pos_id != pos.entry_ts:
            self._pos_id = pos.entry_ts
            self._largura = abs(pos.current_target - pos.entry_price) / self.alvo_fracao_largura
            self._barras = 0
            self._frac_atual = self.alvo_fracao_largura
        if ts <= pos.entry_ts:
            return acoes
        self._barras += 1
        frac = max(self.alvo_fracao_largura - self.passo_fracao * (self._barras // self.passo_barras),
                   self.alvo_piso)
        if frac >= self._frac_atual - 1e-9:
            return acoes
        self._frac_atual = frac
        s = 1.0 if pos.side == "long" else -1.0
        novo = no_tick(pos.entry_price + s * frac * self._largura, self.tick_size)
        return list(acoes) + [AdjustTarget(new_target=novo)]
