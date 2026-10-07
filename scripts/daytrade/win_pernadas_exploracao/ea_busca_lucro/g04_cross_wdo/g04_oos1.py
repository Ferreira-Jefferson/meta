# -*- coding: utf-8 -*-
"""Geracao 4 (`WinBuscaLucroG04CrossWdo`) -- OOS-1 (jul-ago/2026), RODA UMA VEZ.

Vencedor do IS (congelado em
`win_busca_lucro_g04_cross_wdo_congelado_v04.py` ANTES desta rodada):
direcao_aposta=continuacao, janela_min=20, quantil=0,75, stop_pontos=150,
alvo_multiplo=3x, buffer_entrada_pontos=30. IS: liquido=R$1.221,50, 127
trades, win=35,4% (BEnom 25,0%, BEemp 27,5%, IC95[27,7;44,1] -- POSITIVO por
0,2pp), sem_trade=60/122, equity_min=R$243,00 (nao censurado), top3/liquido
=59% (CONCENTRACAO relevante, declarada). Stop mediano 155pts (>=100 --
item 6.47 nao exige checagem obrigatoria com ticks).

O quantil causal do estado anomalo usa o historico REAL acumulado (IS +
OOS-1, ate' o dia anterior a cada barra) -- nao reinicia o burn-in em
jul/2026, que seria o equivalente a um robo ao vivo "esquecer" a historia
que ja' tinha. So' os DIAS de jul-ago/2026 entram no calculo do resultado
(liquido, trades, capital).

Protocolo (ORQUESTRACAO.md / mandato do dono): roda UMA VEZ, sem reajustar
nada depois de ver o numero -- se falhar, esta' MORTA.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g04_cross_wdo/g04_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g04_base as b  # noqa: E402

KW_VENCEDOR = dict(
    direcao_aposta="continuacao",
    stop_pontos=150.0,
    alvo_multiplo=3.0,
    buffer_entrada_pontos=30.0,
)
JANELA_MIN = 20
QUANTIL = 0.75


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    win = b.carrega_win()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    dias_historico = sorted(set(dias_is) | set(dias_oos1))

    print("=" * 110)
    print("WinBuscaLucroG04CrossWdo -- OOS-1 (jul-ago/2026), CONGELADO, roda UMA VEZ")
    print("=" * 110)
    print(f"OOS-1: {len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print(f"kwargs congelados = {KW_VENCEDOR}, janela_min={JANELA_MIN}, quantil={QUANTIL}")
    print("Quantil causal usa o historico acumulado IS+OOS-1 (nao reinicia burn-in em jul/2026).\n", flush=True)

    res, strat = b.roda_congelado(
        dias_oos1, dias_historico=dias_historico,
        janela_min=JANELA_MIN, quantil=QUANTIL, **KW_VENCEDOR)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    be_nom = 1.0 / (1.0 + KW_VENCEDOR["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "bruto": str(strat.stats_bruto),
        "contra_tend": str(strat.stats_contra_tendencia),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "pts/op": b.br(c["pontos_por_op"], 2),
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha = linha_de_resultado("OOS-1 D buffer=30 (congelado)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=10))

    equity_min_ok = equity_min >= b.MARGEM_WIN_BRL
    censurado = c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or not equity_min_ok
    print(f"\nliquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  equity_min={b.br(equity_min)}  "
          f"ordens_recusadas_por_capital={res.ordens_recusadas_por_capital}  censurado={censurado}")
    print(f"bruto={strat.stats_bruto}  contra_tend={strat.stats_contra_tendencia}  emitidas={strat.stats_ordens_emitidas}")
    print(f"top3/liquido={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%")
    stop_med = sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2] if c["stop_dist_pts"] else float("nan")
    print(f"stop_mediana_pts={b.br(stop_med,0)}  (>=100 -> item 6.47 nao exige checagem com ticks; <100 -> EXIGE)")

    print("\nVEREDITO FINAL:")
    if censurado:
        print("  -> MORTA (censurado: 0 trades, ou >=50% pregoes sem trade, ou caixa minimo abaixo da margem crua).")
    elif c["liquido"] <= 0:
        print("  -> MORTA (liquido <= 0 no OOS-1).")
    elif c["veredito"] == "NEGATIVO":
        print("  -> MORTA (win% estatisticamente ABAIXO do breakeven empirico no OOS-1).")
    elif c["veredito"] == "indefinido":
        print("  -> NAO VALIDADA COM FOLGA (liquido>0 mas IC95 do win% cruza o breakeven empirico -- "
              "mesma leitura fragil do IS, nao e' confirmacao independente forte).")
    else:
        print("  -> PASSA COM FOLGA (liquido>0, nao censurado, win% estatisticamente acima do breakeven empirico).")
    print("\nFIM.")


if __name__ == "__main__":
    main()
