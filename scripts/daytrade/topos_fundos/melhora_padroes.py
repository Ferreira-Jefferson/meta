"""Rodadas 7-9: padroes de candle, de figura e combinados, sobre a base v2 (robo M15 + MMS17x34 close).

Protocolo do dono: A = 10 PIORES dias da base; B = 10 outros ruins sorteados; C = 10 bons sorteados;
top 20 de A -> B/C (melhora B e B+C > 0) -> IS (total E pts/op) -> OOS. Conferencia: tudo no IS inteiro + OOS.
Cada padrao em dois modos: EXIGE (so opera com o padrao a favor) e VETA (nao opera com o padrao contra).
Candle lido nas barras c-2..c (c = barra de confirmacao, M15 fechada). Figura lida nos pivos confirmados ate c.
"""
import itertools
import sys
import numpy as np
import pandas as pd
import melhora_mm as mm
import melhora_vol as mv
import motor
import confirma


def base_v2i(per):
    b, f, cache = mv.base_v2(per)
    R = confirma.PER[per]["out"]
    ev = pd.read_pickle(R + "ev_M15_dia_K1.5.pkl")
    f = f.copy(); f["i"] = ev.loc[f.idx, "i"].values
    return b, f, cache


# ---------- candles: devolve (alta, baixa) booleanos para a barra t ----------
def candles(o, h, l, c, t, atr):
    O, H, L, C = o[t], h[t], l[t], c[t]; rng_ = max(H - L, 1e-9); corpo = abs(C - O)
    O1, H1, L1, C1 = o[t - 1], h[t - 1], l[t - 1], c[t - 1]; corpo1 = abs(C1 - O1)
    O2, C2 = o[t - 2], c[t - 2]
    sup = H - max(O, C); inf = min(O, C) - L
    p = {}
    p["engolfo"] = (C > O and C1 < O1 and C >= O1 and O <= C1, C < O and C1 > O1 and C <= O1 and O >= C1)
    p["martelo / estrela cadente"] = (inf >= 2 * corpo and sup <= corpo and corpo > 0, sup >= 2 * corpo and inf <= corpo and corpo > 0)
    p["pin bar (pavio >= 60% do range)"] = (inf >= 0.6 * rng_, sup >= 0.6 * rng_)
    p["harami"] = (C1 < O1 and C > O and max(O, C) <= O1 and min(O, C) >= C1, C1 > O1 and C < O and max(O, C) <= C1 and min(O, C) >= O1)
    p["piercing / nuvem negra"] = (C1 < O1 and C > O and O < C1 and C > (O1 + C1) / 2 and C < O1, C1 > O1 and C < O and O > C1 and C < (O1 + C1) / 2 and C > O1)
    p["estrela da manhã / da tarde"] = (C2 < O2 and corpo1 < 0.3 * abs(C2 - O2) and C > O and C > (O2 + C2) / 2,
                                         C2 > O2 and corpo1 < 0.3 * abs(C2 - O2) and C < O and C < (O2 + C2) / 2)
    p["três soldados / corvos"] = (C2 > O2 and C1 > O1 and C > O and C > C1 > C2, C2 < O2 and C1 < O1 and C < O and C < C1 < C2)
    p["marubozu (corpo >= 80%)"] = (C > O and corpo >= 0.8 * rng_, C < O and corpo >= 0.8 * rng_)
    p["corpo forte (>= 60% e >= 0,5 ATR)"] = (C > O and corpo >= 0.6 * rng_ and corpo >= 0.5 * atr, C < O and corpo >= 0.6 * rng_ and corpo >= 0.5 * atr)
    p["fecha no terço de cima / de baixo"] = (C >= L + 2 / 3 * rng_, C <= L + rng_ / 3)
    p["barra de reversão (anterior contra, atual a favor)"] = (C1 < O1 and C > O and C > H1, C1 > O1 and C < O and C < L1)
    p["inside bar"] = (H <= H1 and L >= L1,) * 2
    p["outside bar a favor"] = (H > H1 and L < L1 and C > O, H > H1 and L < L1 and C < O)
    p["doji (corpo <= 10%)"] = (corpo <= 0.1 * rng_,) * 2
    return p


