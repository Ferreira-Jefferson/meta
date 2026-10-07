# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 18 (`WinBuscaLucroG18OrbCapital1000`).

Mesmo molde de `g08_base.py`/`g13_base.py` (import direto do `br`/
`carrega_win`/`dias_da_janela`/`bars_dos_dias`/`ic95_wilson`/`consistencia`
de `g05_base`, `motor.py` de `rodada4/decisao` para `ruina_mc`/
`ruina_formula`/`p_encolhido`/`tamanho`/`metricas_constancia`), com a MESMA
mudanca de mandato que `g17_base.py` ja aplicou ao sinal cruzado: capital de
TESTE = R$1.000 (nao R$250).

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente G1-G17).

**Item 6.51 aplicado desde o desenho (nao so' no relato):** o criterio de
censura desta geracao SEPARA os dois ramos do OU -- `censura_capital` (equity
cruzou a margem crua OU o motor recusou alguma ordem por capital) e
`seletividade_amostra` (fracao de pregoes sem trade alta, mas SEM que o caixa
tenha encostado na barreira) -- mesma disciplina de `g13_base.censura_separada`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "rodada4" / "decisao"))
import motor  # noqa: E402

br = g05b.br
carrega_win = g05b.carrega_win
dias_da_janela = g05b.dias_da_janela
bars_dos_dias = g05b.bars_dos_dias
ic95_wilson = g05b.ic95_wilson
consistencia = g05b.consistencia

CSV_WIN = g05b.CSV_WIN
SYMBOL = g05b.SYMBOL
MARGEM_WIN_BRL = g05b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g05b.CORTE_IS_INICIO
CORTE_IS_FIM = g05b.CORTE_IS_FIM
CORTE_OOS1_FIM = g05b.CORTE_OOS1_FIM
#: OOS-2 (set/2026) -- SO' aberto se o candidato passar o OOS-1 "com folga".
CORTE_OOS2_FIM = pd.Timestamp("2026-10-01")

#: ==== UNICA mudanca desta geracao (mandato do dono, 2026-10-05): capital
#: de TESTE, nao a margem crua. Mesmo valor/racional de `g17_base.CAPITAL`.
CAPITAL = 1000.0
#: Capital ORIGINAL de G1-G16 (R$250) -- so' para a comparacao explicita
#: "mesma geometria vencedora G8/G13, capital diferente" (item 2 do mandato).
CAPITAL_ORIGINAL = 250.0


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


