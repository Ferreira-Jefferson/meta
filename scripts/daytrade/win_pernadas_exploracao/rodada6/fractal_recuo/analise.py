import sys, numpy as np, pandas as pd
import fractal_core as fc
per = sys.argv[1]
ev = pd.read_pickle(f"ev_{per}.pkl")
real = ev[ev.draw == -1]; shuf = ev[ev.draw >= 0]
ND = shuf.draw.nunique()
rng = np.random.default_rng(7)
SC = fc.ESCALAS
KS = fc.KS
FORMAS = ["a", "a2", "b", "c", "d", "e"]


def sc(df, T, s): return df[(df["T"] == T) & (df.s == s)]
def hbin(h): return np.where(h < 11, "<11h", np.where(h < 13, "11-13h", ">=13h"))


def boot_days(df, vals, B=2000):
    d = pd.DataFrame({"dia": df.dia.values, "v": np.asarray(vals, float)})
    g = d.groupby("dia").v.agg(["sum", "count"]).values
    n = len(g)
    if n < 3: return (np.nan, np.nan)
    ix = rng.integers(0, n, (B, n))
    ms = g[ix, 0].sum(1) / np.maximum(g[ix, 1].sum(1), 1)
    return np.percentile(ms, [2.5, 97.5])


def f(x, n=3): return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{n}f}".replace(".", ",")
def pct(x): return "-" if x is None or np.isnan(x) else f"{100*x:.1f}%".replace(".", ",")


def shuf_stat(fn, T, s):
    vals = [fn(g) for _, g in sc(shuf, T, s).groupby("draw")]
    vals = np.array([v for v in vals if v == v], float)
    if len(vals) == 0: return np.nan, np.nan
    return vals.mean(), vals.std(ddof=1) if len(vals) > 1 else np.nan


def z(real_v, m, sd): return (real_v - m) / sd if sd and sd == sd and sd > 0 else np.nan


out = []
P = out.append
P(f"# Periodo {per}  (dias reais: {real.dia.nunique()}; sorteios: {ND})\n")

# ---- 1 repique
P("## 1. Repique interno (H-F) em % do recuo E-F\n")
P("Eventos com F confirmado (recuo>=2s). '=100%' = voltou ao topo sem o repique confirmar. Analitico: H-F = s + Exp(s) (caminhada aleatoria).\n")
lab = ["<25%", "25-38%", "38-50%", "50-62%", "62-100%", "=100% (topo)"]
P("| T/s | n | " + " | ".join(lab) + " | mediana rho real (emb) |")
P("|---|---|" + "---|" * (len(lab) + 1))


def anal_rho_bin(d1, s):
    def surv(y): return np.where(y <= s, 1.0, np.exp(-(y - s) / s))
    edges = [0, .25, .38, .5, .62, 1.0]
    res = [surv(a * d1) - surv(b * d1) for a, b in zip(edges[:-1], edges[1:])]
    res.append(surv(1.0 * d1))
    return np.array(res).mean(1)


def rho_shares(g):
    return np.array([(g.rho < .25).mean(), ((g.rho >= .25) & (g.rho < .38)).mean(), ((g.rho >= .38) & (g.rho < .5)).mean(),
                     ((g.rho >= .5) & (g.rho < .62)).mean(), ((g.rho >= .62) & (g.rho < 1)).mean(), (g.rho >= 1).mean()])


for T, s in SC:
    r = sc(real, T, s)
    cnt = rho_shares(r)
    an = anal_rho_bin(r.d1.values, s)
    sh = sc(shuf, T, s)
    shc = np.array([rho_shares(g) for _, g in sh.groupby("draw")])
    cells = [f"{pct(cnt[i])} (emb {pct(shc[:,i].mean())}; anal {pct(an[i])})" for i in range(6)]
    P(f"| {T}/{s} | {len(r)} | " + " | ".join(cells) + f" | {f(r.rho.median(),2)} ({f(sh.groupby('draw').rho.median().mean(),2)}) |")

