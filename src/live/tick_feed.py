"""Feed de TICK a tick (negocios reais) — o que a `gremah_tick` consome ao
vivo. Par intradiario de `live/bar_feed.py`, com a MESMA interface, para o
`IntradayLiveRuntime` nao saber de qual dos dois esta lendo.

Por que existe uma segunda classe em vez de um parametro no `MT5BarFeed`
------------------------------------------------------------------------
As duas guardas centrais do feed M1 — "descarta a barra mais nova, que esta
em formacao" e "exige 60s de idade" — nao so' sao desnecessarias aqui: elas
seriam ERRADAS. Uma barra M1 e' um agregado que continua mudando ate' o
minuto acabar; um tick de negocio e' um evento ATOMICO, ja' consumado no
instante em que o terminal o publica. Descartar o mais recente jogaria fora
um negocio que de fato aconteceu, e exigir 60s de idade atrasaria o robo em
um minuto inteiro sem ganhar nada. Espremer as duas politicas opostas na
mesma classe faria "barra fechada" significar duas coisas.

O que isso APAGA da divergencia backtest x operacao
---------------------------------------------------
`live/intraday_runtime.py` declara uma divergencia honesta do lado M1: stop e
alvo so' sao avaliados quando a barra FECHA, entao o robo reage ate' 60s
depois do que o backtest intrabar assume. Com tick essa divergencia
desaparece — a maquina reavalia stop/alvo a cada negocio, que e' exatamente a
granularidade em que o backtest de tick a validou. Continua valendo, sim, o
atraso do proprio ciclo do supervisor (5s, ver `scripts/run_live.py`): o robo
ve o negocio no proximo passo, nao no instante dele.

Tick a tick tambem elimina a ambiguidade que o M1 tem por construcao (stop e
alvo tocados na MESMA barra, sem saber qual veio primeiro — ver
`IntradayBacktestConfig.ambiguous_bar_resolution`): um negocio tem um preco
so', entao ou tocou um, ou tocou o outro.

FUSO DO SERVIDOR — a mesma armadilha do feed M1
-----------------------------------------------
`copy_ticks_range` interpreta os limites que recebe no relogio do SERVIDOR,
nao em UTC (mesmo comportamento de `copy_rates_range`). A conversao de ida e'
`core.b3_session.utc_to_server_wall_clock`; a de volta e' de
`mt5_ticks_source`, pelo FUSO declarado. Depois disso ainda filtramos pelo
index ja' corrigido: se o relogio do servidor divergir do declarado, e' melhor
entregar menos ticks do que entregar ticks rotulados na hora errada — um
offset errado nao levanta erro nenhum, so' faz o robo rodar a fase errada do
dia inteiro (ver `live_stop_intraday_2026_08_20` na memoria do projeto).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional

import pandas as pd

from backtest.intraday.engine import bar_from_row
from core.b3_session import server_utc_offset_hours, utc_to_server_wall_clock
from market_data_intraday.mt5_ticks_source import fetch_ticks_range
from market_data_intraday.tick_bars import ticks_to_degenerate_bars
from strategy.daytrade.base import Bar

#: Quanto tempo para tras buscar quando nao ha marca d'agua (`after_ts=None`)
#: — primeiro passo de um processo recem-subido. Nao precisa ser generoso:
#: quem liga no meio do pregao e ainda tem janela de ancora fixa passa por
#: `session_bars_until` (warm start), que busca a sessao inteira; este numero
#: so' cobre o intervalo entre a decisao de comecar a frio e o primeiro passo.
_COLD_START_LOOKBACK = timedelta(minutes=5)

#: Folga somada ao fim da janela pedida ao terminal. O limite superior e'
#: "agora", e um relogio de servidor alguns segundos adiantado do nosso
#: cortaria justamente os negocios mais recentes — os unicos que interessam.
#: Ticks do "futuro" nao passam: o filtro por `now` abaixo os descarta.
_FUTURE_MARGIN = timedelta(minutes=2)


class MT5TickFeed:
    """Ticks de NEGOCIO de UM simbolo, lidos do terminal MT5, entregues como
    `Bar` degenerada (`open=high=low=close=preco negociado`).

    Interface identica a `live.bar_feed.MT5BarFeed` — `closed_bars_since` e
    `session_bars_until` — porque `IntradayLiveRuntime` consome os dois pelo
    mesmo nome. A "barra" degenerada nao e' uma aproximacao: e' o formato em
    que o motor (`backtest/intraday/machine.py`) ja' sabe ler um evento de
    preco unico, e e' o MESMO formato que o backtest de tick usa (ver
    `market_data_intraday/tick_bars.py`).
    """

    name = "mt5_ticks"
    #: Zero: um negocio ja' aconteceu quando o terminal o publica — nao ha
    #: nada a esperar fechar. Contraste com `MT5BarFeed.nominal_delay_seconds`
    #: (60s, o minuto que a barra precisa para existir). O atraso que sobra e'
    #: o passo do supervisor, que nao e' propriedade do feed.
    nominal_delay_seconds = 0.0

    def __init__(
        self,
        symbol: str,
        on_error: Optional[Callable[[str, Exception], None]] = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        self.symbol = symbol
        self._on_error = on_error
        self._now_fn = now_fn
        self._credentials = dict(login=login, password=password, server=server, path=path)

    # ---------- offset -----------------------------------------------------

    @property
    def offset_hours(self) -> float:
        """Offset servidor<->UTC em vigor, so para o painel REPORTAR — mesma
        semantica de `MT5BarFeed.offset_hours`."""
        return server_utc_offset_hours(self._now_fn())

    # ---------- leitura ----------------------------------------------------

    def _fetch(self, start_utc: datetime, end_utc: datetime) -> pd.DataFrame:
        """Ticks de negocio da janela, com o index ja' em UTC. Converte os
        limites para o relogio do servidor na ida (ver docstring do modulo)."""
        return fetch_ticks_range(
            self.symbol,
            utc_to_server_wall_clock(start_utc),
            utc_to_server_wall_clock(end_utc),
            on_error=self._on_error,
            **self._credentials,
        )

    def _bars(self, ticks: pd.DataFrame, after_ts: Optional[pd.Timestamp],
              agora: pd.Timestamp) -> list[Bar]:
        """Ticks -> `Bar`, descartando o que ja' foi entregue e o que esta
        rotulado no futuro.

        Nao ha guarda de "em formacao": um negocio nao se forma, acontece. O
        corte por `agora` nao e' o equivalente disfarcado dela — e' a defesa
        contra relogio de servidor divergente, o mesmo motivo pelo qual
        `MT5BarFeed` mantem duas guardas redundantes."""
        if ticks.empty:
            return []
        ticks = ticks.sort_index()
        ticks = ticks[ticks.index <= agora]
        if after_ts is not None:
            ticks = ticks[ticks.index > after_ts]
        if ticks.empty:
            return []
        bars = ticks_to_degenerate_bars(ticks)
        return [bar_from_row(ts, row) for ts, row in bars.iterrows()]

    def closed_bars_since(self, after_ts: Optional[pd.Timestamp] = None) -> list[Bar]:
        """Negocios com `ts > after_ts`, em ordem cronologica. Lista vazia
        (nunca excecao) se o terminal falhar — mesmo contrato de
        `MT5BarFeed.closed_bars_since`.

        Lista vazia aqui e' o caso NORMAL, nao um sintoma: num papel iliquido
        podem passar minutos sem um unico negocio. Quem trata buraco de dado
        (`IntradayLiveRuntime`) mede o tempo sem RODAR, nao o tempo sem tick,
        exatamente por isso."""
        agora = pd.Timestamp(self._now_fn())
        inicio = (after_ts.to_pydatetime() if after_ts is not None
                  else agora.to_pydatetime() - _COLD_START_LOOKBACK)
        ticks = self._fetch(inicio, agora.to_pydatetime() + _FUTURE_MARGIN)
        return self._bars(ticks, after_ts, agora)

    def session_bars_until(self, session: date, until_ts: pd.Timestamp) -> list[Bar]:
        """Negocios do pregao `session`, da abertura ate' `until_ts`
        (inclusive) — o material do `warm_start_calibration` quando o robo
        liga no meio do pregao.

        A janela pedida e' ALARGADA em um dia para cada lado e o recorte pro
        pregao certo e' feito depois, sobre o index ja' corrigido de fuso —
        mesma disciplina de `MT5BarFeed.session_bars_until`, e a mesma razao:
        o dia civil do servidor nao e' o dia civil em UTC."""
        meia_noite = datetime.combine(session, time(0, 0), tzinfo=timezone.utc)
        ticks = self._fetch(meia_noite - timedelta(days=1), meia_noite + timedelta(days=2))
        agora = pd.Timestamp(self._now_fn())
        return [b for b in self._bars(ticks, None, agora)
                if b.ts.date() == session and b.ts <= until_ts]
