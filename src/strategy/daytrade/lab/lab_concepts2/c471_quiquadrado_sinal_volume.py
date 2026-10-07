"""Item 72 do catalogo: tabela de contingencia (alta/baixa x volume
acima/abaixo da mediana) numa janela movel -- frequencias observadas vs
esperadas, `((obs-esp)**2/esp).sum()` (so' aritmetica, sem p-valor formal),
comparado a um limiar EMPIRICO.

A celula DOMINANTE (maior desvio positivo) gera o sinal na direcao dessa
combinacao, disparado so' quando a barra atual bate a condicao de volume
daquela celula. Sai quando o desvio cai.
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
class QuiQuadradoSinalVolume(IntradayStrategy):
    """Tabela de contingencia sinal-do-retorno x percentil-de-volume."""

    name: str = "c471_quiquadrado_sinal_volume"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 40
    limiar_entrada: float = 4.0
    limiar_saida: float = 2.0
    stop_ticks: int = 10
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 30
    quantity: int = 1

    _sinais: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _vol_bins: deque = field(default_factory=lambda: deque(maxlen=40), init=False, repr=False)
    _close_anterior: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._sinais = deque(maxlen=self.janela)
        self._vol_bins = deque(maxlen=self.janela)
        self._close_anterior = None

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._close_anterior is not None and self._close_anterior != 0:
            ret = (bar.close - self._close_anterior) / self._close_anterior
            self._sinais.append(1 if ret > 0 else (-1 if ret < 0 else 0))
        self._close_anterior = bar.close
        self._vol_bins.append(bar.volume)

        chi2, celula_dominante = self._chi2()
        if positions:
            if chi2 is not None and chi2 < self.limiar_saida:
                return [Exit(reason="desvio_qui_quadrado_caiu")]
            return []

        if chi2 is None or chi2 < self.limiar_entrada or celula_dominante is None:
            return []
        sinal_dom, vol_bin_dom = celula_dominante
        mediana_vol = float(np.median(self._vol_bins))
        vol_bin_atual = "alto" if bar.volume > mediana_vol else "baixo"
        if vol_bin_atual != vol_bin_dom:
            return []
        if sinal_dom > 0:
            return [self._ordem("long", bar.close, f"chi2_{chi2:.1f}_alta_{vol_bin_dom}")]
        return [self._ordem("short", bar.close, f"chi2_{chi2:.1f}_baixa_{vol_bin_dom}")]

    def _chi2(self) -> tuple[float | None, tuple[int, str] | None]:
        if len(self._sinais) < self.janela or len(self._vol_bins) < self.janela:
            return None, None
        sinais = np.asarray(self._sinais)
        vols = np.asarray(self._vol_bins, dtype=float)
        mediana = float(np.median(vols))
        vol_alto = vols > mediana

        celulas = {
            (1, "alto"): int(np.sum((sinais > 0) & vol_alto)),
            (1, "baixo"): int(np.sum((sinais > 0) & ~vol_alto)),
            (-1, "alto"): int(np.sum((sinais < 0) & vol_alto)),
            (-1, "baixo"): int(np.sum((sinais < 0) & ~vol_alto)),
        }
        n = sum(celulas.values())
        if n == 0:
            return None, None
        total_alta = celulas[(1, "alto")] + celulas[(1, "baixo")]
        total_baixa = celulas[(-1, "alto")] + celulas[(-1, "baixo")]
        total_alto = celulas[(1, "alto")] + celulas[(-1, "alto")]
        total_baixo = celulas[(1, "baixo")] + celulas[(-1, "baixo")]

        chi2 = 0.0
        maior_desvio = -np.inf
        dominante = None
        for (sinal, bin_vol), obs in celulas.items():
            total_linha = total_alta if sinal > 0 else total_baixa
            total_coluna = total_alto if bin_vol == "alto" else total_baixo
            esperado = total_linha * total_coluna / n
            if esperado <= 0:
                continue
            chi2 += (obs - esperado) ** 2 / esperado
            desvio = obs - esperado
            if desvio > maior_desvio:
                maior_desvio = desvio
                dominante = (sinal, bin_vol)
        return float(chi2), dominante

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
