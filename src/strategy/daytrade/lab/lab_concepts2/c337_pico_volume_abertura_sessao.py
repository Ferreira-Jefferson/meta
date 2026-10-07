"""Catálogo volume/microestrutura, item 38: PicoDeVolumeNaAberturaDaSessao.

`initialize` précomputa o perfil sazonal de volume por minuto-do-dia
(mesma normalização de `real_volume`/`tick_volume` do item 37). Acumula
volume real dos primeiros `janela_abertura_min` minutos da sessão contra
o volume sazonal esperado para essa mesma janela; se muito acima, entra
na direção do impulso inicial (fechamento contra a abertura da sessão).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


def _volume_normalizado(row) -> float:
    real = float(row.get("real_volume", 0.0) or 0.0)
    if real > 0:
        return real
    return float(row.get("tick_volume", 0.0) or 0.0)


@dataclass
class PicoDeVolumeNaAberturaDaSessao(IntradayStrategy):
    """Volume dos primeiros minutos da sessão muito acima do sazonal
    histórico desses minutos — entra na direção do impulso inicial."""

    name: str = "pico_volume_abertura_sessao"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela_abertura_min: int = 5
    k_volume_abertura: float = 1.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _perfil_sazonal: dict = field(default_factory=dict, init=False, repr=False)
    _barras_hoje: int = field(default=0, init=False, repr=False)
    _volume_acumulado: float = field(default=0.0, init=False, repr=False)
    _sazonal_esperado: float = field(default=0.0, init=False, repr=False)
    _abertura_preco: float | None = field(default=None, init=False, repr=False)
    _decidido_hoje: bool = field(default=False, init=False, repr=False)

    def initialize(self, bars: pd.DataFrame) -> None:
        if bars.empty:
            self._perfil_sazonal = {}
            return
        volumes = bars.apply(_volume_normalizado, axis=1)
        chave_minuto = pd.Series(
            [(t.hour, t.minute) for t in bars.index], index=bars.index,
        )
        self._perfil_sazonal = volumes.groupby(chave_minuto).mean().to_dict()

    def on_session_start(self, session_date) -> None:
        self._barras_hoje = 0
        self._volume_acumulado = 0.0
        self._sazonal_esperado = 0.0
        self._abertura_preco = None
        self._decidido_hoje = False

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        if self._abertura_preco is None:
            self._abertura_preco = bar.open

        if self._barras_hoje < self.janela_abertura_min:
            self._volume_acumulado += bar.volume
            self._sazonal_esperado += self._perfil_sazonal.get((ts.hour, ts.minute), 0.0)
        self._barras_hoje += 1

        if (not positions and not self._decidido_hoje
                and self._barras_hoje == self.janela_abertura_min
                and self._sazonal_esperado > 0
                and self._volume_acumulado > self.k_volume_abertura * self._sazonal_esperado):
            self._decidido_hoje = True
            nivel = bar.close
            if bar.close > self._abertura_preco:
                limite = no_tick(nivel - self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="long", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]
            elif bar.close < self._abertura_preco:
                limite = no_tick(nivel + self.offset_ticks * self.tick_size, self.tick_size)
                stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side="short", limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        return acao
