# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts da Geracao 19, Parte 2
(`WinBuscaLucroG19CrossWdoSizingGraduado`).

Importa de `g17_base.py` (que por sua vez importa `g04_base.py` + `motor.py`).
Acrescenta `computa_estado_com_magnitude` (chama a funcao NOVA
`magnitude_anomalo_cruzado`, verificando PARIDADE byte a byte contra a
`estado_anomalo_cruzado` original da G4 antes de qualquer backtest -- se a
paridade falhar, a funcao nova tem um bug e o script para, em vez de gerar
numero errado silenciosamente).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g17_capital1000"))
import g17_base as g17b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "rodada4" / "decisao"))
import motor  # noqa: E402

br = g17b.br
carrega_win = g17b.carrega_win
carrega_wdo = g17b.carrega_wdo
dias_da_janela = g17b.dias_da_janela
bars_dos_dias = g17b.bars_dos_dias
ic95_wilson = g17b.ic95_wilson
consistencia = g17b.consistencia
monta_config = g17b.monta_config

CORTE_IS_INICIO = g17b.CORTE_IS_INICIO
CORTE_IS_FIM = g17b.CORTE_IS_FIM
CORTE_OOS1_FIM = g17b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g17b.CORTE_OOS2_FIM
MARGEM_WIN_BRL = g17b.MARGEM_WIN_BRL
CAPITAL = g17b.CAPITAL  # R$1.000 -- mandato 2026-10-05

#: Geometria vencedora da G17 (alvo=4x/stop=150/buffer=30) -- esta geracao
#: NAO revisita geometria, so' o sizing.
GEOMETRIA_G17 = dict(stop_pontos=150.0, alvo_multiplo=4.0, buffer_entrada_pontos=30.0)
#: janela/quantil ja identificados como o melhor ponto no IS original (G4/G17).
JANELA_MIN = 20
QUANTIL = 0.75


def computa_estado_com_magnitude(dias_historico: list, janela_min: int = JANELA_MIN,
                                  quantil: float = QUANTIL, verifica_paridade: bool = True):
    """Computa `(anomalo, direcao, magnitude)` com
    `magnitude_anomalo_cruzado` (Parte 2, nova) e, se `verifica_paridade`,
    confere que `(anomalo, direcao)` batem byte a byte com a funcao
    ORIGINAL da G4 (`estado_anomalo_cruzado`, reimportada so' para este
    teste) -- nunca reaproveita o resultado da G4 no backtest, so' para
    confirmar que a duplicacao de matematica desta geracao esta correta."""
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.lab.win_busca_lucro_g19_cross_wdo_sizing_graduado import (
        magnitude_anomalo_cruzado,
    )

    win = carrega_win()
    wdo = carrega_wdo()
    win_fatia = bars_dos_dias(win, dias_historico)
    wdo_fatia = bars_dos_dias(wdo, dias_historico)
    anomalo, direcao, magnitude = magnitude_anomalo_cruzado(
        win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)

    if verifica_paridade:
        from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import estado_anomalo_cruzado
        anomalo_g4, direcao_g4 = estado_anomalo_cruzado(
            win_fatia["close"], wdo_fatia["close"], janela_min=janela_min, quantil=quantil)
        bate_anomalo = bool((anomalo == anomalo_g4).all())
        bate_direcao = bool((direcao == direcao_g4).all())
        if not (bate_anomalo and bate_direcao):
            raise AssertionError(
                f"PARIDADE FALHOU contra win_busca_lucro_g04_cross_wdo.estado_anomalo_cruzado: "
                f"anomalo_bate={bate_anomalo} direcao_bate={bate_direcao} -- "
                f"magnitude_anomalo_cruzado tem bug, NAO prosseguir com o backtest.")
    return anomalo, direcao, magnitude


