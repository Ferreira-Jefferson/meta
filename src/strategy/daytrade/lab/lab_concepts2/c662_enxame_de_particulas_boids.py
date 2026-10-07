"""Catálogo autômatos/ML/jogos, item 63: EnxameDeParticulasBoids.

Modela os últimos preços como um enxame de "boids": alinhamento (direção
média da tendência), coesão (atração ao preço médio) e separação (evita
níveis de preço aglomerados). Combina os três num vetor de rumo; segue o
rumo quando a "velocidade" do enxame (magnitude do vetor) é alta.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class EnxameDeParticulasBoids(IntradayStrategy):
    """Rumo do enxame = combinação ponderada de alinhamento (média dos
    sinais de retorno), coesão (desvio do preço médio) e separação
    (repulsão de níveis de preço visitados com frequência); entra na
    direção do rumo quando sua magnitude excede o limiar."""

    name: str = "enxame_de_particulas_boids"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    janela: int = 20
    peso_alinhamento: float = 0.5
    peso_coesao: float = 0.3
    peso_separacao: float = 0.2
    limiar_velocidade: float = 0.35
    offset_ticks: int = 1
    stop_ticks: int = 16
    alvo_ticks: int = 8
    entrada_ttl_bars: int = 40

    _closes: deque = field(default_factory=lambda: deque(maxlen=20), init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        if self._closes.maxlen != self.janela:
            self._closes = deque(self._closes, maxlen=self.janela)

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acao: list[IntradayAction] = []

        if not positions and len(self._closes) == self._closes.maxlen:
            closes = list(self._closes)
            retornos = [b - a for a, b in zip(closes[:-1], closes[1:])]
            desvio = max(1e-9, (sum((c - sum(closes) / len(closes)) ** 2 for c in closes) / len(closes)) ** 0.5)

            # alinhamento: direcao media normalizada da tendencia recente
            alinhamento = (sum(1.0 if r > 0 else (-1.0 if r < 0 else 0.0) for r in retornos)
                           / len(retornos)) if retornos else 0.0

            # coesao: atracao para a media do enxame (preco longe da media
            # puxa de volta -- contribuicao com sinal OPOSTO ao desvio)
            media = sum(closes) / len(closes)
            coesao = -(bar.close - media) / desvio
            coesao = max(-1.0, min(1.0, coesao))

            # separacao: repulsao de niveis de preco (arredondados ao tick)
            # visitados com frequencia na janela -- alto count no nivel
            # atual empurra o rumo para LONGE dele.
            niveis = Counter(round(c / self.tick_size) for c in closes)
            nivel_atual = round(bar.close / self.tick_size)
            freq_atual = niveis[nivel_atual] / len(closes)
            direcao_fuga = 1.0 if alinhamento >= 0 else -1.0
            separacao = direcao_fuga * freq_atual

            rumo = (self.peso_alinhamento * alinhamento
                    + self.peso_coesao * coesao
                    + self.peso_separacao * separacao)

            if abs(rumo) > self.limiar_velocidade:
                side = "long" if rumo > 0 else "short"
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

        self._closes.append(bar.close)
        return acao
