# -*- coding: utf-8 -*-
"""Geracao 15 -- DIAGNOSTICO de concentracao temporal (item 1 do mandato),
ANTES de desenhar a politica "por regime": as duas familias (ORB G8/G13,
cruzado G4) disparam em horarios diferentes, ou se sobrepoem o dia inteiro?

Roda o portfolio com `orcamento_modo='ilimitado'` (reproduz EXATAMENTE o
mecanismo da G14 -- nenhuma vaga e' recusada) sobre o IS e tabula a hora do
dia de cada sinal BRUTO (antes de qualquer portao/ja-operou-hoje/orcamento),
usando os contadores `horas_bruto_orb`/`horas_bruto_cross` novos desta
geracao. So' DEPOIS deste diagnostico a politica "regime" ganha um corte de
horario concreto (ou e' descartada, se a sobreposicao for alta).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g15_portfolio_orcamento/g15_diagnostico.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g15_base as b  # noqa: E402


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 100)
    print("G15 -- DIAGNOSTICO de concentracao temporal (IS, jan-jun/2026)")
    print("=" * 100)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})\n", flush=True)

    res_pf, strat = b.roda_portfolio(
        dias, orcamento_modo="ilimitado", orcamento_valor=None,
        politica_prioridade="fifo", **b.KWARGS_GEOMETRIA)

    print(f"sinais BRUTOS (antes de qualquer portao/orcamento/ja-operou-hoje): "
          f"orb={strat.stats_bruto_orb}  cross={strat.stats_bruto_cross}\n")

    horas = list(range(9, 19))
    hist_orb = pd.Series(strat.horas_bruto_orb).value_counts().reindex(horas, fill_value=0)
    hist_cross = pd.Series(strat.horas_bruto_cross).value_counts().reindex(horas, fill_value=0)
    tot_orb = hist_orb.sum()
    tot_cross = hist_cross.sum()

    print(f"{'hora':<6}{'orb(n)':>8}{'orb(%)':>9}{'cross(n)':>10}{'cross(%)':>10}")
    for h in horas:
        po = 100 * hist_orb[h] / tot_orb if tot_orb else 0.0
        pc = 100 * hist_cross[h] / tot_cross if tot_cross else 0.0
        print(f"{h:>4}h {hist_orb[h]:>7}{po:>8.1f}%{hist_cross[h]:>9}{pc:>9.1f}%")

    # -- manha (<12h) x tarde (>=12h), o corte mais simples a testar primeiro
    manha_orb = sum(hist_orb[h] for h in horas if h < 12)
    tarde_orb = tot_orb - manha_orb
    manha_cross = sum(hist_cross[h] for h in horas if h < 12)
    tarde_cross = tot_cross - manha_cross
    print(f"\ncorte <12h / >=12h:")
    print(f"  orb:   manha={manha_orb} ({100*manha_orb/tot_orb:.1f}%)  "
          f"tarde={tarde_orb} ({100*tarde_orb/tot_orb:.1f}%)")
    print(f"  cross: manha={manha_cross} ({100*manha_cross/tot_cross:.1f}%)  "
          f"tarde={tarde_cross} ({100*tarde_cross/tot_cross:.1f}%)")

    # -- qual hora de corte MAXIMIZA a separacao (fracao de cada familia do
    # "seu" lado do corte), varrendo todos os cortes possiveis -- descoberta
    # de dado, nao escolha a dedo.
    print(f"\nvarredura de corte (hora em que orb fica ANTES, cross fica NO/DEPOIS):")
    melhor_corte, melhor_score = None, -1.0
    for corte in range(10, 18):
        orb_antes = sum(hist_orb[h] for h in horas if h < corte)
        cross_depois = sum(hist_cross[h] for h in horas if h >= corte)
        score = (orb_antes / tot_orb if tot_orb else 0) + (cross_depois / tot_cross if tot_cross else 0)
        print(f"  corte={corte:>2}h  orb_antes={100*orb_antes/tot_orb:.1f}%  "
              f"cross_depois={100*cross_depois/tot_cross:.1f}%  score_soma={score:.3f}")
        if score > melhor_score:
            melhor_corte, melhor_score = corte, score

    print(f"\nmelhor corte (maximiza orb-antes + cross-depois): {melhor_corte}h "
          f"(score={melhor_score:.3f}, maximo possivel=2.0)")
    print("\nFIM.")


if __name__ == "__main__":
    main()
