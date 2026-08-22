"""`InvertedStrategy` -- wrapper generico que faz QUALQUER `IntradayStrategy`
operar ao contrario do que ela recomenda: onde a estrategia interna compraria,
esta abre venda; onde compraria, abre venda (e vice-versa).

Motivacao (2026-08-21): as 51 hipoteses ja testadas em PMAM3
(`strategy/daytrade/lab/*.py` + `momentum_dip_intraday.py`) tiveram CAGR
negativo, sem excecao, no in-sample. A pergunta natural -- "e se eu operar o
contrario do que o sinal recomenda?" -- so vale a pena responder com um
mecanismo GENERICO (uma classe, nao 51 reescritas): aplicado igualmente a
todas, sem escolher a dedo qual "quase" funcionava.

Como a inversao e feita (e por que E SO ISSO que e generico)
--------------------------------------------------------------
`Enter(side=X, initial_stop=S, initial_target=T)` vira
`Enter(side=~X, initial_stop=T, initial_target=S)`.

Nao e só trocar `side` -- isso teria SENTIDO errado: se a estrategia original
calculou `S` como o nivel que invalida a aposta (perda) e `T` como o nivel que
a realiza (ganho), ao inverter a DIRECAO da aposta o que antes invalidava
(preco indo para `S`) passa a ser exatamente o cenario que valida a aposta
inversa -- e vice-versa. Trocar `stop`<->`target` junto com o lado preserva a
estrutura de risco/retorno original espelhada, sem precisar entender a
semantica interna de cada hipotese (ORB, VWAP, Fibonacci, etc.).

`Exit` passa direto -- fechar "agora" nao tem direcao para inverter.

`AdjustStop`/`AdjustTarget` (trailing dinamico) sao DESCARTADOS, nao
invertidos -- deliberado. A logica interna que gera esses ajustes normalmente
assume que a posicao dela esta GANHANDO (ex.: ajusta o stop pra proteger lucro
conforme o preco sobe). Na posicao REAL (invertida), o mesmo movimento de
preco significa estar PERDENDO -- nao ha traducao mecanica sadia de "proteger
lucro de quem esta ganhando" para "proteger lucro de quem esta perdendo".
Hipoteses que dependem pesadamente de trailing (ex.: `donchian_channel_
breakout`) devem ser lidas com essa ressalva: a versao invertida delas testa
so a entrada+saida estatica, sem o trailing que a versao original tinha.

Para dar ao `inner` uma visao de posicao coerente com o que ELE decidiu (nao
com o que foi de fato executado), esta classe reconstroi uma posicao-sombra
com o lado e stop/target que o `inner` esperaria ver -- e' o inverso exato da
transformacao acima, aplicada de volta.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import (
    AdjustStop,
    AdjustTarget,
    Bar,
    Enter,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    Side,
)


def _flip(side: Side) -> Side:
    return "short" if side == "long" else "long"


class InvertedStrategy(IntradayStrategy):
    """Roda `inner` "as cegas" (posicao-sombra do lado que `inner` espera) e
    espelha lado + stop/target de cada `Enter`; descarta ajustes dinamicos de
    stop/target (ver docstring do modulo)."""

    version = "0.1"

    def __init__(self, inner: IntradayStrategy):
        self.inner = inner
        self.name = f"inverted_{inner.name}"
        self.symbol = inner.symbol

    def initialize(self, bars: pd.DataFrame) -> None:
        self.inner.initialize(bars)

    def on_session_start(self, session_date) -> None:
        self.inner.on_session_start(session_date)

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        shadow_position = None
        if position is not None:
            shadow_position = IntradayOpenPosition(
                side=_flip(position.side),
                entry_ts=position.entry_ts,
                entry_price=position.entry_price,
                quantity=position.quantity,
                current_stop=position.current_target,
                current_target=position.current_stop,
                bars_held=position.bars_held,
                metadata=dict(position.metadata),
            )

        inner_actions = self.inner.on_bar(ts, bar, shadow_position, session_pnl_brl)

        actions: list[IntradayAction] = []
        for act in inner_actions:
            if isinstance(act, Enter):
                actions.append(Enter(
                    side=_flip(act.side),
                    initial_stop=act.initial_target,
                    initial_target=act.initial_stop,
                    quantity=act.quantity,
                    metadata=act.metadata,
                    reason=f"inverted:{act.reason}",
                ))
            elif isinstance(act, Exit):
                actions.append(act)
            # AdjustStop/AdjustTarget: descartados de proposito (ver docstring).
        return actions
