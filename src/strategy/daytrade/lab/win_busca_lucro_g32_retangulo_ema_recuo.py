"""`win_busca_lucro_g32_retangulo_ema_recuo` — Geração 32 da busca por EA
lucrativo de day trade do WIN (ver `ORQUESTRACAO.md`).

## Pedido do dono (2026-10-05)

"E se entrarmos só quando uma vela vai CONTRA a posição, mas antes de
fechar recua e volta — ex.: operando uma alta, uma vela abre acima da MM,
desce abaixo, fica mais de 50% do tempo abaixo, mas antes de fechar recua e
fecha acima." Um padrão de "mergulho e recuperação" dentro da PRÓPRIA vela
de decisão — mais extremo que a G31 (que só olhava a cor da vela inteira,
não o caminho dela).

## Aproximação declarada (sem dado de tick na descoberta inteira)

"Mais de 50% do TEMPO abaixo" exigiria saber o caminho intra-minuto (ticks),
que só existe de março a setembro/2026 (`data/cache_win_ticks/WIN@D`) — não
cobre jan-fev, parte da descoberta. Esta classe usa uma aproximação por
RANGE, não por tempo: a EMA ficar abaixo do PONTO MÉDIO do range da vela
(`(high+low)/2`) é lido como "mais da metade do range da vela ficou abaixo
da EMA" — proxy de posição, não de tempo. Igual a toda aproximação deste
tipo no projeto (ver LICOES_DE_PRODUCAO.md 6.47: caminho intra-vela por 2
pontos já se mostrou otimista para decisões finas), isto é declarado, não
escondido, e deveria ser conferido com ticks (mar-set/26) antes de qualquer
uso real.

## Regra exata

  - Compra: `open > EMA` (abriu acima) E `low < EMA` (mergulhou abaixo) E
    `EMA < (high+low)/2` (mais da metade do RANGE da vela ficou abaixo —
    proxy do "mais de 50% do tempo") E `close > EMA` (recuperou e fechou
    acima).
  - Venda: espelho (`open < EMA`, `high > EMA`, `EMA > (high+low)/2`,
    `close < EMA`).

Reaproveita a MESMA EMA pré-computada da G29 (`g29_ema34/ema_m1.pkl`,
períodos 21/34/55).
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)
from strategy.daytrade.lab.win_busca_lucro_g29_retangulo_ema34 import (
    PERIODOS_VALIDOS,
    _emas,
)


class WinBuscaLucroG32RetanguloEmaRecuo(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g32_retangulo_ema_recuo"
    version = "1.0.0"

    def __init__(self, periodo: int = 34, **kwargs) -> None:
        if periodo not in PERIODOS_VALIDOS:
            raise ValueError(f"periodo={periodo!r} inválido: {PERIODOS_VALIDOS}")
        super().__init__(**kwargs)
        self.periodo = int(periodo)
        self._ema = _emas()[f"ema{periodo}"]
        self._b: Bar | None = None

    def _ema_em(self, ts: pd.Timestamp) -> float | None:
        try:
            v = self._ema.at[ts]
        except KeyError:
            return None
        return float(v) if v == v else None

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._b = bar
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes

        ema = self._ema_em(ts)
        if ema is None:
            return []

        o, h, l, c = bar.open, bar.high, bar.low, bar.close
        meio_range = (h + l) / 2.0

        filtradas: list[IntradayAction] = []
        for acao in acoes:
            lado = getattr(acao, "side", None)
            if lado is None:
                filtradas.append(acao)
                continue
            if lado == "long":
                passa = (o > ema) and (l < ema) and (ema < meio_range) and (c > ema)
            else:
                passa = (o < ema) and (h > ema) and (ema > meio_range) and (c < ema)
            if passa:
                filtradas.append(acao)
        return filtradas
