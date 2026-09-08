"""Hipotese: SEQUENCIA DE 3 VELAS DA MESMA COR + VOLUME MAIOR NA COR
CONTRARIA -> abre posicao NA COR CONTRARIA (fade por exaustao). Pedido do
dono, 2026-09-04: "faca um teste em wdo usando cores, se as ultimas 3
velas forem da mesma cor, e tiver mais volume de pra cor contraria, abra
uma posicao pra cor contraria" -- alvo e stop declarados a parte, 5 ticks
cada.

## Interpretacao declarada (o pedido nao especifica, entao fica registrado)

"Cor da vela": bullish (verde) se `close > open`, bearish (vermelha) se
`close < open`; `close == open` e' NEUTRA e quebra qualquer sequencia em
andamento (nunca conta como cor de nenhum lado).

"Ultimas 3 velas da mesma cor": as 3 barras M1 mais recentes (incluindo a
barra atual), CONSECUTIVAS -- uma vela neutra no meio zera a contagem.

"Mais volume pra cor contraria": o pedido nao diz em cima de qual janela
comparar -- comparar so' as 3 velas da sequencia e' vazio por definicao
(sao todas da MESMA cor, entao o volume da cor contraria NESSAS 3 barras e'
sempre zero). Esta implementacao soma o volume por cor numa janela rolante
de `lookback_volume_bars` barras (default 10 -- cobre a sequencia de 3 +
as 7 anteriores) e compara `volume_cor_contraria > volume_cor_da_sequencia`
dentro dela. Escolha DECLARADA, nao medida -- sensibilidade a este numero
ainda nao foi testada.

`exigir_volume_contrario=False` (pedido do dono, 2026-09-04: "vamos parar
de olhar pra volume, quero bastante trade") desliga o filtro de volume
por completo -- o sinal vira so' "3 velas consecutivas da mesma cor",
sem nenhuma condicao de volume. Medido (`n_seq3` no diagnostico desta
rodada): a sequencia de 3 velas sozinha ocorre ~4.000x nos ultimos 3
meses de WDO@ M1, contra ~800x com o filtro de volume -- e' o "bastante
trade" pedido.

`inverter_direcao=True` (pedido do dono, mesma rodada: "vamos inverter...
se vier um sinal de compra deve vender e vice versa") troca o lado final
da entrada pelo OPOSTO do que a regra decidiria -- com
`exigir_volume_contrario=False`, o sinal original (fade) e' "3 velas
verdes -> vende, 3 velas vermelhas -> compra"; invertido vira "3 velas
verdes -> compra, 3 velas vermelhas -> vende", ou seja, CONTINUACAO da
sequencia (comprar quando a sequencia e' de alta, vender quando e' de
baixa) em vez de fade -- sem reintroduzir volume nenhum na decisao.

## Entrada e saida

Entra a MERCADO no lado decidido acima (fade por padrao, ou o lado
invertido com `inverter_direcao=True`), com `initial_stop`/
`initial_target` a `stop_ticks`/`target_ticks` da barra que gerou o sinal
(preco de referencia = fechamento da barra do sinal, ajustado a grade via
`no_tick`). Sem gerenciamento ativo depois disso -- o motor fecha por
STOP, por ALVO ou por FLATTEN forcado no fim da sessao; esta estrategia
nunca emite `Exit()`. Nunca piramida: com posicao aberta, ignora qualquer
sinal novo ate o motor fechar a posicao corrente sozinho.

Reseta a janela de cor/volume a cada sessao (`on_session_start`) -- mesma
disciplina de `strategy.daytrade.lab.continuidade_intraday.ContinuidadeIntraday`:
o fim de ontem nao pareia com o inicio de hoje.
"""
from __future__ import annotations

from collections import deque
from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    Enter,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    no_tick,
)

Color = Literal["bullish", "bearish"]


def _bar_color(bar: Bar) -> Color | None:
    if bar.close > bar.open:
        return "bullish"
    if bar.close < bar.open:
        return "bearish"
    return None


def _oposto(cor: Color) -> Color:
    return "bearish" if cor == "bullish" else "bullish"


def _oposto_lado(lado: str) -> str:
    return "short" if lado == "long" else "long"


class CorVolumeReversao(IntradayStrategy):
    name = "cor_volume_reversao"
    version = "0.1"
    is_futuro = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str,
        tick_size: float,
        target_ticks: int = 5,
        stop_ticks: int = 5,
        lookback_volume_bars: int = 10,
        exigir_volume_contrario: bool = True,
        inverter_direcao: bool = False,
        quantity: int | None = None,
    ):
        if target_ticks <= 0 or stop_ticks <= 0:
            raise ValueError(
                f"target_ticks/stop_ticks tem que ser positivos, recebeu "
                f"{target_ticks!r}/{stop_ticks!r}"
            )
        if lookback_volume_bars < 3:
            raise ValueError(
                f"lookback_volume_bars tem que ser >= 3 (cobre a sequencia de "
                f"3 velas), recebeu {lookback_volume_bars!r}"
            )
        self.symbol = symbol
        self.tick_size = tick_size
        self.target_ticks = target_ticks
        self.stop_ticks = stop_ticks
        self.lookback_volume_bars = lookback_volume_bars
        self.exigir_volume_contrario = exigir_volume_contrario
        self.inverter_direcao = inverter_direcao
        self.quantity = quantity
        self._janela: deque[tuple[Color, float]] = deque(maxlen=lookback_volume_bars)
        self._ultimas_cores: deque[Color] = deque(maxlen=3)

    def on_session_start(self, session_date) -> None:
        self._janela.clear()
        self._ultimas_cores.clear()

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        cor = _bar_color(bar)
        if cor is not None:
            self._janela.append((cor, bar.volume))
            self._ultimas_cores.append(cor)
        else:
            self._ultimas_cores.clear()  # vela neutra quebra a sequencia em andamento

        if positions:
            return []  # posicao aberta: espera stop/alvo/flatten fechar sozinho, nunca piramida

        if len(self._ultimas_cores) < 3 or len(set(self._ultimas_cores)) != 1:
            return []
        cor_sequencia = self._ultimas_cores[-1]
        cor_contraria = _oposto(cor_sequencia)
        if self.exigir_volume_contrario:
            vol_sequencia = sum(v for c, v in self._janela if c == cor_sequencia)
            vol_contraria = sum(v for c, v in self._janela if c == cor_contraria)
            if vol_contraria <= vol_sequencia:
                return []

        lado_fade = "long" if cor_contraria == "bullish" else "short"
        lado = _oposto_lado(lado_fade) if self.inverter_direcao else lado_fade
        ref = no_tick(bar.close, self.tick_size)
        delta_target = self.target_ticks * self.tick_size
        delta_stop = self.stop_ticks * self.tick_size
        if lado == "long":
            alvo, stop = ref + delta_target, ref - delta_stop
        else:
            alvo, stop = ref - delta_target, ref + delta_stop
        return [Enter(
            side=lado,
            initial_stop=stop,
            initial_target=alvo,
            quantity=self.quantity,
            reason=f"cor_volume_reversao:{cor_sequencia}->{lado}",
        )]
