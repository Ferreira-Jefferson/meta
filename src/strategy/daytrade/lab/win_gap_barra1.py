"""WIN: 1a barra M5 do pregao fecha CONTRA o gap -> entra na direcao dessa barra, com stop.

Origem: `scripts/daytrade/win_gap_estrategia_2026_10_06/` (rodadas 1 a 4). Lab; NAO registrada em `registry.py`.

## A regra

  gap      = preco do LEILAO de abertura de D  -  preco do CALL de fechamento de D-1
  barra 1  = a 1a barra M5 de D (09:00-09:05, relogio do pregao)
  sinal    = a barra 1 fecha CONTRA o gap  (gap < 0 e close > open  -> COMPRA;
                                             gap > 0 e close < open  -> VENDA)
  entrada  = ordem-limite no CLOSE da barra 1 (`recuo_pts=0`), `ttl_barras` barras M5 de prazo
  saida    = stop a mercado a `stop_pts` do preco preenchido; alvo opcional em limite real fatiado
             (`exit_split_unit`, `EXIT_TTL_BARS_SEM_PRAZO`); zera na ULTIMA barra do continuo.

## O gap sai SO' de barras (puro OHLCV, sem I/O)

Em barras M1/M5 CRUAS do MT5 do WIN$N/WIN@:
  * a 1a barra do dia carrega o leilao de abertura: seu `open` e' o preco do leilao;
  * a ULTIMA barra do dia (18:24 em M1, 18:20 em M5) carrega o call de fechamento: seu `close` e' o preco do call.
A estrategia guarda o `close` da ultima barra que viu em D-1 e o compara com o `open` da 1a barra de D. Nada de arquivo,
banco ou tabela de fases. Se o feed ja' vier SEM leiloes (base `win_sem_leiloes`), o mesmo codigo roda, mas o gap vira
"1o negocio continuo - ultimo negocio continuo" (proxy, sem o salto do leilao/call): o contexto externo `gap_por_dia`
(`{date: gap_pts}`) existe para esse caso e para testes; quando presente, manda sobre o gap calculado das barras.

## Relogio

A estrategia NAO conhece fuso: o "pregao abre" e' o `ts` da 1a barra do dia e tudo e' relativo a ele. Com o feed em BRT
`abertura = 09:00` (default); com o feed em UTC passe `abertura_h=12`. So' opera se a 1a barra do dia comeca na abertura
(dia que abre atrasado, como 2026-07-31, e' pulado). O fim do continuo vem da grade da B3 (`data/b3_grade_horaria_win.csv`):
18:25 no regime atual, 17:55 antes de 2024-03-11 em horario de verao dos EUA -> `fim_continuo_min` (minutos apos a abertura;
565 = 18:25, 535 = 17:55). A ultima barra do continuo comeca em `fim_continuo_min - 5`.

## Fim do dia (nunca na barra do call)

Com `zerar_no_fim=True` (default) a estrategia emite `Exit` no fecho da barra das 18:10 (`fim - zerar_antes_min - 5`) e o
motor o executa na ABERTURA da barra das 18:15, antes do call. Em feed bruto a barra das 18:20 tem o call no `close`, e o
flatten do motor (passo (2), que roda ANTES das acoes filadas) nessa barra seria preco de leilao -- por isso a saida e'
pedida antes. Em feed sem leiloes (ou ao vivo, onde o runtime zera por relogio de parede as 18:20) use `zerar_no_fim=False`
e deixe o `session_end_time` do motor fazer o flatten no ultimo negocio continuo.

## Vencimento (rolagem do WIN$N)

No vencimento (quarta mais proxima do dia 15 dos meses pares) o WIN$N troca de contrato e o gap entre o call de D-1 e o
leilao de D deixa de existir como informacao (degrau de 3.300 a 4.400 pts). `evitar_vencimento=True` pula a 1a sessao em
ou depois do vencimento (cobre o caso de o vencimento cair em feriado). E' so' aritmetica de data.

## Desenho de execucao (CLAUDE.md "FECHADO")

`EnterLimit` com prazo; alvo, se houver, em limite real fatiado sem prazo; `anchor_exits_at_fill=True`; stop a mercado.
`quantity_e_unidade=True`: a quantidade e' 1 unidade multiplicada pelo sistema (escada de risco por caixa).

## Numeros (IS 2026-04-06..2026-10-05, R$1.000, simulador a tick) -- ver `scripts/daytrade/win_gap_estrategia_2026_10_06/rodada4_estrategia_2026_10_06/RESULTADO.md`
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from strategy.daytrade.base import (
    AdjustStop, Bar, EnterLimit, Exit, IntradayAction, IntradayOpenPosition, IntradayStrategy, no_tick,
)

#: a limite do alvo fica parada ate' o mercado pagar; nunca `None` (ver CLAUDE.md).
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9
BARRA_MIN = 5


def vencimento_do_mes(ano: int, mes: int) -> dt.date:
    """Quarta-feira mais proxima do dia 15 (se o 15 e' quarta, ele mesmo)."""
    d15 = dt.date(ano, mes, 15)
    return next(d15 + dt.timedelta(days=k) for k in (0, -1, 1, -2, 2, -3, 3) if (d15 + dt.timedelta(days=k)).weekday() == 2)


def rolagem_entre(anterior: dt.date | None, hoje: dt.date) -> bool:
    """True se um vencimento de mes par cai em (anterior, hoje] -- ie. `hoje` e' a 1a sessao em ou depois do vencimento."""
    if anterior is None:
        return False
    for ano in (anterior.year, hoje.year):
        for mes in (2, 4, 6, 8, 10, 12):
            v = vencimento_do_mes(ano, mes)
            if anterior < v <= hoje:
                return True
    return False


@dataclass
class _Dia:
    data: dt.date | None = None
    n_barras: int = 0
    t0: pd.Timestamp | None = None
    gap: float | None = None
    emitiu: bool = False
    exit_emitido: bool = False
    melhor: float | None = None


class WinGapBarra1(IntradayStrategy):
    """Ver docstring do modulo."""

    name = "win_gap_barra1"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"
    quantity_e_unidade = True

    def __init__(
        self,
        stop_pts: float = 1200.0,
        alvo_pts: float | None = None,
        alvo_r: float | None = None,
        be_r: float | None = None,
        recuo_pts: float = 0.0,
        ttl_barras: int = 6,
        gap_min_pts: float = 0.0,
        evitar_vencimento: bool = True,
        abertura_h: int = 9,
        abertura_m: int = 0,
        fim_continuo_min: int = 565,
        zerar_no_fim: bool = True,
        zerar_antes_min: int = 10,
        tick: float = 5.0,
        gap_por_dia: dict | None = None,
        dias_sem_operar: frozenset = frozenset(),
    ) -> None:
        if stop_pts <= 0:
            raise ValueError("stop_pts tem que ser positivo")
        if ttl_barras is None or ttl_barras <= 0:
            raise ValueError("ordem de entrada sem prazo e' proibida (CLAUDE.md)")
        if alvo_pts is not None and alvo_r is not None:
            raise ValueError("alvo_pts e alvo_r sao excludentes")
        self.stop_pts, self.alvo_pts, self.alvo_r, self.be_r = float(stop_pts), alvo_pts, alvo_r, be_r
        self.recuo_pts, self.ttl_barras, self.gap_min_pts = float(recuo_pts), int(ttl_barras), float(gap_min_pts)
        self.evitar_vencimento = evitar_vencimento
        self.abertura = (int(abertura_h), int(abertura_m))
        self.fim_continuo_min = int(fim_continuo_min)
        self.zerar_no_fim, self.zerar_antes_min = bool(zerar_no_fim), int(zerar_antes_min)
        self.dias_sem_operar = frozenset(dias_sem_operar)
        self.tick = float(tick)
        self.gap_por_dia = gap_por_dia
        self._ult_close: float | None = None          # close da ultima barra vista (o call, em feed bruto)
        self._call_por_dia: dict = {}                 # {data: close da ultima barra do dia} lido de `initialize` (backtest)
        self._ult_data: dt.date | None = None
        self._d = _Dia()
        self.dias_com_sinal = 0

    def initialize(self, bars: pd.DataFrame) -> None:
        """Backtest: o motor NAO entrega a ultima barra de cada dia a `on_bar` (o flatten roda antes e `on_bar` nao roda
        depois dele), entao o call de D-1 nao chega por la'. Guarda aqui o close da ultima barra de cada dia do DataFrame;
        so' a data ANTERIOR a de hoje e' consultada (sem look-ahead). Sem esta tabela (ao vivo) cai no close da ultima
        barra vista."""
        if bars is None or len(bars) == 0:
            return
        ult = bars["close"].groupby(bars.index.normalize()).last()
        self._call_por_dia = {pd.Timestamp(k).date(): float(v) for k, v in ult.items()}

    def _call_anterior(self, hoje: dt.date) -> tuple[float | None, dt.date | None]:
        """(preco do call, data) da sessao anterior a `hoje`."""
        anteriores = [k for k in self._call_por_dia if k < hoje]
        if anteriores:
            k = max(anteriores)
            return self._call_por_dia[k], k
        return self._ult_close, self._ult_data

    # -- relogio relativo a abertura ---------------------------------------------------------------
    def _min_desde_abertura(self, ts: pd.Timestamp) -> float:
        return (ts - self._d.t0).total_seconds() / 60.0

    def on_session_start(self, session_date) -> None:
        self._d = _Dia(data=session_date)

    # -- loop ---------------------------------------------------------------------------------------
    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        d = self._d
        hoje = ts.date()
        if d.data != hoje:                       # feed sem on_session_start: abre o dia aqui
            d = self._d = _Dia(data=hoje)
        acoes: list[IntradayAction] = []
        d.n_barras += 1
        if d.n_barras == 1:
            d.t0 = ts
            abre = (ts.hour, ts.minute) == self.abertura
            gap = None
            if self.gap_por_dia is not None:
                gap = self.gap_por_dia.get(hoje)
            else:
                call, data_call = self._call_anterior(hoje)
                if call is not None and data_call is not None and 0 < (hoje - data_call).days <= 5:
                    gap = bar.open - call                 # leilao de D - call de D-1 (feed bruto)
                    self._ult_data = data_call
            if abre and gap is not None and hoje not in self.dias_sem_operar \
                    and abs(gap) >= max(self.gap_min_pts, self.tick) \
                    and not (self.evitar_vencimento and rolagem_entre(self._ult_data, hoje)):
                s = self._direcao(gap, bar)
                if s != 0:
                    d.gap = gap
                    d.emitiu = True
                    self.dias_com_sinal += 1
                    acoes.append(self._ordem(s, bar))
        elif positions and d.t0 is not None:
            acoes += self._gerencia(positions[0], bar)
        # zera `zerar_antes_min` antes do fim do continuo: o Exit sai no fecho da barra das 18:10 e o motor o executa na
        # ABERTURA da barra das 18:15 -- antes da barra do call (18:20), cujo `close` e' preco de leilao
        if self.zerar_no_fim and d.t0 is not None and not d.exit_emitido and (positions or d.emitiu) \
                and self._min_desde_abertura(ts) >= self.fim_continuo_min - self.zerar_antes_min - BARRA_MIN:
            d.exit_emitido = True
            if positions:
                acoes.append(Exit(reason="fim_do_continuo"))
        self._ult_close, self._ult_data = bar.close, hoje
        return acoes

    # -- partes puras ------------------------------------------------------------------------------
    @staticmethod
    def _direcao(gap: float, bar: Bar) -> int:
        """+1 compra, -1 venda, 0 sem sinal: a barra 1 tem que fechar CONTRA o gap."""
        corpo = bar.close - bar.open
        if gap == 0 or corpo == 0 or (corpo > 0) == (gap > 0):
            return 0
        return 1 if corpo > 0 else -1

    def _ordem(self, s: int, bar: Bar) -> EnterLimit:
        lim = no_tick(bar.close - s * self.recuo_pts, self.tick)
        alvo = None
        if self.alvo_pts is not None:
            alvo = no_tick(lim + s * self.alvo_pts, self.tick)
        elif self.alvo_r is not None:
            alvo = no_tick(lim + s * self.alvo_r * self.stop_pts, self.tick)
        return EnterLimit(
            side="long" if s > 0 else "short",
            limit_price=lim,
            initial_stop=no_tick(lim - s * self.stop_pts, self.tick),
            initial_target=alvo,
            quantity=1,
            ttl_bars=self.ttl_barras,
            exit_split_unit=1 if alvo is not None else None,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO if alvo is not None else None,
            reason="win_gap_barra1",
        )

    def _gerencia(self, pos: IntradayOpenPosition, bar: Bar) -> list[IntradayAction]:
        """Breakeven: depois de +`be_r` x stop de excursao (barras posteriores ao fill), stop vai para o preco de entrada + 1 tick."""
        if self.be_r is None:
            return []
        s = 1 if pos.side == "long" else -1
        d = self._d
        d.melhor = bar.high if d.melhor is None and s > 0 else (bar.low if d.melhor is None else
                                                                  (max(d.melhor, bar.high) if s > 0 else min(d.melhor, bar.low)))
        if (d.melhor - pos.entry_price) * s >= self.be_r * self.stop_pts:
            novo = no_tick(pos.entry_price + s * self.tick, self.tick)
            if pos.current_stop is None or (novo - pos.current_stop) * s > 0:
                return [AdjustStop(new_stop=novo)]
        return []
