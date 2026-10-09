"""Rodada 5: filtros de VOLUME sobre a base v2 (robo M15 + MMS17x34 close a favor), protocolo do dono.

A = os 10 PIORES dias da base v2 no IS; B = 10 outros dias ruins sorteados; C = 10 dias bons sorteados.
Passa A->B/C: melhora B e B+C > 0. IS: melhora total E pts/op. OOS: idem.
Tudo medido na barra de confirmacao (M15 fechada), real_volume do WIN (validado como real).
"""
import numpy as np
import pandas as pd
import melhora_mm as mm
import confirma

FILTRO_MM = "MMS17x34 close: rápida do lado"


def base_v2(per):
    b, f, c = mm.preparar(per)
    V = mm.variantes(b)
    f = f[mm.mascara(f, V[FILTRO_MM])].copy()
    return b, f, c


def indicadores(b):
    v = b.real_volume.astype(float); c, o, h, l = b.close, b.open, b.high, b.low
    x = pd.DataFrame(index=b.index)
    for n in (10, 20, 50):
        x[f"vrel{n}"] = v / v.rolling(n).mean().shift(1)
    hhmm = b.index.strftime("%H%M")
    x["vtod"] = v / v.groupby(hhmm).transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))
    x["vma5_20"] = v.rolling(5).mean() / v.rolling(20).mean()
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    for n in (5, 10, 20):
        x[f"obv{n}"] = np.sign(obv - obv.shift(n))
    mf = (((c - l) - (h - c)) / (h - l).replace(0, np.nan)).fillna(0) * v
    x["cmf20"] = np.sign(mf.rolling(20).sum() / v.rolling(20).sum())
    tp = (h + l + c) / 3
    dia = b.dia
    vwap = (tp * v).groupby(dia).cumsum() / v.groupby(dia).cumsum()
    x["vwap"] = np.sign(c - vwap)
    x["vwap_dist"] = (c - vwap) / b.atr
    acum = v.groupby(dia).cumsum()
    x["dia_rel"] = acum / acum.groupby(hhmm).transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))
    x["corpo"] = np.sign(c - o)
    return x


def variantes(f, x):
    p = f.pos.to_numpy(); L = f.lado.to_numpy()
    g = lambda col: x[col].to_numpy()[p]
    V = {}
    for n in (10, 20, 50):
        r = g(f"vrel{n}")
        for k in (1.0, 1.2, 1.5, 2.0): V[f"barra de confirmação vol > {k}x média {n}"] = r > k
        for k in (0.8, 1.0): V[f"barra de confirmação vol < {k}x média {n}"] = r < k
    r = g("vtod")
    for k in (1.0, 1.2, 1.5): V[f"vol da barra > {k}x o mesmo horário (20 dias)"] = r > k
    for k in (0.8, 1.0): V[f"vol da barra < {k}x o mesmo horário (20 dias)"] = r < k
    r = g("vma5_20")
    V["vol subindo (MM5 > MM20 do volume)"] = r > 1; V["vol caindo (MM5 < MM20 do volume)"] = r < 1
    for n in (5, 10, 20): V[f"OBV a favor em {n} barras"] = g(f"obv{n}") * L == 1
    V["CMF20 a favor"] = g("cmf20") * L == 1
    V["preço do lado da VWAP do dia"] = g("vwap") * L == 1
    d = g("vwap_dist") * L
    for k in (0.5, 1.0, 2.0): V[f"distância da VWAP a favor < {k} ATR"] = (d > 0) & (d < k)
    V["distância da VWAP a favor > 1 ATR"] = d > 1
    r = g("dia_rel")
    for k in (0.8, 1.0, 1.2): V[f"volume do dia até agora > {k}x o normal"] = r > k
    V["volume do dia até agora < 1x o normal"] = r < 1
    V["candle de confirmação a favor + vol > média 20"] = (g("corpo") * L == 1) & (g("vrel20") > 1)
    V["candle de confirmação a favor + vol < média 20"] = (g("corpo") * L == 1) & (g("vrel20") < 1)
    h4 = f.H04.to_numpy(); h5 = f.H05.to_numpy()
    for k in (0.8, 1.0): V[f"correção com vol < {k}x o do impulso"] = h4 < k
    V["correção com vol > 1,2x o do impulso"] = h4 > 1.2
    for k in (1.0, 1.5, 2.0): V[f"barra do fundo/topo com vol > {k}x (clímax)"] = h5 > k
    V["barra do fundo/topo com vol < 1x"] = h5 < 1
    return V