# ---------- figuras: nos pivos (lista piv do dia ate o indice i, inclusive) ----------
def figuras(piv, i, lado, atr, c_conf, abertura):
    """piv[i] = fundo atual (compra) ou topo atual (venda). Devolve dict nome -> (a_favor, contra)."""
    P = lambda j: piv[j][2]
    s = lado
    out = {}
    ok = lambda j: j >= 0
    # compra: F=piv[i], T1=piv[i-1], F1=piv[i-2], T2=piv[i-3], F2=piv[i-4]
    F, T1, F1 = P(i), P(i - 1), P(i - 2)
    out["fundo duplo / topo duplo (|F-F1| <= 0,5 ATR)"] = (abs(F - F1) <= 0.5 * atr, False)
    if ok(i - 4):
        T2, F2 = P(i - 3), P(i - 4)
        oco = (F1 - F2) * s < 0 and (F1 - F) * s < 0 and abs(F - F2) <= 0.5 * atr
        out["OCO invertido / OCO (ombro-cabeça-ombro)"] = (oco, False)
        rngs = [abs(T1 - F1), abs(T2 - F1), abs(T2 - F2)]
        out["triângulo / compressão (amplitudes caindo)"] = (abs(T1 - F) < abs(T1 - F1) < abs(T2 - F1), False)
        out["expansão (amplitudes subindo)"] = (abs(T1 - F) > abs(T1 - F1) > abs(T2 - F1), False)
        inc_t = (T1 - T2) * s; inc_f = (F - F1) * s
        out["canal (topos e fundos com a mesma inclinação ±30%)"] = (inc_t > 0 and inc_f > 0 and abs(inc_t - inc_f) <= 0.3 * max(inc_t, inc_f), False)
        out["topo duplo contra / fundo duplo contra (resistência)"] = (False, abs(T1 - T2) <= 0.5 * atr)
        out["cunha contra (topos sobem menos que fundos)"] = (False, 0 < inc_t < 0.5 * inc_f)
    AI = abs(T1 - F1); AC = abs(T1 - F)
    out["bandeira (impulso >= 3 ATR e correção <= 38%)"] = (AI >= 3 * atr and AC <= 0.382 * AI, False)
    out["correção em 50-62% (Fibonacci)"] = (0.5 <= AC / max(AI, 1e-9) <= 0.618, False)
    out["correção funda contra (> 78,6%)"] = (False, AC / max(AI, 1e-9) > 0.786)
    out["rompimento: já passou do topo anterior"] = ((c_conf - T1) * s > 0, False)
    out["perto do topo anterior contra (< 0,5 ATR)"] = (False, 0 <= (T1 - c_conf) * s < 0.5 * atr)
    out["longe da abertura (> 2 ATR a favor)"] = ((c_conf - abertura) * s > 2 * atr, False)
    return out


def tabelar(b, f, cache, K=1.5):
    """Para cada evento, dicionarios de candle e figura -> DataFrames booleanos de 'exige' e 'veta'."""
    dias = {s: g for s, (_, g) in enumerate(b.groupby(b.dia.values))}
    pivs = {}
    rows = []
    for e in f.itertuples():
        _, o, h, l, c, _ = cache[e.seg]; g = dias[e.seg]
        if e.seg not in pivs:
            pivs[e.seg] = motor.zigzag(g.high.to_numpy(), g.low.to_numpy(), g.atr.to_numpy(), K)
        t = e.t0 - 1; atr = g.atr.iloc[t]; lado = e.lado
        r = {}
        if t >= 2:
            for k, (a, z) in candles(o, h, l, c, t, atr).items():
                fav, con = (a, z) if lado == 1 else (z, a)
                if k in ("inside bar", "doji (corpo <= 10%)"): fav = con = a
                r["C|exige " + k] = bool(fav); r["C|veta " + k + " contra"] = not bool(con)
        else:
            for k in candles(o, h, l, c, 2, atr):
                r["C|exige " + k] = False; r["C|veta " + k + " contra"] = True
        if e.i >= 2:
            for k, (fav, con) in figuras(pivs[e.seg], e.i, lado, atr, c[t], o[0]).items():
                if fav is not False or "contra" not in k: r["F|exige " + k] = bool(fav)
                if "contra" in k: r["F|veta " + k] = not bool(con)
        rows.append(r)
    return pd.DataFrame(rows).fillna(False).astype(bool)


def dd(tr):
    eq = np.cumsum(tr); return (np.maximum.accumulate(eq) - eq).max() if len(tr) else np.nan


