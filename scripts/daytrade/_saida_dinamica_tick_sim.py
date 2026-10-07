"""Simulador TICK a TICK compartilhado pelos dois scripts de "saida dinamica"
de 2026-09-24 (`wdo_cor_minuto_saida_dinamica_2026_09_24.py` e
`wdo_oscilacao_lado_saida_dinamica_2026_09_24.py`).

Nao usa `backtest/intraday/engine.py` porque a regra de saida pedida pelo
dono -- "sai a MERCADO no primeiro instante em que o P&L aberto (medido tick
a tick) alcanca k ticks favoraveis" -- nao e' um `tp`/`sl` fixo amarrado na
entrada, e' um limiar monitorado continuamente. O motor de producao nao
expressa isso; um simulador standalone, tick a tick, expressa direto. Reusa
IGUAL do motor: `core.models.IntradayExitReason`, `backtest.intraday.machine.
IntradayTrade` (o dataclass que ja calcula `pnl_brl`), e a TABELA PADRAO
(`backtest.intraday.report`).

## Janela IS (pequeno teste, ordem do dono -- NAO tocar o OOS)

O script anterior de cor-do-minuto (`wdo_cor_minuto_1mes_2026_09_10.py`, ver
a memoria `cor_do_minuto_wdo_refutada_2026_09_10.md`) usou uma janela IS de
21 pregoes e um OOS de 156 -- 177 no total. `177 pregoes M1
(2025-12-08..2026-08-25)` e' exatamente a janela documentada em
`backtest.intraday.profiles.FUTURES_PROFILES["WDO@"]`, entao a janela IS
(os ULTIMOS 21 pregoes daquela populacao, 2026-07-28..2026-08-25) e' a
reconstrucao mais defensavel disponivel -- o script original ja nao existe
no repo (nao commitado, sem rastro em `git log --all`). Ver a ressalva de
suposicao no topo dos dois scripts principais.

Tres pregoes da janela de 21 tem tick incompleto no parquet canonico
(`data/raw_ticks/WDO_A_.parquet`) -- buraco de captura anterior a esta
tarefa, sem relacao com o sinal -- e foram excluidos:

  * 2026-08-03 e 2026-08-04: SEM nenhum tick (so' M1 nativo existe);
  * 2026-07-31: so' 3.824 negocios (contra 85k-160k dos outros dias) e
    comeca as 12:32 -- falta a sessao inteira da manha (09:00-12:32).

A janela IS efetiva desta run tem 18 pregoes, nao 21.

Os 3 primeiros dias da janela (07-28, 07-29, 07-30) tem um DESVIO GRANDE e
CONSTANTE (33-36 pontos) entre o M1 continuo (`data/raw_intraday/
WDO_A_.parquet`, AJUSTADO por rolagem de contrato -- ver `core.instruments.
InstrumentEconomics` sobre a serie `@` nao reportar o passo real) e o preco
NEGOCIADO de verdade no tick (`data/raw_ticks/WDO_A_.parquet`, cru) -- uma
rolagem de contrato caiu dentro da janela. O desvio e' CONSTANTE dentro de
cada pregao (nao corta o dia ao meio), entao NAO afeta a mediana21 (e'
diferenca de RANGE, invariante a deslocamento) nem a entrada a mercado
(busca por horario, nao por preco) -- so afetaria a entrada-limite se ela
comparasse contra o preco AJUSTADO do M1; por isso `modo_entrada='limite'`
usa o preco CRU do proprio tick no fechamento da barra como preco da ordem
(ver `simular`), nunca `bar['close']`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]

TZ = "America/Sao_Paulo"
TICK_SIZE = 0.5
POINT_VALUE_BRL = 10.0
FEE_ROUND_TRIP_BRL = 0.50
SLIPPAGE_TICKS = 1.0
TRAIL_TICKS = 2.0
MEDIAN_LOOKBACK = 21
CAPITAL_REAL_BRL = 375.0
MARGEM_1_CONTRATO_BRL = 150.0
SYMBOL = "WDO@"

#: Regra de saida "deixa correr" (correcao do dono, 2026-09-24) -- ver
#: `resolver_saida_deixa_correr`. Ativa quando a excursao favoravel bate
#: `DEIXA_CORRER_ATIVACAO_TICKS`; a partir dai o stop nunca mais recua,
#: comeca no PISO (`DEIXA_CORRER_PISO_TICKS` alem da entrada -- cobre custo)
#: e sobe para `max(piso, extremo -/+ trail)`.
DEIXA_CORRER_ATIVACAO_TICKS = 2.0
DEIXA_CORRER_PISO_TICKS = 1.0

SESSION_START = dt.time(9, 0)
FLATTEN_CUTOFF = dt.time(18, 25)  # corte de 5min antes do fim (18:30) -- mesma regra do motor
ENTRY_LIMIT_TTL_MIN = 5  # premissa (nao medida): "prazo curto" pedido pelo dono, ver docstring dos scripts

#: Janela IS -- ultimos 21 pregoes da populacao 2025-12-08..2026-08-25
#: documentada em `profiles.py`, menos os 3 dias com tick incompleto/ausente
#: (ver docstring): 18 pregoes efetivos.
IS_DIAS: list[dt.date] = [
    dt.date(2026, 7, 28), dt.date(2026, 7, 29), dt.date(2026, 7, 30),
    dt.date(2026, 8, 5), dt.date(2026, 8, 6), dt.date(2026, 8, 7),
    dt.date(2026, 8, 10), dt.date(2026, 8, 11), dt.date(2026, 8, 12), dt.date(2026, 8, 13), dt.date(2026, 8, 14),
    dt.date(2026, 8, 17), dt.date(2026, 8, 18), dt.date(2026, 8, 19), dt.date(2026, 8, 20), dt.date(2026, 8, 21),
    dt.date(2026, 8, 24), dt.date(2026, 8, 25),
]


# --------------------------------------------------------------------------
# Carregamento
# --------------------------------------------------------------------------

def carregar_m1(dias: list[dt.date]) -> dict[dt.date, pd.DataFrame]:
    """M1 nativo do MT5 (`data/raw_intraday/WDO_A_.parquet`), so a sessao
    09:00-18:25 (elegivel para SINAL/entrada -- ver `FLATTEN_CUTOFF`), com as
    colunas de cor/streak/mediana21 ja calculadas, POR PREGAO (reinicia a
    cada dia -- nenhuma barra do dia anterior entra na mediana nem na
    sequencia, para nao misturar gap overnight com continuidade intradiaria)."""
    df = pd.read_parquet(RAIZ / "data" / "raw_intraday" / "WDO_A_.parquet",
                          columns=["open", "high", "low", "close"])
    df.index = df.index.tz_convert(TZ)
    out: dict[dt.date, pd.DataFrame] = {}
    for dia in dias:
        sub = df.loc[df.index.date == dia]
        sub = sub.between_time(SESSION_START, FLATTEN_CUTOFF, inclusive="left")
        if sub.empty:
            continue
        sub = sub.copy()
        cor = np.where(sub["close"] > sub["open"], "verde",
              np.where(sub["close"] < sub["open"], "vermelho", "branco"))
        sub["cor"] = cor
        streak_cor = []
        streak_len = []
        cur_cor, cur_len = None, 0
        for c in cor:
            if c == "branco":
                cur_cor, cur_len = None, 0
            elif c == cur_cor:
                cur_len += 1
            else:
                cur_cor, cur_len = c, 1
            streak_cor.append(cur_cor)
            streak_len.append(cur_len)
        sub["streak_cor"] = streak_cor
        sub["streak_len"] = streak_len
        sub["range_ticks"] = (sub["high"] - sub["low"]) / TICK_SIZE
        sub["median21_ticks"] = sub["range_ticks"].rolling(MEDIAN_LOOKBACK).median()
        sub["fecha_ts"] = sub.index + pd.Timedelta(minutes=1)
        out[dia] = sub
    return out


def carregar_ticks(dias: list[dt.date]) -> dict[dt.date, pd.DataFrame]:
    """Negocios reais (`market_data_intraday.tick_storage.load_ticks`), so a
    sessao 09:00-18:25 (mesmo corte de achatamento). Index = timestamp,
    colunas `last`/`volume`."""
    import sys
    sys.path.insert(0, str(RAIZ / "src"))
    from market_data_intraday.tick_storage import load_ticks

    t = load_ticks(SYMBOL)
    t.index = t.index.tz_convert(TZ)
    out: dict[dt.date, pd.DataFrame] = {}
    for dia in dias:
        sub = t.loc[t.index.date == dia, ["last", "volume"]]
        sub = sub.between_time(SESSION_START, FLATTEN_CUTOFF, inclusive="left")
        if sub.empty:
            continue
        out[dia] = sub
    return out


# --------------------------------------------------------------------------
# Resolucao de saida (vetorizada em numpy)
# --------------------------------------------------------------------------

def _ts_tz(valor_np64) -> pd.Timestamp:
    """`ticks.index.values` (numpy `datetime64[us]`) carrega o INSTANTE UTC
    mas perde o rotulo de fuso ao virar array -- `pd.Timestamp` direto sairia
    tz-NAIVE e nao compara com `m1["fecha_ts"]` (tz-aware). Rotula UTC (o
    instante ja esta correto, so falta o rotulo) e converte para `TZ`."""
    return pd.Timestamp(valor_np64, tz="UTC").tz_convert(TZ)


@dataclass
class SaidaResolvida:
    exit_price: float
    exit_ts: pd.Timestamp
    exit_reason: str  # "target" | "stop" | "forced_flatten"
    exit_detail: str | None = None


def resolver_saida(ticks_ts: np.ndarray, ticks_px: np.ndarray, start_idx: int,
                    side: str, fill_price: float, k_ticks: float, stop_ticks: float,
                    trailing: bool) -> SaidaResolvida:
    """`ticks_ts`/`ticks_px` ja cortados no fim da monitoracao (achatamento).
    `start_idx` = indice do tick de FILL; a monitoracao comeca no tick
    SEGUINTE (o fill em si nao pode ja nascer preenchendo o proprio alvo)."""
    px = ticks_px[start_idx + 1:]
    ts = ticks_ts[start_idx + 1:]
    if len(px) == 0:
        return SaidaResolvida(_aplica_slippage(fill_price, side, saida=True),
                               _ts_tz(ticks_ts[start_idx]), "forced_flatten")

    if side == "long":
        alvo = fill_price + k_ticks * TICK_SIZE
        stop = fill_price - stop_ticks * TICK_SIZE
        bate_alvo = px >= alvo
        bate_stop = px <= stop
    else:
        alvo = fill_price - k_ticks * TICK_SIZE
        stop = fill_price + stop_ticks * TICK_SIZE
        bate_alvo = px <= alvo
        bate_stop = px >= stop

    idx_alvo = int(np.argmax(bate_alvo)) if bate_alvo.any() else None
    idx_stop = int(np.argmax(bate_stop)) if bate_stop.any() else None

    if not trailing:
        candidatos = [(i, r) for i, r in ((idx_alvo, "target"), (idx_stop, "stop")) if i is not None]
        if not candidatos:
            exit_px, exit_ts, reason, detail = px[-1], ts[-1], "forced_flatten", None
        else:
            i, reason = min(candidatos, key=lambda t: t[0])
            exit_px, exit_ts, detail = px[i], ts[i], None
    else:
        if idx_stop is not None and (idx_alvo is None or idx_stop < idx_alvo):
            exit_px, exit_ts, reason, detail = px[idx_stop], ts[idx_stop], "stop", None
        elif idx_alvo is not None:
            sub_px, sub_ts = px[idx_alvo:], ts[idx_alvo:]
            if side == "long":
                extremo = np.maximum.accumulate(sub_px)
                nivel_trail = extremo - TRAIL_TICKS * TICK_SIZE
                recuo = sub_px <= nivel_trail
            else:
                extremo = np.minimum.accumulate(sub_px)
                nivel_trail = extremo + TRAIL_TICKS * TICK_SIZE
                recuo = sub_px >= nivel_trail
            idx_recuo = int(np.argmax(recuo)) if recuo.any() else None
            if idx_recuo is not None:
                exit_px, exit_ts, reason, detail = sub_px[idx_recuo], sub_ts[idx_recuo], "target", "trailing_stop"
            else:
                exit_px, exit_ts, reason, detail = px[-1], ts[-1], "forced_flatten", None
        else:
            exit_px, exit_ts, reason, detail = px[-1], ts[-1], "forced_flatten", None

    exit_price = _aplica_slippage(float(exit_px), side, saida=True)
    return SaidaResolvida(exit_price, _ts_tz(exit_ts), reason, detail)


def _aplica_slippage(preco: float, side: str, saida: bool) -> float:
    """`side` = lado da POSICAO (long/short). Entrada LONG / saida SHORT sao
    ordens de COMPRA (sobem); entrada SHORT / saida LONG sao ordens de VENDA
    (descem) -- mesma convencao de `backtest.intraday.costs.
    apply_intraday_slippage` ('compra sobe, venda desce')."""
    compra = (side == "long" and not saida) or (side == "short" and saida)
    delta = SLIPPAGE_TICKS * TICK_SIZE
    return preco + delta if compra else preco - delta


# --------------------------------------------------------------------------
# Simulacao de uma celula (um dia, um sinal ja resolvido em long/short/None)
# --------------------------------------------------------------------------

@dataclass
class TentativaEntradaLimite:
    preenchida: bool
    atraso_min: float | None  # None se nao preencheu (censurado pelo TTL)


@dataclass
class ResultadoCelula:
    trades: list = field(default_factory=list)
    tentativas_limite: list = field(default_factory=list)  # TentativaEntradaLimite, so' modo 'limite'
    dias_com_trade: set = field(default_factory=set)


def simular(dias: list[dt.date], m1_por_dia: dict[dt.date, pd.DataFrame],
            ticks_por_dia: dict[dt.date, pd.DataFrame], sinais_por_dia: dict[dt.date, pd.Series],
            k_ticks: float, trailing: bool, modo_entrada: str = "teto",
            queue_ahead_qty: float = 0.0, capital_inicial: float | None = None,
            margem_1_contrato: float = MARGEM_1_CONTRATO_BRL) -> ResultadoCelula:
    """`sinais_por_dia[dia]` e' uma Series alinhada ao index de `m1_por_dia[dia]`
    com valores em {None, 'long', 'short'} -- o lado PROPOSTO se o robo
    estivesse livre naquele fechamento de barra (posicao/capital sao
    aplicados AQUI, no caminhante causal, nao no sinal).

    `capital_inicial` != None liga o PORTAO de capital (so' abre 1o contrato
    com caixa >= `margem_1_contrato`, regra de 2026-09-08 -- ver CLAUDE.md
    "O piso de capital e indicacao de PARTIDA"). `None` = sem portao (run
    NAO censurada, para as estatisticas por trade)."""
    from backtest.intraday.machine import IntradayTrade
    from core.models import IntradayExitReason

    razao_enum = {"target": IntradayExitReason.TARGET, "stop": IntradayExitReason.STOP,
                  "forced_flatten": IntradayExitReason.FORCED_FLATTEN}

    resultado = ResultadoCelula()
    capital = capital_inicial

    for dia in dias:
        m1 = m1_por_dia.get(dia)
        ticks = ticks_por_dia.get(dia)
        if m1 is None or ticks is None or ticks.empty:
            continue
        sinais = sinais_por_dia.get(dia)
        if sinais is None:
            continue

        ticks_ts = ticks.index.values
        ticks_px = ticks["last"].values.astype(float)
        ticks_vol = ticks["volume"].values.astype(float)
        cutoff_ts = pd.Timestamp.combine(dia, FLATTEN_CUTOFF).tz_localize(TZ).to_datetime64()

        n = len(m1)
        i = 0
        while i < n:
            side = sinais.iloc[i]
            if side is None or (isinstance(side, float) and pd.isna(side)):
                i += 1
                continue
            if capital is not None and capital < margem_1_contrato:
                i += 1
                continue

            bar = m1.iloc[i]
            median_ticks = bar["median21_ticks"]
            if pd.isna(median_ticks):
                i += 1
                continue
            fecha_ts = bar["fecha_ts"]
            stop_ticks = max(2.0, round(1.5 * float(median_ticks)))

            fecha_ts_np = fecha_ts.to_datetime64()
            if modo_entrada == "teto":
                fill_idx = int(np.searchsorted(ticks_ts, fecha_ts_np, side="left"))
                if fill_idx >= len(ticks_ts) or ticks_ts[fill_idx] >= cutoff_ts:
                    i += 1
                    continue
                fill_price = _aplica_slippage(float(ticks_px[fill_idx]), side, saida=False)
                fill_ts = _ts_tz(ticks_ts[fill_idx])
                start_idx = fill_idx
            elif modo_entrada == "limite":
                janela_ini = int(np.searchsorted(ticks_ts, fecha_ts_np, side="left"))
                if janela_ini >= len(ticks_ts):
                    resultado.tentativas_limite.append(TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                # preco CRU do proprio tick no fechamento da barra -- nao
                # `bar["close"]` (M1 continuo, ajustado por rolagem de
                # contrato nos 3 primeiros dias da janela, ver docstring do
                # modulo). Robo real posta a limite no preco que VE no feed,
                # que e' o cru.
                ordem_preco = float(ticks_px[janela_ini])
                ttl_ts = (fecha_ts + pd.Timedelta(minutes=ENTRY_LIMIT_TTL_MIN)).to_datetime64()
                janela_fim = int(np.searchsorted(ticks_ts, min(ttl_ts, cutoff_ts), side="left"))
                if janela_ini >= janela_fim:
                    resultado.tentativas_limite.append(TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                px_janela = ticks_px[janela_ini:janela_fim]
                vol_janela = ticks_vol[janela_ini:janela_fim]
                no_preco = np.isclose(px_janela, ordem_preco, atol=1e-9)
                vol_acumulado = np.cumsum(np.where(no_preco, vol_janela, 0.0))
                preenche = no_preco & (vol_acumulado >= queue_ahead_qty)
                if not preenche.any():
                    resultado.tentativas_limite.append(TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                idx_rel = int(np.argmax(preenche))
                fill_idx = janela_ini + idx_rel
                fill_price = ordem_preco  # ordem-limite: preenche no proprio nivel, sem deslize
                fill_ts = _ts_tz(ticks_ts[fill_idx])
                atraso_min = (fill_ts - fecha_ts).total_seconds() / 60.0
                resultado.tentativas_limite.append(TentativaEntradaLimite(True, atraso_min))
                start_idx = fill_idx
            else:
                raise ValueError(f"modo_entrada desconhecido: {modo_entrada!r}")

            # `ticks_ts`/`ticks_px` ja vem cortados em `FLATTEN_CUTOFF` por
            # `carregar_ticks` -- nao ha' negocio depois do achatamento para
            # filtrar de novo aqui.
            saida = resolver_saida(ticks_ts, ticks_px, start_idx, side,
                                    fill_price, k_ticks, stop_ticks, trailing)

            trade = IntradayTrade(
                symbol=SYMBOL, strategy_name="saida_dinamica", strategy_version="2026-09-24",
                side=side, entry_ts=fill_ts, entry_price=fill_price,
                exit_ts=saida.exit_ts, exit_price=saida.exit_price, quantity=1,
                exit_reason=razao_enum[saida.exit_reason], point_value_brl=POINT_VALUE_BRL,
                capital_base=capital_inicial or CAPITAL_REAL_BRL, fees_total=FEE_ROUND_TRIP_BRL,
                slippage_total=SLIPPAGE_TICKS * TICK_SIZE * POINT_VALUE_BRL, exit_detail=saida.exit_detail,
            )
            resultado.trades.append(trade)
            resultado.dias_com_trade.add(dia)
            if capital is not None:
                capital += trade.pnl_brl

            # retoma na primeira barra cujo FECHAMENTO e' depois da saida
            prox = m1.index[m1["fecha_ts"] > saida.exit_ts]
            if len(prox) == 0:
                break
            i = m1.index.get_loc(prox[0])

    return resultado


# --------------------------------------------------------------------------
# Estatisticas
# --------------------------------------------------------------------------

def estatisticas(trades: list) -> dict:
    pnls = np.array([t.pnl_brl for t in trades], dtype=float)
    n = len(pnls)
    if n == 0:
        return dict(n=0, media=float("nan"), desvio=float("nan"), ic95=(float("nan"), float("nan")),
                    win_pct=float("nan"), breakeven_empirico=float("nan"),
                    ganho_medio=float("nan"), perda_media=float("nan"))
    media = float(pnls.mean())
    desvio = float(pnls.std(ddof=1)) if n > 1 else 0.0
    erro_padrao = desvio / (n ** 0.5) if n > 1 else 0.0
    ic95 = (media - 1.96 * erro_padrao, media + 1.96 * erro_padrao)
    vitorias = pnls[pnls > 0]
    perdas = pnls[pnls < 0]
    win_pct = 100.0 * len(vitorias) / n
    ganho_medio = float(vitorias.mean()) if len(vitorias) else 0.0
    perda_media = float(-perdas.mean()) if len(perdas) else 0.0
    breakeven = (perda_media / (ganho_medio + perda_media)) * 100.0 if (ganho_medio + perda_media) > 0 else float("nan")
    return dict(n=n, media=media, desvio=desvio, ic95=ic95, win_pct=win_pct,
                breakeven_empirico=breakeven, ganho_medio=ganho_medio, perda_media=perda_media)


@dataclass
class ResultadoFake:
    """Substituto minimo de `IntradayBacktestResult` -- so os campos que
    `backtest.intraday.report.linha_de_resultado` le."""
    trades: list
    equity_curve: pd.Series
    metrics: dict
    wiped_out_at = None
    sessoes_puladas_por_capital: list = field(default_factory=list)
    deslize_alvo_ticks: float = 0.0
    fila_entrada_qty: float = 0.0
    fila_saida_qty: float = 0.0
    fila_calibrada: bool | None = None


def monta_resultado(trades: list, capital_inicial: float) -> ResultadoFake:
    from backtest.metrics import max_drawdown

    trades_ordenados = sorted(trades, key=lambda t: t.exit_ts)
    valores = []
    acumulado = capital_inicial
    idx = []
    for t in trades_ordenados:
        acumulado += t.pnl_brl
        valores.append(acumulado)
        idx.append(t.exit_ts)
    if not idx:
        equity = pd.Series([capital_inicial], index=[pd.Timestamp.now(tz=TZ)])
    else:
        equity = pd.Series(valores, index=pd.DatetimeIndex(idx))
    metrics = {"max_drawdown": max_drawdown(equity) if len(equity) > 1 else 0.0}
    return ResultadoFake(trades=trades_ordenados, equity_curve=equity, metrics=metrics)


# --------------------------------------------------------------------------
# Trades HIPOTETICOS -- usado pelo sinal `lado_vencedor` do 2o script
# (oscilacao+lado): "pra qual lado teria dado mais WIN nos ultimos 21
# fechamentos, usando SO' resultado ja RESOLVIDO antes de agora". Mesma regra
# de saida (k/stop) dos trades REAIS -- so' sem deslize/fee (e' feature de
# decisao, nao execucao) e entrando no OPEN da barra (nao no primeiro tick
# depois do fechamento -- e' retrospectivo, "se eu tivesse comprado quando
# aquela barra abriu").
# --------------------------------------------------------------------------

def resolver_hipoteticos_dia(m1_dia: pd.DataFrame, ticks_dia: pd.DataFrame,
                              k_ticks: float, trailing: bool) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Para CADA barra `i` com mediana21 disponivel, resolve um LONG e um
    SHORT hipoteticos entrando no OPEN daquela barra. Devolve 4 Series
    alinhadas ao index de `m1_dia`: `long_resolvido_ts`, `long_venceu`
    (bool), `short_resolvido_ts`, `short_venceu`."""
    ticks_ts = ticks_dia.index.values
    ticks_px = ticks_dia["last"].values.astype(float)
    n = len(m1_dia)
    long_ts = [pd.NaT] * n
    long_win = [None] * n
    short_ts = [pd.NaT] * n
    short_win = [None] * n
    for i in range(n):
        bar = m1_dia.iloc[i]
        median_ticks = bar["median21_ticks"]
        if pd.isna(median_ticks):
            continue
        open_ts_np = m1_dia.index[i].to_datetime64()
        start_idx = int(np.searchsorted(ticks_ts, open_ts_np, side="left"))
        if start_idx >= len(ticks_ts):
            continue
        fill_price = float(ticks_px[start_idx])
        stop_ticks = max(2.0, round(1.5 * float(median_ticks)))
        for side, ts_out, win_out in (("long", long_ts, long_win), ("short", short_ts, short_win)):
            saida = resolver_saida(ticks_ts, ticks_px, start_idx, side, fill_price,
                                    k_ticks, stop_ticks, trailing)
            ts_out[i] = saida.exit_ts
            win_out[i] = (saida.exit_reason == "target")
    return (pd.Series(long_ts, index=m1_dia.index), pd.Series(long_win, index=m1_dia.index, dtype=object),
            pd.Series(short_ts, index=m1_dia.index), pd.Series(short_win, index=m1_dia.index, dtype=object))


