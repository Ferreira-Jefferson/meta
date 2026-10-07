"""Item 71 do catalogo: correlacao cruzada (`numpy.corrcoef`) entre o
retorno na barra t e o VOLUME na barra t-k (defasado), numa janela movel.

Se a correlacao e' significativa (limiar EMPIRICO), entra na direcao
indicada pelo sinal da correlacao combinado com o desvio do volume
defasado atual contra a sua mediana. Sai quando a correlacao cruzada perde
forca na janela mais recente.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class AutocorrelacaoCruzadaRetornoVolumeDefasado(IntradayStrategy):
    """Correlacao cruzada retorno(t) x volume(t-k) numa janela movel."""

    name: str = "c470_autocorrelacao_cruzada_retorno_volume_defasado"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    lag: int = 3
    janela: int = 40
    corr_entrada: float = 0.3
    corr_saida: float = 0.1
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _retornos: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _volumes: deque = field(default_factory=lambda: deque(), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._retornos = deque(maxlen=self.janela)
        self._volumes = deque(maxlen=self.janela + self.lag)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._volumes.append(bar.volume)
        if self._close_anterior is not None and self._close_anterior != 0:
            self._retornos.append((bar.close - self._close_anterior) / self._close_anterior)
        self._close_anterior = bar.close

        corr = self._correlacao()
        if positions:
            if corr is not None and abs(corr) <= self.corr_saida:
                return [Exit(reason="correlacao_cruzada_perdeu_forca")]
            return []

        if corr is None or abs(corr) < self.corr_entrada:
            return []
        vols = np.asarray(self._volumes, dtype=float)
        vol_defasado_atual = vols[-1 - self.lag] if len(vols) > self.lag else vols[0]
        mediana_vol = float(np.median(vols))
        direcao = np.sign(corr) * np.sign(vol_defasado_atual - mediana_vol)
        if direcao > 0:
            return [self._ordem("long", bar.close, f"corr_cruzada_{corr:.2f}")]
        if direcao < 0:
            return [self._ordem("short", bar.close, f"corr_cruzada_{corr:.2f}")]
        return []

    def _correlacao(self) -> float | None:
        if len(self._retornos) < self.janela or len(self._volumes) < self.janela + self.lag:
            return None
        ret = np.asarray(self._retornos, dtype=float)
        vol = np.asarray(self._volumes, dtype=float)
        vol_defasado = vol[-self.janela - self.lag: len(vol) - self.lag]
        if len(vol_defasado) != len(ret) or ret.std() == 0 or vol_defasado.std() == 0:
            return None
        return float(np.corrcoef(ret, vol_defasado)[0, 1])

    def _ordem(self, side: str, preco_ref: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(preco_ref, self.tick_size)
        stop = no_tick(limite - sinal * self.stop_ticks * self.tick_size, self.tick_size)
        alvo = no_tick(limite + sinal * self.alvo_ticks * self.tick_size, self.tick_size)
        return EnterLimit(
            side=side, limit_price=limite, initial_stop=stop, initial_target=alvo,
            quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=reason,
        )
