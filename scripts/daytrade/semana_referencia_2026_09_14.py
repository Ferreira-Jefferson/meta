# -*- coding: utf-8 -*-
"""Script reutilizavel da rodada "semana de referencia 2026-09-14..18" --
ANTES (baseline de producao) e DEPOIS (ajustes aceitos) dos 6 robos de day
trade, pela MESMA tabela padrao (`backtest/intraday/report.py`).

Nao digita `queue_ahead_qty`/`exit_queue_ahead_qty` na mao -- vem de
`config_for(...)`, que le' `backtest.intraday.fidelidade` sozinho. Capital e'
sempre o minimo REAL de cada robo (nunca redondo): R$375 WDO@ (wdo_orb,
wdo_grid_reload_maker, wdo_grid_fade_off_t3), R$3.000 copa_win, R$1.100
win_retangulo, dinamico (preco de hoje) gremah.

Uso:
    python scripts/daytrade/semana_referencia_2026_09_14.py baseline
    python scripts/daytrade/semana_referencia_2026_09_14.py depois
    python scripts/daytrade/semana_referencia_2026_09_14.py sweep-freio
    python scripts/daytrade/semana_referencia_2026_09_14.py is-oos-freio --segundos 10 30
    python scripts/daytrade/semana_referencia_2026_09_14.py copa-defesa
    python scripts/daytrade/semana_referencia_2026_09_14.py copa-defesa-is-oos
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backtest import metrics as bt_metrics  # noqa: E402
from backtest.intraday.engine import (  # noqa: E402
    IntradayBacktestResult, bar_from_row, run_intraday_backtest,
)
from backtest.intraday.machine import (  # noqa: E402
    IntradaySessionMachine, LimitPlaced, PositionClosed,
)
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from core.instruments import economics_for  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.copa_win import CopaWin  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402
from strategy.daytrade.lab.wdo_grid_fade_off_t3 import WdoGridFadeOffT3  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker  # noqa: E402
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

# ---------------------------------------------------------------- capital --
CAPITAL_WDO = 375.0
CAPITAL_COPA_WIN = 3_000.0
CAPITAL_WIN_RETANGULO = 1_100.0

SEMANA_DIAS = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
OOS_CUTOFF_WIN = "2026-06-13"

# ------------------------------------------------------------------ paths --
TICK_WDO_SEMANA = RAIZ / "data" / "raw_ticks" / "WDO_A_semana_2026_09_14.parquet"
WDO_F1 = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"
M1_WIN_CANON = RAIZ / "data" / "raw_intraday" / "WIN_A_.parquet"
M1_WIN_SEMANA = RAIZ / "data" / "raw_intraday" / "WIN_A_semana_2026_09_14_M1.parquet"
M1_PMAM3_SEMANA = RAIZ / "data" / "raw_intraday" / "PMAM3_semana_2026_09_14_M1.parquet"

_ECON_CACHE: dict[str, tuple[float, float]] = {}


def _econ(real_symbol: str) -> tuple[float, float]:
    """(trade_tick_value, trade_tick_size) lido do TERMINAL MT5 -- nunca
    digitado a mao (mesmo caminho de `scripts/run_live.py::build_intraday`).
    `config_for` reescala pela grade do perfil; so' a RAZAO (valor do ponto)
    importa."""
    if real_symbol not in _ECON_CACHE:
        econ = symbol_economics(real_symbol)
        if econ is None:
            raise RuntimeError(f"terminal MT5 nao respondeu symbol_info({real_symbol!r})")
        _ECON_CACHE[real_symbol] = (econ.trade_tick_value, econ.trade_tick_size)
    return _ECON_CACHE[real_symbol]


# -------------------------------------------------------------- carregar --
def carregar_tick_wdo_semana() -> pd.DataFrame:
    df = pd.read_parquet(TICK_WDO_SEMANA, columns=["last", "volume", "volume_real"])
    return ticks_to_degenerate_bars(df)


def carregar_wdo_f1(janela: str) -> pd.DataFrame:
    """Bars degeneradas de tick, ja rotuladas IS/OOS -- ver
    `WDO_A_f1.parquet` (2026-02-27..2026-08-25, 72 IS + 51 OOS pregoes)."""
    df = pd.read_parquet(WDO_F1, columns=["open", "high", "low", "close", "volume", "janela"])
    df = df[df["janela"] == janela]
    return df[["open", "high", "low", "close", "volume"]]


def carregar_m1_win_semana() -> pd.DataFrame:
    a = pd.read_parquet(M1_WIN_CANON)
    b = pd.read_parquet(M1_WIN_SEMANA)
    df = pd.concat([a, b]).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    ini = pd.Timestamp(SEMANA_DIAS[0], tz="UTC")
    fim = pd.Timestamp(SEMANA_DIAS[-1], tz="UTC") + pd.Timedelta(days=1)
    return df.loc[(df.index >= ini) & (df.index < fim)]


def carregar_m1_win_is_oos() -> tuple[pd.DataFrame, pd.DataFrame]:
    a = pd.read_parquet(M1_WIN_CANON)
    b = pd.read_parquet(M1_WIN_SEMANA)
    df = pd.concat([a, b]).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    corte = pd.Timestamp(OOS_CUTOFF_WIN, tz="UTC")
    return df.loc[df.index < corte], df.loc[df.index >= corte]


def carregar_m1_pmam3_semana() -> pd.DataFrame:
    return pd.read_parquet(M1_PMAM3_SEMANA).sort_index()


# --------------------------------------------------------------- rodagem --
def _pregoes_sem_trade(bars: pd.DataFrame, result: IntradayBacktestResult) -> int:
    dias_totais = set(pd.DatetimeIndex(bars.index).date)
    dias_com_trade = {t.entry_ts.date() for t in result.trades}
    return len(dias_totais - dias_com_trade)


def rodar(
    bars: pd.DataFrame, strategy, symbol_perfil: str, real_symbol: str, capital: float,
    variante: str, extras: dict | None = None, capital_nocional: bool = False,
    anchor_exits_at_fill: bool = True,
):
    profile = profile_for(symbol_perfil)
    tick_value, tick_size = _econ(real_symbol)
    cfg = config_for(
        profile, trade_tick_value=tick_value, trade_tick_size=tick_size,
        initial_capital=capital, target_fills_as_maker=strategy.target_fills_as_maker,
        anchor_exits_at_fill=anchor_exits_at_fill,
    )
    result = run_intraday_backtest(bars, strategy, cfg)
    extras = dict(extras or {})
    extras.setdefault("preg.s/trade", str(_pregoes_sem_trade(bars, result)))
    return linha_de_resultado(variante, result, capital, capital_nocional=capital_nocional, extras=extras)


def rodar_com_contagem(bars: pd.DataFrame, strategy, symbol_perfil: str, real_symbol: str,
                        capital: float):
    """Mesmo caminho de `rodar`, mas tambem CONTA niveis armados (`LimitPlaced`)
    -- diagnostico da familia maker (achado B, CLAUDE.md/tarefa). So' vale
    para futuro sem gate de capital minimo por sessao (WDO@: `enforce_
    capital_minimo` sai False do perfil, entao nao ha sessao pulada a
    replicar aqui)."""
    profile = profile_for(symbol_perfil)
    tick_value, tick_size = _econ(real_symbol)
    cfg = config_for(
        profile, trade_tick_value=tick_value, trade_tick_size=tick_size,
        initial_capital=capital, target_fills_as_maker=strategy.target_fills_as_maker,
        anchor_exits_at_fill=True,
    )
    assert not cfg.enforce_capital_minimo, "gate de capital minimo por sessao nao replicado aqui"
    strategy.initialize(bars)
    machine = IntradaySessionMachine(strategy, cfg)
    trades = []
    equity_index, equity_values = [], []
    armados = 0
    wiped = None
    for session_date, session_df in bars.groupby(bars.index.date):
        machine.begin_session(session_date)
        last_ts = session_df.index[-1]
        for ts, row in session_df.iterrows():
            bar = bar_from_row(ts, row)
            for event in machine.on_closed_bar(bar, is_last_bar=(ts == last_ts)):
                if isinstance(event, PositionClosed):
                    trades.append(event.trade)
                elif isinstance(event, LimitPlaced):
                    armados += 1
            equity_index.append(ts)
            equity_atual = capital + machine.realized_pnl + machine.unrealized_brl(bar.close)
            equity_values.append(equity_atual)
            if equity_atual <= 0:
                wiped = ts
                break
        if wiped is not None:
            break
    equity_curve = pd.Series(equity_values, index=pd.DatetimeIndex(equity_index), name="equity")
    result = IntradayBacktestResult(
        trades=trades, equity_curve=equity_curve,
        metrics={"max_drawdown": bt_metrics.max_drawdown(equity_curve)} if not equity_curve.empty else {},
        wiped_out_at=wiped,
        deslize_alvo_ticks=(cfg.costs.target_slippage_ticks if cfg.target_fills_as_maker else 0.0),
        fila_entrada_qty=float(cfg.queue_ahead_qty or 0.0),
        fila_saida_qty=float(cfg.exit_queue_ahead_qty or 0.0),
        fila_calibrada=cfg.costs.fidelidade_calibrada,
    )
    return result, armados, len(trades)


def agregar_por_pregao(resultados: list[IntradayBacktestResult], capital: float) -> IntradayBacktestResult:
    """Combina N resultados de UM PREGAO cada (capital REPOSTO -- mesmo
    desenho de `wdo_orb_geometria_is_oos_2026_09_14.py`) numa unica linha.

    A curva de patrimonio devolvida e' a caminhada do P&L REALIZADO
    (capital + soma cumulativa dos trades, por ordem de saida) -- mede o
    formato da SEQUENCIA de trades (MaxDD da geometria), NAO sobrevivencia de
    caixa (essa e' medida a parte, na semana de referencia, com caminhada
    continua de verdade). Use sempre com `capital_nocional=True` na tabela."""
    trades = [t for r in resultados for t in r.trades]
    trades.sort(key=lambda t: t.exit_ts)
    idx, vals = [], []
    acumulado = capital
    for t in trades:
        acumulado += t.pnl_brl
        idx.append(t.exit_ts)
        vals.append(acumulado)
    equity = pd.Series(vals, index=pd.DatetimeIndex(idx), name="equity") if idx else pd.Series(dtype=float)
    dias_zerados = sum(1 for r in resultados if r.wiped_out_at is not None)
    base = resultados[0] if resultados else None
    return IntradayBacktestResult(
        trades=trades, equity_curve=equity, metrics={}, wiped_out_at=None,
        sessoes_puladas_por_capital=[r for res in resultados for r in res.sessoes_puladas_por_capital],
        deslize_alvo_ticks=(base.deslize_alvo_ticks if base else 0.0),
        fila_entrada_qty=(base.fila_entrada_qty if base else 0.0),
        fila_saida_qty=(base.fila_saida_qty if base else 0.0),
        fila_calibrada=(base.fila_calibrada if base else None),
    ), dias_zerados


# ------------------------------------------------------- robo: wdo_orb --
def robo_wdo_orb_semana(variante: str = "wdo_orb (producao)"):
    bars = carregar_tick_wdo_semana()
    strat = get_daytrade_robot("wdo_orb")
    return rodar(bars, strat, "WDO@", "WDOV26", CAPITAL_WDO, variante)


# ---------------------------------------------- robo: wdo_grid_reload_maker --
def _reload_maker(reancora_min_segundos: float = 10.0, reancora_min_ticks: int = 2) -> WdoGridReloadMaker:
    return WdoGridReloadMaker(
        margin_per_contract_brl=economics_for("WDO@").margin_per_contract_brl,
        hard_cap_contratos=5,
        risco_pct_por_trade=0.01,
        point_value_brl=economics_for("WDO@").point_value_brl,
        fatiar_saida_alvo=True,
        reancora_min_segundos=reancora_min_segundos,
        reancora_min_ticks=reancora_min_ticks,
    )


def _fade_off_t3(reancora_min_segundos: float = 10.0, reancora_min_ticks: int = 2) -> WdoGridFadeOffT3:
    return WdoGridFadeOffT3(reancora_min_segundos=reancora_min_segundos,
                             reancora_min_ticks=reancora_min_ticks)


def robo_reload_maker_semana(reancora_min_segundos: float = 10.0, variante: str | None = None):
    bars = carregar_tick_wdo_semana()
    strat = _reload_maker(reancora_min_segundos)
    result, armados, preenchidos = rodar_com_contagem(bars, strat, "WDO@", "WDOV26", CAPITAL_WDO)
    extras = {
        "preg.s/trade": str(_pregoes_sem_trade(bars, result)),
        "niveis armados": str(armados),
        "preenchidos": str(preenchidos),
        "freio(s)": f"{reancora_min_segundos:g}",
    }
    label = variante or f"reload_maker freio={reancora_min_segundos:g}s"
    return linha_de_resultado(label, result, CAPITAL_WDO, extras=extras)


def robo_fade_off_t3_semana(reancora_min_segundos: float = 10.0, variante: str | None = None):
    bars = carregar_tick_wdo_semana()
    strat = _fade_off_t3(reancora_min_segundos)
    result, armados, preenchidos = rodar_com_contagem(bars, strat, "WDO@", "WDOV26", CAPITAL_WDO)
    extras = {
        "preg.s/trade": str(_pregoes_sem_trade(bars, result)),
        "niveis armados": str(armados),
        "preenchidos": str(preenchidos),
        "freio(s)": f"{reancora_min_segundos:g}",
    }
    label = variante or f"fade_off_t3 freio={reancora_min_segundos:g}s"
    return linha_de_resultado(label, result, CAPITAL_WDO, extras=extras)


def _rodar_um_dia_grid(args) -> IntradayBacktestResult:
    """Worker de `ProcessPoolExecutor` -- roda UM pregao (capital reposto)
    de `wdo_grid_reload_maker`/`wdo_grid_fade_off_t3`. `args` e' uma tupla
    picklavel (sem instancia de estrategia -- reconstruida aqui dentro).

    `tick_value`/`tick_size` chegam JA' LIDOS do terminal (uma unica vez, no
    processo PAI) -- ler de novo aqui dentro chamaria `symbol_economics` (IPC
    com o terminal MT5) uma vez por PREGAO por WORKER, e com 8 workers x 123
    pregoes isso serializa/trava a conexao unica do terminal em vez de
    paralelizar o backtest."""
    cls_nome, dia, day_bars, reancora_min_segundos, tick_value, tick_size = args
    strat = _reload_maker(reancora_min_segundos) if cls_nome == "reload_maker" \
        else _fade_off_t3(reancora_min_segundos)
    profile = profile_for("WDO@")
    cfg = config_for(profile, trade_tick_value=tick_value, trade_tick_size=tick_size,
                      initial_capital=CAPITAL_WDO, target_fills_as_maker=True,
                      anchor_exits_at_fill=True)
    return run_intraday_backtest(day_bars, strat, cfg)


def rodar_is_oos_grid(cls_nome: str, janela: str, reancora_min_segundos: float,
                       max_workers: int = 8) -> tuple[IntradayBacktestResult, int]:
    bars = carregar_wdo_f1(janela)
    dias = sorted(set(pd.DatetimeIndex(bars.index).date))
    tick_value, tick_size = _econ("WDOV26")
    trabalhos = [(cls_nome, str(d), bars.loc[str(d)], reancora_min_segundos, tick_value, tick_size)
                 for d in dias]
    resultados = []
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futuros = {pool.submit(_rodar_um_dia_grid, t): t[1] for t in trabalhos}
        for fut in as_completed(futuros):
            dia = futuros[fut]
            r = fut.result()
            print(f"    [{cls_nome} {janela} freio={reancora_min_segundos:g}s] {dia}: "
                  f"{len(r.trades)} trades, liquido {sum(t.pnl_brl for t in r.trades):+.2f}", flush=True)
            resultados.append(r)
    return agregar_por_pregao(resultados, CAPITAL_WDO)


# --------------------------------------------------------------- copa_win --
def _copa_win(defesa_ativa: bool = True) -> CopaWin:
    return CopaWin(
        teto_contratos=15,
        janela_rompimento=10, alvo_vol=7.6, stop_vol=12.0, trail_vol=None,
        fatiar_saida_alvo=True,
        vol_min_ticks=8.0, fracao_entrada=1.0, aquecimento_barras=45,
        max_entradas_dia=10, entrada_maker=True, entrada_ttl_barras=5,
        margin_per_contract_brl=economics_for("WIN@").margin_per_contract_brl,
        risco_pct_por_trade=0.05,
        corte_persistencia_ativo=True, corte_persistencia_min_barras=10,
        corte_persistencia_frac_adverso=1.0,
        defesa_ativa=defesa_ativa, defesa_gatilho_stop_pct=0.20,
        defesa_alvo_proximidade_pct=0.10,
    )


def robo_copa_win_semana(defesa_ativa: bool = True, variante: str | None = None):
    bars = carregar_m1_win_semana()
    strat = _copa_win(defesa_ativa)
    label = variante or f"copa_win defesa={defesa_ativa}"
    return rodar(bars, strat, "WIN@", "WINV26", CAPITAL_COPA_WIN, label)


def robo_copa_win_janela(janela_df: pd.DataFrame, defesa_ativa: bool, variante: str):
    strat = _copa_win(defesa_ativa)
    return rodar(janela_df, strat, "WIN@", "WINV26", CAPITAL_COPA_WIN, variante, capital_nocional=False)


# ---------------------------------------------------------- win_retangulo --
def robo_win_retangulo_semana(variante: str = "win_retangulo (producao)"):
    bars = carregar_m1_win_semana()
    strat = get_daytrade_robot("win_retangulo")
    return rodar(bars, strat, "WIN@", "WINV26", CAPITAL_WIN_RETANGULO, variante)


# ---------------------------------------------------------------- gremah --
def robo_gremah_semana(variante: str = "gremah/PMAM3 (producao)"):
    bars = carregar_m1_pmam3_semana()
    if bars.empty:
        return None
    # Preco de ABERTURA do 1o pregao da semana -- o capital e' decisao de
    # PARTIDA (CLAUDE.md, "o piso de capital e' indicacao de PARTIDA, nunca
    # condicao de continuidade"), checada 1x, no preco de quando o dono
    # comecaria a operar a semana -- nao no fechamento do ultimo pregao.
    preco_ref = float(bars["open"].iloc[0])
    capital = capital_minimo_brl(preco_ref)
    strat = get_daytrade_robot("gremah", symbol="PMAM3")
    return rodar(bars, strat, "PMAM3", "PMAM3", capital, variante,
                 extras={"preco ref.": f"{preco_ref:.4f}", "capital": f"{capital:.2f}"})


# --------------------------------------------------------------------- CLI --
def cmd_baseline(args) -> None:
    linhas = []
    print("[wdo_orb] rodando semana de referencia...", flush=True)
    linhas.append(robo_wdo_orb_semana())
    print("[wdo_grid_reload_maker] rodando semana de referencia...", flush=True)
    linhas.append(robo_reload_maker_semana(10.0, "wdo_grid_reload_maker (producao, freio 10s)"))
    print("[wdo_grid_fade_off_t3] rodando semana de referencia...", flush=True)
    linhas.append(robo_fade_off_t3_semana(10.0, "wdo_grid_fade_off_t3 (producao, freio 10s)"))
    print("[copa_win] rodando semana de referencia...", flush=True)
    linhas.append(robo_copa_win_semana(True, "copa_win (producao, defesa ON)"))
    print("[win_retangulo] rodando semana de referencia...", flush=True)
    linhas.append(robo_win_retangulo_semana())
    print("[gremah] rodando semana de referencia...", flush=True)
    g = robo_gremah_semana()
    if g is not None:
        linhas.append(g)
    else:
        print("[gremah] SEM DADO M1 PMAM3 na semana de referencia -- nao medivel.")
    extras = ("preg.s/trade", "niveis armados", "preenchidos", "freio(s)", "preco ref.", "capital")
    print()
    print(tabela(linhas, extras))


def cmd_sweep_freio(args) -> None:
    valores = args.segundos or [0.0, 5.0, 10.0, 20.0, 30.0, 60.0]
    for cls_nome, fn in (("reload_maker", robo_reload_maker_semana), ("fade_off_t3", robo_fade_off_t3_semana)):
        print(f"\n=== {cls_nome}: varredura de freio na semana de referencia ===", flush=True)
        linhas = []
        with ProcessPoolExecutor(max_workers=min(6, len(valores))) as pool:
            futuros = {pool.submit(fn, v): v for v in valores}
            for fut in as_completed(futuros):
                v = futuros[fut]
                item = fut.result()
                print(f"  [{cls_nome} freio={v:g}s] liquido={item.liquido_brl:+.2f} "
                      f"trades={item.trades} win%={item.win_rate_pct:.1f}", flush=True)
                linhas.append((v, item))
        linhas.sort(key=lambda x: x[0])
        extras = ("preg.s/trade", "niveis armados", "preenchidos", "freio(s)")
        print(tabela([item for _, item in linhas], extras))


def cmd_is_oos_freio(args) -> None:
    valores = args.segundos or [10.0]
    for cls_nome in ("reload_maker", "fade_off_t3"):
        for v in valores:
            for janela in ("IS", "OOS"):
                print(f"\n=== {cls_nome} freio={v:g}s {janela} ===", flush=True)
                agregado, dias_zerados = rodar_is_oos_grid(cls_nome, janela, v)
                extras = {"dias c/zeragem": str(dias_zerados)}
                item = linha_de_resultado(f"{cls_nome} freio={v:g}s {janela}", agregado,
                                          CAPITAL_WDO, capital_nocional=True, extras=extras)
                print(tabela([item], ("dias c/zeragem",)))


def cmd_depois(args) -> None:
    """Roda as variantes ACEITAS lado a lado com a producao -- preencher
    depois de decidir quais sobrevivem ao Fase 3."""
    linhas = []
    linhas.append(robo_wdo_orb_semana("wdo_orb (depois -- so' fix de live/, sem mudanca de estrategia)"))
    linhas.append(robo_reload_maker_semana(10.0, "wdo_grid_reload_maker (depois)"))
    linhas.append(robo_fade_off_t3_semana(10.0, "wdo_grid_fade_off_t3 (depois)"))
    linhas.append(robo_copa_win_semana(True, "copa_win (depois)"))
    linhas.append(robo_win_retangulo_semana("win_retangulo (depois -- NADA mudou)"))
    g = robo_gremah_semana("gremah/PMAM3 (depois)")
    if g is not None:
        linhas.append(g)
    extras = ("preg.s/trade", "niveis armados", "preenchidos", "freio(s)", "preco ref.", "capital")
    print(tabela(linhas, extras))


def cmd_copa_defesa(args) -> None:
    print("=== copa_win: defesa de recuo ON (producao) x OFF, semana de referencia ===", flush=True)
    a = robo_copa_win_semana(True, "copa_win defesa=ON (producao)")
    b = robo_copa_win_semana(False, "copa_win defesa=OFF")
    print(tabela([a, b], ("preg.s/trade",)))


def cmd_copa_defesa_is_oos(args) -> None:
    print("=== copa_win: defesa ON x OFF, IS/OOS congelado (corte 2026-06-13) ===", flush=True)
    is_df, oos_df = carregar_m1_win_is_oos()
    linhas = []
    for nome, df in (("IS", is_df), ("OOS", oos_df)):
        for defesa in (True, False):
            print(f"  rodando {nome} defesa={defesa}...", flush=True)
            item = robo_copa_win_janela(df, defesa, f"copa_win defesa={defesa} {nome}")
            linhas.append(item)
    print(tabela(linhas, ("preg.s/trade",)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baseline")
    sub.add_parser("depois")
    sp = sub.add_parser("sweep-freio")
    sp.add_argument("--segundos", type=float, nargs="+")
    sp2 = sub.add_parser("is-oos-freio")
    sp2.add_argument("--segundos", type=float, nargs="+")
    sub.add_parser("copa-defesa")
    sub.add_parser("copa-defesa-is-oos")
    args = parser.parse_args()
    {
        "baseline": cmd_baseline,
        "depois": cmd_depois,
        "sweep-freio": cmd_sweep_freio,
        "is-oos-freio": cmd_is_oos_freio,
        "copa-defesa": cmd_copa_defesa,
        "copa-defesa-is-oos": cmd_copa_defesa_is_oos,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