def resolver_hipoteticos_dia_deixa_correr(m1_dia: pd.DataFrame, ticks_dia: pd.DataFrame,
                                           trail_mult: float) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Igual a `resolver_hipoteticos_dia`, mas resolvendo pela regra "deixa
    correr" (`resolver_saida_deixa_correr`) -- usada pelo sinal
    `lado_vencedor` de `wdo_saida_deixa_correr_2026_09_24.py`. "Venceu" =
    P&L LIQUIDO positivo (deslize + corretagem ja descontados), nao so' ter
    capturado algum tick bruto -- uma saida no PISO captura +1 tick bruto e
    ainda assim e' perda liquida (deslize de 1 tick + corretagem)."""
    ticks_ts = ticks_dia.index.values
    ticks_px = ticks_dia["last"].values.astype(float)
    n = len(m1_dia)
    long_ts = [pd.NaT] * n
    long_win = [None] * n
    short_ts = [pd.NaT] * n
    short_win = [None] * n
    for i in range(n):
        bar = m1_dia.iloc[i]
        median_ticks = bar["median21_ticks"]
        if pd.isna(median_ticks):
            continue
        open_ts_np = m1_dia.index[i].to_datetime64()
        start_idx = int(np.searchsorted(ticks_ts, open_ts_np, side="left"))
        if start_idx >= len(ticks_ts):
            continue
        fill_price = float(ticks_px[start_idx])
        stop_ticks_inicial = max(2.0, round(1.5 * float(median_ticks)))
        trail_ticks = max(2.0, round(trail_mult * float(median_ticks)))
        for side, ts_out, win_out in (("long", long_ts, long_win), ("short", short_ts, short_win)):
            saida = resolver_saida_deixa_correr(ticks_ts, ticks_px, start_idx, side, fill_price,
                                                 stop_ticks_inicial, trail_ticks)
            ts_out[i] = saida.exit_ts
            pnl_liquido = ((saida.capturado_ticks - SLIPPAGE_TICKS) * TICK_SIZE * POINT_VALUE_BRL
                           - FEE_ROUND_TRIP_BRL)
            win_out[i] = pnl_liquido > 0
    return (pd.Series(long_ts, index=m1_dia.index), pd.Series(long_win, index=m1_dia.index, dtype=object),
            pd.Series(short_ts, index=m1_dia.index), pd.Series(short_win, index=m1_dia.index, dtype=object))


