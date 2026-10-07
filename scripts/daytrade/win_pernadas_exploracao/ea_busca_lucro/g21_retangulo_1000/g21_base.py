# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 21
(`WinBuscaLucroG21Retangulo1000`).

Mesmo molde de `g16_retangulo_250/g16_base.py` -- importa:
  - `g05_base` (br/carrega_win/dias_da_janela/bars_dos_dias/ic95_wilson/
    consistencia/monta_config/CORTE_IS_INICIO/CORTE_IS_FIM/CORTE_OOS1_FIM)
  - `g15_base` (concentracao_topn/maior_sequencia_perdas/ruina_do_resultado/
    constancia_motor/resumo/censurado/imprime_resumo -- generico, usa
    `motor.py` de rodada4/decisao por baixo)
  - `g13_base` (censura_separada -- item 6.51 de LICOES_DE_PRODUCAO.md, e
    CORTE_OOS2_FIM)

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente `WinRetangulo`/G1-G20).

**MUDANCA DE MANDATO, 2026-10-05 (so' para esta busca):** capital de teste
R$1.000,00 (substitui o R$250 das geracoes G1-G20, inclusive a G16 que esta
geracao reabre) e piso de multiplo alvo/stop caindo de 3x para 2x. A barreira
de ruina (margem crua do WIN@) continua R$100 -- nao muda com o capital de
partida, e' o que a corretora cobra por 1 contrato.
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
#: Capital de teste desta geracao -- R$1.000, NAO o CAPITAL (R$250) de g05_base.
CAPITAL = 1000.0
MARGEM_WIN_BRL = g05b.MARGEM_WIN_BRL  # R$100 -- margem crua, nao muda com o capital
CORTE_IS_INICIO = g05b.CORTE_IS_INICIO
CORTE_IS_FIM = g05b.CORTE_IS_FIM
CORTE_OOS1_FIM = g05b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g13b.CORTE_OOS2_FIM

concentracao_topn = g15b.concentracao_topn
maior_sequencia_perdas = g15b.maior_sequencia_perdas
constancia_motor = g15b.constancia_motor
censura_separada = g13b.censura_separada


def monta_config(capital: float = CAPITAL):
    return g05b.monta_config(capital)


def ruina_do_resultado(trades, pregoes_da_janela: int, caixa: float = CAPITAL,
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 44,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
    """Identico a `g15_base.ruina_do_resultado`, so' com os defaults de
    CAIXA/PISO desta geracao (R$1.000 / R$100) em vez dos de g05_base
    (R$250 / R$100)."""
    return g15b.ruina_do_resultado(trades, pregoes_da_janela=pregoes_da_janela,
                                    caixa=caixa, piso=piso,
                                    horizonte_pregoes=horizonte_pregoes,
                                    n_caminhos=n_caminhos, seed=seed)


def roda(dias_operar: list, capital: float = CAPITAL, congelado: bool = False,
         **kwargs_estrategia):
    """Roda `WinBuscaLucroG21Retangulo1000` (ou `_congelado_v21` se
    `congelado=True`) nos `dias_operar`. Sem pool causal externo -- a
    deteccao do retangulo usa so' a propria janela deslizante do WIN@."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    if congelado:
        from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000_congelado_v21 import (
            WinBuscaLucroG21Retangulo1000 as Estrategia,
        )
    else:
        from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
            WinBuscaLucroG21Retangulo1000 as Estrategia,
        )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat
