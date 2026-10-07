# -*- coding: utf-8 -*-
"""Ticks continuos do WIN$N por pregao (2026-04-06..2026-10-05) -> cache compacto + reconciliacao.

Fonte: data/comparativo_win_2026/ticks/<dia>.npz (t ms em BRT rotulado UTC, p pontos, v). Filtro:
`filtra_ticks_continuo` (tira leilao de abertura e tudo >= fim do pregao da grade, call incluso).
Cache: so' os pontos em que o preco MUDA (a ordem-limite/stop/alvo so' dependem do caminho de
preco): `t` = ms desde 00:00 do dia (int32), `p` int32, e o ultimo tick do dia sempre mantido.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from market_data_intraday.win_sem_leiloes import filtra_ticks_continuo  # noqa: E402

AQUI = Path(__file__).resolve().parent
CACHE = AQUI / "cache"
TICKS = ROOT / "data" / "comparativo_win_2026" / "ticks"
INI, FIM = "2026-04-06", "2026-10-05"


def dias_is() -> list[pd.Timestamp]:
    d = pd.read_csv(ROOT / "data" / "win_fases_pregao_6m.csv", sep=";", encoding="utf-8-sig", parse_dates=["data"])
    return [x for x in d["data"] if pd.Timestamp(INI) <= x <= pd.Timestamp(FIM)]


def prepara(dia: pd.Timestamp) -> dict:
    z = np.load(TICKS / f"{dia.date()}.npz")
    t0, p0, v0 = z["t"], z["p"], z["v"]
    t, p, v = filtra_ticks_continuo(t0, p0, v0)
    ini_dia = int(dia.value // 10**6)
    rel = (t.astype("int64") - ini_dia)
    chg = np.r_[True, p[1:] != p[:-1]]
    chg[-1] = True
    out = dict(t=rel[chg].astype("int32"), p=p[chg].astype("int32"))
    np.savez(CACHE / f"{dia.date()}.npz", **out)
    return dict(dia=dia, n_bruto=len(t0), n_cont=len(t), n_cache=int(chg.sum()),
                t_ini=int(rel[0]), p_ini=int(p[0]), t_fim=int(rel[-1]), p_fim=int(p[-1]),
                p_max=int(p.max()), p_min=int(p.min()))


def carrega(dia) -> tuple[np.ndarray, np.ndarray]:
    z = np.load(CACHE / f"{pd.Timestamp(dia).date()}.npz")
    return z["t"], z["p"]


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor, as_completed
    ds = dias_is()
    linhas = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        fut = {ex.submit(prepara, d): d for d in ds}
        for f in as_completed(fut):
            r = f.result(); linhas.append(r)
            print(r["dia"].date(), r["n_bruto"], r["n_cont"], r["n_cache"], flush=True)
    pd.DataFrame(linhas).sort_values("dia").to_csv(AQUI / "ticks_resumo.csv", sep=";", index=False)