def sinal_lado_vencedor(m1_dia: pd.DataFrame, long_ts: pd.Series, long_win: pd.Series,
                         short_ts: pd.Series, short_win: pd.Series, lookback: int = 21) -> pd.Series:
    """No fechamento da barra `i`, olha ate' `lookback` barras anteriores
    (janela `[max(0, i-lookback), i)`) e conta vitorias hipoteticas por lado
    ENTRE AS JA RESOLVIDAS antes do fechamento de `i` (`resolvido_ts <
    fecha_ts[i]`) -- e' o que faz a leitura ser sem look-ahead: uma
    hipotetica ainda pendente (alvo/stop nao bateu) nao pode informar a
    decisao de agora. Empate (inclusive 0 a 0) pula."""
    n = len(m1_dia)
    fecha = m1_dia["fecha_ts"]
    lado = pd.Series(None, index=m1_dia.index, dtype=object)
    for i in range(n):
        ini = max(0, i - lookback)
        if ini >= i:
            continue
        fecha_i = fecha.iloc[i]
        janela_long_ts = long_ts.iloc[ini:i]
        janela_long_win = long_win.iloc[ini:i]
        janela_short_ts = short_ts.iloc[ini:i]
        janela_short_win = short_win.iloc[ini:i]
        long_resolvidos = janela_long_win[(janela_long_ts < fecha_i) & janela_long_win.notna()]
        short_resolvidos = janela_short_win[(janela_short_ts < fecha_i) & janela_short_win.notna()]
        n_long_win = int(long_resolvidos.sum()) if len(long_resolvidos) else 0
        n_short_win = int(short_resolvidos.sum()) if len(short_resolvidos) else 0
        if n_long_win == n_short_win:
            continue
        lado.iloc[i] = "long" if n_long_win > n_short_win else "short"
    return lado


