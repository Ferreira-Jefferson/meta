# -*- coding: utf-8 -*-
"""PLACEBO critico (nao faz parte da busca oficial): o vencedor do IS
(continuacao, j20/q75, stop150/alvo3x/buffer30) dispara quase sempre a FAVOR
da tendencia maior (so' 47 de 214 brutos foram contra-tendencia) -- ou seja,
o gatilho de "WIN e WDO andam juntos" pode nao estar adicionando informacao
nenhuma alem do que o proprio IMPULSO do WIN (sem olhar WDO) ja' diria. Este
script roda a MESMA geometria com um gatilho que usa SO' o delta do WIN
(ignora WDO inteiramente -- qualquer impulso de 20min do WIN acima do
quantil causal dispara, sem checar o instrumento irmao) para servir de
contrafactual. Se o placebo bater perto do vencedor oficial, a hipotese
cruzada nao esta comprovada -- e' so' um filtro de impulso do proprio WIN
disfarcado de confirmacao cruzada.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import numpy as np
import pandas as pd

import g04_base as b  # noqa: E402

JANELA_MIN = 20
QUANTIL = 0.75
MIN_DIAS_BURN_IN = 20
KW_GEOMETRIA = dict(direcao_aposta="continuacao", stop_pontos=150.0,
                     alvo_multiplo=3.0, buffer_entrada_pontos=30.0)


def estado_so_win(close_win: pd.Series, janela_min: int, quantil: float,
                   min_dias_burn_in: int = MIN_DIAS_BURN_IN):
    """Mesma mecanica causal de `estado_anomalo_cruzado`, mas SO' com o WIN:
    'anomalo' = impulso de `janela_min` minutos acima do quantil causal do
    PROPRIO WIN -- sem checar o WDO de jeito nenhum."""
    idx = close_win.index
    dia = pd.Series(idx.date, index=idx)
    delta = close_win.groupby(dia).diff(janela_min)
    absd = delta.abs()
    dias_ordenados = sorted(dia.unique())
    thr_por_dia = {}
    acumulado = []
    for i, d in enumerate(dias_ordenados):
        if i >= min_dias_burn_in:
            thr_por_dia[d] = float(np.quantile(np.concatenate(acumulado), quantil))
        else:
            thr_por_dia[d] = None
        mask = (dia == d).values
        acumulado.append(absd.values[mask][~np.isnan(absd.values[mask])])
    thr = dia.map(thr_por_dia)
    tem_historico = thr.notna()
    sinal = np.sign(delta)
    acima = absd >= thr.astype(float)
    anomalo = (tem_historico & acima & (sinal != 0)).fillna(False)
    direcao = pd.Series(np.where(anomalo, sinal, 0), index=idx).astype(int)
    return anomalo, direcao


def main() -> None:
    sys.path.insert(0, str(b.ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.report import linha_de_resultado, tabela
    from strategy.daytrade.lab.win_busca_lucro_g04_cross_wdo import WinBuscaLucroG04CrossWdo

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    win_fatia = b.bars_dos_dias(win, dias)

    anomalo, direcao = estado_so_win(win_fatia["close"], JANELA_MIN, QUANTIL)
    strat = WinBuscaLucroG04CrossWdo(wdo_anomalo=anomalo, wdo_direcao=direcao, **KW_GEOMETRIA)
    cfg = b.monta_config(b.CAPITAL)
    res = run_intraday_backtest(win_fatia, strat, cfg)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    be_nom = 1.0 / (1.0 + KW_GEOMETRIA["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "bruto": str(strat.stats_bruto),
        "contra_tend": str(strat.stats_contra_tendencia),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha = linha_de_resultado("PLACEBO so'-WIN (ignora WDO)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=10))
    print(f"\nliquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"equity_min={b.br(equity_min)}  bruto={strat.stats_bruto}  "
          f"contra_tend={strat.stats_contra_tendencia}  emitidas={strat.stats_ordens_emitidas}  "
          f"sem_trade={c['sem_trade']}/{c['pregoes']}  top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%")
    print("\nCOMPARACAO: vencedor oficial (cruzado WIN+WDO) tinha liquido=1.221,50, trades=127, win=35,4%, "
          "sem_trade=60/122, top3/liq=59% (mesma geometria, mesma janela/quantil).")


if __name__ == "__main__":
    main()
