"""`win_busca_lucro_g31_retangulo_ema_rejeicao` — Geração 31 da busca por EA
lucrativo de day trade do WIN (ver `ORQUESTRACAO.md`).

## Pedido do dono (2026-10-05, refinamento depois da G30)

"E se for uma vela de BAIXA fechar totalmente acima da MM, se for compra?
E se for uma vela de ALTA fechar totalmente abaixo da MM, se for um sinal
de venda?" — um padrão de REJEIÇÃO: para comprar, quer uma vela que caiu
dentro do próprio intervalo (cor vermelha/baixa) mas mesmo assim fechou
com o corpo inteiro ACIMA da média — a baixa foi "absorvida"; para vender,
o espelho (vela verde/alta que não conseguiu tirar o corpo da média).

## O que esta classe faz

Subclasse de `WinBuscaLucroG21Retangulo1000` (mesmo padrão de G26-G30).
Como a vela exigida é sempre da cor OPOSTA à direção do corpo mais próximo
da EMA, a condição "corpo inteiro do lado certo" se reduz a comparar só o
FECHAMENTO (o ponto do corpo mais próximo da EMA já é o fechamento nos dois
casos — ver docstring do módulo/ORQUESTRACAO.md para a álgebra):
  - Compra: `bar.close < bar.open` (vela de baixa) E `bar.close > EMA`.
  - Venda: `bar.close > bar.open` (vela de alta) E `bar.close < EMA`.

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


class WinBuscaLucroG31RetanguloEmaRejeicaoCongeladoV31(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g31_retangulo_ema_rejeicao_congelado_v31"
    version = "1.0.0"

    def __init__(self, periodo: int = 34, **kwargs) -> None:
        if periodo not in PERIODOS_VALIDOS:
            raise ValueError(f"periodo={periodo!r} inválido: {PERIODOS_VALIDOS}")
        super().__init__(**kwargs)
        self.periodo = int(periodo)
        self._ema = _emas()[f"ema{periodo}"]
        self._ultimo_open: float | None = None
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
        self._ultimo_open = bar.open
        self._ultimo_close = bar.close
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes

        ema = self._ema_em(ts)
        if ema is None:
            return []

        vela_baixa = self._ultimo_close < self._ultimo_open
        vela_alta = self._ultimo_close > self._ultimo_open

        filtradas: list[IntradayAction] = []
        for acao in acoes:
            lado = getattr(acao, "side", None)
            if lado is None:
                filtradas.append(acao)
                continue
            if lado == "long":
                passa = vela_baixa and (self._ultimo_close > ema)
            else:
                passa = vela_alta and (self._ultimo_close < ema)
            if passa:
                filtradas.append(acao)
        return filtradas