# --------------------------------------------------------------------------
# Saida "DEIXA CORRER" -- correcao do dono, 2026-09-24. O desenho k/fixo/
# trailing anterior fechava no PRIMEIRO lucro (fixo) ou punha o stop a
# ~breakeven-custo assim que ativava (trailing, `best-2t` com ativacao em
# `k=2`) -- as DUAS formas cortavam o ganho no primeiro recuo normal, dai o
# win% de 0-20% medido em `wdo_cor_minuto_saida_dinamica_2026_09_24.py` /
# `wdo_oscilacao_lado_saida_dinamica_2026_09_24.py`. Aqui o stop so' aperta
# (ratchet monotonico): comeca no stop INICIAL de sempre, vira um PISO fixo
# (entrada + 1 tick) quando a excursao favoravel bate 2 ticks, e dali sobe
# para `max(piso, extremo -/+ trail)`. NAO reusa `simular`/`resolver_saida`
# por dentro -- ver a nota na docstring de `simular_deixa_correr`.
# --------------------------------------------------------------------------

@dataclass
class SaidaDeixaCorrer:
    exit_price: float
    exit_ts: pd.Timestamp
    exit_detail: str  # "inicial" | "piso" | "trailing" | "forced_flatten"
    ativou: bool
    mfe_ticks: float
    capturado_ticks: float


