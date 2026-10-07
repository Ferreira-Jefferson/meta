"""`win_busca_lucro_g39_retangulo_gestao_por_direcao` — Geração 39 (pedido
do dono, 2026-10-06): sobre o PADRÃO G37 (alvo que se aproxima a cada 5
velas), mover alvo e/ou stop conforme o preço anda A FAVOR ou CONTRA, cada
regra sozinha e em conjunto, para aprender o efeito de cada uma.

R = distância inicial entrada→stop (0,45 x largura). Gatilhos, avaliados no
fechamento das velas DEPOIS da vela do fill (vale a partir da seguinte):
  "favor"  = excursão favorável máxima >= 1R
  "contra" = excursão adversa máxima   >= 0,5R
Regras (`regras`, conjunto de nomes):
  alvo_perto_contra : alvo -> no máximo 0,50 x largura
  alvo_perto_favor  : alvo -> no máximo 0,60 x largura
  alvo_longe_favor  : alvo + 1R (somado ao relógio do G37)
  alvo_longe_contra : alvo + 1R
  stop_perto_contra : stop -> 0,75R da entrada
  stop_perto_favor  : stop -> preço de entrada
Stop "longe" não existe aqui: o motor nunca afrouxa stop nativo.
`regras=()` reproduz o padrão G37 exatamente.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import AdjustStop, AdjustTarget, Bar, IntradayAction, IntradayOpenPosition, no_tick
from strategy.daytrade.lab.win_busca_lucro_g29_retangulo_ema34_congelado_v29 import (
    WinBuscaLucroG29RetanguloEma34CongeladoV29,
)

REGRAS = ("alvo_perto_contra", "alvo_perto_favor", "alvo_longe_favor", "alvo_longe_contra",
          "stop_perto_contra", "stop_perto_favor")


class WinBuscaLucroG39RetanguloGestaoPorDirecao(WinBuscaLucroG29RetanguloEma34CongeladoV29):
    name = "win_busca_lucro_g39_retangulo_gestao_por_direcao"
    version = "1.0.0"

    PASSO_BARRAS = 5
    PASSO_FRACAO = 0.10
    ALVO_PISO = 0.50

    def __init__(self, regras: tuple[str, ...] = (), **kwargs) -> None:
        for r in regras:
            if r not in REGRAS:
                raise ValueError(f"regra {r!r} inválida: {REGRAS}")
        super().__init__(**kwargs)
        self.regras = frozenset(regras)
        self._pos_id = None

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not positions:
            self._pos_id = None
            return acoes
        pos = positions[0]
        if pos.current_target is None or pos.current_stop is None:
            return acoes
        s = 1.0 if pos.side == "long" else -1.0
        if self._pos_id != pos.entry_ts:
            self._pos_id = pos.entry_ts
            self._L = abs(pos.current_target - pos.entry_price) / self.alvo_fracao_largura
            self._R = self.stop_fracao_largura * self._L
            self._barras = 0
            self._fav = 0.0
            self._adv = 0.0
            self._alvo_emitido = pos.current_target
            self._stop_emitido = pos.current_stop
        if ts <= pos.entry_ts:
            return acoes
        self._barras += 1
        e = pos.entry_price
        self._fav = max(self._fav, s * ((bar.high if s > 0 else bar.low) - e))
        self._adv = max(self._adv, -s * ((bar.low if s > 0 else bar.high) - e))
        favor = self._fav >= self._R
        contra = self._adv >= 0.5 * self._R

        frac = max(self.alvo_fracao_largura - self.PASSO_FRACAO * (self._barras // self.PASSO_BARRAS),
                   self.ALVO_PISO)
        extra = 0.0
        if favor and "alvo_longe_favor" in self.regras:
            extra += self.stop_fracao_largura
        if contra and "alvo_longe_contra" in self.regras:
            extra += self.stop_fracao_largura
        frac += extra
        if contra and "alvo_perto_contra" in self.regras:
            frac = min(frac, 0.50)
        if favor and "alvo_perto_favor" in self.regras:
            frac = min(frac, 0.60)
        alvo = no_tick(e + s * frac * self._L, self.tick_size)

        out = list(acoes)
        if alvo != self._alvo_emitido:
            out.append(AdjustTarget(new_target=alvo))
            self._alvo_emitido = alvo

        stop = None
        if contra and "stop_perto_contra" in self.regras:
            stop = e - s * 0.75 * self._R
        if favor and "stop_perto_favor" in self.regras:
            stop = e if stop is None else (max(stop, e) if s > 0 else min(stop, e))
        if stop is not None:
            stop = no_tick(stop, self.tick_size)
            if s * (stop - self._stop_emitido) > 0:
                out.append(AdjustStop(new_stop=stop))
                self._stop_emitido = stop
        return out
