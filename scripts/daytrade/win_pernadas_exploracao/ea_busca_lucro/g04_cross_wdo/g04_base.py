# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 4 (`WinBuscaLucroG04CrossWdo`).

Mesmo molde de `g03_recuo_raso/g03_base.py` (script NOVO, nao edita o da G3),
mas carrega DOIS instrumentos (`WIN@D` e `WDO@D`, ambos M1 ajuste por
diferenca) porque a hipotese desta geracao e' de confirmacao CRUZADA entre
os dois.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
Nunca abre 2025 ou anterior; nunca abre set/2026 em diante nesta geracao.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA nas duas janelas (precedente `WinRetangulo`/G1-G3).

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

CSV_WIN = ROOT / "data" / "wdo-mt5" / "WIN@D_M1_202110010900_202610011717.csv"
CSV_WDO = ROOT / "data" / "wdo-mt5" / "WDO@D_M1_202109290900_202609291020.csv"
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


def _carrega_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    ts = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df = df.set_index(ts).sort_index()
    df = df.rename(columns={"tickvol": "tick_volume", "vol": "real_volume"})
    return df[~df.index.duplicated(keep="first")]


def carrega_win() -> pd.DataFrame:
    if "win" not in _CACHE:
        _CACHE["win"] = _carrega_csv(CSV_WIN)
    return _CACHE["win"]


def carrega_wdo() -> pd.DataFrame:
    if "wdo" not in _CACHE:
        _CACHE["wdo"] = _carrega_csv(CSV_WDO)
    return _CACHE["wdo"]


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


def correlacao_incrementos_minuto(win: pd.DataFrame, wdo: pd.DataFrame,
                                   dias: list) -> dict:
    """Correlacao dos incrementos de 1 MINUTO (close.diff(1), DENTRO do
    pregao -- groupby(dia).diff, nunca atravessa a virada de sessao) entre
    WIN@ e WDO@, remedida do zero nesta janela (NUNCA reaproveita o r do
    estudo antigo de 2026-09-15)."""
    w = bars_dos_dias(win, dias)["close"]
    d = bars_dos_dias(wdo, dias)["close"]
    idx = w.index.intersection(d.index).sort_values()
    w = w.reindex(idx)
    d = d.reindex(idx)
    dia = pd.Series(idx.date, index=idx)
    dw = w.groupby(dia).diff(1).dropna()
    dd = d.groupby(dia).diff(1).dropna()
    comuns = dw.index.intersection(dd.index)
    dw, dd = dw.loc[comuns], dd.loc[comuns]
    r = float(dw.corr(dd))
    return dict(r=r, n=len(comuns))


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


def computa_estado(dias_historico: list, janela_min: int, quantil: float):
    """Computa `(anomalo, direcao)` -- a funcao PURA de
    `win_busca_lucro_g04_cross_wdo.estado_anomalo_cruzado` -- usando todos os
    dias em `dias_historico` (ORDENADOS cronologicamente) como pool de
    historico causal. O chamador decide depois quais dias SUBSET usar para
    executar o backtest (ex.: IS inteiro para a busca; IS+OOS-1 para o
    OOS-1, fatiando so' os dias de OOS-1 para o motor -- o quantil causal
    carrega a historia de verdade, igual um robo ao vivo carregaria)."""
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import estado_anomalo_cruzado

    win = carrega_win()
    wdo = carrega_wdo()
    win_fatia = bars_dos_dias(win, dias_historico)
    wdo_fatia = bars_dos_dias(wdo, dias_historico)
    anomalo, direcao = estado_anomalo_cruzado(
        win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)
    return anomalo, direcao


def roda(dias_operar: list, dias_historico: list | None = None,
         janela_min: int = 15, quantil: float = 0.75,
         capital: float = CAPITAL, **kwargs_estrategia):
    """Devolve `(result, strategy)`. `dias_historico` (default = `dias_operar`)
    e' o pool usado pelo quantil causal do estado anomalo -- passe IS+OOS-1
    para rodar o OOS-1 com a historia real acumulada desde o IS."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import WinBuscaLucroG04CrossWdo

    hist = dias_historico if dias_historico is not None else dias_operar
    anomalo, direcao = computa_estado(hist, janela_min, quantil)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG04CrossWdo(wdo_anomalo=anomalo, wdo_direcao=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_congelado(dias_operar: list, dias_historico: list | None = None,
                    janela_min: int = 15, quantil: float = 0.75,
                    capital: float = CAPITAL, **kwargs_estrategia):
    """Mesma coisa que `roda`, mas importando a classe do arquivo CONGELADO
    (`win_busca_lucro_g04_cross_wdo_congelado_v04.py`) -- so' usar no OOS-1,
    depois que o IS ja' apontou o vencedor."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo_congelado_v04 import (
        WinBuscaLucroG04CrossWdo as WinBuscaLucroG04CrossWdoCongelado,
        estado_anomalo_cruzado as estado_anomalo_cruzado_congelado,
    )

    hist = dias_historico if dias_historico is not None else dias_operar
    win = carrega_win()
    wdo = carrega_wdo()
    win_fatia = bars_dos_dias(win, hist)
    wdo_fatia = bars_dos_dias(wdo, hist)
    anomalo, direcao = estado_anomalo_cruzado_congelado(
        win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG04CrossWdoCongelado(wdo_anomalo=anomalo, wdo_direcao=direcao, **kwargs_estrategia)
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
    stop_dist_pts = [abs(t.entry_price - t.exit_price) for t in stops_trades]
    # concentracao: liquido dos top-3 pregoes / liquido total (item 7 do mandato).
    por_dia_ordenado = sorted(por_dia.values(), key=lambda v: -v)
    top3 = sum(por_dia_ordenado[:3])
    concentracao_top3 = (top3 / liquido) if liquido != 0 else float("nan")
    return dict(
        liquido=liquido, n=n, pregoes=len(dias_da_janela_),
        com_trade=len(com_trade), sem_trade=len(dias_da_janela_) - len(com_trade),
        win=win, be=be, lo=lo, hi=hi, veredito=ver,
        ganho_medio=gm, perda_media=pm, maxdd=maxdd, seq_neg=pior,
        n_stops=len(stops),
        pontos_por_op=(liquido / n / 0.20) if n else float("nan"),
        lucro_dd=(liquido / maxdd) if maxdd > 0 else float("nan"),
        stop_dist_pts=stop_dist_pts,
        concentracao_top3=concentracao_top3,
        serie=serie,
    )
