"""Melhorar o robo M15 com um filtro de medias moveis, por etapas pequenas (protocolo do dono, 2026-10-08).

Base: robo M15 (escada est>=1, ZigZag 1,5 ATR, H1 9/21/34 a favor + lado da abertura do dia; entrada limitada no
fechamento da barra de confirmacao, preco passa 2 ticks, 3 barras; stop na estrutura; zera no fim do dia; -10 pts/op).
Filtro extra decidido na barra de confirmacao (M15, serie continua, so barras fechadas).

Etapas (dias sorteados com semente fixa, so da PESQUISA 2022-set/25):
  A = 10 dias ruins -> todas as variantes; ordena pela melhora no total do dia
  B = outros 10 dias ruins e C = 10 dias bons -> as 20 melhores de A; passa quem melhora B e nao piora C (B+C > 0)
  IS completo -> passa quem melhora o total E o liquido por operacao
  OOS (reserva) -> so as que passaram no IS
"""
import itertools
import numpy as np
import pandas as pd
import motor
import vies
import confirma

K, FURA, TTL = 1.5, 10, 3


def wma(s, n):
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def media(s, tipo, n):
    if tipo == "MMS": return s.rolling(n).mean()
    if tipo == "MME": return s.ewm(span=n, adjust=False).mean()
    return wma(s, n)


def preparar(per):
    R = confirma.PER[per]["out"]
    f = pd.read_pickle(R + f"feat0_M15_dia_K{K}.pkl"); ev = pd.read_pickle(R + f"ev_M15_dia_K{K}.pkl")
    b = pd.read_pickle(R + "barras_M15_dia.pkl")
    flag = vies.htf_flag(b, "60min", (9, 21, 34))
    dias = list(b.groupby(b.dia.values))
    f = f[f.est >= 1].copy()
    f["seg"] = ev.loc[f.idx, "seg"].values; f["t0"] = ev.loc[f.idx, "t0"].values; f["stop"] = ev.loc[f.idx, "stop"].values
    f["pos"] = [b.index.get_loc(dias[s][1].index[t - 1]) for s, t in zip(f.seg, f.t0)]  # linha da barra de confirmacao
    f["htf"] = [flag.asof(b.index[p]) if b.index[p] >= flag.index[0] else 0 for p in f.pos]
    f = f[(f.htf * f.lado == 1) & (f.H13 > 0)].sort_values(["seg", "t0"])
    cache = {}
    for s, (_, g) in enumerate(dias):
        cache[s] = (g.index[0].normalize(), g.open.to_numpy(), g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy(),
                    {p[3]: p for p in motor.zigzag(g.high.to_numpy(), g.low.to_numpy(), g.atr.to_numpy(), K)})
    return b, f, cache


def simular(f, cache, keep=None, segs=None):
    """Robo sequencial. keep: array bool alinhado a f (None = todos). Devolve liquido por dia (dict) e lista de trades."""
    por_dia, trades, ocup = {}, [], {}
    ff = f if keep is None else f[keep]
    if segs is not None: ff = ff[ff.seg.isin(segs)]
    for e in ff.itertuples():
        dia, o0, h, l, c, conf = cache[e.seg]
        if e.t0 <= ocup.get(e.seg, -1): continue
        lado, lim, tf_ = e.lado, c[e.t0 - 1], None
        for t in range(e.t0, min(e.t0 + TTL, len(o0))):
            if (l[t] <= e.stop) if lado == 1 else (h[t] >= e.stop): break
            if (l[t] <= lim - FURA) if lado == 1 else (h[t] >= lim + FURA):
                tf_ = t; px = min(o0[t], lim) if lado == 1 else max(o0[t], lim); break
        if tf_ is None or (px - e.stop) * lado <= 0: continue
        o = o0.copy(); o[tf_] = px
        res, _, ts = motor.trail(o, h, l, c, conf, tf_, lado, e.stop)
        ocup[e.seg] = ts
        por_dia[e.seg] = por_dia.get(e.seg, 0) + res - 10
        trades.append(res - 10)
    return por_dia, trades


