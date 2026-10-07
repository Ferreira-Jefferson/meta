# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 12 (`WinBuscaLucroG12AndOrbCross`).

Mesmo molde de `g08_orb_sobrevivencia/g08_base.py` (reusa `g05_base` para
`br`/`carrega_win`/`dias_da_janela`/`bars_dos_dias`/`ic95_wilson`/
`consistencia`, e `motor.py` de `rodada4/decisao` para `ruina_mc`/
`ruina_formula`/`tamanho`/`p_encolhido`/`metricas_constancia`) + o SINAL B
(estado anomalo WIN x WDO) importado direto de `win_busca_lucro_g04_cross_wdo`
(`estado_anomalo_cruzado`) -- a mesma funcao pura que a G4 usa, parametros
FIXOS pelo mandato desta geracao (`janela_min=20, quantil=0.75,
direcao_aposta="continuacao"`), nao re-tunados aqui.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente G1-G11).

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
carrega_wdo = g05b.carrega_wdo
dias_da_janela = g05b.dias_da_janela
bars_dos_dias = g05b.bars_dos_dias
ic95_wilson = g05b.ic95_wilson
consistencia = g05b.consistencia

CSV_WIN = g05b.CSV_WIN
CSV_WDO = g05b.CSV_WDO
SYMBOL = g05b.SYMBOL
CAPITAL = g05b.CAPITAL
MARGEM_WIN_BRL = g05b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g05b.CORTE_IS_INICIO
CORTE_IS_FIM = g05b.CORTE_IS_FIM
CORTE_OOS1_FIM = g05b.CORTE_OOS1_FIM
#: OOS-2 (set/2026) -- SO' aberto se o candidato passar o OOS-1 "com folga".
CORTE_OOS2_FIM = pd.Timestamp("2026-10-01")

#: Parametros do SINAL B -- FIXOS pelo mandato desta geracao (nao re-tunados
#: aqui; sao os parametros que a G4 ja tinha identificado como o unico
#: candidato com liquido positivo no IS e OOS-1 antes de reprovar por
#: concentracao/IC).
JANELA_MIN_SINAL_B = 20
QUANTIL_SINAL_B = 0.75


def monta_config(capital: float = CAPITAL):
    return g05b.monta_config(capital)


def concentracao_topn(serie: pd.Series, n: int) -> float:
    liquido = float(serie.sum())
    if liquido == 0:
        return float("nan")
    melhores = sorted(serie.values, reverse=True)[:n]
    return float(sum(melhores) / liquido)


def computa_sinal_b(dias_historico: list, janela_min: int = JANELA_MIN_SINAL_B,
                     quantil: float = QUANTIL_SINAL_B):
    """Pre-computa `(anomalo, direcao)` -- a funcao PURA
    `estado_anomalo_cruzado` da G4, IMPORTADA, nao reimplementada -- usando
    `dias_historico` (ordenados) como pool causal. Devolve as duas series
    indexadas por timestamp M1."""
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import estado_anomalo_cruzado

    win = carrega_win()
    wdo = carrega_wdo()
    win_fatia = bars_dos_dias(win, dias_historico)
    wdo_fatia = bars_dos_dias(wdo, dias_historico)
    anomalo, direcao = estado_anomalo_cruzado(
        win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)
    return anomalo, direcao


def roda_orb_puro(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Linha de REFERENCIA -- ORB puro (G8), sinal A isolado, sem filtro B.
    Importa `WinBuscaLucroG08OrbSobrevivencia` direto (nao reimplementado)
    para a comparacao lado a lado ser EXATA (mesma classe, mesmo motor)."""
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


def roda(dias_operar: list, dias_historico: list | None = None,
         janela_min: int = JANELA_MIN_SINAL_B, quantil: float = QUANTIL_SINAL_B,
         capital: float = CAPITAL, **kwargs_estrategia):
    """Roda `WinBuscaLucroG12AndOrbCross`. `dias_historico` (default =
    `dias_operar`) e' o pool causal do sinal B -- passe IS+OOS-1 para rodar
    o OOS-1 com a historia real acumulada desde o IS (mesmo precedente da
    G4)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g12_and_orb_cross import (
        WinBuscaLucroG12AndOrbCross,
    )

    hist = dias_historico if dias_historico is not None else dias_operar
    anomalo, direcao = computa_sinal_b(hist, janela_min, quantil)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG12AndOrbCross(wdo_anomalo=anomalo, wdo_direcao=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_congelado(dias_operar: list, dias_historico: list | None = None,
                    janela_min: int = JANELA_MIN_SINAL_B, quantil: float = QUANTIL_SINAL_B,
                    capital: float = CAPITAL, **kwargs_estrategia):
    """Mesma coisa que `roda`, mas importando a classe do arquivo CONGELADO
    (`..._congelado_v12.py`) -- so' usar no OOS-1/OOS-2, depois que o IS ja'
    apontou o vencedor."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g12_and_orb_cross_congelado_v12 import (
        WinBuscaLucroG12AndOrbCross as WinBuscaLucroG12AndOrbCrossCongelado,
    )
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import estado_anomalo_cruzado

    hist = dias_historico if dias_historico is not None else dias_operar
    win = carrega_win()
    wdo = carrega_wdo()
    win_fatia = bars_dos_dias(win, hist)
    wdo_fatia = bars_dos_dias(wdo, hist)
    anomalo, direcao = estado_anomalo_cruzado(
        win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG12AndOrbCrossCongelado(wdo_anomalo=anomalo, wdo_direcao=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def ruina_do_resultado(trades, pregoes_da_janela: int, caixa: float = CAPITAL,
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 44,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
    """Identico a` `g08_base.ruina_do_resultado` -- Monte Carlo (`motor.ruina_mc`)
    reamostrando com reposicao os P&L reais, partindo de `caixa`, barreira
    `piso`. `n_ops` projeta a taxa de disparo observada sobre `horizonte_pregoes`."""
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
    if not trades:
        return dict(liquido=0.0, pior_seq_ops=0, pior_seq_brl=0.0, maxdd_brl=0.0)
    pnl = np.asarray([t.pnl_brl for t in trades], dtype=float)
    mes = np.asarray([t.exit_ts.year * 100 + t.exit_ts.month for t in trades])
    return motor.metricas_constancia(pnl, mes, caixa0)


def sizing_motor(trades, caixa: float = CAPITAL) -> dict:
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
