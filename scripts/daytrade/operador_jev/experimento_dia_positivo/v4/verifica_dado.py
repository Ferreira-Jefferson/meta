"""Item 6 da v4: verifica o salto de 2026-10-02 -> 2026-10-05 e lista saltos > 3 ATR diario entre fechamento e abertura na base IS/OOS/virgem.
Tambem procura saltos INTRADIA (M1 aberto vs fechamento do M1 anterior, mesmo pregao) > 1 ATR diario e pregoes curtos. Nao corrige a base: so reporta.
Uso: python verifica_dado.py  -> imprime e grava ../verificacao_dado.json"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
PAI = EXP.parent
sys.path.insert(0, str(PAI))
from mercado import Mercado  # noqa: E402

RAIZ = PAI.parents[2]


def main():
    mk = Mercado.carregar()
    d = mk.diario.copy()
    d["oc"] = d.close.shift(1)
    d["gap"] = d.open - d.oc
    d["atr_ant"] = d.atr_d.shift(1)
    d["gap_atr"] = d.gap / d.atr_ant
    d["gap_pct"] = d.gap / d.oc * 100
    venc = pd.DatetimeIndex(mk.venc)

    def dist_venc(x):
        dd = (venc - x).days
        return int(dd[np.argmin(abs(dd))])
    big = d[d.gap_atr.abs() > 3]
    out = dict(n_dias=int(len(d)), saltos_fech_abertura_3atr=[dict(data=str(x.date()), anterior=float(r.oc), abertura=float(r.open), gap=float(r.gap),
                                                                    gap_atrd=float(r.gap_atr), gap_pct=float(r.gap_pct), dias_ao_vencimento_mais_proximo=dist_venc(x)) for x, r in big.iterrows()])
    out["maiores_gaps_pct"] = [dict(data=str(x.date()), gap_pct=float(r.gap_pct), gap_atrd=float(r.gap_atr)) for x, r in d.gap_pct.abs().sort_values().tail(8).items() for r in [d.loc[x]]]
    # fontes: base sem leiloes x comparativo x ticks
    a = pd.read_parquet(RAIZ / "data/win_sem_leiloes/m1_WIN$N.parquet")
    b = pd.read_parquet(RAIZ / "data/comparativo_win_2026/m1_WIN$N.parquet")
    f = {}
    for nome, x in (("win_sem_leiloes", a), ("comparativo_win_2026", b)):
        y = x[(x.index >= "2026-10-01") & (x.index < "2026-10-06")]
        g = y.groupby(y.index.normalize()).agg(o=("open", "first"), c=("close", "last"))
        f[nome] = {str(k.date()): [float(r.o), float(r.c)] for k, r in g.iterrows()}
    tk = {}
    for dia in ("2026-10-02", "2026-10-05"):
        z = np.load(RAIZ / f"data/comparativo_win_2026/ticks/{dia}.npz")
        tk[dia] = dict(primeiro_tick=int(z["p"][0]), ultimo_tick=int(z["p"][-1]), n=int(len(z["p"])))
    out["fontes_2026_10_02_05"] = dict(m1=f, ticks=tk)
    # intradia
    m1 = mk.m1
    dia = m1.index.normalize()
    prev_c = m1.close.shift(1).where(dia == pd.Series(dia, index=m1.index).shift(1).values)
    salto = (m1.open - prev_c)
    atr_ant = d.atr_d.shift(1).reindex(dia).values
    r = (salto.abs() / atr_ant)
    r = r[r > 1.0]
    out["saltos_intradia_m1_acima_1atrd"] = [dict(t=str(i), salto=float(salto[i]), atrd=float(atr_ant[m1.index.get_loc(i)] if False else d.atr_d.shift(1).loc[i.normalize()]), x_atrd=float(v)) for i, v in r.items()]
    n1 = m1.groupby(dia).size()
    out["pregoes_curtos_menos_de_400_m1"] = {str(k.date()): int(v) for k, v in n1[n1 < 400].items()}
    (EXP / "verificacao_dado.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
