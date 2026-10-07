"""Catálogo catástrofe/criticalidade, item 83: LeiDeZipfFrequenciaMovimentos.

Classifica o tamanho de cada movimento (em ticks, `|close-open|`) por
frequência (rank) numa contagem online. Zipf prevê `freq(rank) ~ freq(1)/
rank`; movimentos GRANDES mais frequentes do que a lei prevê para o seu
rank ("super-representados") levam a FADE; movimentos PEQUENOS menos
frequentes do que previsto ("sub-representados", raros) são SEGUIDOS.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class LeiDeZipfFrequenciaMovimentos(IntradayStrategy):
    """Contagem online de tamanhos de movimento (em ticks); compara a
    frequência observada do bucket da barra atual contra a frequência
    que a Lei de Zipf (`freq(1)/rank`) prevê para o rank dele: grande e
    super-representado = fade; pequeno e sub-representado = segue."""

    name: str = "lei_de_zipf_frequencia_movimentos"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    min_amostras: int = 200
    fator_super_representado: float = 1.5
    fator_sub_representado: float = 0.5
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _contagem_buckets: Counter = field(default_factory=Counter, init=False, repr=False)
    _total: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        pass  # `_contagem_buckets`/`_total` sobrevivem entre sessões de propósito.

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []
        bucket = round(abs(bar.close - bar.open) / self.tick_size)

        if self._total >= self.min_amostras and not positions:
            ranking = self._contagem_buckets.most_common()
            posicoes = {b: r + 1 for r, (b, _) in enumerate(ranking)}
            freq_rank1 = ranking[0][1] / self._total if ranking else 0.0
            rank_atual = posicoes.get(bucket, len(ranking) + 1)
            freq_obs = self._contagem_buckets.get(bucket, 0) / self._total
            freq_zipf = freq_rank1 / rank_atual if rank_atual > 0 else 0.0

            bucket_mediano = sorted(self._contagem_buckets.elements())
            mediana_bucket = bucket_mediano[len(bucket_mediano) // 2] if bucket_mediano else 0

            side = None
            if bucket > mediana_bucket and freq_zipf > 0 and freq_obs > self.fator_super_representado * freq_zipf:
                # movimento grande, super-representado para o rank -> fade
                side = "short" if bar.close > bar.open else "long"
            elif bucket < mediana_bucket and freq_obs < self.fator_sub_representado * freq_zipf and bucket > 0:
                # movimento pequeno, sub-representado (raro) -> segue
                side = "long" if bar.close > bar.open else "short"

            if side is not None:
                if side == "long":
                    limite = no_tick(bar.close + self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite - self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite + self.alvo_ticks * self.tick_size, self.tick_size)
                else:
                    limite = no_tick(bar.close - self.offset_ticks * self.tick_size, self.tick_size)
                    stop = no_tick(limite + self.stop_ticks * self.tick_size, self.tick_size)
                    alvo = no_tick(limite - self.alvo_ticks * self.tick_size, self.tick_size)
                acao = [EnterLimit(
                    side=side, limit_price=limite, initial_stop=stop,
                    initial_target=alvo, quantity=1, ttl_bars=self.entrada_ttl_bars,
                    exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO, reason=self.name,
                )]

        self._contagem_buckets[bucket] += 1
        self._total += 1
        return acao