def variantes(b):
    """Devolve dict nome -> serie (+1 favorece compra, -1 favorece venda, 0 neutro) indexada como b."""
    out = {}
    srcs = {"close": b.close, "open": b.open}
    lens = [9, 17, 21, 34, 50, 72, 100, 200]
    pares = [(9, 21), (9, 34), (17, 34), (21, 34), (21, 50), (34, 72), (34, 100), (50, 200), (9, 200)]
    cache = {}
    for tipo, (sn, s) in itertools.product(("MMS", "MME", "MMP"), srcs.items()):
        for n in lens:
            cache[(tipo, sn, n)] = media(s, tipo, n)
    for (tipo, sn, n), m in cache.items():
        sinal_preco = np.sign(b.close - m); incl = np.sign(m - m.shift(3))
        out[f"{tipo}{n} {sn}: preço do lado"] = sinal_preco
        out[f"{tipo}{n} {sn}: inclinada a favor"] = incl
        out[f"{tipo}{n} {sn}: preço do lado + inclinada"] = np.where(sinal_preco == incl, sinal_preco, 0)
    for tipo, sn in itertools.product(("MMS", "MME", "MMP"), srcs):
        for a, z in pares:
            ma, mz = cache[(tipo, sn, a)], cache[(tipo, sn, z)]
            cruz = np.sign(ma - mz); ia = np.sign(ma - ma.shift(3)); iz = np.sign(mz - mz.shift(3))
            out[f"{tipo}{a}x{z} {sn}: rápida do lado"] = cruz
            out[f"{tipo}{a}x{z} {sn}: rápida do lado + as duas inclinadas"] = np.where((cruz == ia) & (ia == iz), cruz, 0)
            out[f"{tipo}{a}+{z} {sn}: preço acima/abaixo das duas"] = np.where(np.sign(b.close - ma) == np.sign(b.close - mz), np.sign(b.close - ma), 0)
    return {k: pd.Series(np.asarray(v), index=b.index) for k, v in out.items()}


def mascara(f, serie):
    return (serie.to_numpy()[f.pos.to_numpy()] * f.lado.to_numpy()) == 1


def main():
    b, f, cache = preparar("pesquisa")
    base_dia, base_tr = simular(f, cache)
    s_dia = pd.Series(base_dia)
    rng = np.random.default_rng(2026)
    ruins = s_dia[s_dia < 0].index.to_numpy(); bons = s_dia[s_dia > 0].index.to_numpy()
    rs = rng.permutation(ruins); A, B = rs[:10], rs[10:20]; C = rng.permutation(bons)[:10]
    print(f"base IS: {len(base_tr)} ops, liq/op {np.mean(base_tr):+.1f}, total {sum(base_tr):+.0f}; dias com trade {len(s_dia)}, ruins {len(ruins)}, bons {len(bons)}")
    print("A:", [str(cache[s][0].date()) for s in A], "\nB:", [str(cache[s][0].date()) for s in B], "\nC:", [str(cache[s][0].date()) for s in C], flush=True)
    tot = lambda d, segs: sum(d.get(s, 0) for s in segs)
    bA, bB, bC = tot(base_dia, A), tot(base_dia, B), tot(base_dia, C)
    print(f"base A {bA:+.0f}  B {bB:+.0f}  C {bC:+.0f}", flush=True)
    V = variantes(b)
    rows = []
    for nome, serie in V.items():
        d, _ = simular(f, cache, mascara(f, serie), segs=A)
        rows.append(dict(var=nome, dA=tot(d, A) - bA))
    ra = pd.DataFrame(rows).sort_values("dA", ascending=False)
    print(f"\nETAPA A: {len(ra)} variantes; melhoram A: {(ra.dA > 0).sum()}")
    top = ra.head(20).copy()
    for i, r in top.iterrows():
        k = mascara(f, V[r["var"]])
        dB, _ = simular(f, cache, k, segs=B); dC, _ = simular(f, cache, k, segs=C)
        top.loc[i, "dB"] = tot(dB, B) - bB; top.loc[i, "dC"] = tot(dC, C) - bC
    top["passa_BC"] = (top.dB > 0) & (top.dB + top.dC > 0)
    print("\nETAPA B/C (20 melhores de A):"); print(top.round(0).to_string(index=False), flush=True)
    fin = []
    bo, fo, co = preparar("reserva"); Vo = variantes(bo)
    oos_base_d, oos_base = simular(fo, co)
    for r in top[top.passa_BC].itertuples():
        _, tr = simular(f, cache, mascara(f, V[r.var]))
        lin = dict(var=r.var, n_IS=len(tr), liq_op_IS=np.mean(tr), total_IS=sum(tr),
                   passa_IS=sum(tr) > sum(base_tr) and np.mean(tr) > np.mean(base_tr))
        if lin["passa_IS"]:
            _, to = simular(fo, co, mascara(fo, Vo[r.var]))
            lin.update(n_OOS=len(to), liq_op_OOS=np.mean(to), total_OOS=sum(to),
                       passa_OOS=sum(to) > sum(oos_base) and np.mean(to) > np.mean(oos_base))
        fin.append(lin)
    fin = pd.DataFrame(fin)
    print(f"\nBASE  IS: n {len(base_tr)} liq/op {np.mean(base_tr):+.1f} total {sum(base_tr):+.0f} | OOS: n {len(oos_base)} liq/op {np.mean(oos_base):+.1f} total {sum(oos_base):+.0f}")
    print("IS / OOS das que passaram em B/C:"); print(fin.round(1).to_string(index=False))
    pd.to_pickle(dict(ra=ra, top=top, fin=fin, A=A, B=B, C=C), confirma.PER["reserva"]["out"] + "melhora_mm.pkl")


if __name__ == "__main__":
    main()
