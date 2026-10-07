# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 26
(`WinBuscaLucroG26RetanguloTendencia`) -- filtro de tendencia sobre a
geometria vencedora do IS da G21 (stop=0,45x largura, alvo=0,90x = 2,0x o
stop), pedido do dono depois de olhar o replay visual
(`.claude/artifacts/g21_retangulo/index.html`).

Mesmo molde de `g21_retangulo_1000/g21_base.py` -- reaproveita g05_base (br/
carrega_win/dias_da_janela/bars_dos_dias/ic95_wilson/consistencia/
monta_config/CORTE_*), g15_base (concentracao/ruina/sequencia) e g13_base
(censura_separada/CORTE_OOS2_FIM). Capital R$1.000 e piso de multiplo 2,0x,
mesmo mandato 2026-10-05 da G21-G25.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g15_portfolio_orcamento"))
import g15_base as g15b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g13_orb_grade_fina"))
import g13_base as g13b  # noqa: E402

br = g05b.br
carrega_win = g05b.carrega_win
dias_da_janela = g05b.dias_da_janela
bars_dos_dias = g05b.bars_dos_dias
ic95_wilson = g05b.ic95_wilson
consistencia = g05b.consistencia

CSV_WIN = g05b.CSV_WIN
SYMBOL = g05b.SYMBOL
CAPITAL = 1000.0
MARGEM_WIN_BRL = g05b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g05b.CORTE_IS_INICIO
CORTE_IS_FIM = g05b.CORTE_IS_FIM
CORTE_OOS1_FIM = g05b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g13b.CORTE_OOS2_FIM

concentracao_topn = g15b.concentracao_topn
maior_sequencia_perdas = g15b.maior_sequencia_perdas
constancia_motor = g15b.constancia_motor
censura_separada = g13b.censura_separada

# Geometria vencedora do IS da G21 -- herdada, NAO retunada aqui. Esta
# geracao testa SO' o filtro de tendencia por cima dela.
STOP_FRACAO = 0.45
ALVO_MULTIPLO = 2.0
ALVO_FRACAO = STOP_FRACAO * ALVO_MULTIPLO


def monta_config(capital: float = CAPITAL):
    return g05b.monta_config(capital)


def ruina_do_resultado(trades, pregoes_da_janela: int, caixa: float = CAPITAL,
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 44,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
    return g15b.ruina_do_resultado(trades, pregoes_da_janela=pregoes_da_janela,
                                    caixa=caixa, piso=piso,
                                    horizonte_pregoes=horizonte_pregoes,
                                    n_caminhos=n_caminhos, seed=seed)


def roda(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Roda `WinBuscaLucroG26RetanguloTendencia` nos `dias_operar`, com a
    geometria vencedora da G21 fixa e os parametros do filtro de tendencia
    em `kwargs_estrategia` (medida/janela_tendencia/estrito)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g26_retangulo_tendencia import (
        WinBuscaLucroG26RetanguloTendencia as Estrategia,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(stop_fracao_largura=STOP_FRACAO, alvo_fracao_largura=ALVO_FRACAO,
                        **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat
