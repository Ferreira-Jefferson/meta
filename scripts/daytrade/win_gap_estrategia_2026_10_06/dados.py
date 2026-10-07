# -*- coding: utf-8 -*-
"""Dados do estudo WIN gap/1a barra M5 (2026-10-06): barras M5 sem leiloes (WIN$N, preco
cru), tabela por dia (gap, volume do call de D-1, dia de rolagem) e contexto causal por dia.

Gap = leilao_preco[D] - call_preco[D-1] (colunas de `dias_WIN$N*.csv`). 2022-25 e
2025-10..2026-04-03 sao `proxy=True`; de 2026-04-06 em diante os valores sao medidos por tick.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
D = ROOT / "data" / "win_sem_leiloes"
BASES = {
    "2026": (D / "m5_WIN$N.parquet", D / "dias_WIN$N.csv"),
    "2022_25": (D / "m5_WIN$N_2022_2025.parquet", D / "dias_WIN$N_2022_2025.csv"),
}
JANELA_VOL = 60
MIN_VOL = 20
MIN_BARRAS_DIA = 80      # M5 do pregao cheio = 112 (09:00-18:20)


def _quarta_mais_proxima_do_15(ano: int, mes: int) -> date:
    d15 = date(ano, mes, 15)
    cand = [d15 + timedelta(days=k) for k in range(-3, 4)]
    return next(c for c in cand if c.weekday() == 2)


def dias_de_rolagem(dias_negociados: list[date]) -> set[date]:
    """Vencimento do WIN: quarta mais proxima do dia 15 dos meses pares. Se nao houve pregao
    nesse dia, o proximo pregao. O WIN$N troca de contrato nessa data e o gap fica falso."""
    ds = sorted(dias_negociados)
    out = set()
    for ano in range(ds[0].year, ds[-1].year + 1):
        for mes in (2, 4, 6, 8, 10, 12):
            v = _quarta_mais_proxima_do_15(ano, mes)
            prox = [x for x in ds if x >= v]
            if prox and (prox[0] - v).days <= 3:
                out.add(prox[0])
    return out


def carrega(base: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(barras M5, tabela por dia). A tabela traz gap, vol_call_prev, vol_alto, excluir, motivo."""
    pq, csv = BASES[base]
    b = pd.read_parquet(pq)
    d = pd.read_csv(csv, sep=";", encoding="utf-8-sig", parse_dates=["data"]).set_index("data")
    d.index = pd.DatetimeIndex(d.index).normalize()
    for c in ("fim_continuo", "ultima_barra_continua"):
        d[c] = pd.to_datetime(d[c])
    dia_b = b.index.normalize()
    n_barras = b.groupby(dia_b).size()
    prim = b.groupby(dia_b).apply(lambda x: x.index[0].time())
    d["n_barras"] = n_barras.reindex(d.index)
    d["primeira"] = prim.reindex(d.index)
    d["dprev"] = d.index.to_series().diff().dt.days
    d["gap"] = d["leilao_preco"] - d["call_preco"].shift(1)
    d["vol_call_prev"] = d["call_volume"].shift(1)
    # volume do call alto: acima da mediana dos ate' 60 dias ANTERIORES a D (D-1 inclusive), so'
    # com valores do mesmo regime (proxy x medido)
    prox = d["proxy"].astype(bool)
    alto = pd.Series(np.nan, index=d.index)
    for reg in (True, False):
        s = d["call_volume"].where(prox == reg)
        med = s.rolling(JANELA_VOL, min_periods=MIN_VOL).median().shift(1)
        sel = (prox.shift(1) == reg)
        alto = alto.where(~sel, (d["vol_call_prev"] > med).where(med.notna()).astype(float).where(med.notna()))
    d["vol_alto"] = alto  # NaN = sem historico suficiente (tratado como "nao alto")
    rol = dias_de_rolagem([x.date() for x in d.index])
    motivo = pd.Series("", index=d.index)
    for x in d.index:
        m = []
        if x.date() in rol:
            m.append("rolagem")
        if x == pd.Timestamp("2026-07-31"):
            m.append("abertura_atrasada")
        if not (d.loc[x, "dprev"] <= 5) or not np.isfinite(d.loc[x, "gap"]):
            m.append("sem_dia_anterior")
        n = d.loc[x, "n_barras"]
        if not (n == n and n >= MIN_BARRAS_DIA) or d.loc[x, "primeira"] > pd.Timestamp("09:10").time():
            m.append("pregao_parcial")
        motivo[x] = "+".join(m)
    d["motivo_excl"] = motivo
    d["excluir"] = motivo != ""
    return b, d


def janela(b: pd.DataFrame, d: pd.DataFrame, ini: str, fim: str):
    """Fatia [ini, fim] (datas inclusivas). Devolve (barras dos dias elegiveis, tabela dos dias da
    janela incl. excluidos, contexto por dia {date: (gap, vol_alto)} dos elegiveis)."""
    ini, fim = pd.Timestamp(ini), pd.Timestamp(fim)
    dj = d[(d.index >= ini) & (d.index <= fim)]
    ok = dj[~dj.excluir]
    dia_b = b.index.normalize()
    bj = b[dia_b.isin(ok.index)]
    ctx = {x.date(): (float(r.gap), bool(r.vol_alto == 1.0)) for x, r in ok.iterrows()}
    return bj, dj, ctx


if __name__ == "__main__":
    for k in BASES:
        b, d = carrega(k)
        print(k, b.shape, d.shape, "excluidos:", d.motivo_excl[d.excluir].value_counts().to_dict())
        r = d[d.motivo_excl.str.contains("rolagem")]
        print("  |gap| rolagem mediana", r.gap.abs().median(), "| outros mediana", d[~d.excluir].gap.abs().median(), "| n rol", len(r))
        print("  vol_alto:", d.vol_alto.value_counts(dropna=False).to_dict())
        print("  barras fora do continuo (>=fim_continuo):", int((b.index.time >= pd.Timestamp('18:25').time()).sum()),
              "| ultima barra max hora:", b.index.time.max())
