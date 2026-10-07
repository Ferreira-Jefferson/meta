# -*- coding: utf-8 -*-
"""Patch em tempo de execucao (sem tocar em nenhum arquivo antigo) para refazer as
geracoes ORB do `ea_busca_lucro` sem os leiloes (auditoria 2026-10-06, linha A4).

MODO (env ORB_MODO):
  antes  -> NAO muda base nem config; so' liga o log de saidas (reproduz o antigo).
  depois -> `g05_base.carrega_win()` passa a devolver as barras de
            `carrega_win_m1_sem_leiloes` (1a barra: open = 1o negocio continuo; ultima
            barra = ultima continua, sem o call) e `monta_config` recebe
            `session_end_time=18:20` (BRT, passado AQUI, motor intocado).

LOG (env ORB_LOG): cada `run_intraday_backtest` anexa uma linha JSON com n de trades,
saidas forcadas e quantas cairam na ULTIMA barra do dia (no 'antes' = call).
`aplica()` precisa rodar em TODO processo (o runner chama no topo, e o spawn o reexecuta).
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))
G05 = ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao" / "ea_busca_lucro" / "g05_regime_vol"
sys.path.insert(0, str(G05))

_FEITO = False
_COLS = ["open", "high", "low", "close", "tick_volume", "real_volume"]


def modo() -> str:
    return os.environ.get("ORB_MODO", "depois")


def _carrega_sem_leilao(g05b):
    from market_data_intraday.win_sem_leiloes import carrega_win_m1_sem_leiloes
    r = carrega_win_m1_sem_leiloes(g05b.CSV_WIN)
    g05b._CACHE["win_sl"] = r
    return r.barras[_COLS].copy()


def aplica() -> None:
    global _FEITO
    if _FEITO:
        return
    _FEITO = True
    import g05_base as g05b
    from backtest.intraday import engine

    if modo() == "depois":
        def carrega_win():
            if "win_novo" not in g05b._CACHE:
                g05b._CACHE["win_novo"] = _carrega_sem_leilao(g05b)
            return g05b._CACHE["win_novo"]

        orig_cfg = g05b.monta_config

        def monta_config(capital=g05b.CAPITAL):
            cfg = orig_cfg(capital)
            return dataclasses.replace(cfg, session_end_time=time(18, 20))

        g05b.carrega_win = carrega_win
        g05b.monta_config = monta_config

    orig = engine.run_intraday_backtest

    def run(bars, strat, cfg, *a, **k):
        res = orig(bars, strat, cfg, *a, **k)
        log = os.environ.get("ORB_LOG")
        if log:
            try:
                ult = bars.groupby(bars.index.normalize()).apply(lambda d: d.index[-1])
                ultset = set(ult.values)
                tr = list(res.trades)
                ff = [t for t in tr if str(getattr(t.exit_reason, "value", t.exit_reason)) == "forced_flatten"]
                nult = sum(1 for t in ff if t.exit_ts.to_datetime64() in ultset)
                with open(log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(dict(modo=modo(), n=len(tr), ff=len(ff), ultima=nult,
                                            pid=os.getpid())) + "\n")
            except Exception as e:  # nunca derruba a medicao por causa do log
                with open(log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(dict(erro=repr(e))) + "\n")
        return res

    engine.run_intraday_backtest = run
