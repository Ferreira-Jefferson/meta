# -*- coding: utf-8 -*-
"""WinGapReversao -- hipotese do gap do WIN (lab; NAO registrada em registry.py).

Origem: `scripts/daytrade/win_fases_correlacao_2026_10_06/SINTESE.md` (pistas, nenhuma passou BH):
  V1  fade do gap: direcao CONTRA o gap (gap = leilao de abertura de D - call de D-1).
  V2  1a barra M5 do continuo fechada CONTRA o gap -> entra na direcao dessa barra.
  V3  V2 + volume do call de D-1 alto (acima da mediana dos ate 60 pregoes anteriores):
      `vol_modo="skip"` nao opera; `vol_modo="alvo_menor"` usa `alvo_pequeno_pts`.

O gap e o flag de volume sao calculados FORA (precisam do dia anterior e de uma janela de varios
dias, e a estrategia fica pura -- AGENTS.md regra 2) e entram em `contexto_por_dia`
{date: (gap_pts, vol_alto)}; `on_session_start` so' faz a consulta. Dia fora do dicionario
(rolagem de contrato, pregao parcial) nunca opera.

Desenho de execucao FECHADO (CLAUDE.md): `EnterLimit` com `ttl_bars`, alvo por ordem-limite real
fatiada sem prazo (`exit_split_unit`, `exit_ttl_bars=10**9`), `anchor_exits_at_fill=True`, stop a
mercado. Sem alvo (`alvo_pts=None`): segura ate o fim do CONTINUO (flatten do motor).
Decisao na barra 09:00 FECHADA; a ordem so' existe a partir da barra seguinte (sem look-ahead).
Barra M5: `ttl_barras` x 5 = minutos de espera, sem conversao tick->barra.

`null_seed` / `dir_forcada`: sorteiam / forcam a direcao (+1/-1) nos MESMOS dias de gatilho e com a
mesma geometria (nulo de direcao aleatoria). Nao sao parte da estrategia -- sao o instrumento do nulo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.daytrade.base import Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


class WinGapReversao(IntradayStrategy):
    name = "win_gap_reversao"
    version = "0.1.0"
    symbol = "WIN@"          # perfil/custos/tick do WIN (dado aqui e' WIN$N)
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(self, variante: str = "V2", contexto_por_dia: dict | None = None,
                 recuo_pts: float = 0.0, stop_pts: float = 300.0, alvo_pts: float | None = None,
                 gap_min_pts: float = 0.0, ttl_barras: int = 6, vol_modo: str | None = None,
                 alvo_pequeno_pts: float | None = None, null_seed: int | None = None,
                 dir_forcada: int | None = None,
                 quantity: int = 1, tick: float = 5.0) -> None:
        if variante not in ("V1", "V2", "V3"):
            raise ValueError(variante)
        if ttl_barras is None or ttl_barras <= 0:
            raise ValueError("ordem de entrada sem prazo e' proibida (CLAUDE.md)")
        if variante == "V3" and vol_modo not in ("skip", "alvo_menor"):
            raise ValueError("V3 exige vol_modo")
        if vol_modo == "alvo_menor" and not alvo_pequeno_pts:
            raise ValueError("alvo_menor exige alvo_pequeno_pts")
        self.variante = variante
        self.ctx = contexto_por_dia or {}
        self.recuo_pts, self.stop_pts, self.alvo_pts = float(recuo_pts), float(stop_pts), alvo_pts
        self.gap_min_pts, self.ttl_barras = float(gap_min_pts), int(ttl_barras)
        self.vol_modo, self.alvo_pequeno_pts = vol_modo, alvo_pequeno_pts
        self.null_seed, self.quantity, self.tick = null_seed, int(quantity), float(tick)
        self.dir_forcada = dir_forcada
        self.dir_real: dict = {}      # date -> direcao que a regra pede (antes de qualquer sorteio/forca)
        # contadores de auditoria (por run)
        self.dias_elegiveis = self.dias_gatilho = self.ordens = 0
        self.sinal_ts: dict = {}     # date -> Timestamp em que a ordem foi emitida (fecho da 1a barra)
        self._dia = None
        self._n = 0

    def on_session_start(self, session_date) -> None:
        self._dia, self._n = session_date, 0

    def _direcao(self, gap: float, bar: Bar) -> int:
        """+1 compra / -1 venda / 0 sem sinal."""
        if gap == 0:
            return 0
        if self.variante == "V1":
            return -1 if gap > 0 else 1
        corpo = bar.close - bar.open
        if corpo == 0 or np.sign(corpo) == np.sign(gap):
            return 0                       # 1a barra nao fechou CONTRA o gap
        return 1 if corpo > 0 else -1

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        self._n += 1
        if self._n != 1 or self._dia not in self.ctx:
            return []
        self.dias_elegiveis += 1
        gap, vol_alto = self.ctx[self._dia]
        if abs(gap) < self.gap_min_pts:
            return []
        s = self._direcao(gap, bar)
        if s == 0:
            return []
        self.dias_gatilho += 1
        alvo = self.alvo_pts
        if self.variante == "V3" and vol_alto:
            if self.vol_modo == "skip":
                return []
            alvo = self.alvo_pequeno_pts
        self.dir_real[self._dia] = s
        if self.dir_forcada is not None:
            s = int(self.dir_forcada)
        elif self.null_seed is not None:
            s = int(np.random.default_rng([self.null_seed, self._dia.toordinal()]).choice([-1, 1]))
        lim = no_tick(bar.close - s * self.recuo_pts, self.tick)
        self.ordens += 1
        self.sinal_ts[self._dia] = ts
        return [EnterLimit(
            side="long" if s > 0 else "short",
            limit_price=lim,
            initial_stop=no_tick(lim - s * self.stop_pts, self.tick),
            initial_target=None if alvo is None else no_tick(lim + s * alvo, self.tick),
            quantity=self.quantity, ttl_bars=self.ttl_barras,
            exit_split_unit=self.quantity, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=f"win_gap_{self.variante}")]
