# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts da Geracao 19, Parte 1
(`WinBuscaLucroG19OrbSizingGraduado`).

Nao reimplementa nada generico -- importa de `g18_base.py` (que por sua vez
ja importa de `g05_base.py` + `motor.py`). A UNICA coisa nova aqui e'
`roda`, apontando para a classe nova (sizing graduado por balde de forca),
e os helpers de analise pos-hoc (tercis sobre os trades REAIS, nunca
simulacao exclusiva -- item 6.50).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g18_orb_capital1000"))
import g18_base as g18b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "rodada4" / "decisao"))
import motor  # noqa: E402

br = g18b.br
carrega_win = g18b.carrega_win
dias_da_janela = g18b.dias_da_janela
bars_dos_dias = g18b.bars_dos_dias
ic95_wilson = g18b.ic95_wilson
consistencia = g18b.consistencia
monta_config = g18b.monta_config
concentracao_topn = g18b.concentracao_topn
ruina_do_resultado = g18b.ruina_do_resultado
constancia_motor = g18b.constancia_motor
censura_separada = g18b.censura_separada

CORTE_IS_INICIO = g18b.CORTE_IS_INICIO
CORTE_IS_FIM = g18b.CORTE_IS_FIM
CORTE_OOS1_FIM = g18b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g18b.CORTE_OOS2_FIM
MARGEM_WIN_BRL = g18b.MARGEM_WIN_BRL
CAPITAL = g18b.CAPITAL  # R$1.000 -- mandato 2026-10-05

#: Geometria vencedora da G18 (stop_max=140/alvo=3x) -- esta geracao NAO
#: revisita geometria, so' o sizing.
GEOMETRIA_G18 = dict(stop_max_pontos=140.0, alvo_multiplo=3.0)


def roda(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Roda `WinBuscaLucroG19OrbSizingGraduado` nos `dias_operar`."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g19_orb_sizing_graduado import (
        WinBuscaLucroG19OrbSizingGraduado,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG19OrbSizingGraduado(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_congelado(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g19_orb_sizing_graduado_congelado_v19 import (
        WinBuscaLucroG19OrbSizingGraduado as Congelado,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Congelado(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def quantis_forca(forcas: list[float]) -> tuple[float, float]:
    arr = np.asarray(forcas, dtype=float)
    return tuple(np.quantile(arr, (1 / 3, 2 / 3)))


def correlacoes_pos_hoc(trades, forcas_entrada: list[float]) -> dict:
    """Correlacao ponto-bisserial aproximada (pearson) entre a forca DA
    ORDEM QUE VIROU TRADE e o resultado -- mesma analise de
    `g11_is_posthoc.py`, reaproveitada aqui para a geometria/capital desta
    geracao."""
    if len(trades) != len(forcas_entrada) or not trades:
        return dict(corr_forca_ganho=float("nan"), corr_forca_pnl=float("nan"))
    arr = np.asarray(forcas_entrada, dtype=float)
    pnl = np.asarray([t.pnl_brl for t in trades], dtype=float)
    ganhou = (pnl > 0).astype(float)
    corr_fg = float(np.corrcoef(arr, ganhou)[0, 1]) if np.std(arr) > 0 and np.std(ganhou) > 0 else float("nan")
    corr_fp = float(np.corrcoef(arr, pnl)[0, 1]) if np.std(arr) > 0 and np.std(pnl) > 0 else float("nan")
    return dict(corr_forca_ganho=corr_fg, corr_forca_pnl=corr_fp)


def baldes_pos_hoc(trades, forcas_entrada: list[float], q_baixo: float, q_alto: float) -> dict:
    """Estratifica os trades REAIS (ja ordenados por `entry_ts`) em 3
    baldes pelos cortes dados -- NUNCA roda simulacao exclusiva (item 6.50)."""
    ordem = sorted(range(len(trades)), key=lambda i: trades[i].entry_ts)
    trades_ord = [trades[i] for i in ordem]
    forcas_ord = [forcas_entrada[i] for i in ordem]
    baldes: dict[str, list] = {"fraco": [], "medio": [], "forte": []}
    for t, f in zip(trades_ord, forcas_ord):
        if f < q_baixo:
            baldes["fraco"].append((t, f))
        elif f < q_alto:
            baldes["medio"].append((t, f))
        else:
            baldes["forte"].append((t, f))
    resumo = {}
    for nome, pares in baldes.items():
        n = len(pares)
        k = sum(1 for t, _ in pares if t.pnl_brl > 0)
        win = (k / n) if n else float("nan")
        liquido = sum(t.pnl_brl for t, _ in pares)
        ganhos = [t.pnl_brl for t, _ in pares if t.pnl_brl > 0]
        perdas = [t.pnl_brl for t, _ in pares if t.pnl_brl <= 0]
        gm = (sum(ganhos) / len(ganhos)) if ganhos else 0.0
        pm = (abs(sum(perdas)) / len(perdas)) if perdas else 0.0
        be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
        lo, hi = ic95_wilson(k, n) if n else (float("nan"), float("nan"))
        resumo[nome] = dict(n=n, k=k, win=win, liquido=liquido, be=be, lo=lo, hi=hi)
    return resumo
