# -*- coding: utf-8 -*-
"""Geracao 8 (`WinBuscaLucroG08OrbSobrevivencia`) -- OOS-1 (jul-ago/2026), RODA UMA VEZ.

Vencedor do IS (congelado em
`win_busca_lucro_g08_orb_sobrevivencia_congelado_v08.py` ANTES desta rodada,
escolhido pelo CRITERIO COMPOSTO desta geracao -- liquido>0 E nao censurado E
win% != NEGATIVO E p_ruina(MC) <= 25% (limiar revisado de 20% para 25% ANTES
de ver qualquer OOS, ver docstring do modulo congelado para a razao):
range_minutos=5min, stop_min_pontos=50, stop_max_pontos=140, alvo_multiplo=3x,
buffer_entrada_pontos=20, ttl_barras_entrada=10.

IS: liquido=+R$1.365,50, 121 trades, win=37,2% (BEnom 25,0%, BEemp 27,4%,
IC95[29,1;46,1] -- POSITIVO com folga), 121/122 pregoes com trade (nao
censurado), p_ruina(MC, 44 operacoes, R$250->R$100)=24,8%, pior sequencia de
perdas no IS=6.

Protocolo (ORQUESTRACAO.md / mandato do dono): roda UMA VEZ, sem reajustar
nada depois de ver o numero -- se falhar, esta' MORTA. Compara explicitamente
a RUINA OBSERVADA nesta janela (a sequencia real aconteceu ou nao cruzou a
margem?) contra a ruina PREVISTA pelo Monte Carlo do IS.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g08_orb_sobrevivencia/g08_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g08_base as b  # noqa: E402

KW_VENCEDOR = dict(
    range_minutos=5.0,
    stop_min_pontos=50.0,
    stop_max_pontos=140.0,
    alvo_multiplo=3.0,
    buffer_entrada_pontos=20.0,
    ttl_barras_entrada=10,
)

#: p_ruina prevista pelo IS (MC, 10.000 caminhos, 44 operacoes, R$250->R$100)
#: -- referencia fixa para comparar com a ruina OBSERVADA nesta janela.
P_RUINA_PREVISTA_IS = 0.248


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    win = b.carrega_win()
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)

    print("=" * 140)
    print("WinBuscaLucroG08OrbSobrevivencia -- OOS-1 (jul-ago/2026), CONGELADO, roda UMA VEZ")
    print("=" * 140)
    print(f"OOS-1: {len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print(f"kwargs congelados = {KW_VENCEDOR}\n", flush=True)

    res, strat = b.roda_congelado(dias_oos1, **KW_VENCEDOR)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos1), horizonte_pregoes=len(dias_oos1))
    const = b.constancia_motor(trades)
    be_nom = 1.0 / (1.0 + KW_VENCEDOR["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha = linha_de_resultado("OOS-1 (congelado)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=11))

    equity_min_ok = equity_min >= b.MARGEM_WIN_BRL
    censurado = c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or not equity_min_ok
    stop_dist = sorted(c["stop_dist_pts"])
    stop_med = stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")

    print(f"\nliquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  pregoes_c_trade={c['com_trade']}/{c['pregoes']}  "
          f"equity_min={b.br(equity_min)}  "
          f"ordens_recusadas_por_capital={res.ordens_recusadas_por_capital}  censurado={censurado}")
    print(f"bruto={strat.stats_bruto}  ja_operou_hoje={strat.stats_ja_operou_hoje}  "
          f"emitidas={strat.stats_ordens_emitidas}")
    print(f"top3/liquido={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liquido={b.br(100*top5,0) if top5==top5 else '--'}%")
    print(f"stop_mediana_pts={b.br(stop_med,0)}  (>=100 -> item 6.47 nao exige checagem com ticks; <100 -> EXIGE)")

    print("\n--- RUINA: PREVISTA (IS) vs OBSERVADA (OOS-1) ---")
    print(f"p_ruina PREVISTA pelo IS (MC, 44 ops projetadas, R$250->R$100) = {b.br(100*P_RUINA_PREVISTA_IS,1)}%")
    print(f"p_ruina recalculada sobre os proprios trades do OOS-1 (MC, {ruina['n_ops']} ops, "
          f"R$250->R$100) = {b.br(100*ruina['p_ruina'],1) if ruina['p_ruina']==ruina['p_ruina'] else '--'}%  "
          f"(ruina_formula/Lundberg={b.br(100*ruina['ruina_formula'],1) if ruina['ruina_formula']==ruina['ruina_formula'] else '--'}%)")
    print(f"RUINA REALMENTE OCORREU nesta janela (caixa cruzou R$100 em algum momento)? "
          f"{'SIM' if not equity_min_ok else 'NAO'} (equity_min={b.br(equity_min)})")
    print(f"pior sequencia de perdas OBSERVADA={const.get('pior_seq_ops','--')} "
          f"(R${b.br(const.get('pior_seq_brl',0.0))})  -- no IS tinha sido 6 (R$-205,50)")

    print("\nVEREDITO FINAL:")
    if censurado:
        print("  -> MORTA (censurado: 0 trades, ou >=50% pregoes sem trade, ou caixa minimo abaixo da margem crua "
              "-- A MESMA FORMA COMO A G7 MORREU).")
    elif c["liquido"] <= 0:
        print("  -> MORTA (liquido <= 0 no OOS-1).")
    elif c["veredito"] == "NEGATIVO":
        print("  -> MORTA (win% estatisticamente ABAIXO do breakeven empirico no OOS-1).")
    elif c["veredito"] == "indefinido":
        print("  -> NAO VALIDADA COM FOLGA (liquido>0 mas IC95 do win% cruza o breakeven empirico) "
              "-- OOS-2 (set/2026) NAO sera' aberto por protocolo.")
    else:
        print("  -> PASSA COM FOLGA (liquido>0, nao censurado, win% estatisticamente acima do breakeven "
              "empirico) -- avanca para o OOS-2 (set/2026), gate final.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