def funil(nome_rodada, V, Vo, f, cache, fo, co, seed):
    base_d, base_tr = mm.simular(f, cache); _, oos = mm.simular(fo, co)
    s = pd.Series(base_d); rng = np.random.default_rng(seed)
    A = s.sort_values().index[:10].to_numpy()
    B = rng.permutation(s[(s < 0) & (~s.index.isin(A))].index.to_numpy())[:10]
    C = rng.permutation(s[s > 0].index.to_numpy())[:10]
    tot = lambda d, segs: sum(d.get(q, 0) for q in segs)
    bA, bB, bC = tot(base_d, A), tot(base_d, B), tot(base_d, C)
    print(f"\n===== {nome_rodada}: {len(V)} variantes | A(10 piores) {bA:+.0f}  B {bB:+.0f}  C {bC:+.0f}", flush=True)
    rows = []
    for k, m in V.items():
        d, _ = mm.simular(f, cache, m, segs=A); rows.append(dict(var=k, mantem=m.mean(), dA=tot(d, A) - bA))
    ra = pd.DataFrame(rows).sort_values("dA", ascending=False)
    top = ra.head(20).copy()
    for i, r in top.iterrows():
        m = V[r["var"]]; dB, _ = mm.simular(f, cache, m, segs=B); dC, _ = mm.simular(f, cache, m, segs=C)
        top.loc[i, "dB"] = tot(dB, B) - bB; top.loc[i, "dC"] = tot(dC, C) - bC
    top["passa_BC"] = (top.dB > 0) & (top.dB + top.dC > 0)
    full = []
    for k, m in V.items():
        _, tr = mm.simular(f, cache, m); _, to = mm.simular(fo, co, Vo[k])
        full.append(dict(var=k, mantem=m.mean(), n_IS=len(tr), op_IS=np.mean(tr) if tr else np.nan, total_IS=sum(tr), dd_IS=dd(tr),
                         n_OOS=len(to), op_OOS=np.mean(to) if to else np.nan, total_OOS=sum(to), dd_OOS=dd(to)))
    full = pd.DataFrame(full).set_index("var")
    full["passa_IS"] = (full.total_IS > sum(base_tr)) & (full.op_IS > np.mean(base_tr))
    full["passa_OOS"] = full.passa_IS & (full.total_OOS > sum(oos)) & (full.op_OOS > np.mean(oos))
    top = top.join(full[["passa_IS", "passa_OOS", "total_IS", "total_OOS"]], on="var")
    top["funil_ok"] = top.passa_BC & top.passa_IS & top.passa_OOS
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    print(top.round(2).to_string(index=False))
    print(f"BASE IS {sum(base_tr):+.0f} ({np.mean(base_tr):+.1f}/op, DD {dd(base_tr):.0f}) | OOS {sum(oos):+.0f} ({np.mean(oos):+.1f}/op, DD {dd(oos):.0f})")
    print("CONFERENCIA IS inteiro (passa_IS):")
    print(full[full.passa_IS].sort_values("total_IS", ascending=False).round(1).to_string())
    return ra, top, full


def main():
    b, f, cache = base_v2i("pesquisa"); bo, fo, co = base_v2i("reserva")
    T = tabelar(b, f, cache); To = tabelar(bo, fo, co)
    cols = [c for c in T.columns if c in To.columns]
    V = {c: T[c].to_numpy() for c in cols}; Vo = {c: To[c].to_numpy() for c in cols}
    Vc = {k: v for k, v in V.items() if k.startswith("C|")}; Vf = {k: v for k, v in V.items() if k.startswith("F|")}
    res = {}
    res["candle"] = funil("RODADA 7: CANDLES", Vc, Vo, f, cache, fo, co, 2029)
    res["figura"] = funil("RODADA 8: FIGURAS", Vf, Vo, f, cache, fo, co, 2030)
    # combinados: os 8 melhores de cada familia no IS inteiro (por total), E e OU
    tc = res["candle"][2].sort_values("total_IS", ascending=False).index[:8]
    tf = res["figura"][2].sort_values("total_IS", ascending=False).index[:8]
    Vj, Vjo = {}, {}
    for a, z in itertools.product(tc, tf):
        Vj[f"{a} E {z}"] = V[a] & V[z]; Vjo[f"{a} E {z}"] = Vo[a] & Vo[z]
        Vj[f"{a} OU {z}"] = V[a] | V[z]; Vjo[f"{a} OU {z}"] = Vo[a] | Vo[z]
    res["junto"] = funil("RODADA 9: CANDLE + FIGURA", Vj, Vjo, f, cache, fo, co, 2031)
    pd.to_pickle(res, confirma.PER["reserva"]["out"] + "melhora_padroes.pkl")


if __name__ == "__main__":
    main()