def roda(dias_operar: list, dias_historico: list | None = None,
         janela_min: int = JANELA_MIN, quantil: float = QUANTIL,
         capital: float = CAPITAL, congelado: bool = False,
         **kwargs_estrategia):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    if congelado:
        from strategy.daytrade.lab.win_busca_lucro_g19_cross_wdo_sizing_graduado_congelado_v19 import (
            WinBuscaLucroG19CrossWdoSizingGraduado as Estrategia,
        )
    else:
        from strategy.daytrade.lab.win_busca_lucro_g19_cross_wdo_sizing_graduado import (
            WinBuscaLucroG19CrossWdoSizingGraduado as Estrategia,
        )

    hist = dias_historico if dias_historico is not None else dias_operar
    anomalo, direcao, magnitude = computa_estado_com_magnitude(hist, janela_min, quantil)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(wdo_anomalo=anomalo, wdo_direcao=direcao, wdo_magnitude=magnitude,
                        **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def concentracao_topn(serie, n: int) -> float:
    liquido = float(serie.sum())
    if liquido == 0:
        return float("nan")
    melhores = sorted(serie.values, reverse=True)[:n]
    return float(sum(melhores) / liquido)


def ruina_do_resultado(trades, pregoes_da_janela: int, caixa: float = CAPITAL,
                        piso: float = MARGEM_WIN_BRL, horizonte_pregoes: int = 44,
                        n_caminhos: int = 10_000, seed: int = 0) -> dict:
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


def censura_separada(res, c: dict, piso: float = MARGEM_WIN_BRL) -> dict:
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    recusadas = int(getattr(res, "ordens_recusadas_por_capital", 0) or 0)
    censura_capital = (equity_min == equity_min and equity_min < piso) or recusadas > 0
    seletividade = c["n"] == 0 or (c["sem_trade"] >= 0.5 * c["pregoes"] and not censura_capital)
    return dict(
        equity_min=equity_min, ordens_recusadas_por_capital=recusadas,
        censura_capital=censura_capital, seletividade_amostra=seletividade,
        censurado=censura_capital or (c["sem_trade"] >= 0.5 * c["pregoes"]),
    )


def quantis_magnitude(magnitudes: list[float]) -> tuple[float, float]:
    arr = np.asarray(magnitudes, dtype=float)
    return tuple(np.quantile(arr, (1 / 3, 2 / 3)))


def correlacoes_pos_hoc(trades, magnitudes_entrada: list[float]) -> dict:
    if len(trades) != len(magnitudes_entrada) or not trades:
        return dict(corr_mag_ganho=float("nan"), corr_mag_pnl=float("nan"))
    arr = np.asarray(magnitudes_entrada, dtype=float)
    pnl = np.asarray([t.pnl_brl for t in trades], dtype=float)
    ganhou = (pnl > 0).astype(float)
    corr_fg = float(np.corrcoef(arr, ganhou)[0, 1]) if np.std(arr) > 0 and np.std(ganhou) > 0 else float("nan")
    corr_fp = float(np.corrcoef(arr, pnl)[0, 1]) if np.std(arr) > 0 and np.std(pnl) > 0 else float("nan")
    return dict(corr_mag_ganho=corr_fg, corr_mag_pnl=corr_fp)


def baldes_pos_hoc(trades, magnitudes_entrada: list[float], m_baixo: float, m_alto: float) -> dict:
    ordem = sorted(range(len(trades)), key=lambda i: trades[i].entry_ts)
    trades_ord = [trades[i] for i in ordem]
    mags_ord = [magnitudes_entrada[i] for i in ordem]
    baldes: dict[str, list] = {"no_quantil": [], "moderado": [], "muito_acima": []}
    for t, m in zip(trades_ord, mags_ord):
        if m < m_baixo:
            baldes["no_quantil"].append((t, m))
        elif m < m_alto:
            baldes["moderado"].append((t, m))
        else:
            baldes["muito_acima"].append((t, m))
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
        dias_distintos = len({t.entry_ts.date() for t, _ in pares})
        resumo[nome] = dict(n=n, k=k, win=win, liquido=liquido, be=be, lo=lo, hi=hi,
                             dias_distintos=dias_distintos)
    return resumo
