"""`win_busca_lucro_g28_retangulo_regime_indefinido` — Geração 28 da busca
por EA lucrativo de day trade do WIN (ver `ORQUESTRACAO.md`).

## Por que esta geração existe

G26 e G27 testaram "só entrar a favor da tendência" (bloquear o lado que
CONTRARIA a tendência medida) de 5 jeitos diferentes — nenhum se confirmou
no OOS-1. Pedido do dono, 2026-10-05, depois de ver os 3 resultados: "não é
medir tendência, é ter mais dados para decidir — sabendo que a confirmação
não ajuda, será que quando elas não estão de acordo não é o momento de
entrar? Usar a NÃO confirmação como base para operar."

Ou seja: em vez de um filtro de DIREÇÃO (que lado operar), um filtro de
REGIME (quando operar, nos dois lados igual) — a hipótese é que a G21
(reversão ao meio de um retângulo de 20 min) funciona melhor quando o
mercado mais amplo está SEM uma tendência clara e nítida (M15 e H1
discordando, ou sem consenso entre as 3 escalas), e pior quando há consenso
forte de tendência (que favoreceria rompimento, não reversão). Isto nunca
foi testado nesta busca: G26/G27 sempre usaram a tendência para ESCOLHER o
lado, nunca para decidir SE entra, independente do lado.

## O que esta classe faz

Subclasse de `WinBuscaLucroG21Retangulo1000`, mesmo padrão da G26/G27:
nenhuma lógica de detecção/geometria reimplementada. Intercepta a ação
`EnterLimit` do pai e descarta (nos DOIS lados igual, sem favorecer
nenhum) quando o mercado está em REGIME DE CONSENSO — usa as mesmas 3
medidas pré-computadas da G27 (`i_m15`, `i_h1`, `i_leg`).

`regime` ∈ {"m15_h1_discordam", "sem_consenso_total"}:
  - `"m15_h1_discordam"`: bloqueia quando `i_m15 == i_h1` (ambos não-zero) —
    "tendência clara" nas duas escalas médias. Deixa passar quando
    discordam (cerca de 28% do tempo no IS).
  - `"sem_consenso_total"`: bloqueia só quando `i_m15 == i_h1 == i_leg`
    (consenso TOTAL nas 3 escalas, cerca de 48% do tempo no IS) — mais
    frouxo que o anterior, deixa passar mais.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)
from strategy.daytrade.lab.win_busca_lucro_g27_retangulo_tendencia_maior import (
    _tendencias,
)

REGIMES_VALIDOS = ("m15_h1_discordam", "sem_consenso_total")


class WinBuscaLucroG28RetanguloRegimeIndefinido(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g28_retangulo_regime_indefinido"
    version = "1.0.0"

    def __init__(self, regime: str = "m15_h1_discordam", **kwargs) -> None:
        if regime not in REGIMES_VALIDOS:
            raise ValueError(f"regime={regime!r} inválido: {REGIMES_VALIDOS}")
        super().__init__(**kwargs)
        self.regime = regime
        df = _tendencias()
        m15, h1, leg = df["i_m15"], df["i_h1"], df["i_leg"]
        concordam_m15_h1 = (m15 == h1) & (m15 != 0)
        if regime == "m15_h1_discordam":
            self._bloqueia = concordam_m15_h1
        else:
            self._bloqueia = concordam_m15_h1 & (leg == m15)

    def _regime_bloqueado(self, ts: pd.Timestamp) -> bool:
        try:
            return bool(self._bloqueia.at[ts])
        except KeyError:
            return False

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes
        if self._regime_bloqueado(ts):
            return []
        return acoes
