# -*- coding: utf-8 -*-
"""Diagnostico rapido (NAO e' a busca oficial): confirma que os dados carregam,
remede a correlacao dos incrementos de minuto no IS e mede a frequencia bruta
do estado anomalo para a grade de janela/quantil antes de rodar qualquer
backtest. Uso: `.venv\\Scripts\\python.exe -u
scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/g04_cross_wdo/g04_diagnostico.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g04_base as b  # noqa: E402


def main() -> None:
    win = b.carrega_win()
    wdo = b.carrega_wdo()
    print(f"WIN@: {len(win)} barras, {win.index[0]} a {win.index[-1]}")
    print(f"WDO@: {len(wdo)} barras, {wdo.index[0]} a {wdo.index[-1]}")

    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"\nIS (jan-jun/2026): {len(dias_is)} pregoes completos ({dias_is[0]} a {dias_is[-1]})")

    corr = b.correlacao_incrementos_minuto(win, wdo, dias_is)
    print(f"\nCorrelacao incrementos de 1 min (IS, remedida do zero): "
          f"r={corr['r']:.4f}  n={corr['n']}")

    print("\nFrequencia bruta do estado anomalo (janela x quantil), IS inteiro:")
    print(f"{'janela':>7} {'quantil':>8} {'anomalo_barras':>15} {'%barras':>9} {'episodios(borda)':>17}")
    for janela in (10, 15, 20):
        for quantil in (0.60, 0.75, 0.90):
            anomalo, direcao = b.computa_estado(dias_is, janela, quantil)
            win_fatia = b.bars_dos_dias(win, dias_is)
            a = anomalo.reindex(win_fatia.index, fill_value=False)
            n_barras = int(a.sum())
            # episodios = bordas False->True
            borda = (a.astype(int).diff() == 1).sum()
            pct = 100.0 * n_barras / len(a) if len(a) else float("nan")
            print(f"{janela:>7} {quantil:>8.2f} {n_barras:>15} {pct:>8.3f}% {int(borda):>17}")


if __name__ == "__main__":
    main()