def resolver_saida_deixa_correr(ticks_ts: np.ndarray, ticks_px: np.ndarray, start_idx: int,
                                 side: str, fill_price: float, stop_ticks_inicial: float,
                                 trail_ticks: float) -> SaidaDeixaCorrer:
    """1) stop INICIAL fixo (`stop_ticks_inicial`) ate' a excursao favoravel
    bater `DEIXA_CORRER_ATIVACAO_TICKS`; 2) dali em diante o stop vira um
    PISO (entrada +/- 1 tick, nunca recua) que sobe para `max(piso, extremo
    -/+ trail_ticks)` -- ratchet monotonico, so aperta. Sai a mercado no
    primeiro toque, sempre com 1 tick de deslize (`_aplica_slippage`)."""
    px = ticks_px[start_idx + 1:]
    ts = ticks_ts[start_idx + 1:]
    if len(px) == 0:
        exit_price = _aplica_slippage(fill_price, side, saida=True)
        return SaidaDeixaCorrer(exit_price, _ts_tz(ticks_ts[start_idx]), "forced_flatten", False, 0.0, 0.0)

    if side == "long":
        favor = (px - fill_price) / TICK_SIZE
        stop_inicial_nivel = fill_price - stop_ticks_inicial * TICK_SIZE
        piso_nivel = fill_price + DEIXA_CORRER_PISO_TICKS * TICK_SIZE
        bate_inicial = px <= stop_inicial_nivel
    else:
        favor = (fill_price - px) / TICK_SIZE
        stop_inicial_nivel = fill_price + stop_ticks_inicial * TICK_SIZE
        piso_nivel = fill_price - DEIXA_CORRER_PISO_TICKS * TICK_SIZE
        bate_inicial = px >= stop_inicial_nivel

    ativa_mask = favor >= DEIXA_CORRER_ATIVACAO_TICKS
    idx_inicial = int(np.argmax(bate_inicial)) if bate_inicial.any() else None
    idx_ativacao = int(np.argmax(ativa_mask)) if ativa_mask.any() else None
    ativou = idx_ativacao is not None and (idx_inicial is None or idx_inicial > idx_ativacao)

    if not ativou:
        if idx_inicial is not None:
            exit_idx_abs, detail = idx_inicial, "inicial"
        else:
            exit_idx_abs, detail = len(px) - 1, "forced_flatten"
    else:
        sub_px = px[idx_ativacao:]
        if side == "long":
            extremo = np.maximum.accumulate(sub_px)
            nivel = np.maximum(piso_nivel, extremo - trail_ticks * TICK_SIZE)
            bate = sub_px <= nivel
        else:
            extremo = np.minimum.accumulate(sub_px)
            nivel = np.minimum(piso_nivel, extremo + trail_ticks * TICK_SIZE)
            bate = sub_px >= nivel
        idx_rel = int(np.argmax(bate)) if bate.any() else None
        if idx_rel is not None:
            exit_idx_abs = idx_ativacao + idx_rel
            detail = "piso" if abs(float(nivel[idx_rel]) - piso_nivel) < 1e-9 else "trailing"
        else:
            exit_idx_abs, detail = len(px) - 1, "forced_flatten"

    exit_px_raw = float(px[exit_idx_abs])
    exit_price = _aplica_slippage(exit_px_raw, side, saida=True)
    mfe_ticks = float(favor[:exit_idx_abs + 1].max())
    capturado_ticks = float(favor[exit_idx_abs])
    return SaidaDeixaCorrer(exit_price, _ts_tz(ts[exit_idx_abs]), detail, ativou, mfe_ticks, capturado_ticks)


