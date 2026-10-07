# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 8 (`WinBuscaLucroG08OrbSobrevivencia`).

Mesmo molde de `g07_orb/g07_base.py` (import direto do `br`/`carrega_win`/
`dias_da_janela`/`bars_dos_dias`/`ic95_wilson`/`consistencia` de `g05_base`,
e `concentracao_topn` reusado de `g07_base`) + a FERRAMENTA CENTRAL desta
geracao: `motor.py` (`scripts/daytrade/win_pernadas_exploracao/rodada4/
decisao/motor.py`), importado direto (nao duplicado) -- `ruina_mc`,
`ruina_formula`, `p_encolhido`, `tamanho`, `metricas_constancia`.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente `WinRetangulo`/G1-G7).

Capital: R$250,00 (margem crua R$100 x buffer 2,0 x reserva 1,25 -- o piso de
PARTIDA real do WIN@, ver CLAUDE.md "Capital inicial: sempre o minimo real").
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
CAPITAL = g05b.CAPITAL
MARGEM_WIN_BRL = g05b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g05b.CORTE_IS_INICIO
CORTE_IS_FIM = g05b.CORTE_IS_FIM
CORTE_OOS1_FIM = g05b.CORTE_OOS1_FIM
#: OOS-2 (set/2026) -- SO' aberto se o candidato passar o OOS-1 "com folga"
#: (protocolo do mandato desta geracao). Exclusivo, mesma convencao dos cortes
#: acima.
CORTE_OOS2_FIM = pd.Timestamp("2026-10-01")


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
    """Roda `WinBuscaLucroG08OrbSobrevivencia` nos `dias_operar`. Sem pool
    causal externo -- o ORB nao depende de historico de dias ANTERIORES (a
    faixa de abertura e' calculada dentro do proprio pregao)."""
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


def roda_congelado(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Mesmo papel de `g07_oos1.roda_congelado` -- importa a classe do
    modulo CONGELADO (`..._congelado_v08`), nunca do modulo vivo, para o
    OOS-1/OOS-2 nao poderem ser afetados por uma edicao posterior de
    `win_busca_lucro_g08_orb_sobrevivencia.py`."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g08_orb_sobrevivencia_congelado_v08 import (
        WinBuscaLucroG08OrbSobrevivencia as WinBuscaLucroG08OrbSobrevivenciaCongelado,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG08OrbSobrevivenciaCongelado(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def ruina_do_resultado(trades, pregoes_da_janela: int, caixa: float = CAPITAL,
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 44,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
    """Probabilidade de ruina via Monte Carlo (`motor.ruina_mc`), reamostrando
    com reposicao os resultados REAIS (R$) das operacoes fechadas de
    `trades`, partindo de `caixa` (R$250 real), barreira `piso` (margem crua
    R$100).

    `n_ops` (quantas operacoes simular por caminho) e' a TAXA de disparo
    observada nesta amostra (`len(trades)/pregoes_da_janela`) projetada sobre
    `horizonte_pregoes` (default 44 = tamanho do OOS-1) -- nao um numero fixo
    arbitrario, para a pergunta ser sempre "se esta cadencia continuar por
    mais ~2 meses (ou o horizonte pedido), qual a chance de cruzar a margem?"
    tanto para uma variante que opera quase todo dia quanto para uma mais
    rara. Tambem devolve a aproximacao de Lundberg (`motor.ruina_formula`,
    horizonte infinito, tamanho fixo) para referencia -- `motor.py` recomenda
    o MC quando a perda e' grande frente a` barreira, que e' exatamente o
    caso aqui (perda de 1 stop pode valer 20-50% do caixa de R$250)."""
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
    `report.py` -- aqui serve para comparar entre CELULAS da busca, nao para
    a tabela padrao)."""
    if not trades:
        return dict(liquido=0.0, pior_seq_ops=0, pior_seq_brl=0.0, maxdd_brl=0.0)
    pnl = np.asarray([t.pnl_brl for t in trades], dtype=float)
    mes = np.asarray([t.exit_ts.year * 100 + t.exit_ts.month for t in trades])
    return motor.metricas_constancia(pnl, mes, caixa0)


def sizing_motor(trades, caixa: float = CAPITAL) -> dict:
    """`motor.tamanho`/`motor.p_encolhido` sobre o payoff medio REALIZADO
    (ganho/perda medios em PONTOS, nao R$ -- `motor.tamanho` espera pontos e
    converte com `VALOR_PONTO` internamente) desta celula, para checar se o
    Kelly fracionario a` R$250 algum dia pediria mais de 1 contrato -- se
    nunca pedir, a politica de 1 contrato fixo desta geracao nao esta' sendo
    conservadora demais."""
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
