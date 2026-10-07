"""`win_busca_lucro_g29_retangulo_ema34` — Geração 29 da busca por EA
lucrativo de day trade do WIN (ver `ORQUESTRACAO.md`).

## Pedido do dono (2026-10-05, palavras dele)

"Coloque uma média exponencial de 34. Se o preço anterior fechar abaixo e
for sinal de venda, vendemos; se fechar acima e for sinal de compra,
compramos." Ou seja: um filtro de posição do preço contra uma EMA clássica
(período 34) — diferente de tudo que já foi tentado nesta busca (G26 usou
drift cru; G27 usou inclinação de EMA em M15/H1 e a pernada de 750; G28
usou falta de consenso entre essas). Esta é a primeira vez que se testa
POSIÇÃO do preço contra uma média, no mesmo tempo gráfico (M1) da própria
estratégia.

## O que esta classe faz

Subclasse de `WinBuscaLucroG21Retangulo1000`, mesmo padrão de G26/G27/G28:
nenhuma lógica de detecção/geometria reimplementada. Intercepta a ação
`EnterLimit` do pai e descarta quando o fechamento da última vela (a
"vela anterior" à decisão, já fechada) está do lado ERRADO da EMA: venda só
passa se `close <= EMA`, compra só passa se `close >= EMA` — exatamente a
regra literal do dono.

`periodo` ∈ {21, 34, 55} — 34 é o pedido; 21 e 55 são vizinhos testados por
padrão (o projeto varia todo número citado antes de aceitar um só, ver
`feedback_variar_parametros_do_dono`). EMA pré-computada uma vez por
`g29_prep.py` em `g29_ema34/ema_m1.pkl` (causal: `ewm` só usa o passado).

Diferente de G26/G27 (sinal discreto {-1,0,1}, com modo frouxo/estrito):
aqui a EMA é um valor contínuo, então a comparação já é sempre decisiva —
não existe "neutro" (empate exato é desprezível), não há eixo frouxo/
estrito para variar.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)

PKL = Path(__file__).resolve().parents[4] / "scripts" / "daytrade" / "win_pernadas_exploracao" \
    / "ea_busca_lucro" / "g29_ema34" / "ema_m1.pkl"

PERIODOS_VALIDOS = (21, 34, 55)

_CACHE: dict = {}


def _emas() -> pd.DataFrame:
    if "df" not in _CACHE:
        _CACHE["df"] = pd.read_pickle(PKL)
    return _CACHE["df"]


class WinBuscaLucroG29RetanguloEma34CongeladoV29(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g29_retangulo_ema34_congelado_v29"
    version = "1.0.0"

    def __init__(self, periodo: int = 34, **kwargs) -> None:
        if periodo not in PERIODOS_VALIDOS:
            raise ValueError(f"periodo={periodo!r} inválido: {PERIODOS_VALIDOS}")
        super().__init__(**kwargs)
        self.periodo = int(periodo)
        self._ema = _emas()[f"ema{periodo}"]
        self._ultimo_close: float | None = None

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
        self._ultimo_close = bar.close
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes

        ema = self._ema_em(ts)
        if ema is None:
            return []  # sem EMA (fora do periodo pre-computado) -- nao arrisca sem o filtro

        filtradas: list[IntradayAction] = []
        for acao in acoes:
            lado = getattr(acao, "side", None)
            if lado is None:
                filtradas.append(acao)
                continue
            # regra literal do dono: venda só com fechamento <= EMA, compra só com >= EMA.
            passa = (self._ultimo_close <= ema) if lado == "short" else (self._ultimo_close >= ema)
            if passa:
                filtradas.append(acao)
        return filtradas
