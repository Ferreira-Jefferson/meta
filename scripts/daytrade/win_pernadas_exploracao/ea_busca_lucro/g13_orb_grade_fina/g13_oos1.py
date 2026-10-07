# -*- coding: utf-8 -*-
"""Geracao 13 (`WinBuscaLucroG13OrbGradeFina`) -- OOS-1 (jul-ago/2026), RODA UMA VEZ.

Vencedor do IS congelado em
`win_busca_lucro_g13_orb_grade_fina_congelado_v13.py` ANTES desta rodada --
ver docstring do modulo congelado para o kwargs exato e a razao da escolha
(vencedor composto da grade 3D: stop_max_pontos x alvo_multiplo x
confirma_pontos, familia tecnico, mais o resultado dos Estagios B/C de
ATR-M15 e stop fixo na vizinhanca).

Protocolo (ORQUESTRACAO.md / mandato do dono): roda UMA VEZ, sem reajustar
nada depois de ver o numero -- se falhar, esta' MORTA. Preenchido com o kwargs
do vencedor ANTES de rodar (ver `KW_VENCEDOR`/`P_RUINA_PREVISTA_IS` abaixo).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g13_orb_grade_fina/g13_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g13_base as b  # noqa: E402

# PREENCHIDO pelo vencedor do IS -- ver win_busca_lucro_g13_orb_grade_fina_congelado_v13.py
KW_VENCEDOR: dict = {}
P_RUINA_PREVISTA_IS: float = float("nan")
ATR_SERIE_NECESSARIA = False  # True se o vencedor for stop_family="atr"


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    if not KW_VENCEDOR:
        raise RuntimeError("KW_VENCEDOR vazio -- preencha com o vencedor do IS antes de rodar o OOS-1")

    win = b.carrega_win()
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)

    print("=" * 150)
    print("WinBuscaLucroG13OrbGradeFina -- OOS-1 (jul-ago/2026), CONGELADO, roda UMA VEZ")
    print("=" * 150)
    print(f"OOS-1: {len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print(f"kwargs congelados = {KW_VENCEDOR}\n", flush=True)

    atr_serie_completa = None
    if ATR_SERIE_NECESSARIA or KW_VENCEDOR.get("stop_family") == "atr":
        # ATR precomputado sobre IS+OOS-1 (acumulado, nao reinicia burn-in em
        # julho -- mesmo principio de um robo ao vivo que nao "esquece" a
        # historia, precedente G4).
        dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
        bars_acumulado = b.bars_dos_dias(win, dias_is + dias_oos1)
        atr_serie_completa = b.computa_atr_serie(bars_acumulado)

    res, strat = b.roda_congelado(dias_oos1, atr_serie_completa=atr_serie_completa, **KW_VENCEDOR)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    top5 = b.concentracao_topn(c["serie"], 5)
    censura = b.censura_separada(res, c)
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

    stop_dist = sorted(c["stop_dist_pts"])
    stop_med = stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")

    print(f"\nliquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  pregoes_c_trade={c['com_trade']}/{c['pregoes']}  "
          f"equity_min={b.br(censura['equity_min'])}  "
          f"ordens_recusadas_por_capital={censura['ordens_recusadas_por_capital']}  "
          f"censura_capital={censura['censura_capital']}  seletividade_amostra={censura['seletividade_amostra']}")
    print(f"bruto={strat.stats_bruto}  ja_operou_hoje={strat.stats_ja_operou_hoje}  "
          f"emitidas={strat.stats_ordens_emitidas}  sem_atr_disponivel={getattr(strat,'stats_sem_atr_disponivel',0)}")
    print(f"top3/liquido={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liquido={b.br(100*top5,0) if top5==top5 else '--'}%")
    print(f"stop_mediana_pts={b.br(stop_med,0)}  (>=100 -> item 6.47 nao exige checagem com ticks; <100 -> EXIGE)")

    print("\n--- RUINA: PREVISTA (IS) vs OBSERVADA (OOS-1) ---")
    print(f"p_ruina PREVISTA pelo IS (MC, 44 ops projetadas, R$250->R$100) = "
          f"{b.br(100*P_RUINA_PREVISTA_IS,1) if P_RUINA_PREVISTA_IS==P_RUINA_PREVISTA_IS else '--'}%")
    print(f"p_ruina recalculada sobre os proprios trades do OOS-1 (MC, {ruina['n_ops']} ops, "
          f"R$250->R$100) = {b.br(100*ruina['p_ruina'],1) if ruina['p_ruina']==ruina['p_ruina'] else '--'}%  "
          f"(ruina_formula/Lundberg={b.br(100*ruina['ruina_formula'],1) if ruina['ruina_formula']==ruina['ruina_formula'] else '--'}%)")
    print(f"RUINA REALMENTE OCORREU nesta janela (caixa cruzou R$100 em algum momento OU ordem recusada por capital)? "
          f"{'SIM' if censura['censura_capital'] else 'NAO'} (equity_min={b.br(censura['equity_min'])})")
    print(f"pior sequencia de perdas OBSERVADA={const.get('pior_seq_ops','--')} "
          f"(R${b.br(const.get('pior_seq_brl',0.0))})")

    print("\nVEREDITO FINAL:")
    if censura["censura_capital"]:
        print("  -> MORTA (censura por CAPITAL -- caixa cruzou a margem crua ou ordem recusada por falta de capital, "
              "item 6.51: este e' o modo de falha real, nao so' poucos pregoes com trade).")
    elif c["liquido"] <= 0:
        print("  -> MORTA (liquido <= 0 no OOS-1).")
    elif c["veredito"] == "NEGATIVO":
        print("  -> MORTA (win% estatisticamente ABAIXO do breakeven empirico no OOS-1).")
    elif c["veredito"] == "indefinido":
        print("  -> NAO VALIDADA COM FOLGA (liquido>0 mas IC95 do win% cruza o breakeven empirico) "
              "-- OOS-2 (set/2026) NAO sera' aberto por protocolo.")
    else:
        print("  -> PASSA COM FOLGA (liquido>0, nao censurado por capital, win% estatisticamente acima do "
              "breakeven empirico) -- avanca para o OOS-2 (set/2026), gate final.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