def roda(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Roda `WinBuscaLucroG18OrbCapital1000` nos `dias_operar`. Sem pool
    causal externo -- o ORB nao depende de historico de dias ANTERIORES (a
    faixa de abertura e' calculada dentro do proprio pregao)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g18_orb_capital1000 import (
        WinBuscaLucroG18OrbCapital1000,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG18OrbCapital1000(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_congelado(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Mesmo papel de `g08_oos1.roda_congelado` -- importa a classe do
    modulo CONGELADO (`..._congelado_v18`), nunca do modulo vivo, para o
    OOS-1/OOS-2 nao poderem ser afetados por uma edicao posterior de
    `win_busca_lucro_g18_orb_capital1000.py`."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g18_orb_capital1000_congelado_v18 import (
        WinBuscaLucroG18OrbCapital1000 as WinBuscaLucroG18OrbCapital1000Congelado,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG18OrbCapital1000Congelado(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_g08_original(dias_operar: list, capital: float = CAPITAL_ORIGINAL, **kwargs_estrategia):
    """Roda a classe ORIGINAL da G8 (`WinBuscaLucroG08OrbSobrevivencia`,
    import direto, SEM alteracao) -- usada so' para a comparacao explicita
    "mesma geometria vencedora G8/G13 (stop_max=140/alvo=3x), capital R$250
    vs R$1.000" (item 2 do mandato da G18, mesma logica de
    `g17_base.roda_g04_original`). Nao aceita `alvo_multiplo<3,0` (contrato
    antigo da G8, intacto)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g08_orb_sobrevivencia import (
        WinBuscaLucroG08OrbSobrevivencia,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG08OrbSobrevivencia(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def ruina_do_resultado(trades, pregoes_da_janela: int, caixa: float = CAPITAL,
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 44,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
    """Probabilidade de ruina via Monte Carlo (`motor.ruina_mc`), reamostrando
    com reposicao os resultados REAIS (R$) das operacoes fechadas de
    `trades`, partindo de `caixa` (R$1.000, capital de TESTE desta geracao),
    barreira `piso` (margem crua R$100). Mesma ferramenta/convencao de
    G8/G13/G17. `horizonte_pregoes` default=44 (tamanho do OOS-1)."""
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


def constancia_motor(trades, caixa0: float = CAPITAL) -> dict:
    """`motor.metricas_constancia` sobre os trades fechados -- pior sequencia
    de perdas, pior mes, ulcer, lucro/DD (versao do motor.py, nao a do
    `report.py`)."""
    if not trades:
        return dict(liquido=0.0, pior_seq_ops=0, pior_seq_brl=0.0, maxdd_brl=0.0)
    pnl = np.asarray([t.pnl_brl for t in trades], dtype=float)
    mes = np.asarray([t.exit_ts.year * 100 + t.exit_ts.month for t in trades])
    return motor.metricas_constancia(pnl, mes, caixa0)


def sizing_motor(trades, caixa: float = CAPITAL) -> dict:
    """`motor.tamanho`/`motor.p_encolhido` sobre o payoff medio REALIZADO
    (ganho/perda medios em PONTOS) desta celula, para checar se o Kelly
    fracionario a` R$1.000 algum dia pediria mais de 1 contrato (1 contrato
    fixo e' a politica DECLARADA desta geracao -- escalar fica para a G19)."""
    if not trades:
        return dict(p_encolhido=float("nan"), contratos_kelly=0)
    ganhos_pts = [abs(t.exit_price - t.entry_price) for t in trades if t.pnl_brl > 0]
    perdas_pts = [abs(t.exit_price - t.entry_price) for t in trades if t.pnl_brl <= 0]
    k = sum(1 for t in trades if t.pnl_brl > 0)
    n = len(trades)
    p0 = k / n
    pe = motor.p_encolhido(k, n, p0)
    gm = float(np.mean(ganhos_pts)) if ganhos_pts else 0.0
    lm = float(np.mean(perdas_pts)) if perdas_pts else 0.0
    nc = motor.tamanho(pe, gm, lm, caixa) if gm and lm else 0
    return dict(p_encolhido=pe, ganho_pts_medio=gm, perda_pts_medio=lm, contratos_kelly=nc)


def censura_separada(res, c: dict, piso: float = MARGEM_WIN_BRL) -> dict:
    """Item 6.51 -- separa os DOIS ramos do criterio de censura herdado
    (mesma logica de `g13_base.censura_separada`): `censura_capital` (o
    caixa de fato cruzou a margem crua OU o motor recusou alguma ordem por
    falta de capital) e' o modo de falha REAL que matou G7/G8 no OOS-1 a
    R$250; `seletividade_amostra` (fracao de pregoes sem trade >= 50% SEM
    que o ramo de capital tenha disparado) e' so' baixa frequencia por
    desenho, nao morte por caixa."""
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    recusadas = int(getattr(res, "ordens_recusadas_por_capital", 0) or 0)
    censura_capital = (equity_min == equity_min and equity_min < piso) or recusadas > 0
    seletividade = c["n"] == 0 or (c["sem_trade"] >= 0.5 * c["pregoes"] and not censura_capital)
    return dict(
        equity_min=equity_min, ordens_recusadas_por_capital=recusadas,
        censura_capital=censura_capital, seletividade_amostra=seletividade,
        censurado=censura_capital or (c["sem_trade"] >= 0.5 * c["pregoes"]),
    )
