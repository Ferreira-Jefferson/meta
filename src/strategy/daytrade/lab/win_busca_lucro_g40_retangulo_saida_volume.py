"""`win_busca_lucro_g40_retangulo_saida_volume` — Geração 40 (ideia do dono,
2026-10-06): com a posição aberta, se a vela que ACABOU DE FECHAR teve volume
anormal contra a média das `janela` velas anteriores, sai na abertura da
vela seguinte.

Causalidade (o ponto do dono): nunca o volume da vela em formação. `on_bar`
roda com a vela t já fechada (volume final, igual ao da tabela parada) e o
`Exit` executa na abertura de t+1 -- reproduzível ao vivo.

`modo`: "alto" (volume > k x média) ou "baixo" (volume < média / k).
`so_no_lucro`: só sai se o fechamento da vela t estiver a favor da entrada.
A saída é a mercado (mesmo caminho do stop -- é saída de proteção, não o
alvo, que continua ordem-limite).
Base: padrão G37 congelado (alvo que se aproxima a cada 5 velas).
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from strategy.daytrade.base import Bar, Exit, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g37_retangulo_ema34_alvo_aproxima_congelado_v37 import (
    WinBuscaLucroG37RetanguloEma34AlvoAproximaCongeladoV37,
)


class WinBuscaLucroG40RetanguloSaidaVolume(WinBuscaLucroG37RetanguloEma34AlvoAproximaCongeladoV37):
    name = "win_busca_lucro_g40_retangulo_saida_volume"
    version = "1.0.0"

    def __init__(self, modo: str | None = None, k: float = 2.0, janela: int = 20,
                 so_no_lucro: bool = False, **kwargs) -> None:
        if modo not in (None, "alto", "baixo"):
            raise ValueError(f"modo={modo!r} inválido")
        super().__init__(**kwargs)
        self.modo = modo
        self.k = float(k)
        self.janela = int(janela)
        self.so_no_lucro = so_no_lucro
        self._vols: deque[float] = deque(maxlen=self.janela)

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._vols.clear()

    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        media = sum(self._vols) / len(self._vols) if len(self._vols) == self.janela else None
        vol = float(bar.volume or 0.0)
        self._vols.append(vol)
        if self.modo is None or not positions or media is None or media <= 0:
            return acoes
        pos = positions[0]
        if ts <= pos.entry_ts:
            return acoes
        anormal = vol > self.k * media if self.modo == "alto" else vol < media / self.k
        if not anormal:
            return acoes
        if self.so_no_lucro:
            s = 1.0 if pos.side == "long" else -1.0
            if s * (bar.close - pos.entry_price) <= 0:
                return acoes
        return list(acoes) + [Exit(reason=f"g40_volume_{self.modo}_{self.k:g}")]
