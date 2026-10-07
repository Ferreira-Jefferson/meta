"""Deslocamento matinal da abertura (WIN@, replicavel no WDO@): dia que se afasta
cedo da abertura e' dia de fluxo direcional -- entra A FAVOR, a abertura e' a
linha de invalidacao.

ORIGEM (estudo de 2026-10-04, `scripts/daytrade/win_estudo_direcao_2026_10_04/`,
validacao V3/H3): as 10:30, se o preco esta a >= 0,3 x ATR14 (diario, ate' D-1)
da abertura e NUNCA fechou do outro lado dela (banda morta 0,05 ATR) nesse
trecho, (a) 78,0% dos dias nao cruzam mais a abertura, contra 72% no nulo que
preserva a volatilidade por horario, e (b) o preco anda em media +0,10 ATR
(~200 pts no WIN) a favor do lado ate' o fechamento, contra ~0 no nulo.
Positivo em 5/5 anos e no WDO; z so' de 1 a 2 (n ~ 270 dias) -- por isso e'
PISTA e nao achado validado, e por isso esta estrategia foi pre-registrada e
medida com IS/OOS (ver `scripts/daytrade/win_deslocamento_matinal_2026_10_04/`).

O QUE ELA FAZ. Uma decisao por pregao, aos `minutos_decisao` (90) minutos de
pregao. Se `|close - abertura| >= desloc_min_atr x ATR` e o pregao esta
"limpo" (nenhum fechamento M1 alem de `banda_atr x ATR` do outro lado da
abertura), deixa uma `EnterLimit` no ultimo preco, a favor do lado. Stop do
lado de la' da abertura (abertura -/+ banda), com teto `stop_atr` em ATR
(existe por CAPITAL: o stop da linha pura custa ~R$140 num caixa de R$250).
Alvo opcional (`alvo_atr`) como limite real fatiada; sem alvo, sai no
achatamento de fim de pregao do motor. No maximo 1 operacao por pregao; nao
persegue: se a limite nao enche em `entrada_ttl_bars` o dia passa em branco.

SINAL PURO. So' OHLCV: o ATR vem das barras diarias que o motor entrega em
`seed_daily_volatility` (mesmo caminho do ao vivo); a hora do pregao e'
RELATIVA a primeira barra (nada de relogio absoluto/fuso aqui). Decisao no
fechamento da barra de rotulo abertura+89min (= 10:30), execucao a partir da
barra seguinte -- sem look-ahead.

DESENHO DE EXECUCAO FECHADO (CLAUDE.md): entrada `EnterLimit` com prazo,
alvo ordem-limite fatiada sem prazo, `anchor_exits_at_fill=True`, stop a
mercado (unica excecao), nunca `Enter`.

RESTRICAO PROIBIDA (refutada no estudo, nao entra aqui nem como filtro):
direcao de D-1/semana/mes, gap, dia da semana, niveis de D-1, Fibonacci,
pernadas, 1a hora, WDO de D-1, corpo/range, eficiencia, reversao M1.
`escala_volume` (volume relativo de D-1 -> escala de stop/alvo) e'
INCONCLUSIVO no estudo e fica desligado: so' existe para a ablacao.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

#: Prazo da fatia de saida por ALVO: sem prazo, NUNCA `None` (ver `wdo_orb`).
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

#: coeficiente de log(range/ATR) em log(relvol20) medido em V2 (ablacao).
_EXPOENTE_VOLUME = 0.33


@dataclass
class WinDeslocamentoMatinal(IntradayStrategy):
    """Continuacao a favor do deslocamento matinal da abertura."""

    name: str = "win_deslocamento_matinal"
    version: str = "1.0.0"
    symbol: str = "WIN@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True

    tick_size: float = 5.0
    quantity: int = 1

    #: minutos de pregao ate' a decisao (10:30 com abertura as 09:00).
    minutos_decisao: float = 90.0
    #: ATR14 diario: media de `atr_janela` true ranges ate' D-1.
    atr_janela: int = 14
    #: deslocamento minimo da abertura, em ATR (headline do estudo: 0,3).
    desloc_min_atr: float = 0.3
    #: banda morta (ATR) que define "cruzou a abertura" -- a do estudo.
    banda_atr: float = 0.05
    #: teto do stop em ATR; `None` = a linha pura (abertura -/+ banda).
    stop_atr: float | None = None
    #: alvo em ATR (limite real fatiada, sem prazo); `None` = so' achatamento.
    alvo_atr: float | None = None
    #: prazo da limite de entrada EM BARRAS M1 (1 barra = 1 minuto).
    entrada_ttl_bars: int = 15
    offset_ticks: int = 0
    #: ABLACAO (inconclusivo no estudo): escala stop/alvo pelo volume relativo de D-1.
    escala_volume: bool = False
    #: teto do stop em fracao do CAIXA atual (0,10 = 10%); `None` = sem teto. Se o stop da
    #: linha custa mais que o teto, o stop e' APERTADO ate' o teto (minimo 2 ticks). Decisao
    #: do dono, 2026-10-06: 10% (medido em `risco/`: com R$1.000 a linha pura zera o caixa).
    #: Use com capital CONTINUO; com capital reposto por pregao o teto le' o caixa reposto.
    risco_max_pct: float | None = None
    #: R$ por ponto por contrato (WIN: 0,20).
    ponto_brl: float = 0.2

    _open_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _open_px: float | None = field(default=None, init=False, repr=False)
    _min_close: float = field(default=float("inf"), init=False, repr=False)
    _max_close: float = field(default=float("-inf"), init=False, repr=False)
    _decidiu: bool = field(default=False, init=False, repr=False)
    _atr: float | None = field(default=None, init=False, repr=False)
    _escala: float = field(default=1.0, init=False, repr=False)
    _caixa: float | None = field(default=None, init=False, repr=False)
    #: diagnostico: um item por sinal emitido (ts, lado, deslocamento em ATR).
    sinais: list = field(default_factory=list, init=False, repr=False)

    tagline: str = "Dia que se afasta da abertura ate' as 10:30 e' dia direcional: entra a favor"
    plain_summary: tuple[str, ...] = (
        "Anota a abertura e, aos 90 minutos de pregao, mede o quanto o preco ja' "
        "andou em relacao ao ATR diario.",
        "Se andou 0,3 ATR ou mais sem nunca ter fechado do outro lado da abertura, "
        "entra a favor com ordem parada no ultimo preco.",
        "A abertura e' a linha de invalidacao (stop do outro lado dela, com teto em ATR).",
        "Sai no fim do pregao ou no alvo, por ordem parada. Uma operacao por dia.",
    )

    # ---------------- sementes do motor ----------------------------------

    def on_capital_update(self, cash_brl: float) -> None:
        self._caixa = cash_brl

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        """ATR14 (media de true ranges) e volume relativo ate' D-1."""
        self._atr = None
        self._escala = 1.0
        bars = previous_daily_bars
        n = self.atr_janela
        if len(bars) >= n + 1:
            trs = []
            for prev, cur in zip(bars[-n - 1:-1], bars[-n:]):
                trs.append(max(cur.high - cur.low, abs(cur.high - prev.close),
                               abs(cur.low - prev.close)))
            atr = sum(trs) / n
            self._atr = atr if atr > 0 else None
        if self.escala_volume and len(bars) >= 20:
            media = sum(b.volume for b in bars[-20:]) / 20.0
            if media > 0 and bars[-1].volume > 0:
                rel = bars[-1].volume / media
                self._escala = min(1.25, max(0.8, rel ** _EXPOENTE_VOLUME))

    def on_session_start(self, session_date) -> None:
        self._open_ts = None
        self._open_px = None
        self._min_close = float("inf")
        self._max_close = float("-inf")
        self._decidiu = False

    # ---------------- decisao ---------------------------------------------

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._open_ts is None:
            self._open_ts = ts
            self._open_px = bar.open
        self._min_close = min(self._min_close, bar.close)
        self._max_close = max(self._max_close, bar.close)

        if self._decidiu or positions:
            return []
        decorrido = (ts - self._open_ts) / pd.Timedelta(minutes=1)
        if decorrido < self.minutos_decisao - 1:
            return []
        # passou da janela (barra faltando / feed atrasado): o achado e' das 10:30, nao de depois.
        self._decidiu = True
        if decorrido > self.minutos_decisao - 1 + 5:
            return []
        atr = self._atr
        if atr is None or self._open_px is None:
            return []

        abertura = self._open_px
        banda = self.banda_atr * atr
        desloc = bar.close - abertura
        if desloc >= self.desloc_min_atr * atr and self._min_close >= abertura - banda:
            lado, sinal, linha = "long", 1.0, abertura - banda
        elif -desloc >= self.desloc_min_atr * atr and self._max_close <= abertura + banda:
            lado, sinal, linha = "short", -1.0, abertura + banda
        else:
            return []

        off = self.offset_ticks * self.tick_size
        limite = no_tick(bar.close - sinal * off, self.tick_size)
        dist_linha = sinal * (limite - linha)
        dist = dist_linha
        if self.stop_atr is not None:
            dist = min(dist, self.stop_atr * self._escala * atr)
        if self.risco_max_pct is not None and self._caixa is not None:
            teto_pts = self.risco_max_pct * self._caixa / (self.ponto_brl * self.quantity)
            teto_pts = int(teto_pts / self.tick_size) * self.tick_size
            dist = min(dist, max(teto_pts, 2 * self.tick_size))
        dist = max(dist, self.tick_size)
        stop = no_tick(limite - sinal * dist, self.tick_size)
        alvo = None
        if self.alvo_atr is not None:
            alvo = no_tick(limite + sinal * self.alvo_atr * self._escala * atr, self.tick_size)
            # alvo de 1 tick e' proibido (fila): minimo 2 ticks
            if abs(alvo - limite) < 2 * self.tick_size:
                alvo = limite + sinal * 2 * self.tick_size
        self.sinais.append((ts, lado, abs(desloc) / atr))
        return [EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=stop,
            initial_target=alvo,
            quantity=self.quantity,
            ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=(1 if alvo is not None else None),
            exit_ttl_bars=(EXIT_TTL_BARS_SEM_PRAZO if alvo is not None else None),
            reason="deslocamento_matinal_" + lado,
        )]
