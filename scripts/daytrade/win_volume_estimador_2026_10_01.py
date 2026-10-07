"""Compara ESTIMADORES da linha de base do WinVolumeRazao (mediana, aparada, geometrica, ponderada
pela recencia, com ajuste de nivel) para achar a razao mais "honesta" do volume.

Proposito da razao: dizer quanto o volume desta vela esta' acima/abaixo do normal PARA ESTE DIA DA
SEMANA E HORARIO. Uma razao honesta tem (1) nivel sem vies e sem deriva (mediana mensal ~1 e ~15% das
barras fora de cada linha, em qualquer mes), (2) pouca dispersao (a base explica o volume), (3) poder
de antecipar a volatilidade (range da proxima barra / normal do horario).

Uso: python win_volume_estimador_2026_10_01.py ajuste_teste | vault
Grupos: (dia da semana, hora). Todos estritos (precisam de N ocorrencias anteriores validas, volume>0).
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
RESERVA1 = ["2026-01", "2026-02", "2026-03", "2025-09", "2025-10", "2025-11", "2025-12"]
VAULT = [f"{a}-{m:02d}" for a in (2022, 2023, 2024) for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 9)]
LO, HI = 0.65, 1.35


def peso(n: int, meia_vida: float | None) -> np.ndarray:
    idade = np.arange(n, 0, -1, dtype=float)  # coluna 0 = mais antiga (idade n), ultima = mais recente (idade 1)
    return np.ones(n) if meia_vida is None else 0.5 ** ((idade - 1) / meia_vida)


def est_mediana(M, p):  # M: (k, n) janelas; p: pesos
    if np.allclose(p, p[0]):
        return np.median(M, axis=1)
    o = np.argsort(M, axis=1)
    Ms, Ps = np.take_along_axis(M, o, 1), p[o]
    c = np.cumsum(Ps, axis=1)
    idx = (c >= 0.5 * c[:, -1:]).argmax(axis=1)
    return Ms[np.arange(len(M)), idx]


def est_aparada(M, p):
    return np.sort(M, axis=1)[:, 1:-1].mean(axis=1)


def est_media(M, p):
    return (M * p).sum(axis=1) / p.sum()


def est_geom(M, p):
    return np.exp((np.log(M) * p).sum(axis=1) / p.sum())


ESTIMADORES = {
    "mediana": est_mediana, "aparada": est_aparada, "media": est_media, "geometrica": est_geom,
}


def base_grupo(d: pd.DataFrame, n: int, est: str, meia_vida: float | None) -> pd.Series:
    """Baseline por barra: estimador das n ocorrencias ANTERIORES do mesmo (dia da semana, hora)."""
    chave = d.index.dayofweek * 10000 + d.index.hour * 60 + d.index.minute
    v = d["vol"].where(d["vol"] > 0)
    out = pd.Series(np.nan, index=d.index)
    p = peso(n, meia_vida)
    f = ESTIMADORES[est]
    for _, idx in pd.Series(np.arange(len(d))).groupby(chave):
        pos = idx.to_numpy()
        x = v.iloc[pos].dropna()
        if len(x) <= n:
            continue
        a = x.to_numpy()
        win = np.lib.stride_tricks.sliding_window_view(a[:-1], n)  # janela de n ocorrencias antes de cada a[i], i>=n
        out.loc[x.index[n:]] = f(win, p)
    return out


def ajuste_nivel(d: pd.DataFrame, base: pd.Series, sessoes: int = 5, lim: tuple = (0.7, 1.4)) -> pd.Series:
    """Corrige a deriva: multiplica a base pela mediana (clip) das razoes medianas das ULTIMAS `sessoes` sessoes."""
    r0 = d["vol"] / base
    dia = pd.Series(d.index.date, index=d.index)
    med = r0.groupby(dia).median()  # mediana da razao de cada sessao
    nivel = med.shift(1).rolling(sessoes, min_periods=sessoes).median().clip(*lim)
    return base * dia.map(nivel).to_numpy()


def avaliar(d, razao, meses, rng_norm_alvo) -> dict:
    mes = razao.index.strftime("%Y-%m")
    sel = np.isin(mes, meses)
    r = razao[sel].dropna()
    lr = np.log(r.where(r > 0).dropna())
    fr_lo = r.groupby(r.index.strftime("%Y-%m")).apply(lambda x: (x < LO).mean())
    fr_hi = r.groupby(r.index.strftime("%Y-%m")).apply(lambda x: (x > HI).mean())
    med_mes = r.groupby(r.index.strftime("%Y-%m")).median()
    x = pd.concat([razao, rng_norm_alvo], axis=1, keys=["r", "a"])[sel].dropna()
    return {
        "n": len(r), "sd_log": lr.std(), "vies_log": lr.median(),
        "lo%": (r < LO).mean() * 100, "hi%": (r > HI).mean() * 100,
        "dev_mes": float(((fr_lo - .15).abs().mean() + (fr_hi - .15).abs().mean()) / 2 * 100),
        "med_mes_dp": float(med_mes.std()), "spearman": x.r.rank().corr(x.a.rank()),
    }


def main(fase: str) -> None:
    d = w.ler_m5_volume("M5")
    rng = d.high - d.low
    chave = d.index.dayofweek * 10000 + d.index.hour * 60 + d.index.minute
    norm = rng.groupby(chave).transform(lambda x: x.shift(1).rolling(8, min_periods=8).median())
    mesmo_dia = pd.Series(d.index.date, index=d.index).shift(-1) == pd.Series(d.index.date, index=d.index)
    alvo = (rng.shift(-1) / norm).where(mesmo_dia.to_numpy())

    cand = [("mediana N=10 (atual)", 10, "mediana", None, False)]
    for n in (6, 15, 20):
        cand.append((f"mediana N={n}", n, "mediana", None, False))
    for n in (10, 20):
        cand += [(f"aparada N={n}", n, "aparada", None, False), (f"geometrica N={n}", n, "geometrica", None, False),
                 (f"media N={n}", n, "media", None, False)]
    for h in (4, 8):
        cand += [(f"mediana pond. N=20 meia-vida {h}", 20, "mediana", h, False),
                 (f"geometrica pond. N=20 meia-vida {h}", 20, "geometrica", h, False)]
    cand += [("mediana N=10 + ajuste nivel", 10, "mediana", None, True),
             ("mediana pond. N=20 mv 8 + ajuste nivel", 20, "mediana", 8, True),
             ("geometrica pond. N=20 mv 8 + ajuste nivel", 20, "geometrica", 8, True)]

    grupos = {"ajuste": AJUSTE, "teste": TESTE} if fase == "ajuste_teste" else {"reserva1": RESERVA1, "VAULT": VAULT}
    linhas = []
    for nome, n, est, h, aj in cand:
        base = base_grupo(d, n, est, h)
        if aj:
            base = ajuste_nivel(d, base)
        razao = (d["vol"] / base).where(base > 0)
        for g, ms in grupos.items():
            linhas.append({"estimador": nome, "periodo": g, **avaliar(d, razao, ms, alvo)})
        print(f"ok {nome}", flush=True)
    df = pd.DataFrame(linhas)
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 200)
    for g in grupos:
        t = df[df.periodo == g].drop(columns="periodo").set_index("estimador").round(3)
        print(f"\n== {g}\n{t}", flush=True)
    df.to_csv(Path(__file__).with_name(f"win_volume_estimador_2026_10_01_{fase}.csv"), index=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ajuste_teste")
