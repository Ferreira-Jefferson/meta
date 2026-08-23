"""Feed de BARRAS M1 fechadas — o que o robo de day trade consome ao vivo.

Diferente de `live/feed.py` (que entrega o ultimo PRECO, um `Quote`): aqui a
unidade e' a barra M1 JA FECHADA, porque e' isso que
`backtest/intraday/machine.py::IntradaySessionMachine` consome. Alimentar a
maquina com a barra em formacao seria a versao intradiaria do look-ahead:
`bar.high`/`bar.low` do minuto corrente ainda vao mudar, e a maquina resolve
stop/alvo/toque de ordem-limite exatamente nesses dois campos — um stop
"disparado" pela maxima parcial de um minuto que ainda nao acabou nao
existiu.

Duas guardas, as duas obrigatorias:

1. **descarta a barra mais nova** de todo lote que o MT5 devolve. O
   `copy_rates_from_pos(..., 0, n)` inclui SEMPRE a barra do minuto corrente,
   em formacao.
2. **exige idade minima** (`_MIN_BAR_AGE_SECONDS`): a barra so e' aceita se
   `ts <= agora - 60s`. O `ts` de uma barra M1 do MT5 e' o instante de
   ABERTURA dela (a barra rotulada 13:02 fecha as 13:03), entao esta e'
   exatamente a condicao "ja fechou". Redundante de proposito com a guarda 1:
   se o relogio do servidor estiver ADIANTADO do nosso, o lote chega com
   varias barras rotuladas no nosso futuro proximo, e descartar so a ultima
   deixaria as outras passarem como fechadas.

FUSO DO SERVIDOR — a armadilha desta camada
--------------------------------------------
No day trade o fuso nao e' cosmetico: `Gremah` troca de ancora fixa para
rolante comparando `ts.time() < fixed_anchor_until`, e o motor acha a posicao
comparando `ts.time() >= session_end_time`. Um offset errado nao produz erro
nenhum — produz um robo rodando a fase errada, o dia inteiro, em silencio.
Ver `live_stop_intraday_2026_08_20` na memoria do projeto.

A conversao e' delegada inteira a `mt5_source`, que converte pelo FUSO
declarado e medido em `core.b3_session`. Este feed NAO recebe mais um
`offset_provider` apontando para a calibracao viva do `MT5Feed`: essa era a
via pela qual um offset INFERIDO de um tick parado chegava as barras. Medido
em 2026-08-21 no terminal real, a inferencia adotou +4.0h onde o correto e'
+3.0h, e teria deslocado o dia inteiro do robo. Conferir o relogio continua
sendo feito — em `MT5Feed.verify_server_clock`, contra um papel liquido, e o
resultado IMPEDE a operacao em vez de reescrever o offset em silencio.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional

import pandas as pd

from backtest.intraday.engine import bar_from_row
from core.b3_session import server_utc_offset_hours
from market_data_intraday.mt5_source import fetch_m1_range, fetch_m1_recent
from strategy.daytrade.base import Bar

#: idade minima (segundos) para uma barra M1 ser considerada FECHADA.
_MIN_BAR_AGE_SECONDS = 60.0

#: quantas barras pedir por leitura. 240 = 4h de pregao — folga larga para
#: um processo que ficou alguns minutos sem rodar (reinicio, maquina travada)
#: sem nunca precisar de mais de uma chamada no caminho normal.
_RECENT_BARS = 240


class MT5BarFeed:
    """Barras M1 fechadas de UM simbolo, lidas do terminal MT5.

    A correcao de fuso e' toda de `mt5_source` (pelo fuso declarado em
    `core.b3_session`) — ver a secao "FUSO DO SERVIDOR" na docstring do
    modulo para o motivo de nao haver mais um offset injetavel aqui.
    """

    name = "mt5_bars"
    #: Atraso MINIMO entre o preco acontecer e este feed poder entrega-lo. Uma
    #: barra M1 so' e' legivel depois de fechar, entao o piso e' o proprio
    #: minuto — nao e' latencia de rede, e' o formato do dado. O painel reporta
    #: este numero (`IntradayLiveRuntime.status`).
    nominal_delay_seconds = 60.0

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
        """Offset servidor<->UTC em vigor, so para o painel REPORTAR. Nao e'
        usado na conversao: quem converte e' `mt5_source`, pelo fuso."""
        return server_utc_offset_hours(self._now_fn())

    # ---------- leitura ----------------------------------------------------

    def _closed(self, df: pd.DataFrame, after_ts: Optional[pd.Timestamp]) -> list[Bar]:
        """Aplica as duas guardas (descarta a barra em formacao; exige idade
        minima) e filtra o que ja foi entregue."""
        if df.empty:
            return []
        df = df.sort_index()
        # (1) a barra mais nova do lote e' a do minuto CORRENTE, em formacao.
        df = df.iloc[:-1]
        if df.empty:
            return []
        # (2) redundancia proposital: relogio do servidor != nosso relogio.
        limite = pd.Timestamp(self._now_fn()) - pd.Timedelta(seconds=_MIN_BAR_AGE_SECONDS)
        df = df[df.index <= limite]
        if after_ts is not None:
            df = df[df.index > after_ts]
        return [bar_from_row(ts, row) for ts, row in df.iterrows()]

    def closed_bars_since(self, after_ts: Optional[pd.Timestamp] = None) -> list[Bar]:
        """Barras M1 FECHADAS com `ts > after_ts`, em ordem cronologica.
        Lista vazia (nunca excecao) se o terminal falhar — mesmo contrato de
        `MT5Feed.quotes`."""
        df = fetch_m1_recent(
            self.symbol, count=_RECENT_BARS, on_error=self._on_error,
            **self._credentials,
        )
        return self._closed(df, after_ts)

    def session_bars_until(self, session: date, until_ts: pd.Timestamp) -> list[Bar]:
        """Barras M1 fechadas do pregao `session`, da abertura ate `until_ts`
        (inclusive) — o material do `warm_start_calibration` quando o robo
        liga no meio do pregao.

        Usa `fetch_m1_range` (nao `fetch_m1_recent`): a janela pedida e' a
        SESSAO, nao "as ultimas N barras", e um pregao pode ter mais barras
        que `_RECENT_BARS`. As duas guardas de fechamento tambem valem aqui —
        `until_ts` costuma ser a ultima barra ja processada, mas mesmo assim
        nao ha razao para relaxar a regra.

        A janela pedida ao terminal e' ALARGADA em um dia para cada lado, e o
        recorte pro pregao certo e' feito DEPOIS, sobre o index ja corrigido
        de fuso: os limites de `copy_rates_range` sao interpretados no
        relogio do SERVIDOR (ver docstring de `mt5_source`), entao pedir
        exatamente [00:00, 24:00) do dia em UTC cortaria a sessao no lugar
        errado por `offset_hours`."""
        meia_noite = datetime.combine(session, time(0, 0), tzinfo=timezone.utc)
        df = fetch_m1_range(
            self.symbol, meia_noite - timedelta(days=1), meia_noite + timedelta(days=2),
            on_error=self._on_error,
            **self._credentials,
        )
        if df.empty:
            return []
        # `_closed` primeiro (descarta a barra em formacao e a idade minima),
        # recorte por sessao/`until_ts` depois — na ordem inversa, a ultima
        # barra do recorte seria descartada como "em formacao" sem ser.
        return [b for b in self._closed(df, None)
                if b.ts.date() == session and b.ts <= until_ts]
