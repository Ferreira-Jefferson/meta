# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 17
(`WinBuscaLucroG17CrossWdoCapital1000`).

Nao reimplementa utilitarios ja genericos desta linha de pesquisa -- importa:
  - `g04_base` (br/carrega_win/carrega_wdo/dias_da_janela/bars_dos_dias/
    correlacao_incrementos_minuto/ic95_wilson/consistencia/cortes IS-OOS1,
    identico ao usado por toda a linha desde a G4)
  - `motor` (`rodada4/decisao/motor.py` -- `ruina_mc`/`ruina_formula`/
    `metricas_constancia`, mesmo usado por G8/G13/G14/G15/G16)

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

## MUDANCA DE MANDATO (dono, 2026-10-05), so' nesta geracao

Capital de teste = **R$1.000** (nao R$250 -- `CAPITAL` deste modulo). A
margem CRUA do WIN@ nao muda (`MARGEM_WIN_BRL=100`, sempre -- e' o que a
corretora cobra por 1 contrato, nao um parametro de teste). O piso de
RUINA do Monte Carlo usa a margem crua, nao o capital de partida (mesmo
precedente de G8/G13/G15/G16 -- "ruina = nao sustenta nem 1 contrato").

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente G1-G16).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g04_cross_wdo"))
import g04_base as g04b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "rodada4" / "decisao"))
import motor  # noqa: E402

br = g04b.br
carrega_win = g04b.carrega_win
carrega_wdo = g04b.carrega_wdo
dias_da_janela = g04b.dias_da_janela
bars_dos_dias = g04b.bars_dos_dias
correlacao_incrementos_minuto = g04b.correlacao_incrementos_minuto
ic95_wilson = g04b.ic95_wilson
consistencia = g04b.consistencia
computa_estado = g04b.computa_estado

SYMBOL = g04b.SYMBOL
CORTE_IS_INICIO = g04b.CORTE_IS_INICIO
CORTE_IS_FIM = g04b.CORTE_IS_FIM
CORTE_OOS1_FIM = g04b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = pd.Timestamp("2026-10-01")      # exclusivo (set/2026)

#: ==== UNICA mudanca desta geracao: capital de TESTE, nao a margem crua ====
CAPITAL = 1000.0
#: Capital da G4 original (R$250) -- so' para a comparacao explicita
#: "mesma geometria, capital diferente" (item 2 do mandato da G17).
CAPITAL_G4_ORIGINAL = 250.0
MARGEM_WIN_BRL = g04b.MARGEM_WIN_BRL  # R$100 -- nao muda com o capital de teste


def monta_config(capital: float = CAPITAL):
    return g04b.monta_config(capital)


def roda(dias_operar: list, dias_historico: list | None = None,
         janela_min: int = 20, quantil: float = 0.75,
         capital: float = CAPITAL, congelado: bool = False,
         **kwargs_estrategia):
    """Roda `WinBuscaLucroG17CrossWdoCapital1000` (ou `_congelado_v17` se
    `congelado=True`). `dias_historico` (default=`dias_operar`) e' o pool
    causal do estado anomalo -- passe IS+OOS-1/IS+OOS-1+OOS-2 para rodar o
    OOS com a historia acumulada desde o IS (mesmo precedente G4/G12/G14/G15)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    if congelado:
        from strategy.daytrade.lab.win_busca_lucro_g17_cross_wdo_capital1000_congelado_v17 import (
            WinBuscaLucroG17CrossWdoCapital1000 as Estrategia,
        )
    else:
        from strategy.daytrade.lab.win_busca_lucro_g17_cross_wdo_capital1000 import (
            WinBuscaLucroG17CrossWdoCapital1000 as Estrategia,
        )

    hist = dias_historico if dias_historico is not None else dias_operar
    anomalo, direcao = computa_estado(hist, janela_min, quantil)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(wdo_anomalo=anomalo, wdo_direcao=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_g04_original(dias_operar: list, dias_historico: list | None = None,
                       janela_min: int = 20, quantil: float = 0.75,
                       capital: float = CAPITAL_G4_ORIGINAL, **kwargs_estrategia):
    """Roda a classe ORIGINAL da G4 (`WinBuscaLucroG04CrossWdo`, import
    direto, SEM alteracao) -- usada so' para a comparacao "mesma geometria
    vencedora, capital R$250 vs R$1.000" (item 2 do mandato da G17). Nao
    aceita `alvo_multiplo<3,0` (contrato antigo da G4, intacto)."""
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


# ----------------------------------------------------------------- ruina/concentracao/constancia
def concentracao_topn(serie: pd.Series, n: int) -> float:
    liquido = float(serie.sum())
    if liquido == 0:
        return float("nan")
    melhores = sorted(serie.values, reverse=True)[:n]
    return float(sum(melhores) / liquido)


def maior_sequencia_perdas(trades) -> tuple[int, float]:
    ordenados = sorted(trades, key=lambda t: t.exit_ts)
    pior_n, pior_brl = 0, 0.0
    atual_n, atual_brl = 0, 0.0
    for t in ordenados:
        if t.pnl_brl <= 0:
            atual_n += 1
            atual_brl += t.pnl_brl
        else:
            atual_n, atual_brl = 0, 0.0
        if atual_n > pior_n:
            pior_n, pior_brl = atual_n, atual_brl
    return pior_n, pior_brl


def ruina_do_resultado(trades, pregoes_da_janela: int, caixa: float = CAPITAL,
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 122,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
    """Monte Carlo (`motor.ruina_mc`) reamostrando com reposicao os P&L REAIS
    observados, partindo de `caixa` (R$1.000, o capital de TESTE desta
    geracao), barreira `piso` (margem crua R$100 -- nao sustenta nem 1
    contrato). `horizonte_pregoes` default=122 (tamanho do proprio IS) para
    a leitura "ruina dentro do horizonte de desenvolvimento" ficar direta."""
    pnl = np.asarray([t.pnl_brl for t in trades], dtype=float)
    if len(pnl) == 0:
        return dict(p_ruina=float("nan"), t_mediano=float("nan"),
                     caixa_final_mediana=caixa, n_ops=0, ruina_formula=float("nan"))
    taxa_por_pregao = len(pnl) / max(1, pregoes_da_janela)
    n_ops = max(1, int(round(taxa_por_pregao * horizonte_pregoes)))
    mc = motor.ruina_mc(pnl, None, caixa, n_ops, n_caminhos=n_caminhos, piso=piso, seed=seed)
    mc["n_ops"] = n_ops
    mc["ruina_formula"] = motor.ruina_formula(pnl, None, caixa, piso=piso)
    return mc


def resumo(rotulo: str, trades: list, dias: list, capital: float = CAPITAL,
           horizonte_pregoes: int = 122) -> dict:
    c = consistencia(trades, dias)
    top5 = concentracao_topn(c["serie"], 5)
    ruina = ruina_do_resultado(trades, pregoes_da_janela=len(dias), caixa=capital,
                                horizonte_pregoes=horizonte_pregoes)
    pior_seq_n, pior_seq_brl = maior_sequencia_perdas(trades)
    return dict(rotulo=rotulo, c=c, top5=top5, ruina=ruina,
                pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, trades=trades)


def censurado(c: dict, equity_min: float, piso: float = MARGEM_WIN_BRL) -> bool:
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or equity_min < piso
