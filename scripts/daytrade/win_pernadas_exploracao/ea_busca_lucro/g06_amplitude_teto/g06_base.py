# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 6 (`WinBuscaLucroG06AmplitudeTeto`).

Mesmo molde de `g05_regime_vol/g05_base.py` (import direto do `consistencia`
e do `ic95_wilson` de la' -- nao duplica), com um extra: `max_trades_por_
pregao` como parametro da geometria, e `concentracao_topN` (top3 E top5) a
partir da serie diaria ja' calculada por `consistencia`.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
Nunca abre 2025 ou anterior; nunca abre set/2026 em diante nesta geracao.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA nas duas janelas (precedente `WinRetangulo`/G1-G5).

Capital: R$250,00 (margem crua R$100 x buffer 2,0 x reserva 1,25 -- o piso de
PARTIDA real do WIN@, ver CLAUDE.md "Capital inicial: sempre o minimo real").
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

# Reusa br/carrega/janelas/ic95_wilson/consistencia da G5 -- nao duplica.
sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

br = g05b.br
carrega_win = g05b.carrega_win
carrega_wdo = g05b.carrega_wdo
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
    """`serie` e' a serie diaria de P&L (`consistencia(...)["serie"]`,
    indexada por dia da janela, ZEROS incluidos nos dias sem trade). Soma os
    `n` melhores dias e divide pelo liquido total -- `nan` se liquido=0."""
    liquido = float(serie.sum())
    if liquido == 0:
        return float("nan")
    melhores = sorted(serie.values, reverse=True)[:n]
    return float(sum(melhores) / liquido)


def roda(dias_operar: list, dias_historico: list | None, regime_kwargs: dict,
         capital: float = CAPITAL, **kwargs_estrategia):
    """Computa `regime_amplitude_bloco` com `dias_historico` como pool
    causal (default = `dias_operar`), fatia so' os dias de `dias_operar` para
    o motor, e roda o backtest com `WinBuscaLucroG06AmplitudeTeto`. Devolve
    `(result, strategy)`."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g06_amplitude_teto import (
        WinBuscaLucroG06AmplitudeTeto, regime_amplitude_bloco,
    )

    hist = dias_historico if dias_historico is not None else dias_operar
    win = carrega_win()
    win_hist = bars_dos_dias(win, hist)
    regime = regime_amplitude_bloco(win_hist, **regime_kwargs)
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG06AmplitudeTeto(regime_ativo=regime, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat
