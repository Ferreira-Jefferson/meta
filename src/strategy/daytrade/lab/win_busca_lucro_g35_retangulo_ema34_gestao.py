"""`win_busca_lucro_g35_retangulo_ema34_gestao` — Geração 35 da busca de EA
do WIN (ver `ORQUESTRACAO.md`).

Pedido do dono (2026-10-06): mexer na SAÍDA do padrão atual (G21+EMA34,
congelado v29), sem tocar na entrada:
  1. alvo maior que o stop (3x, com vizinhos 2,5x e 4x; 2x = padrão);
  2. stop que anda a favor conforme o preço caminha para o alvo;
  3. alvo que se afasta enquanto o preço avança e nenhum sinal contrário
     aparece (sinal contrário = fechamento do lado errado da EMA34, a
     mesma régua da entrada), com o stop acompanhando;
  4. combinações.

Gestões (`gestao`), todas medidas em R = distância inicial entrada→stop:
  - "nenhuma": stop e alvo fixos (comportamento da G29).
  - "breakeven": depois de andar 1R a favor, stop vai para o preço de entrada.
  - "trail1R" / "trail05R": depois de 1R a favor, stop segue o extremo
    favorável a 1R / 0,5R de distância (só aperta, nunca afrouxa).
  - "alvo_movel": trail1R + quando o fechamento chega a 0,5R do alvo e está
    do lado certo da EMA34, o alvo é empurrado +1R. Com sinal contrário o
    alvo para de andar (o stop continua seguindo).

Decisões só com velas FECHADAS depois do preenchimento (o extremo da própria
vela de entrada pode ter acontecido antes do fill, então não conta). O
ajuste vale a partir da vela seguinte, igual a qualquer ação do motor.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import AdjustStop, AdjustTarget, Bar, IntradayAction, IntradayOpenPosition, no_tick
from strategy.daytrade.lab.win_busca_lucro_g29_retangulo_ema34_congelado_v29 import (
    WinBuscaLucroG29RetanguloEma34CongeladoV29,
)

GESTOES = ("nenhuma", "breakeven", "trail1R", "trail05R", "alvo_movel")


class WinBuscaLucroG35RetanguloEma34Gestao(WinBuscaLucroG29RetanguloEma34CongeladoV29):
    name = "win_busca_lucro_g35_retangulo_ema34_gestao"
    version = "1.0.0"

    def __init__(self, gestao: str = "nenhuma", **kwargs) -> None:
        if gestao not in GESTOES:
            raise ValueError(f"gestao={gestao!r} inválida: {GESTOES}")
        super().__init__(**kwargs)
        self.gestao = gestao
        self._pos_id = None
        self._R = None
        self._extremo = None
        self._alvo_parado = False

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not positions:
            self._pos_id = None
            return acoes
        if self.gestao == "nenhuma":
            return acoes
        return list(acoes) + self._gerir(ts, bar, positions[0])

    def _gerir(self, ts, bar: Bar, pos: IntradayOpenPosition) -> list[IntradayAction]:
        s = 1.0 if pos.side == "long" else -1.0
        if self._pos_id != pos.entry_ts:
            self._pos_id = pos.entry_ts
            self._R = abs(pos.entry_price - pos.current_stop) if pos.current_stop else None
            self._extremo = pos.entry_price
            self._alvo_parado = False
        if not self._R or ts <= pos.entry_ts:
            return []
        R = self._R
        fav = bar.high if s > 0 else bar.low
        self._extremo = max(self._extremo, fav) if s > 0 else min(self._extremo, fav)
        andou = s * (self._extremo - pos.entry_price)
        if andou < R:
            return []

        out: list[IntradayAction] = []
        if self.gestao == "breakeven":
            novo = pos.entry_price
        else:
            dist = 0.5 * R if self.gestao == "trail05R" else R
            novo = self._extremo - s * dist
        novo = no_tick(novo, self.tick_size)
        if pos.current_stop is None or s * (novo - pos.current_stop) > 0:
            out.append(AdjustStop(new_stop=novo))

        if self.gestao == "alvo_movel" and pos.current_target is not None:
            ema = self._ema_em(ts)
            contra = ema is not None and s * (bar.close - ema) < 0
            if contra:
                self._alvo_parado = True
            perto = s * (pos.current_target - bar.close) <= 0.5 * R
            if perto and not self._alvo_parado:
                out.append(AdjustTarget(new_target=no_tick(pos.current_target + s * R, self.tick_size)))
        return out
