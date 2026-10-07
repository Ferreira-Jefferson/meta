# -*- coding: utf-8 -*-
"""Geracao 13 -- ESTAGIO C isolado (stop FIXO), rodado separado do Estagio B
(ATR-M15) porque o Estagio B demonstrou custo computacional anomalo nesta
maquina (>200s de CPU por celula sem terminar, contra 5,7s da familia
tecnico no mesmo periodo de 122 dias -- ver ORQUESTRACAO.md, nota de metodo
da Geracao 13) e foi abortado. Reusa o vencedor confirmado do Estagio A
(stop_max=140, alvo=3x, confirma=0) como vizinhanca fixa.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g13_base as b  # noqa: E402
from g13_is_busca import _bate_composto, _worker  # noqa: E402

MAX_WORKERS = 4
STOP_FIXO_GRID = (100.0, 120.0, 140.0, 160.0)
ALVO_VENC = 3.0
CONFIRMA_VENC = 0.0


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"ESTAGIO C isolado -- stop FIXO (vizinhanca: alvo={ALVO_VENC:g}x, confirma={CONFIRMA_VENC:g}pt)", flush=True)

    variantes_c = [
        (f"C fixo sf={sf:g} (alvo={ALVO_VENC:g}x conf={CONFIRMA_VENC:g})",
         dict(range_minutos=5.0, stop_family="fixo", stop_min_pontos=50.0,
              stop_fixo_pontos=sf, alvo_multiplo=ALVO_VENC, confirma_pontos=CONFIRMA_VENC,
              buffer_entrada_pontos=20.0))
        for sf in STOP_FIXO_GRID
    ]
    resultados = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, kw, dias, None): rot for rot, kw in variantes_c}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            c = r["c"]
            ru = r["ruina"]
            print(f"  {rot:<32} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
                  f"cap_cens={r['censura']['censura_capital']}  composto={_bate_composto(r)}", flush=True)

    EXTRAS = ("familia", "confirma_pt", "BEnom%", "BEemp%", "IC95 win", "veredito",
              "top3/liq", "top5/liq", "pregoes c/trade", "p_ruina(MC)", "pior_seq_perdas",
              "censura_capital", "seletiv_amostra")
    print("\nTABELA ESTAGIO C:")
    print(tabela([r["linha"] for r in resultados.values()], extras=EXTRAS, largura_extra=11))
    print("\nFIM ESTAGIO C.")


if __name__ == "__main__":
    main()
