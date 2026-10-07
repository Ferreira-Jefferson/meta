"""Hipotese B: o que a razao de volume do WIN rastreia -- volatilidade, direcao ou nada?
Ajuste: 2026-06/07/08. Teste: 2026-09/05/04. Nada anterior a 2026-04 entra na analise (so' aquecimento da razao)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from win_volume_razao_py import ler_m5_volume, razao_volume  # noqa: E402

AJUSTE = ["2026-06", "2026-07", "2026-08"]
TESTE = ["2026-09", "2026-05", "2026-04"]
RNG = np.random.default_rng(7)
NB = 400
FAIXAS = [(0, 0.7), (0.7, 1.0), (1.0, 1.5), (1.5, 1e9)]
NOMES = ["<0,7", "0,7-1,0", "1,0-1,5", ">=1,5"]


def spearman(x, y):
    return pd.Series(x).rank().corr(pd.Series(y).rank())


def boot_dia(df, fn, nb=NB):
    """fn(df)->float; reamostra DIAS com reposicao."""
    g = {k: v for k, v in df.groupby("dia")}
    chaves = list(g)
    out = []
    for _ in range(nb):
        s = RNG.choice(len(chaves), len(chaves))
        out.append(fn(pd.concat([g[chaves[i]] for i in s])))
    return np.nanpercentile(out, [2.5, 97.5])


def preparar(tf="M5"):
    d = ler_m5_volume(tf)
    d["dia"] = d.index.normalize()
    d["hm"] = d.index.hour * 60 + d.index.minute
    d["dow"] = d.index.dayofweek
    d["rng"] = d["high"] - d["low"]
    # normalizador do range: mediana das 8 ocorrencias ANTERIORES do mesmo horario/dia da semana
    k = d["dow"] * 10000 + d["hm"]
    d["rng_n"] = d.groupby(k)["rng"].transform(lambda x: x.shift(1).rolling(8, min_periods=8).median())
    d["rn"] = d["rng"] / d["rng_n"]
    d["dir"] = np.sign(d["close"] - d["open"])
    d["corpo"] = (d["close"] - d["open"]).abs()
    # alvos: apenas barras t+1..t+h do MESMO dia
    for h in (1, 6):
        fut = sum(d["rng"].shift(-j) for j in range(1, h + 1))
        futn = sum(d["rng_n"].shift(-j) for j in range(1, h + 1))
        ok = d["dia"].shift(-h) == d["dia"]
        d[f"vol{h}"] = (fut / futn).where(ok)
    for h in (1, 3, 6):
        ret = d["close"].shift(-h) - d["open"].shift(-1)
        ok = d["dia"].shift(-h) == d["dia"]
        d[f"cont{h}"] = (ret * d["dir"]).where(ok & (d["dir"] != 0))
    return d


def mes(d, meses):
    return d[d.index.strftime("%Y-%m").isin(meses)]


def faixa_tab(df, col, alvo, titulo):
    lin = []
    for (lo, hi), nm in zip(FAIXAS, NOMES):
        s = df[(df[col] >= lo) & (df[col] < hi)].dropna(subset=[alvo])
        if len(s) < 5:
            lin.append((nm, len(s), np.nan, np.nan, np.nan))
            continue
        ic = boot_dia(s, lambda z: z[alvo].mean(), 200)
        lin.append((nm, len(s), s[alvo].mean(), ic[0], ic[1]))
    t = pd.DataFrame(lin, columns=["faixa", "n", "media", "ic_lo", "ic_hi"])
    print(f"\n{titulo}\n{t.round(3).to_string(index=False)}")


def nulo_spearman(df, col, alvo, nb=300):
    """embaralha a razao entre barras do MESMO horario."""
    s = df.dropna(subset=[col, alvo])
    obs = spearman(s[col], s[alvo])
    vals = []
    for _ in range(nb):
        r = s.groupby("hm")[col].transform(lambda x: RNG.permutation(x.to_numpy()))
        vals.append(spearman(r, s[alvo]))
    return obs, np.percentile(vals, [2.5, 97.5]), np.mean(np.abs(vals) >= abs(obs))


def main():
    d = preparar()
    dias_l = [1, 2, 3, 4, 6, 10, 20]
    for dias in dias_l:
        for modo in ("semana", "hora"):
            for agg in ("mediana", "media"):
                d[f"r_{dias}_{modo}_{agg}"] = razao_volume(d, dias, modo, agg)
    d["razao"] = d["r_2_semana_mediana"]
    aj, te = mes(d, AJUSTE), mes(d, TESTE)
    print(f"barras M5: ajuste {len(aj)} ({aj['dia'].nunique()} dias) | teste {len(te)} ({te['dia'].nunique()} dias)")

    # ---- 1) volatilidade (indicador padrao)
    print("\n=== 1) VOLATILIDADE (razao padrao Dias=2 semana mediana) ===")
    for nome, df in (("AJUSTE", aj), ("TESTE", te)):
        for a in ("vol1", "vol6"):
            s = df.dropna(subset=["razao", a])
            rho = spearman(s["razao"], s[a])
            ic = boot_dia(s, lambda z: spearman(z["razao"], z[a]), 200)
            o, nic, p = nulo_spearman(df, "razao", a)
            print(f"{nome} {a}: n={len(s)} rho={rho:.3f} IC95 dia [{ic[0]:.3f};{ic[1]:.3f}] nulo95 [{nic[0]:.3f};{nic[1]:.3f}] p_nulo={p:.3f}")
        faixa_tab(df, "razao", "vol1", f"{nome}: range prox. barra / mediana (1 = normal)")
        faixa_tab(df, "razao", "vol6", f"{nome}: range 6 prox. barras / mediana")

    # ---- 2) direcao / continuacao
    print("\n=== 2) DIRECAO (pontos de WIN a favor da direcao da barra t; >0 continua) ===")
    lim = aj["corpo"].median()
    print(f"corpo grande = |close-open| >= {lim:.0f} pts (mediana do AJUSTE)")
    for nome, df in (("AJUSTE", aj), ("TESTE", te)):
        for h in (1, 3, 6):
            faixa_tab(df, "razao", f"cont{h}", f"{nome}: continuidade t+1..t+{h}, todas as barras")
        for tam, cond in (("corpo GRANDE", df["corpo"] >= lim), ("corpo PEQUENO", df["corpo"] < lim)):
            faixa_tab(df[cond], "razao", "cont3", f"{nome}: continuidade t+1..t+3, {tam}")

    # ---- 3) variantes
    print("\n=== 3) VARIANTES: Spearman(razao, vol) em amostra COMUM (todas as variantes validas) ===")
    cols = [c for c in d.columns if c.startswith("r_")]
    rows = []
    comum_aj = aj.dropna(subset=cols + ["vol1", "vol6"])
    comum_te = te.dropna(subset=cols + ["vol1", "vol6"])
    print(f"amostra comum: ajuste n={len(comum_aj)}, teste n={len(comum_te)}")
    for c in cols:
        _, dias, modo, agg = c.split("_")
        rows.append(dict(dias=int(dias), modo=modo, agg=agg,
                         aj_v1=spearman(comum_aj[c], comum_aj["vol1"]), aj_v6=spearman(comum_aj[c], comum_aj["vol6"]),
                         te_v1=spearman(comum_te[c], comum_te["vol1"]), te_v6=spearman(comum_te[c], comum_te["vol6"])))
    v = pd.DataFrame(rows)
    v["aj_media"] = (v.aj_v1 + v.aj_v6) / 2
    v["te_media"] = (v.te_v1 + v.te_v6) / 2
    v = v.sort_values("aj_media", ascending=False)
    print(v.round(3).to_string(index=False))
    best = v.iloc[0]
    cb = f"r_{int(best['dias'])}_{best['modo']}_{best['agg']}"
    print(f"\nmelhor no ajuste: {cb}; padrao r_2_semana_mediana")
    for nome, df in (("AJUSTE", comum_aj), ("TESTE", comum_te)):
        for a in ("vol1", "vol6"):
            dif = lambda z, a=a: spearman(z[cb], z[a]) - spearman(z["razao"], z[a])
            ic = boot_dia(df, dif, 150)
            print(f"{nome} {a}: melhor - padrao = {dif(df):.3f} IC95 dia [{ic[0]:.3f};{ic[1]:.3f}]")

    # ---- 4) percentis (todas as barras dos meses de AJUSTE; teste so' confere)
    print("\n=== 4) PERCENTIS da razao padrao ===")
    for nome, df in (("AJUSTE", aj), ("TESTE", te)):
        q = df["razao"].dropna().quantile([.1, .2, .5, .8, .9])
        print(nome, {k: round(x, 2) for k, x in q.items()}, f"n={df['razao'].notna().sum()}")
    q20, q80 = aj["razao"].quantile([.2, .8])
    for nome, df in (("AJUSTE", aj), ("TESTE", te)):
        for a in ("vol1", "vol6"):
            lo = df[df["razao"] <= q20][a]
            hi = df[df["razao"] >= q80][a]
            print(f"{nome} {a}: quinto baixo (<={q20:.2f}) media={lo.mean():.3f} n={lo.count()} | quinto alto (>={q80:.2f}) media={hi.mean():.3f} n={hi.count()}")


if __name__ == "__main__":
    main()
