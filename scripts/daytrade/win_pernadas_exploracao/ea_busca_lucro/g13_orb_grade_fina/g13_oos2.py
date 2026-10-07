# -*- coding: utf-8 -*-
"""Geracao 13 (`WinBuscaLucroG13OrbGradeFina`) -- OOS-2 (set/2026), RODA UMA
VEZ, SO' SE O OOS-1 PASSAR "COM FOLGA".

Nenhuma geracao desta busca (G1-G12) chegou a abrir este gate -- toda geracao
anterior morreu ou ficou "indefinida" no OOS-1. Se este script estiver sendo
executado, e' porque o OOS-1 desta geracao passou com folga (liquido>0, nao
censurado por capital, veredito do win% POSITIVO). Protocolo: roda UMA VEZ,
sem reajustar nada depois de ver o numero.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g13_orb_grade_fina/g13_oos2.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g13_base as b  # noqa: E402
from g13_oos1 import KW_VENCEDOR  # noqa: E402 -- mesmo kwargs congelado do OOS-1


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    if not KW_VENCEDOR:
        raise RuntimeError("KW_VENCEDOR vazio -- preencha g13_oos1.KW_VENCEDOR antes de rodar o OOS-2")

    win = b.carrega_win()
    dias_oos2 = b.dias_da_janela(win, b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM)

    print("=" * 150)
    print("WinBuscaLucroG13OrbGradeFina -- OOS-2 (set/2026), CONGELADO, roda UMA VEZ, gate FINAL")
    print("=" * 150)
    print(f"OOS-2: {len(dias_oos2)} pregoes completos ({dias_oos2[0]} a {dias_oos2[-1]})")
    print(f"kwargs congelados (identicos ao OOS-1) = {KW_VENCEDOR}\n", flush=True)

    atr_serie_completa = None
    if KW_VENCEDOR.get("stop_family") == "atr":
        dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
        dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
        bars_acumulado = b.bars_dos_dias(win, dias_is + dias_oos1 + dias_oos2)
        atr_serie_completa = b.computa_atr_serie(bars_acumulado)

    res, strat = b.roda_congelado(dias_oos2, atr_serie_completa=atr_serie_completa, **KW_VENCEDOR)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos2)
    top5 = b.concentracao_topn(c["serie"], 5)
    censura = b.censura_separada(res, c)
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos2), horizonte_pregoes=len(dias_oos2))
    const = b.constancia_motor(trades)
    be_nom = 1.0 / (1.0 + KW_VENCEDOR["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha = linha_de_resultado("OOS-2 (congelado)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=11))

    print(f"\nliquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"censura_capital={censura['censura_capital']}  equity_min={b.br(censura['equity_min'])}  "
          f"ordens_recusadas_por_capital={censura['ordens_recusadas_por_capital']}")
    print(f"top3/liquido={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%")
    print(f"p_ruina(MC, {ruina['n_ops']} ops)={b.br(100*ruina['p_ruina'],1) if ruina['p_ruina']==ruina['p_ruina'] else '--'}%  "
          f"pior_seq_perdas={const.get('pior_seq_ops','--')}")

    print("\nVEREDITO FINAL (gate final desta linha de pesquisa):")
    if censura["censura_capital"] or c["liquido"] <= 0 or c["veredito"] == "NEGATIVO":
        print("  -> MORTA no OOS-2.")
    elif c["veredito"] == "indefinido":
        print("  -> NAO VALIDADA COM FOLGA no OOS-2 (liquido>0 mas IC95 cruza o breakeven).")
    else:
        print("  -> VALIDADA nas TRES janelas (IS, OOS-1, OOS-2) -- primeira desta busca inteira (G1-G13) "
              "a chegar ate' aqui. Calcular % mensal equivalente sobre R$250 e reportar ao dono antes de "
              "qualquer passo em direcao a dinheiro real.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
