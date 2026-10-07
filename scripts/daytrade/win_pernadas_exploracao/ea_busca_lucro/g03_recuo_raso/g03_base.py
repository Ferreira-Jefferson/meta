# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 3 (`WinBuscaLucroG03RecuoRaso`).

Mesmo molde de `g02_r65/g02_base.py` (deliberado -- script NOVO, nao edita o
da G2): carrega `data/wdo-mt5/WIN@D_M1_...csv` (M1, ajuste por diferenca),
monta a config do motor pelo caminho padrao do repo (`config_for`) e define
as metricas de consistencia + breakeven empirico usadas em toda tabela desta
geracao.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS  = jan-jun/2026 (desenvolvimento/tuning)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
Nunca abre 2025 ou anterior; nunca abre set/2026 em diante nesta geracao.

Fila: WIN@ NAO tem fidelidade calibrada (`backtest.intraday.fidelidade` so'
tem WDO@) -- toda ordem-limite enche no TOQUE (`queue_ahead_qty=0.0`,
`exit_queue_ahead_qty=0.0`), premissa OTIMISTA e IDENTICA nas duas janelas
(precedente `WinRetangulo`/`copawin_retangulo_oos_congelado`/G1/G2).

Capital: R$250,00 (margem crua R$100 x buffer 2,0 x reserva 1,25 -- o piso de
PARTIDA real do WIN@, ver CLAUDE.md "Capital inicial: sempre o minimo real").
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

CSV_PATH = ROOT / "data" / "wdo-mt5" / "WIN@D_M1_202110010900_202610011717.csv"
SYMBOL = "WIN@"
CAPITAL = 250.0
MARGEM_WIN_BRL = 100.0

CORTE_IS_INICIO = pd.Timestamp("2026-01-01")
CORTE_IS_FIM = pd.Timestamp("2026-07-01")        # exclusivo
CORTE_OOS1_FIM = pd.Timestamp("2026-09-01")      # exclusivo

_CACHE: dict = {}


def br(v, dec: int = 2) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def carrega_df() -> pd.DataFrame:
    """DataFrame M1 completo, index = timestamp (naive, hora local B3). So'
    carregado 1x por processo (cache de modulo)."""
    if "df" in _CACHE:
        return _CACHE["df"]
    df = pd.read_csv(CSV_PATH, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    ts = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df = df.set_index(ts).sort_index()
    df = df.rename(columns={"tickvol": "tick_volume", "vol": "real_volume"})
    _CACHE["df"] = df
    return df


def dias_da_janela(df: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp,
                    min_barras: int = 300) -> list:
    """Dias de calendario com pelo menos `min_barras` barras M1 dentro de
    [inicio, fim) -- filtra pregoes incompletos."""
    fatia = df[(df.index >= inicio) & (df.index < fim)]
    contagem = fatia.groupby(fatia.index.date).size()
    return sorted(d for d, n in contagem.items() if n >= min_barras)


def bars_dos_dias(df: pd.DataFrame, dias: list) -> pd.DataFrame:
    alvo = set(dias)
    return df[[d in alvo for d in df.index.date]]


def monta_config(capital: float = CAPITAL):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.profiles import config_for, profile_for
    from core.instruments import economics_for

    profile = profile_for(SYMBOL)
    economia = economics_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=economia.point_value_brl * economia.price_tick_size,
        trade_tick_size=economia.price_tick_size,
        initial_capital=capital,
        target_fills_as_maker=True,
        anchor_exits_at_fill=True,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0,
        exit_queue_ahead_qty=0.0,
        cash_brl=capital,
        margin_per_contract_brl=MARGEM_WIN_BRL,
    )
    return cfg


def roda(dias: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Devolve `(result, strategy)` -- a instancia da estrategia e'
    necessaria para ler `stats_bruto_r57`/`stats_ordens_emitidas` (auditoria
    da licao da Geracao 2, ver docstring da classe)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g03_recuo_raso import WinBuscaLucroG03RecuoRaso

    df = carrega_df()
    bars = bars_dos_dias(df, dias)
    strat = WinBuscaLucroG03RecuoRaso(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_congelado(dias: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Mesma coisa que `roda`, mas importando a classe do arquivo CONGELADO
    (`win_busca_lucro_g03_recuo_raso_congelado_v03.py`) -- so' usar no OOS-1,
    depois que o IS ja' apontou o vencedor."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g03_recuo_raso_congelado_v03 import (
        WinBuscaLucroG03RecuoRaso as WinBuscaLucroG03RecuoRasoCongelado,
    )

    df = carrega_df()
    bars = bars_dos_dias(df, dias)
    strat = WinBuscaLucroG03RecuoRasoCongelado(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def ic95_wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


def consistencia(trades, dias_da_janela_: list) -> dict:
    """Metricas padrao desta linha de pesquisa -- mesmo molde de
    `g02_r65/g02_base.consistencia`."""
    por_dia: dict = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    serie = pd.Series([por_dia.get(d, 0.0) for d in dias_da_janela_],
                       index=pd.to_datetime(dias_da_janela_))
    com_trade = list(por_dia.values())
    liquido = float(serie.sum())
    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = (abs(sum(p) / len(p))) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95_wilson(len(g), n)
    win = (len(g) / n) if n else float("nan")
    ver = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if be == be and n else "--"
    eq = serie.cumsum()
    maxdd = float((eq.cummax() - eq).max()) if len(eq) else 0.0
    seq = pior = 0
    for v in serie.values:
        if v < 0:
            seq += 1
            pior = max(pior, seq)
        elif v > 0:
            seq = 0
    stops_trades = [t for t in trades if getattr(t, "exit_reason", None) is not None
                    and "stop" in str(t.exit_reason.value).lower()]
    stops = [t.pnl_brl for t in stops_trades]
    # distancia REALIZADA do stop, em pontos (preco de saida - preco de
    # entrada, em modulo) -- proxy honesto: o motor nao expoe o nivel de
    # stop ARMADO no `IntradayTrade`, so' onde a saida de fato aconteceu.
    stop_dist_pts = [abs(t.entry_price - t.exit_price) for t in stops_trades]
    return dict(
        liquido=liquido, n=n, pregoes=len(dias_da_janela_),
        com_trade=len(com_trade), sem_trade=len(dias_da_janela_) - len(com_trade),
        win=win, be=be, lo=lo, hi=hi, veredito=ver,
        ganho_medio=gm, perda_media=pm, maxdd=maxdd, seq_neg=pior,
        n_stops=len(stops),
        pontos_por_op=(liquido / n / 0.20) if n else float("nan"),
        lucro_dd=(liquido / maxdd) if maxdd > 0 else float("nan"),
        stop_dist_pts=stop_dist_pts,
        serie=serie,
    )