# ---- 2 reteste
P("\n## 2. Reteste: onde fica o fundo G em relacao a F (eventos com H confirmado)\n")
P("Analitico: P(G<x)=exp(-(H-s-x)/s). Mais alto = G>F+10; duplo = |G-F|<=10; mais baixo = G<F-10 (inclui quem tocou S antes de G confirmar).\n")
P("| T/s | n | alto real | emb | anal | duplo real | emb | anal | baixo real | emb | anal | z(baixo vs emb) | fura: mediana pts (media) | fura mediana % recuo |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def fshares(g):
    g = g[g.forma != "s"]
    G = g.G.fillna(g.F - 999)
    return pd.Series(dict(alto=(G > g.F + fc.TOL).mean(), dup=((G - g.F).abs() <= fc.TOL).mean(), baixo=(G < g.F - fc.TOL).mean()))


for T, s in SC:
    r = sc(real, T, s); rr = r[r.forma != "s"]
    sr = fshares(r)
    shs = pd.DataFrame([fshares(g) for _, g in sc(shuf, T, s).groupby("draw")])
    Hs = rr.H.values - s
    pl = lambda x: np.exp(-(Hs - x) / s)
    p_baixo = np.clip(pl(rr.F.values - fc.TOL), 0, 1).mean()
    p_dup = (np.clip(pl(rr.F.values + fc.TOL), 0, 1) - np.clip(pl(rr.F.values - fc.TOL), 0, 1)).mean()
    p_alto = 1 - p_baixo - p_dup
    low = rr[rr.G < rr.F - fc.TOL]
    fur = (low.F - low.G)
    P(f"| {T}/{s} | {len(rr)} | {pct(sr.alto)} | {pct(shs.alto.mean())} | {pct(p_alto)} | {pct(sr.dup)} | {pct(shs.dup.mean())} | {pct(p_dup)} | {pct(sr.baixo)} | {pct(shs.baixo.mean())} | {pct(p_baixo)} | {f(z(sr.baixo, shs.baixo.mean(), shs.baixo.std()),1)} | {f(fur.median(),0)} ({f(fur.mean(),0)}) | {pct((fur/low.d1).median())} |")

# ---- 3 desfecho por forma
P("\n## 3. Desfecho por forma (a partir de t3): P(supera topo E antes de tocar S)\n")
P("ruina = media de (G+s-S)/(E-S). emb = mesma forma nos dados embaralhados. IC = bootstrap de dias da diferenca real-ruina. (forma e: inclui os que tocaram S antes de G confirmar; nesses nao ha ruina, entram so na coluna real.)\n")
P("| T/s | forma | n real | n emb/sorteio | P(sup) real | ruina | emb | dif real-ruina [IC95 dias] | z vs emb | P(vira) real |")
P("|---|---|---|---|---|---|---|---|---|---|")


def forma_stat(g, fm):
    h = g[(g.forma == fm) & (g.out != "nada") & (g.j3 >= 0)]
    return (h.out == "sup").mean() if len(h) else np.nan


for T, s in SC:
    r = sc(real, T, s)
    for fm in FORMAS:
        h = r[(r.forma == fm) & (r.out != "nada") & (r.j3 >= 0)]
        if len(h) < 30: continue
        y = (h.out == "sup").astype(float).values
        pr = h.p_sup_ruina.values
        ic = boot_days(h, y - pr)
        m, sd = shuf_stat(lambda g: forma_stat(g, fm), T, s)
        nsh = len(sc(shuf, T, s)[lambda d: d.forma == fm]) / ND
        P(f"| {T}/{s} | {fm} | {len(h)} | {nsh:.0f} | {pct(y.mean())} | {pct(pr.mean())} | {pct(m)} | {f(100*(y.mean()-pr.mean()),1)}pp [{f(100*ic[0],1)};{f(100*ic[1],1)}] | {f(z(y.mean(), m, sd),1)} | {pct((h.out=='vira').mean())} |")

# ---- 4 excesso
P("\n## 4. Quanto fura o fundo antes de o preco superar o topo (excesso = F - minimo desde t1, pts)\n")
P("Eventos cujo desfecho final (de t1) e 'sup'. P(exc<=k) = fracao em que um stop k pts abaixo de F sobrevive ate o alvo. Embaralhado entre parenteses.\n")
P("| T/s | recorte | n | mediana | p75 | p90 | " + " | ".join(f"<=({k})" for k in KS) + " |")
P("|---|---|---|---|---|---|" + "---|" * len(KS))
for T, s in SC:
    r = sc(real, T, s); r = r[r.out == "sup"]
    sh = sc(shuf, T, s); sh = sh[sh.out == "sup"]

    def row(rec, g, gs):
        if len(g) < 20: return
        cells = [f"{pct((g.exc_min <= k).mean())} ({pct((gs.exc_min <= k).mean())})" for k in KS]
        P(f"| {T}/{s} | {rec} | {len(g)} | {f(g.exc_min.median(),0)} ({f(gs.exc_min.median(),0)}) | {f(g.exc_min.quantile(.75),0)} | {f(g.exc_min.quantile(.9),0)} | " + " | ".join(cells) + " |")
    row("todos", r, sh)
    hb, hbs = hbin(r.hora.values), hbin(sh.hora.values)
    for h in ["<11h", "11-13h", ">=13h"]:
        row(h, r[hb == h], sh[hbs == h])
    for lo, hi, nm in [(1, 1.5, "A/T<1,5"), (1.5, 2, "A/T 1,5-2"), (2, 99, "A/T>=2")]:
        row(nm, r[(r.A / r["T"] >= lo) & (r.A / r["T"] < hi)], sh[(sh.A / sh["T"] >= lo) & (sh.A / sh["T"] < hi)])
    for lo, hi, nm in [(0, .3, "r<30%"), (.3, .5, "r 30-50%"), (.5, .7, "r 50-70%"), (.7, 2, "r>=70%")]:
        row(nm, r[(r.r1 >= lo) & (r.r1 < hi)], sh[(sh.r1 >= lo) & (sh.r1 < hi)])

# ---- 5 geometria
P("\n## 5. Geometria: limite de compra em F (posta quando H e confirmado), alvo E (topo de origem), stop F-k\n")
P("fill = preenchida ao tocar F (otimista: sem fila). acerto = P(alvo antes do stop | fill). ruina = media de k/(d1+k). BE = breakeven empirico = perda/(ganho+perda). R$/op = pts*0,20 (custo 2 pts + deslize do stop 5). emb = embaralhado.\n")
HDR = "| T/s | recorte | k | n fill | fill% | recuo medio d1 | alvo/stop | acerto real | acerto ruina | acerto emb | BE emp | pts/op real | pts/op emb | R$/op real | IC95 dias pts/op | z vs emb |"
P(HDR)
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def geo(df, k):
    h = df[df.g_fill == 1]
    if len(h) == 0: return None
    exc = h.g_mn_exc.values; alvo = h.g_alvo.values == 1
    win = alvo & (exc < k); loss = exc >= k
    pts = np.where(win, h.d1.values - fc.CUSTO, np.where(loss, -(k + fc.DESLIZE_STOP + fc.CUSTO), h.g_ult.values - fc.CUSTO))
    return h, win, loss, pts


def geo_row(T, s, rec, mask_fn, k, minn=40):
    r = sc(real, T, s); r = r[mask_fn(r)]
    g = geo(r, k)
    if g is None or len(g[0]) < minn: return None
    h, win, loss, pts = g
    nev = len(r)
    ruina = (k / (h.d1.values + k)).mean()
    ac = win.sum() / max(win.sum() + loss.sum(), 1)
    ganho = (h.d1.values[win] - fc.CUSTO).mean() if win.any() else np.nan
    perda = k + fc.DESLIZE_STOP + fc.CUSTO
    be = perda / (ganho + perda) if ganho == ganho else np.nan
    accs, ptss = [], []
    for _, gg in sc(shuf, T, s).groupby("draw"):
        gg = gg[mask_fn(gg)]
        x = geo(gg, k)
        if x is None or len(x[0]) < 5: continue
        accs.append(x[1].sum() / max(x[1].sum() + x[2].sum(), 1)); ptss.append(x[3].mean())
    ptss = np.array(ptss); accs = np.array(accs)
    ic = boot_days(h, pts)
    return (f"| {T}/{s} | {rec} | {k} | {len(h)} | {pct(len(h)/nev)} | {f(h.d1.mean(),0)} | {f(h.d1.mean()/k,1)} | {pct(ac)} | {pct(ruina)} | {pct(accs.mean())} | {pct(be)} | "
            f"{f(pts.mean(),1)} | {f(ptss.mean(),1)} | {f(pts.mean()*0.2,2)} | [{f(ic[0],1)};{f(ic[1],1)}] | {f(z(pts.mean(), ptss.mean(), ptss.std(ddof=1)),1)} |")


for T, s in SC:
    for k in KS:
        ln = geo_row(T, s, "todos", lambda d: np.ones(len(d), bool), k)
        if ln: P(ln)

P("\n### 5b. Estratos (escalas T/4: 250/65, 500/125, 750/190), k=100 e 200\n")
P(HDR)
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for T, s in [(250, 65), (500, 125), (750, 190)]:
    for k in (100, 200):
        for nm, fn in [("<11h", lambda d: hbin(d.hora.values) == "<11h"), ("11-13h", lambda d: hbin(d.hora.values) == "11-13h"), (">=13h", lambda d: hbin(d.hora.values) == ">=13h"),
                       ("r<30%", lambda d: d.r1.values < .3), ("r30-50%", lambda d: (d.r1.values >= .3) & (d.r1.values < .5)), ("r50-70%", lambda d: (d.r1.values >= .5) & (d.r1.values < .7)), ("r>=70%", lambda d: d.r1.values >= .7),
                       ("A/T<1,5", lambda d: (d.A / d["T"]).values < 1.5), ("A/T>=2", lambda d: (d.A / d["T"]).values >= 2),
                       ("d1>=3k", lambda d, k=k: d.d1.values >= 3 * k), ("d1>=5k", lambda d, k=k: d.d1.values >= 5 * k)]:
            ln = geo_row(T, s, nm, fn, k)
            if ln: P(ln)

# ---- 6 auto-semelhanca
P("\n## 6. Auto-semelhanca: recuo/avanco (macro) x repique/recuo e reteste/repique (micro)\n")
P("macro = (E-F)/A ; micro1 = (H-F)/(E-F) ; micro2 = (H-G)/(H-F). Medianas (media). corr = Pearson(macro, micro1), total e por A/T.\n")
P("| T/s | n | macro mediana (media) | micro1 mediana (media) | micro2 mediana (media) | corr real | corr emb | corr A/T<1,5 | corr A/T 1,5-2 | corr A/T>=2 |")
P("|---|---|---|---|---|---|---|---|---|---|")


def corr(a, b):
    return np.corrcoef(a, b)[0, 1] if len(a) > 20 else np.nan


for T, s in SC:
    r = sc(real, T, s); r = r[r.forma != "s"]
    m2 = ((r.H - r.G) / (r.H - r.F)).dropna()
    csh = np.nanmean([corr(g[g.forma != "s"].r1.values, g[g.forma != "s"].rho.values) for _, g in sc(shuf, T, s).groupby("draw")])
    cs = []
    for lo, hi in [(1, 1.5), (1.5, 2), (2, 99)]:
        q = r[(r.A / r["T"] >= lo) & (r.A / r["T"] < hi)]
        cs.append(f(corr(q.r1.values, q.rho.values), 2))
    P(f"| {T}/{s} | {len(r)} | {f(r.r1.median(),2)} ({f(r.r1.mean(),2)}) | {f(r.rho.median(),2)} ({f(r.rho.mean(),2)}) | {f(m2.median(),2)} ({f(m2.mean(),2)}) | {f(corr(r.r1.values,r.rho.values),2)} | {f(csh,2)} | {cs[0]} | {cs[1]} | {cs[2]} |")
P("\nMacro por escala (recuo/avanco, F confirmado), mesma razao s/T=1/4:\n")
P("| T | n | q25 | mediana | q75 | media |")
P("|---|---|---|---|---|---|")
for T, s in [(250, 65), (500, 125), (750, 190)]:
    r = sc(real, T, s)
    P(f"| {T} | {len(r)} | {f(r.r1.quantile(.25),2)} | {f(r.r1.median(),2)} | {f(r.r1.quantile(.75),2)} | {f(r.r1.mean(),2)} |")

open(f"tabelas_{per}.md", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
