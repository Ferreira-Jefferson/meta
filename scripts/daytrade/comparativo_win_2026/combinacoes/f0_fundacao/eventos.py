"""Tabela de eventos -> eventos.parquet: uma linha por ENTRADA de cada estrategia (resultados/<nome>.csv).

Colunas:
  estrategia, entrada (Timestamp), t_entrada_ms, saida, lado, preco_entrada, preco_saida, motivo, pontos, rs
  linha_voto            : barra M1 (abertura) cujos votos foram lidos = ultima M1 FECHADA antes da entrada
                          (abertura <= floor(entrada, 1min) - 1min). voto_mesmo_dia = 0 se essa barra e' do pregao anterior.
  <E>.voto/.forca/.posicao (e .ret) das 6 estrategias nessa linha (a propria inclusa).
  favor / contra / neutro : quantas das OUTRAS 5 votam lado / -lado / 0 nessa linha.
  (Win e Win_c1 tem voto identico -> para essas duas, 1 das 5 "outras" e' a gemea; ver favor_sem_gemea etc.)
  Contexto (so' dados fechados antes da entrada):
    hora (decimal), dow (0 = segunda), atr_m5 (media simples de 14 TR da ultima M5 fechada, como o Win),
    atr_d1 (14 D1 fechadas, como o Deslocamento), abertura (1a M1 do dia), amplitude_dia (max-min das M1 fechadas do
    dia ate' a linha_voto), dist_abertura_atr_m5 / dist_abertura_atr_d1 = (preco_entrada - abertura) / ATR (sinal do preco,
    nao do lado).
  Excursoes nos ticks (pontos, >= 0, a favor = mfe, contra = mae), do tick da entrada:
    mfe_saida / mae_saida  : ate' o tick da saida original (inclusive; saida em outro dia -> ate' o fim do pregao);
    mfe_1750 / mae_1750    : ate' o ultimo tick antes de 17:50 (NaN se a entrada for >= 17:50).

Uso: python eventos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(AQUI))
import dados as D  # noqa: E402
import port_win as PW  # noqa: E402
import port_deslocamento as PD  # noqa: E402
from votos import ESTRATEGIAS, ARQ as ARQ_VOTOS  # noqa: E402
from saida import _ticks  # noqa: E402

ARQ = AQUI / "eventos.parquet"
GEMEA = {"Win": "Win_c1", "Win_c1": "Win"}


def carrega_entradas() -> pd.DataFrame:
    fs = []
    for nm in ESTRATEGIAS:
        t = pd.read_csv(BASE / "resultados" / f"{nm}.csv")
        fs.append(t)
    df = pd.concat(fs, ignore_index=True)
    df["entrada"] = pd.to_datetime(df.entrada, format="mixed")
    df["saida"] = pd.to_datetime(df.saida, format="mixed")
    df["t_entrada_ms"] = df.entrada.values.astype("datetime64[ms]").astype(np.int64)
    df["t_saida_ms"] = df.saida.values.astype("datetime64[ms]").astype(np.int64)
    return df.drop(columns=["qtd"]).sort_values(["entrada", "estrategia"], kind="stable").reset_index(drop=True)


def contexto(ev: pd.DataFrame, linha: pd.DatetimeIndex) -> pd.DataFrame:
    m1 = D.m1()
    # ATR M5 (como o Win) da ultima M5 fechada ate' o fim da linha_voto
    m5 = PW._ohlc(m1, "5min")
    h, l, c = (m5[k].to_numpy(float) for k in ("high", "low", "close"))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc))); tr[0] = np.nan
    atr5 = pd.Series(tr).rolling(14).mean().to_numpy()
    fim5 = (m5.index + pd.Timedelta(minutes=5)).values
    k = np.searchsorted(fim5, (linha + pd.Timedelta(minutes=1)).values, "right") - 1
    out = pd.DataFrame(index=ev.index)
    out["atr_m5"] = np.where(k >= 0, atr5[np.clip(k, 0, None)], np.nan)
    d1 = PD.d1_de(m1)
    dia = ev.entrada.dt.date
    atrd = {d: PD.atr_d1(d1, d, 14) for d in dia.unique()}
    out["atr_d1"] = dia.map(atrd).astype(float)
    # abertura e amplitude do dia ate' a linha_voto (so' barras do mesmo dia)
    g = m1.groupby(m1.index.date)
    ab = g.open.first()
    out["abertura"] = dia.map(ab).astype(float)
    hi_c = g.high.cummax(); lo_c = g.low.cummin()
    mesmo = linha.date == dia.values
    li = pd.Index(m1.index).get_indexer(linha)
    out["amplitude_dia"] = np.where(mesmo & (li >= 0), hi_c.to_numpy()[li] - lo_c.to_numpy()[li], np.nan)
    out["dist_abertura_atr_m5"] = (ev.preco_entrada - out.abertura) / out.atr_m5
    out["dist_abertura_atr_d1"] = (ev.preco_entrada - out.abertura) / out.atr_d1
    out["hora"] = ev.entrada.dt.hour + ev.entrada.dt.minute / 60 + ev.entrada.dt.second / 3600
    out["dow"] = ev.entrada.dt.dayofweek
    return out


def excursoes(ev: pd.DataFrame) -> pd.DataFrame:
    res = np.full((len(ev), 4), np.nan)
    d0 = ev.t_entrada_ms.to_numpy() // 86_400_000 * 86_400_000
    for dd in np.unique(d0):
        sel = np.flatnonzero(d0 == dd)
        t, p = _ticks(pd.Timestamp(int(dd), unit="ms").date())
        i0 = np.searchsorted(t, ev.t_entrada_ms.to_numpy()[sel], "left")
        i1 = np.searchsorted(t, ev.t_saida_ms.to_numpy()[sel], "right")      # inclusive; outro dia -> len(t)
        iz = int(np.searchsorted(t, dd + (17 * 60 + 50) * 60000, "left"))
        for q, i in enumerate(sel):
            lado, pe = ev.lado.iat[i], ev.preco_entrada.iat[i]
            a = int(i0[q])
            for col, b in ((0, int(i1[q])), (2, iz)):
                if b > a:
                    x = lado * (p[a:b] - pe)
                    res[i, col] = max(0.0, x.max()); res[i, col + 1] = max(0.0, -x.min())
    return pd.DataFrame(res, index=ev.index, columns=["mfe_saida", "mae_saida", "mfe_1750", "mae_1750"])


def gerar():
    ev = carrega_entradas()
    V = pd.read_parquet(ARQ_VOTOS)
    alvo = ev.entrada.dt.floor("min") - pd.Timedelta(minutes=1)
    k = np.searchsorted(V.index.values, alvo.values, "right") - 1
    if (k < 0).any():
        raise SystemExit(f"{int((k < 0).sum())} entradas sem linha de voto")
    linha = V.index[k]
    ev["linha_voto"] = linha
    ev["voto_mesmo_dia"] = (linha.date == ev.entrada.dt.date.values).astype(int)
    cols = [c for c in V.columns if c.split(".")[1] in ("voto", "forca", "posicao", "ret")]
    vv = V[cols].iloc[k].reset_index(drop=True)
    ev = pd.concat([ev, vv], axis=1)
    lado = ev.lado.to_numpy()
    for tag, gem in (("", True), ("_sem_gemea", False)):
        fav = np.zeros(len(ev), int); con = np.zeros(len(ev), int); neu = np.zeros(len(ev), int)
        for nm in ESTRATEGIAS:
            outra = (ev.estrategia != nm).to_numpy().copy()
            if not gem:
                outra &= (ev.estrategia.map(GEMEA) != nm).to_numpy()
            v = ev[f"{nm}.voto"].to_numpy()
            fav += outra & (v == lado); con += outra & (v == -lado); neu += outra & (v == 0)
        ev["favor" + tag], ev["contra" + tag], ev["neutro" + tag] = fav, con, neu
    ev = pd.concat([ev, contexto(ev, linha), excursoes(ev)], axis=1)
    ev.to_parquet(ARQ)
    print(f"salvo {ARQ} {ev.shape}", flush=True)
    # conferencia: a propria estrategia votava no lado da entrada?
    for nm in ESTRATEGIAS:
        e = ev[ev.estrategia == nm]
        print(f"  {nm:24s} n={len(e):4d}  proprio voto = lado {100 * (e[f'{nm}.voto'] == e.lado).mean():5.1f}%"
              f"  (forca media {e[f'{nm}.forca'].mean():.2f})  mfe_saida med {e.mfe_saida.median():.0f}"
              f"  mae_saida med {e.mae_saida.median():.0f}", flush=True)
    return ev


if __name__ == "__main__":
    gerar()
