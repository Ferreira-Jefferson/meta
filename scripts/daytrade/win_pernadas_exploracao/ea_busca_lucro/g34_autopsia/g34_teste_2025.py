# -*- coding: utf-8 -*-
"""Teste unico, em meses nunca abertos, dos dois filtros da G34 CONGELADOS:
  - nao entra se o sinal for entre 13:00 e 14:59
  - so' entra se vol_rel >= corte do tercil superior do IS (jan-jun/26)
Meses escolhidos so' pela variacao de preco do WIN (dono pediu 1 de alta e
1 de baixa, autorizou abrir 2 meses da reserva de 2025 em 2026-10-06):
  jul/2025 -4,39% (baixa) e ago/2025 +5,21% (alta). Resto de 2025 continua fechado.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import g34_autopsia as a  # noqa: E402

b = a.b

MESES = {
    "jul/2025 (baixa -4,4%)": (pd.Timestamp("2025-07-01"), pd.Timestamp("2025-08-01")),
    "ago/2025 (alta +5,2%)": (pd.Timestamp("2025-08-01"), pd.Timestamp("2025-09-01")),
}


def main():
    trades_is = pd.read_csv(AQUI / "g34_autopsia_trades.csv", sep=";", decimal=",")
    corte_vol = float(np.nanquantile(trades_is[trades_is.janela == "IS jan-jun"].vol_rel, 2 / 3))
    print(f"corte de volume congelado (IS): {corte_vol:.4f}\n", flush=True)

    win = b.carrega_win()
    d = a.prepara_serie(win)
    linhas = []
    for nome, (ini, fim) in MESES.items():
        dias = b.dias_da_janela(win, ini, fim)
        trades, sinais = a.roda(dias)
        t = a.monta_tabela(trades, sinais, d, nome)
        fora = ~((t.hora >= 13) & (t.hora < 15))
        vol = t.vol_rel >= corte_vol
        for rot, m in (("sem filtro", t.hora > 0), ("pula 13-15h", fora),
                       ("so volume alto", vol), ("os dois", fora & vol)):
            s = t[m]
            linhas.append(dict(mes=nome, regra=rot, pregoes=len(dias), trades=len(s),
                               win=100 * s.ganhou.mean() if len(s) else float("nan"),
                               liquido=s.pnl.sum()))
        print(f"{nome}: {len(dias)} pregoes, {len(trades)} trades, {len(t)} casados", flush=True)
    r = pd.DataFrame(linhas)
    print()
    print(r.to_string(index=False))
    r.to_csv(AQUI / "g34_teste_2025_resultado.csv", index=False, sep=";", decimal=",")


if __name__ == "__main__":
    main()
