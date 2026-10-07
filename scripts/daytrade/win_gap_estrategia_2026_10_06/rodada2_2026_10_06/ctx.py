# -*- coding: utf-8 -*-
"""Contexto por pregao da rodada 2: barras M5 (sem leilao), gap, volume do call, ATR de dias anteriores.

Tudo causal: o que a estrategia usa no pregao D vem de D-1 para tras (dentro das 6 meses; nada antes
de 2026-04-06 e' lido). `atr_prev` = media da amplitude (max-min) dos ate' 10 pregoes ANTERIORES a D
(exige >= 3). `vol_alto` vem de `dados.carrega` (mediana movel de ate' 60 dias, `shift(1)`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import dados  # noqa: E402  (round 1; poe src/ no path)

INI, FIM = "2026-04-06", "2026-10-05"
ATR_JANELA, ATR_MIN = 10, 3
M5 = 5 * 60_000
ABERTURA_MS = 9 * 3_600_000

#: dias que a tabela de fases marca como completados pelo M1 / sem 1o negocio -- decisao em CHECAGEM_DADOS.md
EXCLUIR_EXTRA: dict[str, str] = {
    "2026-05-06": "ticks_faltando_09:16-09:23(janela de ordem)",
    "2026-08-10": "ticks_faltando_10:00-10:08(posicao aberta)",
    "2026-09-24": "ticks_so_comecam_09:14(sem 1a barra nem janela de ordem)",
}


def amplitudes_diarias(b: pd.DataFrame) -> pd.Series:
    g = b.groupby(b.index.normalize())
    return g["high"].max() - g["low"].min()


def calcula_atr_prev(amp: pd.Series, dias_validos: list) -> dict:
    """atr_prev[D] = media das amplitudes dos <=10 dias validos ANTERIORES a D (nunca inclui D)."""
    out, hist = {}, []
    for d in sorted(dias_validos):
        out[d] = float(np.mean(hist[-ATR_JANELA:])) if len(hist) >= ATR_MIN else float("nan")
        hist.append(float(amp.loc[pd.Timestamp(d)]))
    return out


def constroi():
    """(barras M5 IS dos dias elegiveis, tabela de dias IS, {date: dict de contexto})."""
    b, d = dados.carrega("2026")
    ini, fim = pd.Timestamp(INI), pd.Timestamp(FIM)
    dj = d[(d.index >= ini) & (d.index <= fim)].copy()
    for dia, motivo in EXCLUIR_EXTRA.items():
        dj.loc[pd.Timestamp(dia), "excluir"] = True
        dj.loc[pd.Timestamp(dia), "motivo_excl"] = motivo
    # volume do call de D-1 so' conta se D-1 esta DENTRO da janela (medido por tick): o 1o pregao, cujo D-1
    # e' pre-janela (proxy), nao usa filtro de volume
    prev_proxy = d["proxy"].astype(bool).shift(1).reindex(dj.index)
    dj.loc[prev_proxy.fillna(True).to_numpy(), "vol_alto"] = np.nan
    ok = dj[~dj.excluir]
    bj = b[b.index.normalize().isin(ok.index)]
    amp = amplitudes_diarias(bj)
    atr = calcula_atr_prev(amp, list(ok.index))
    ctx = {}
    for dia, r in ok.iterrows():
        g = bj[bj.index.normalize() == dia]
        b1 = g.iloc[0]
        ctx[dia.date()] = dict(
            gap=float(r.gap), vol_alto=bool(r.vol_alto == 1.0), prev_call=float(r.call_preco - 0) if False else None,
            atr_prev=atr[dia], o1=float(b1.open), h1=float(b1.high), l1=float(b1.low), c1=float(b1.close),
            t1=int(g.index[0].hour * 3_600_000 + g.index[0].minute * 60_000))
    # preco do call de D-1 (alvo "fechar o gap"): coluna call_preco do dia anterior na tabela completa
    cp = d["call_preco"].shift(1)
    for dia in list(ctx):
        ctx[dia]["prev_call"] = float(cp.loc[pd.Timestamp(dia)])
    return bj, dj, ctx


def barras_do_dia(bj: pd.DataFrame, dia) -> dict:
    g = bj[bj.index.normalize() == pd.Timestamp(dia)]
    st = (g.index.hour * 3_600_000 + g.index.minute * 60_000).to_numpy().astype("int64")
    return dict(st=st, o=g.open.to_numpy(float), h=g.high.to_numpy(float), l=g.low.to_numpy(float), c=g.close.to_numpy(float))
