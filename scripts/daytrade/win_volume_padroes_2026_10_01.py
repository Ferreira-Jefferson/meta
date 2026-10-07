"""Calibra os padroes finais do WinVolumeRazao (Dias=10, semana, mediana) e valida nos meses reservados.

Niveis: percentis p15 e p85 da razao nos meses de AJUSTE (2026-06/07/08), arredondados a 0,05,
por tempo grafico. Confirmacao nos meses de TESTE (2026-04/05/09) e validacao FINAL nos meses
reservados (2026-01/02/03 e 2025-09..12), que nenhum estudo anterior tocou.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_volume_razao_py as w  # noqa: E402

AJUSTE = ["2026-06", "2026-07", "2026-08"]
TESTE = ["2026-04", "2026-05", "2026-09"]
RESERVA = ["2026-01", "2026-02", "2026-03", "2025-09", "2025-10", "2025-11", "2025-12"]
DIAS, MODO, AGG = 10, "semana", "mediana"


def fr(r, lo, hi):
    r = r.dropna()
    return f"{(r < lo).mean()*100:4.1f}% / {(r > hi).mean()*100:4.1f}%  (n={len(r)})"


def main() -> None:
    for tf in ("M5", "M1"):
        d = w.ler_m5_volume(tf)
        r = w.razao_volume(d, DIAS, MODO, AGG)
        mes = r.index.strftime("%Y-%m")
        aj = r[mes.isin(AJUSTE)].dropna()
        p = aj.quantile([.05, .10, .15, .20, .25, .5, .75, .80, .85, .90, .95]).round(2)
        print(f"\n== {tf} Dias={DIAS} {MODO} {AGG} | percentis no AJUSTE:", dict(zip(p.index.round(2), p.values)), flush=True)
        lo = round(float(aj.quantile(.15)) / 0.05) * 0.05
        hi = round(float(aj.quantile(.85)) / 0.05) * 0.05
        print(f"niveis escolhidos (p15/p85 arredondados): baixo {lo:.2f}  alto {hi:.2f}", flush=True)
        for nome, ms in (("ajuste", AJUSTE), ("teste", TESTE), ("RESERVA", RESERVA)):
            print(f"  {nome:8} fracao <baixo / >alto: {fr(r[mes.isin(ms)], lo, hi)}", flush=True)
        # validacao final do poder de prever volatilidade (range da proxima barra / mediana do horario)
        if tf == "M5":
            rng = (d.high - d.low)
            alvo = rng.shift(-1)
            chave = d.index.dayofweek * 10000 + d.index.hour * 60 + d.index.minute
            norm = rng.groupby(chave).transform(lambda x: x.shift(1).rolling(8, min_periods=8).median())
            alvo = alvo / norm
            same_day = pd.Series(d.index.date, index=d.index).shift(-1) == pd.Series(d.index.date, index=d.index)
            for nome, ms in (("teste", TESTE), ("RESERVA", RESERVA)):
                for dias_c in (2, DIAS):
                    rr = w.razao_volume(d, dias_c, MODO, AGG)
                    x = pd.concat([rr, alvo], axis=1, keys=["r", "a"])[mes.isin(ms) & same_day.to_numpy()].dropna()
                    print(f"  {nome:8} Spearman(razao Dias={dias_c:>2}, range prox barra) = {x.r.rank().corr(x.a.rank()):.3f} (n={len(x)})", flush=True)


if __name__ == "__main__":
    main()
