# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 7 (`WinBuscaLucroG07Orb`).

Mesmo molde de `g05_regime_vol/g05_base.py` (import direto do `br`/`carrega_
win`/`dias_da_janela`/`bars_dos_dias`/`ic95_wilson`/`consistencia` de la' --
nao duplica) + `concentracao_topn` de `g06_amplitude_teto/g06_base.py`.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
Nunca abre 2025 ou anterior; nunca abre set/2026 em diante nesta geracao.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA nas duas janelas (precedente `WinRetangulo`/G1-G6).

Capital: R$250,00 (margem crua R$100 x buffer 2,0 x reserva 1,25 -- o piso de
PARTIDA real do WIN@, ver CLAUDE.md "Capital inicial: sempre o minimo real").
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

br = g05b.br
carrega_win = g05b.carrega_win
dias_da_janela = g05b.dias_da_janela
bars_dos_dias = g05b.bars_dos_dias
ic95_wilson = g05b.ic95_wilson
consistencia = g05b.consistencia

CSV_WIN = g05b.CSV_WIN
SYMBOL = g05b.SYMBOL
CAPITAL = g05b.CAPITAL
MARGEM_WIN_BRL = g05b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g05b.CORTE_IS_INICIO
CORTE_IS_FIM = g05b.CORTE_IS_FIM
CORTE_OOS1_FIM = g05b.CORTE_OOS1_FIM


def monta_config(capital: float = CAPITAL):
    return g05b.monta_config(capital)


def concentracao_topn(serie: pd.Series, n: int) -> float:
    """`serie` e' a serie diaria de P&L (`consistencia(...)["serie"]`, zeros
    incluidos nos dias sem trade). Soma os `n` melhores dias / liquido total
    -- `nan` se liquido=0."""
    liquido = float(serie.sum())
    if liquido == 0:
        return float("nan")
    melhores = sorted(serie.values, reverse=True)[:n]
    return float(sum(melhores) / liquido)


def roda(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Roda `WinBuscaLucroG07Orb` nos `dias_operar`. Sem pool causal externo
    -- ao contrario de G4/G5/G6, o ORB nao depende de historico de dias
    ANTERIORES (a faixa de abertura e' calculada dentro do proprio pregao),
    entao nao ha' burn-in nem `dias_historico` separado."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g07_orb import WinBuscaLucroG07Orb

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG07Orb(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat
