# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts da Geracao 15 (`WinBuscaLucroG15PortfolioOrcamento`).

Mesmo molde de `g14_portfolio_orb_cross/g14_base.py` (reusa `g05_base` para
`br`/`carrega_win`/`carrega_wdo`/`dias_da_janela`/`bars_dos_dias`/
`ic95_wilson`/`consistencia`, e `motor.py` de `rodada4/decisao` para
`ruina_mc`/`ruina_formula`/`metricas_constancia`) + funcoes proprias desta
geracao: rodar o PORTFOLIO com orcamento (varias politicas), rodar cada
familia SOLO no MESMO periodo (referencia, identico a G14), medir a
concentracao temporal (diagnostico item 1 do mandato) e a correlacao diaria.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente G1-G14).

Capital: R$250,00 (margem crua R$100 x buffer 2,0 x reserva 1,25 -- o piso de
PARTIDA real do WIN@, ver CLAUDE.md "Capital inicial: sempre o minimo real").

Geometrias herdadas (NAO retunadas aqui -- esta geracao testa o MECANISMO de
orcamento/alocacao, nao parametro novo de geometria):
  ORB (G8/G13):  range=5min, stop_min=50, stop_max=140, alvo=3x, buffer=20pts
  Cruzado (G4):  continuacao, janela=20min, quantil=0,75, stop=150pts,
                 alvo=3x, buffer=30pts
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
CORTE_OOS1_INICIO = pd.Timestamp("2026-07-01")
CORTE_OOS1_FIM = pd.Timestamp("2026-09-01")      # exclusivo (jul-ago/2026)
CORTE_OOS2_INICIO = pd.Timestamp("2026-09-01")
CORTE_OOS2_FIM = pd.Timestamp("2026-10-01")      # exclusivo

#: Parametros do sinal B (cruzado) -- vencedor da G4, FIXOS nesta geracao.
JANELA_MIN_CROSS = 20
QUANTIL_CROSS = 0.75

#: Geometrias vencedoras herdadas (G8/G13 e G4) -- ponto de partida unico
#: desta geracao, nao retunadas.
KWARGS_GEOMETRIA = dict(
    orb_range_minutos=5.0, orb_stop_min_pontos=50.0, orb_stop_max_pontos=140.0,
    orb_alvo_multiplo=3.0, orb_buffer_entrada_pontos=20.0,
    cross_direcao_aposta="continuacao", cross_pernada_pontos=750.0,
    cross_stop_pontos=150.0, cross_alvo_multiplo=3.0, cross_buffer_entrada_pontos=30.0,
    ttl_barras_entrada=10,
)
KWARGS_G08_SOLO = dict(
    range_minutos=5.0, stop_min_pontos=50.0, stop_max_pontos=140.0,
    alvo_multiplo=3.0, buffer_entrada_pontos=20.0, ttl_barras_entrada=10,
)
KWARGS_G04_SOLO = dict(
    direcao_aposta="continuacao", pernada_pontos=750.0, stop_pontos=150.0,
    alvo_multiplo=3.0, buffer_entrada_pontos=30.0, ttl_barras_entrada=10,
)


def monta_config(capital: float = CAPITAL):
    return g05b.monta_config(capital)


def concentracao_topn(serie: pd.Series, n: int) -> float:
    liquido = float(serie.sum())
    if liquido == 0:
        return float("nan")
    melhores = sorted(serie.values, reverse=True)[:n]
    return float(sum(melhores) / liquido)


def computa_sinal_cross(dias_historico: list, janela_min: int = JANELA_MIN_CROSS,
                         quantil: float = QUANTIL_CROSS):
    """Pre-computa `(anomalo, direcao)` -- `estado_anomalo_cruzado` da G4,
    IMPORTADA, nao reimplementada -- usando `dias_historico` como pool
    causal."""
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import estado_anomalo_cruzado

    win = carrega_win()
    wdo = carrega_wdo()
    win_fatia = bars_dos_dias(win, dias_historico)
    wdo_fatia = bars_dos_dias(wdo, dias_historico)
    anomalo, direcao = estado_anomalo_cruzado(
        win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)
    return anomalo, direcao


def roda_portfolio(dias_operar: list, dias_historico: list | None = None,
                    capital: float = CAPITAL, congelado: bool = False,
                    **kwargs_estrategia):
    """Roda `WinBuscaLucroG15PortfolioOrcamento` (ou a versao `_congelado_v15`
    se `congelado=True`) nos `dias_operar`. `dias_historico` (default =
    `dias_operar`) e' o pool causal do sinal cruzado -- passe IS+OOS-1 para
    rodar o OOS-1 com a historia real acumulada desde o IS (mesmo precedente
    de G4/G12/G14)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    if congelado:
        from strategy.daytrade.lab.win_busca_lucro_g15_portfolio_orcamento_congelado_v15 import (
            WinBuscaLucroG15PortfolioOrcamento as Estrategia,
        )
    else:
        from strategy.daytrade.lab.win_busca_lucro_g15_portfolio_orcamento import (
            WinBuscaLucroG15PortfolioOrcamento as Estrategia,
        )

    hist = dias_historico if dias_historico is not None else dias_operar
    anomalo, direcao = computa_sinal_cross(hist)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(wdo_anomalo=anomalo, wdo_direcao=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_g08_solo(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Linha SOLO -- ORB puro (G8), import direto (nao reimplementado), para
    a comparacao de p_ruina/liquido ser EXATA (mesma classe, mesmo motor,
    MESMO periodo desta geracao)."""
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


def roda_g04_solo(dias_operar: list, dias_historico: list | None = None,
                   janela_min: int = JANELA_MIN_CROSS, quantil: float = QUANTIL_CROSS,
                   capital: float = CAPITAL, **kwargs_estrategia):
    """Linha SOLO -- confirmacao cruzada (G4), import direto, MESMO periodo
    desta geracao (remede, nao reusa o numero antigo)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import (
        WinBuscaLucroG04CrossWdo, estado_anomalo_cruzado,
    )

    hist = dias_historico if dias_historico is not None else dias_operar
    win = carrega_win()
    wdo = carrega_wdo()
    win_fatia = bars_dos_dias(win, hist)
    wdo_fatia = bars_dos_dias(wdo, hist)
    anomalo, direcao = estado_anomalo_cruzado(
        win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG04CrossWdo(wdo_anomalo=anomalo, wdo_direcao=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def serie_diaria(trades, dias_da_janela_: list) -> pd.Series:
    """P&L diario (zeros incluidos nos dias sem trade) -- base da correlacao
    e da concentracao."""
    por_dia: dict = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    return pd.Series([por_dia.get(d, 0.0) for d in dias_da_janela_],
                      index=pd.to_datetime(dias_da_janela_))


def maior_sequencia_perdas(trades) -> tuple[int, float]:
    """Maior sequencia de perdas CONSECUTIVAS (ordenadas por `exit_ts`,
    origem agnostica -- e' isso que ameaca o caixa, nao importa de qual
    familia veio cada perda). Devolve `(tamanho_da_sequencia, R$_da_sequencia)`."""
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
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 44,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
    """Identico a `g14_base.ruina_do_resultado` -- Monte Carlo
    (`motor.ruina_mc`) reamostrando com reposicao os P&L reais, partindo de
    `caixa`, barreira `piso`."""
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


def resumo(rotulo: str, trades: list, dias: list, capital: float = CAPITAL,
           horizonte_pregoes: int = 44) -> dict:
    c = consistencia(trades, dias)
    top5 = concentracao_topn(c["serie"], 5)
    ruina = ruina_do_resultado(trades, pregoes_da_janela=len(dias), horizonte_pregoes=horizonte_pregoes)
    const = constancia_motor(trades)
    pior_seq_n, pior_seq_brl = maior_sequencia_perdas(trades)
    return dict(rotulo=rotulo, c=c, top5=top5, ruina=ruina, const=const,
                pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, trades=trades)


def censurado(c: dict, equity_min: float) -> bool:
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or equity_min < MARGEM_WIN_BRL


def imprime_resumo(r: dict, equity_min: float) -> None:
    c = r["c"]
    ru = r["ruina"]
    print(f"  {r['rotulo']:<34} liquido={br(c['liquido']):>11}  trades={c['n']:>4}  "
          f"win={br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"p_ruina={br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"top3/liq={br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"pior_seq={r['pior_seq_n']:>2} (R${br(r['pior_seq_brl'])})  "
          f"sem_trade={c['sem_trade']}/{c['pregoes']}  equity_min={br(equity_min)}  "
          f"censurado={censurado(c, equity_min)}", flush=True)
