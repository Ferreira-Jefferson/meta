"""Rodada 6: osciladores (sobrecompra/sobrevenda, momento, forca de tendencia) sobre a base v2, protocolo do dono.

A = 10 dias ruins SORTEADOS da base v2 (nao os piores: os piores so premiam filtro que corta operacao, rodada 5);
B = outros 10 ruins sorteados; C = 10 bons sorteados. Top 20 de A -> B/C -> IS (total E pts/op) -> OOS.
Conferencia: todas as variantes no IS inteiro, com OOS e vizinhos dos que passarem.
Leitura na barra de confirmacao (M15 fechada). Compra usa o limiar; venda usa o espelho (100 - x, ou -x).
"""
import numpy as np
import pandas as pd
import melhora_mm as mm
import melhora_vol as mv
import confirma


def rsi(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def estoc(b, n, s=3):
    ll = b.low.rolling(n).min(); hh = b.high.rolling(n).max()
    k = 100 * (b.close - ll) / (hh - ll).replace(0, np.nan)
    k = k.rolling(s).mean(); return k, k.rolling(3).mean()


def adx(b, n=14):
    up = b.high.diff(); dn = -b.low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([b.high - b.low, (b.high - b.close.shift()).abs(), (b.low - b.close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=b.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(mdm, index=b.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def variantes(b, f):
    p = f.pos.to_numpy(); L = f.lado.to_numpy(); c = b.close
    at = lambda s: np.asarray(s)[p]
    V = {}
    def osc0_100(nome, x):  # oscilador 0-100: "compra" le x, "venda" le 100-x
        xv = at(x); xm = np.where(L == 1, xv, 100 - xv)
        for k in (70, 80): V[f"{nome} não esticado (<{k})"] = xm < k
        for k in (30, 40, 50): V[f"{nome} recuado (<{k})"] = xm < k
        V[f"{nome} acima de 50 (momento)"] = xm > 50
        V[f"{nome} subindo a favor"] = np.sign(at(x.diff(2))) * L == 1
    for n in (2, 7, 9, 14, 21): osc0_100(f"IFR{n}", rsi(c, n))
    for n in (5, 14):
        k, d = estoc(b, n); osc0_100(f"Estoc{n}", k)
        V[f"Estoc{n} %K>%D a favor"] = np.sign(at(k - d)) * L == 1
    k60 = rsi(c.resample("60min").last().dropna(), 14); k60.index = k60.index + pd.Timedelta("60min")
    osc0_100("IFR14 do H1", k60.reindex(b.index, method="ffill"))
    tp = (b.high + b.low + c) / 3
    cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True))
    cm = at(cci) * L
    V["CCI20 a favor (>0)"] = cm > 0
    V["CCI20 não esticado (<100)"] = cm < 100
    V["CCI20 entre 0 e 100"] = (cm > 0) & (cm < 100)
    V["CCI20 recuado (<-100)"] = cm < -100
    ema = lambda s, n: s.ewm(span=n, adjust=False).mean()
    macd = ema(c, 12) - ema(c, 26); sig = ema(macd, 9); hist = macd - sig
    V["MACD acima de zero a favor"] = np.sign(at(macd)) * L == 1
    V["MACD histograma a favor"] = np.sign(at(hist)) * L == 1
    V["MACD histograma crescendo a favor"] = np.sign(at(hist.diff())) * L == 1
    for n in (5, 10, 20): V[f"ROC{n} a favor"] = np.sign(at(c - c.shift(n))) * L == 1
    a, pdi, mdi = adx(b)
    for k in (15, 20, 25, 30): V[f"ADX14 > {k}"] = at(a) > k
    V["ADX14 < 20 (sem tendência)"] = at(a) < 20
    V["ADX14 subindo"] = at(a.diff(2)) > 0
    V["+DI/-DI a favor"] = np.sign(at(pdi - mdi)) * L == 1
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(); pb = (c - (mid - 2 * sd)) / (4 * sd)
    pbm = np.where(L == 1, at(pb), 1 - at(pb))
    for k in (0.8, 1.0): V[f"Bollinger %B não esticado (<{k})"] = pbm < k
    V["Bollinger %B na metade a favor (>0,5)"] = pbm > 0.5
    V["Bollinger largura crescendo"] = at((4 * sd).diff(3)) > 0
    st = (c - ema(c, 21)) / b.atr
    sm = at(st) * L
    for k in (0.5, 1.0, 2.0): V[f"distância da MME21 < {k} ATR"] = sm < k
    mf_tp = tp * b.real_volume
    pos = mf_tp.where(tp > tp.shift(), 0).rolling(14).sum(); neg = mf_tp.where(tp < tp.shift(), 0).rolling(14).sum()
    osc0_100("MFI14", 100 - 100 / (1 + pos / neg.replace(0, np.nan)))
    return V


def dd(tr):
    eq = np.cumsum(tr); return (np.maximum.accumulate(eq) - eq).max() if len(tr) else np.nan


def main():
    b, f, cache = mv.base_v2("pesquisa"); V = variantes(b, f)
    bo, fo, co = mv.base_v2("reserva"); Vo = variantes(bo, fo)
    base_d, base_tr = mm.simular(f, cache); _, oos = mm.simular(fo, co)
    s = pd.Series(base_d); rng = np.random.default_rng(2028)
    ruins = rng.permutation(s[s < 0].index.to_numpy()); A, B = ruins[:10], ruins[10:20]
    C = rng.permutation(s[s > 0].index.to_numpy())[:10]
    tot = lambda d, segs: sum(d.get(q, 0) for q in segs)
    bA, bB, bC = tot(base_d, A), tot(base_d, B), tot(base_d, C)
    print(f"BASE v2 IS {len(base_tr)} ops {np.mean(base_tr):+.1f}/op total {sum(base_tr):+.0f} DD {dd(base_tr):.0f} | "
          f"OOS {len(oos)} ops {np.mean(oos):+.1f}/op total {sum(oos):+.0f} DD {dd(oos):.0f}")
    print(f"A {bA:+.0f}  B {bB:+.0f}  C {bC:+.0f}; variantes {len(V)}", flush=True)
    rows = []
    for nome, k in V.items():
        d, _ = mm.simular(f, cache, k, segs=A); rows.append(dict(var=nome, mantem=k.mean(), dA=tot(d, A) - bA))
    ra = pd.DataFrame(rows).sort_values("dA", ascending=False)
    top = ra.head(20).copy()
    for i, r in top.iterrows():
        k = V[r["var"]]; dB, _ = mm.simular(f, cache, k, segs=B); dC, _ = mm.simular(f, cache, k, segs=C)
        top.loc[i, "dB"] = tot(dB, B) - bB; top.loc[i, "dC"] = tot(dC, C) - bC
    top["passa_BC"] = (top.dB > 0) & (top.dB + top.dC > 0)
    fin = []
    for r in top[top.passa_BC].itertuples():
        _, tr = mm.simular(f, cache, V[r.var])
        lin = dict(var=r.var, n_IS=len(tr), op_IS=np.mean(tr), total_IS=sum(tr), dd_IS=dd(tr),
                   passa_IS=sum(tr) > sum(base_tr) and np.mean(tr) > np.mean(base_tr))
        if lin["passa_IS"]:
            _, to = mm.simular(fo, co, Vo[r.var])
            lin.update(n_OOS=len(to), op_OOS=np.mean(to), total_OOS=sum(to), dd_OOS=dd(to),
                       passa_OOS=sum(to) > sum(oos) and np.mean(to) > np.mean(oos))
        fin.append(lin)
    pd.set_option("display.width", 230)
    print(f"\nETAPA A: melhoram {(ra.dA > 0).sum()} de {len(ra)}"); print(top.round(2).to_string(index=False))
    print("\nFUNIL -> IS/OOS:"); print(pd.DataFrame(fin).round(1).to_string(index=False), flush=True)
    full = []
    for nome, k in V.items():
        _, tr = mm.simular(f, cache, k); _, to = mm.simular(fo, co, Vo[nome])
        full.append(dict(var=nome, mantem=k.mean(), n_IS=len(tr), op_IS=np.mean(tr), total_IS=sum(tr), dd_IS=dd(tr),
                         n_OOS=len(to), op_OOS=np.mean(to) if to else np.nan, total_OOS=sum(to), dd_OOS=dd(to)))
    full = pd.DataFrame(full)
    full["passa_IS"] = (full.total_IS > sum(base_tr)) & (full.op_IS > np.mean(base_tr))
    full["passa_OOS"] = full.passa_IS & (full.total_OOS > sum(oos)) & (full.op_OOS > np.mean(oos))
    print("\nCONFERENCIA IS inteiro (passa_IS):"); print(full[full.passa_IS].sort_values("total_IS", ascending=False).round(1).to_string(index=False))
    pd.to_pickle(dict(ra=ra, top=top, fin=pd.DataFrame(fin), full=full, A=A, B=B, C=C), confirma.PER["reserva"]["out"] + "melhora_osc.pkl")


if __name__ == "__main__":
    main()