def main():
    b, f, cache = base_v2("pesquisa")
    x = indicadores(b)
    base_d, base_tr = mm.simular(f, cache)
    s = pd.Series(base_d)
    rng = np.random.default_rng(2027)
    A = s.sort_values().index[:10].to_numpy()
    resto_ruim = s[(s < 0) & (~s.index.isin(A))].index.to_numpy()
    B = rng.permutation(resto_ruim)[:10]; C = rng.permutation(s[s > 0].index.to_numpy())[:10]
    tot = lambda d, segs: sum(d.get(q, 0) for q in segs)
    bA, bB, bC = tot(base_d, A), tot(base_d, B), tot(base_d, C)
    print(f"BASE v2 IS: {len(base_tr)} ops, {np.mean(base_tr):+.1f}/op, total {sum(base_tr):+.0f}")
    print("A (10 piores):", [str(cache[q][0].date()) for q in A], f"total {bA:+.0f}")
    print("B:", [str(cache[q][0].date()) for q in B], f"total {bB:+.0f}")
    print("C:", [str(cache[q][0].date()) for q in C], f"total {bC:+.0f}", flush=True)
    V = variantes(f, x)
    rows = []
    for nome, k in V.items():
        d, _ = mm.simular(f, cache, k, segs=A)
        rows.append(dict(var=nome, mantem=k.mean(), dA=tot(d, A) - bA))
    ra = pd.DataFrame(rows).sort_values("dA", ascending=False)
    print(f"\nETAPA A: {len(ra)} variantes, melhoram A: {(ra.dA > 0).sum()}")
    top = ra.head(20).copy()
    for i, r in top.iterrows():
        k = V[r["var"]]
        dB, _ = mm.simular(f, cache, k, segs=B); dC, _ = mm.simular(f, cache, k, segs=C)
        top.loc[i, "dB"] = tot(dB, B) - bB; top.loc[i, "dC"] = tot(dC, C) - bC
    top["passa_BC"] = (top.dB > 0) & (top.dB + top.dC > 0)
    pd.set_option("display.width", 220)
    print(top.round(2).to_string(index=False), flush=True)
    bo, fo, co = base_v2("reserva"); xo = indicadores(bo); Vo = variantes(fo, xo)
    _, oos_base = mm.simular(fo, co)
    fin = []
    for r in top[top.passa_BC].itertuples():
        _, tr = mm.simular(f, cache, V[r.var])
        eq = np.cumsum(tr); dd = (np.maximum.accumulate(eq) - eq).max()
        lin = dict(var=r.var, n_IS=len(tr), op_IS=np.mean(tr), total_IS=sum(tr), dd_IS=dd,
                   passa_IS=sum(tr) > sum(base_tr) and np.mean(tr) > np.mean(base_tr))
        if lin["passa_IS"]:
            _, to = mm.simular(fo, co, Vo[r.var])
            eq = np.cumsum(to); ddo = (np.maximum.accumulate(eq) - eq).max()
            lin.update(n_OOS=len(to), op_OOS=np.mean(to), total_OOS=sum(to), dd_OOS=ddo,
                       passa_OOS=sum(to) > sum(oos_base) and np.mean(to) > np.mean(oos_base))
        fin.append(lin)
    eq = np.cumsum(base_tr); ddb = (np.maximum.accumulate(eq) - eq).max()
    eq = np.cumsum(oos_base); ddbo = (np.maximum.accumulate(eq) - eq).max()
    print(f"\nBASE v2  IS: n {len(base_tr)} {np.mean(base_tr):+.1f}/op total {sum(base_tr):+.0f} DD {ddb:.0f} | "
          f"OOS: n {len(oos_base)} {np.mean(oos_base):+.1f}/op total {sum(oos_base):+.0f} DD {ddbo:.0f}")
    fin = pd.DataFrame(fin); print(fin.round(1).to_string(index=False))
    pd.to_pickle(dict(ra=ra, top=top, fin=fin), confirma.PER["reserva"]["out"] + "melhora_vol.pkl")


if __name__ == "__main__":
    main()