@dataclass
class DiagnosticoTrade:
    ativou: bool
    mfe_ticks: float
    capturado_ticks: float
    holding_min: float


@dataclass
class ResultadoCelulaDeixaCorrer(ResultadoCelula):
    diagnosticos: list = field(default_factory=list)


def simular_deixa_correr(dias: list[dt.date], m1_por_dia: dict[dt.date, pd.DataFrame],
                          ticks_por_dia: dict[dt.date, pd.DataFrame], sinais_por_dia: dict[dt.date, pd.Series],
                          trail_mult: float, modo_entrada: str = "teto", queue_ahead_qty: float = 0.0,
                          capital_inicial: float | None = None,
                          margem_1_contrato: float = MARGEM_1_CONTRATO_BRL) -> ResultadoCelulaDeixaCorrer:
    """Mesma entrada (teto/limite) e mesmo portao de capital de `simular` --
    so' a SAIDA muda (`resolver_saida_deixa_correr` no lugar de
    `resolver_saida`). DUPLICA o bloco de entrada em vez de fatorar por cima
    de `simular` de proposito: os dois scripts anteriores (cor-do-minuto e
    oscilacao+lado) ja rodaram sobre `simular` e nao podem quebrar por uma
    mudanca de assinatura aqui."""
    from backtest.intraday.machine import IntradayTrade
    from core.models import IntradayExitReason

    resultado = ResultadoCelulaDeixaCorrer()
    capital = capital_inicial

    for dia in dias:
        m1 = m1_por_dia.get(dia)
        ticks = ticks_por_dia.get(dia)
        if m1 is None or ticks is None or ticks.empty:
            continue
        sinais = sinais_por_dia.get(dia)
        if sinais is None:
            continue

        ticks_ts = ticks.index.values
        ticks_px = ticks["last"].values.astype(float)
        ticks_vol = ticks["volume"].values.astype(float)
        cutoff_ts = pd.Timestamp.combine(dia, FLATTEN_CUTOFF).tz_localize(TZ).to_datetime64()

        n = len(m1)
        i = 0
        while i < n:
            side = sinais.iloc[i]
            if side is None or (isinstance(side, float) and pd.isna(side)):
                i += 1
                continue
            if capital is not None and capital < margem_1_contrato:
                i += 1
                continue

            bar = m1.iloc[i]
            median_ticks = bar["median21_ticks"]
            if pd.isna(median_ticks):
                i += 1
                continue
            fecha_ts = bar["fecha_ts"]
            stop_ticks_inicial = max(2.0, round(1.5 * float(median_ticks)))
            trail_ticks = max(2.0, round(trail_mult * float(median_ticks)))

            fecha_ts_np = fecha_ts.to_datetime64()
            if modo_entrada == "teto":
                fill_idx = int(np.searchsorted(ticks_ts, fecha_ts_np, side="left"))
                if fill_idx >= len(ticks_ts) or ticks_ts[fill_idx] >= cutoff_ts:
                    i += 1
                    continue
                fill_price = _aplica_slippage(float(ticks_px[fill_idx]), side, saida=False)
                fill_ts = _ts_tz(ticks_ts[fill_idx])
                start_idx = fill_idx
            elif modo_entrada == "limite":
                janela_ini = int(np.searchsorted(ticks_ts, fecha_ts_np, side="left"))
                if janela_ini >= len(ticks_ts):
                    resultado.tentativas_limite.append(TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                ordem_preco = float(ticks_px[janela_ini])
                ttl_ts = (fecha_ts + pd.Timedelta(minutes=ENTRY_LIMIT_TTL_MIN)).to_datetime64()
                janela_fim = int(np.searchsorted(ticks_ts, min(ttl_ts, cutoff_ts), side="left"))
                if janela_ini >= janela_fim:
                    resultado.tentativas_limite.append(TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                px_janela = ticks_px[janela_ini:janela_fim]
                vol_janela = ticks_vol[janela_ini:janela_fim]
                no_preco = np.isclose(px_janela, ordem_preco, atol=1e-9)
                vol_acumulado = np.cumsum(np.where(no_preco, vol_janela, 0.0))
                preenche = no_preco & (vol_acumulado >= queue_ahead_qty)
                if not preenche.any():
                    resultado.tentativas_limite.append(TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                idx_rel = int(np.argmax(preenche))
                fill_idx = janela_ini + idx_rel
                fill_price = ordem_preco
                fill_ts = _ts_tz(ticks_ts[fill_idx])
                atraso_min = (fill_ts - fecha_ts).total_seconds() / 60.0
                resultado.tentativas_limite.append(TentativaEntradaLimite(True, atraso_min))
                start_idx = fill_idx
            else:
                raise ValueError(f"modo_entrada desconhecido: {modo_entrada!r}")

            saida = resolver_saida_deixa_correr(ticks_ts, ticks_px, start_idx, side, fill_price,
                                                 stop_ticks_inicial, trail_ticks)

            razao = (IntradayExitReason.FORCED_FLATTEN if saida.exit_detail == "forced_flatten"
                     else IntradayExitReason.STOP)
            trade = IntradayTrade(
                symbol=SYMBOL, strategy_name="deixa_correr", strategy_version="2026-09-24",
                side=side, entry_ts=fill_ts, entry_price=fill_price,
                exit_ts=saida.exit_ts, exit_price=saida.exit_price, quantity=1,
                exit_reason=razao, point_value_brl=POINT_VALUE_BRL,
                capital_base=capital_inicial or CAPITAL_REAL_BRL, fees_total=FEE_ROUND_TRIP_BRL,
                slippage_total=SLIPPAGE_TICKS * TICK_SIZE * POINT_VALUE_BRL, exit_detail=saida.exit_detail,
            )
            resultado.trades.append(trade)
            resultado.dias_com_trade.add(dia)
            holding_min = (saida.exit_ts - fill_ts).total_seconds() / 60.0
            resultado.diagnosticos.append(DiagnosticoTrade(saida.ativou, saida.mfe_ticks,
                                                             saida.capturado_ticks, holding_min))
            if capital is not None:
                capital += trade.pnl_brl

            prox = m1.index[m1["fecha_ts"] > saida.exit_ts]
            if len(prox) == 0:
                break
            i = m1.index.get_loc(prox[0])

    return resultado
