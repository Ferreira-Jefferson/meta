# -*- coding: utf-8 -*-
"""Geracao 12 -- DIAGNOSTICO rapido no IS: quanto o AND reduz a frequencia?

Roda so' uma vez por `k_minutos`, com a geometria-base herdada da G08
(stop_max=140, alvo=3x -- NAO E' a busca de geometria, so' para medir
`stats_bruto_a` (ORB), `stats_bruto_b` (anomalo), `stats_and_bruto` (A∩B,
mesma direcao, dentro da janela) e `stats_ordens_emitidas` (depois dos
filtros de execucao de 1 trade/dia). Os tres primeiros contadores NAO
dependem da geometria (sao calculados ANTES de qualquer filtro de
posicao/armado) -- rodar com qualquer geometria fixa basta para o
diagnostico; so' `stats_ordens_emitidas` e o P&L dependem da geometria
escolhida, e aqui usamos a da G08 so' como ponto de partida.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g12_and_orb_cross/g12_diagnostico.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g12_base as b  # noqa: E402

GEOMETRIA_BASE = dict(range_minutos=5.0, stop_min_pontos=50.0, stop_max_pontos=140.0,
                       alvo_multiplo=3.0, buffer_entrada_pontos=20.0, ttl_barras_entrada=10)


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 120)
    print("Geracao 12 -- DIAGNOSTICO no IS (jan-jun/2026): brutas A, B, A-interseccao-B por k_minutos")
    print("=" * 120)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print(f"sinal B: janela_min={b.JANELA_MIN_SINAL_B} quantil={b.QUANTIL_SINAL_B} direcao=continuacao (fixos pelo mandato)")
    print(f"geometria-base (so' para o diagnostico, NAO e' a busca): {GEOMETRIA_BASE}\n", flush=True)

    # referencia ORB puro (G8) -- so' para o bruto_a de referencia (deve bater
    # com o bruto_a desta classe, mesma logica de deteccao).
    res_ref, strat_ref = b.roda_orb_puro(dias, **GEOMETRIA_BASE)
    print(f"REF ORB puro (G8): bruto_a={strat_ref.stats_bruto}  ordens_emitidas={strat_ref.stats_ordens_emitidas}  "
          f"liquido={b.br(sum(t.pnl_brl for t in res_ref.trades))}  trades={len(res_ref.trades)}")

    for k in (0.0, 5.0, 15.0, 30.0):
        res, strat = b.roda(dias, k_minutos=k, **GEOMETRIA_BASE)
        trades = list(res.trades)
        liquido = sum(t.pnl_brl for t in trades)
        dias_distintos = len({t.exit_ts.date() for t in trades})
        print(f"k={k:>4g}min  bruto_a={strat.stats_bruto_a:>5}  bruto_b={strat.stats_bruto_b:>5}  "
              f"and_bruto={strat.stats_and_bruto:>5}  emitidas={strat.stats_ordens_emitidas:>4}  "
              f"trades={len(trades):>4}  pregoes_distintos={dias_distintos:>3}  liquido={b.br(liquido):>12}",
              flush=True)

    print("\nFIM.")


if __name__ == "__main__":
    main()
