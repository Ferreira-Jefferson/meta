"""Lente 3 - mapa de correlacoes entre fases (timing rotulado) + caminho intradia M5 + perfil de volume.
Reprodutivel: .venv\\Scripts\\python.exe <este arquivo>. Escreve tabelas em out/ ao lado do script.
"""
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
def rankdata(a):
    return pd.Series(a).rank().values

warnings.filterwarnings("ignore")
ROOT = Path(r"C:\Users\Jeffe\Documents\study\meta")
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
RNG = np.random.default_rng(20261006)
NPERM = 10000
PROBLEM = {"2026-07-31", "2026-09-24", "2026-10-05"}
ROLL = {"2026-04-15", "2026-06-17", "2026-08-12"}  # vencimentos; rodar sem esses dias + o dia seguinte


# ---------------------------------------------------------------- utilidades estatisticas
def spearman_perm(x, y, nperm=NPERM):
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 20:
        return n, np.nan, np.nan
    xr = rankdata(x[m]); yr = rankdata(y[m])
    xz = (xr - xr.mean()) / xr.std(); yz = (yr - yr.mean()) / yr.std()
    rho = float((xz * yz).mean())
    idx = RNG.permuted(np.tile(np.arange(n), (nperm, 1)), axis=1)
    null = (yz[idx] @ xz) / n
    p = (1 + np.sum(np.abs(null) >= abs(rho) - 1e-12)) / (nperm + 1)
    return n, rho, float(p)


def bh(p):
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    pv = p[ok]
    o = np.argsort(pv)
    r = pv[o] * len(pv) / (np.arange(len(pv)) + 1)
    r = np.minimum.accumulate(r[::-1])[::-1]
    qq = np.empty_like(pv); qq[o] = np.minimum(r, 1)
    q[ok] = qq
    return q


def rho_only(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 15:
        return np.nan
    return float(np.corrcoef(rankdata(x[m]), rankdata(y[m]))[0, 1])


# ---------------------------------------------------------------- dados
d = pd.read_csv(ROOT / "data/win_fases_pregao_6m.csv", sep=";", encoding="utf-8-sig")
d["dt"] = pd.to_datetime(d["data"])
d["gap"] = d.pre_preco_fechamento - d.pos_preco_fechamento.shift()
for c in ["pre_volume", "pre_negocios"]:
    d[c] = d[c].replace(0, np.nan)
d.loc[d.pre_volume.isna(), "pre_hora_leilao"] = np.nan
hh = pd.to_datetime(d.pre_hora_leilao, format="%H:%M:%S.%f", errors="coerce")
d["pre_hora_min"] = hh.dt.hour * 60 + hh.dt.minute + hh.dt.second / 60 - 540
d["pre_vpn"] = d.pre_volume / d.pre_negocios
d["preg_ret"] = d.pregao_preco_fechamento - d.pregao_preco_inicio
d["preg_rng"] = d.pregao_maxima - d.pregao_minima
d["preg_vol"] = d.pregao_volume
d["preg_neg"] = d.pregao_negocios
d["preg_vpn"] = d.preg_vol / d.preg_neg
d["pos_ret"] = d.pos_preco_fechamento - d.pregao_preco_fechamento
d["pos_vol"] = d.pos_volume
d["pos_neg"] = d.pos_negocios
d["pos_vpn"] = d.pos_vol / d.pos_neg
d["pre_vol"] = d.pre_volume
d["pre_neg"] = d.pre_negocios
d["d_pre_vol"] = d.pre_vol.pct_change() * 100
d["d_preg_vol"] = d.preg_vol.pct_change() * 100
d["d_pos_vol"] = d.pos_vol.pct_change() * 100
d["abs_gap"] = d.gap.abs()
d["abs_preg_ret"] = d.preg_ret.abs()
d["abs_pos_ret"] = d.pos_ret.abs()
d["retorno_dia_close"] = d.pos_preco_fechamento - d.pos_preco_fechamento.shift()  # call D - call D-1

PHASE = {"pre": 0, "preg": 1, "pos": 2}
VARS = ["gap", "pre_vol", "pre_neg", "pre_vpn", "pre_hora_min", "d_pre_vol",
        "preg_ret", "preg_rng", "preg_vol", "preg_neg", "preg_vpn", "d_preg_vol",
        "pos_ret", "pos_vol", "pos_neg", "pos_vpn", "d_pos_vol"]


def phase_of(v):
    return "pre" if v.startswith(("gap", "pre_", "d_pre_")) else ("pos" if v.startswith(("pos_", "d_pos_")) else "preg")


MECH = {frozenset(s) for s in [("pre_vol", "pre_neg"), ("pre_vol", "pre_vpn"), ("pre_neg", "pre_vpn"),
                              ("preg_vol", "preg_neg"), ("preg_vol", "preg_vpn"), ("preg_neg", "preg_vpn"),
                              ("pos_vol", "pos_neg"), ("pos_vol", "pos_vpn"), ("pos_neg", "pos_vpn"),
                              ("preg_ret", "preg_rng"), ("d_preg_vol", "preg_vol"), ("d_pre_vol", "pre_vol"), ("d_pos_vol", "pos_vol")]}

cols = {}
for v in VARS:
    cols[f"{v}[D]"] = d[v].values
    cols[f"{v}[D-1]"] = d[v].shift(1).values
V = pd.DataFrame(cols, index=d.data)
NAMES = list(V.columns)


def tinfo(name):
    v, lag = name[:-1].split("[")
    lagd = 0 if lag == "D" else -1
    return v, PHASE[phase_of(v)] + 3 * lagd


def label(a, b):
    """Rotulo da relacao entre a (X) e b (Y), ordenando no tempo."""
    va, ta = tinfo(a); vb, tb = tinfo(b)
    if ta == tb:
        return "contemporaneo (mesma fase)" + (" [mecanico]" if frozenset((va, vb)) in MECH else "")
    first, second = (a, b) if ta < tb else (b, a)
    vs, ts = tinfo(second)
    # operavel se a variavel posterior e' do pregao de D (ph=1, lag D) e a anterior ja' ocorreu antes do pregao
    if ts == 1 and tinfo(first)[1] < 1:
        return f"preditivo OPERAVEL ({first} -> {second})"
    if ts == 2:
        return f"contemporaneo/descritivo ({first} antecede call de D)"
    return f"sequencial D-1->D nao-pregao ({first} -> {second})"


def build_matrix(mask, tag):
    rows = []
    for i in range(len(NAMES)):
        for j in range(i + 1, len(NAMES)):
            a, b = NAMES[i], NAMES[j]
            va, ta = tinfo(a); vb, tb = tinfo(b)
            if va == vb:  # mesma variavel D vs D-1: autocorrelacao, mantida
                pass
            if ta < 0 and tb < 0:  # ambos D-1: duplicata deslocada
                continue
            if ta <= -1 and tb <= -1:
                continue
            x = V[a].values.astype(float).copy(); y = V[b].values.astype(float).copy()
            x[~mask] = np.nan; y[~mask] = np.nan
            n, rho, p = spearman_perm(x, y)
            h = np.where(d.dt.values < np.datetime64("2026-07-01"))[0]
            m1 = np.zeros(len(d), bool); m1[h] = True
            r1 = rho_only(np.where(m1, x, np.nan), np.where(m1, y, np.nan))
            r2 = rho_only(np.where(~m1, x, np.nan), np.where(~m1, y, np.nan))
            rows.append(dict(X=a, Y=b, n=n, rho=rho, p_perm=p, rho_H1=r1, rho_H2=r2, rotulo=label(a, b)))
    t = pd.DataFrame(rows)
    t["q_BH"] = bh(t.p_perm.values)
    t["estavel"] = np.sign(t.rho_H1) == np.sign(t.rho_H2)
    t["abs_rho"] = t.rho.abs()
    t = t.sort_values("abs_rho", ascending=False).reset_index(drop=True)
    t.to_csv(OUT / f"matriz_{tag}.csv", index=False, sep=";", decimal=",")
    return t


good_all = np.ones(len(d), bool)
bad = d.data.isin(PROBLEM).values
rollmask = d.data.isin(ROLL | {str((pd.Timestamp(r) + pd.Timedelta(days=1)).date()) for r in ROLL}).values
# dia seguinte util pode ser +3; pega proximo pregao
idxr = [d.index[d.data == r][0] for r in ROLL if (d.data == r).any()]
rollmask = np.zeros(len(d), bool)
for i in idxr:
    rollmask[i:i + 2] = True
# D-1 problematico contamina D: remove tambem o dia seguinte aos problemas
bad_ext = bad.copy()
for i in np.where(bad)[0]:
    if i + 1 < len(d):
        bad_ext[i + 1] = True
mask_clean = ~bad_ext & ~rollmask

print("n dias", len(d), "limpo", mask_clean.sum())
M_all = build_matrix(good_all, "todos")
M_cln = build_matrix(mask_clean, "limpo")
for tag, M in [("todos", M_all), ("limpo", M_cln)]:
    print(f"\n== matriz {tag}: {len(M)} pares testados; q<0,05: {(M.q_BH < 0.05).sum()}; q<0,10: {(M.q_BH < 0.10).sum()}")
    nm = M[~M.rotulo.str.contains("mecanico")]
    print(nm.head(20)[["X", "Y", "n", "rho", "p_perm", "q_BH", "estavel", "rotulo"]].to_string())

# sobreviventes entre os operaveis (alvo = variavel do pregao de D)
for tag, M in [("todos", M_all), ("limpo", M_cln)]:
    op = M[M.rotulo.str.startswith("preditivo OPERAVEL")].copy()
    op["q_BH_familia"] = bh(op.p_perm.values)
    op = op.sort_values("p_perm")
    op.to_csv(OUT / f"operaveis_{tag}.csv", index=False, sep=";", decimal=",")
    print(f"\n== operaveis {tag}: {len(op)} pares; q<0,05: {(op.q_BH_familia < 0.05).sum()}")
    print(op.head(12)[["X", "Y", "n", "rho", "p_perm", "q_BH_familia", "rho_H1", "rho_H2"]].to_string())

# ---------------------------------------------------------------- Parte 2: caminho M5
m1 = pd.read_parquet(ROOT / "data/win_sem_leiloes/m1_WIN$N.parquet")
m1 = m1[m1.index >= "2026-04-06"].copy()
m1["dia"] = m1.index.strftime("%Y-%m-%d")
dd = d.set_index("data")
# corrige contaminacao do leilao (1a barra) e do call (barra 18:24)
first_idx = m1.groupby("dia").head(1).index
last_idx = m1.groupby("dia").tail(1).index
adj = m1.real_volume.astype(float).copy()  # base sem leiloes: volume ja limpo, nao subtrair pre/pos
m1["vol"] = adj
m5 = m1.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum", "dia": "first"}).dropna(subset=["open"])
m5["dia"] = m5.index.strftime("%Y-%m-%d")
NB = 114
paths = {}
for dia, g in m5.groupby("dia"):
    g = g.copy()
    slot = ((g.index.hour * 60 + g.index.minute) - 540) // 5
    g = g.set_index(slot.values)
    full = g.reindex(range(NB))
    full.loc[NB - 1, "close"] = dd.loc[dia, "pregao_preco_fechamento"]
    full["close"] = full.close.ffill()
    paths[dia] = full
KS = [1, 3, 6, 12, 24]
rows = []
for dia, g in paths.items():
    r = dict(data=dia)
    o = dd.loc[dia, "pregao_preco_inicio"]
    endp = dd.loc[dia, "pregao_preco_fechamento"]
    for k in KS:
        ck = g.close.iloc[k - 1]
        r[f"mov{k}"] = ck - o
        r[f"rest{k}"] = endp - ck
        hi = g.high.iloc[k:].max(); lo = g.low.iloc[k:].min()
        r[f"amp{k}"] = hi - lo
        r[f"absrest{k}"] = abs(endp - ck)
        r[f"movabs{k}"] = abs(ck - o)
        r[f"rng{k}"] = g.high.iloc[:k].max() - g.low.iloc[:k].min()
    rows.append(r)
P = pd.DataFrame(rows).set_index("data").join(d.set_index("data")[["gap", "pre_vol", "pre_neg", "pos_ret", "preg_ret", "preg_rng", "pos_vol", "d_pre_vol"]])
P["gap_sinal"] = np.sign(P.gap)
P["mask_clean"] = pd.Series(mask_clean, index=d.data).reindex(P.index)
P.to_csv(OUT / "caminho_m5.csv", sep=";", decimal=",")


def split_tests(df, xs, ys, label_, tests, mask):
    pass


res = []


def add(fam, nome, x, y, mask, rotulo):
    x = x.values.astype(float).copy(); y = y.values.astype(float).copy()
    x[~mask] = np.nan; y[~mask] = np.nan
    n, rho, p = spearman_perm(x, y)
    h1 = (P.index < "2026-07-01")
    r1 = rho_only(np.where(h1, x, np.nan), np.where(h1, y, np.nan))
    r2 = rho_only(np.where(~h1, x, np.nan), np.where(~h1, y, np.nan))
    res.append(dict(familia=fam, relacao=nome, n=n, rho=rho, p_perm=p, rho_H1=r1, rho_H2=r2, rotulo=rotulo))


mk_all = np.ones(len(P), bool)
mk_cln = P.mask_clean.values.astype(bool)
for mname, mk in [("todos", mk_all), ("limpo", mk_cln)]:
    for k in KS:
        add(f"P2_{mname}", f"mov{k} -> rest{k} (todos)", P[f"mov{k}"], P[f"rest{k}"], mk, "preditivo OPERAVEL (barras fechadas)")
        add(f"P2_{mname}", f"|mov{k}| -> amp restante{k}", P[f"movabs{k}"], P[f"amp{k}"], mk, "preditivo OPERAVEL")
        add(f"P2_{mname}", f"rng ate k={k} -> amp restante", P[f"rng{k}"], P[f"amp{k}"], mk, "preditivo OPERAVEL")
        # condicionado ao gap: alinhamento
        al = np.sign(P.gap) * np.sign(P[f"mov{k}"])
        fav = (al > 0).values & mk; con = (al < 0).values & mk
        add(f"P2_{mname}", f"mov{k} -> rest{k} | gap A FAVOR do 1o mov", P[f"mov{k}"], P[f"rest{k}"], fav, "preditivo OPERAVEL")
        add(f"P2_{mname}", f"mov{k} -> rest{k} | gap CONTRA o 1o mov", P[f"mov{k}"], P[f"rest{k}"], con, "preditivo OPERAVEL")
        # terços de leilao
        pv = P.pre_vol
        q = pv.rank(pct=True)
        add(f"P2_{mname}", f"mov{k} -> rest{k} | leilao vol alto (tercil sup)", P[f"mov{k}"], P[f"rest{k}"], (q > 2 / 3).values & mk, "preditivo OPERAVEL")
        add(f"P2_{mname}", f"mov{k} -> rest{k} | leilao vol baixo (tercil inf)", P[f"mov{k}"], P[f"rest{k}"], (q <= 1 / 3).values & mk, "preditivo OPERAVEL")
        # call de D vs restante (contemporaneo)
        add(f"P2_{mname}", f"rest{k} -> pos_ret (call corrige o fim?)", P[f"rest{k}"], P.pos_ret, mk, "contemporaneo (call depois do pregao)")
        add(f"P2_{mname}", f"mov{k} -> pos_ret", P[f"mov{k}"], P.pos_ret, mk, "contemporaneo")
    add(f"P2_{mname}", "preg_ret -> pos_ret", P.preg_ret, P.pos_ret, mk, "contemporaneo")
    add(f"P2_{mname}", "gap -> mov1", P.gap, P.mov1, mk, "preditivo OPERAVEL")
    add(f"P2_{mname}", "gap -> rest1 (restante pos 1a barra)", P.gap, P.rest1, mk, "preditivo OPERAVEL")
    add(f"P2_{mname}", "gap -> rest3", P.gap, P.rest3, mk, "preditivo OPERAVEL")
    add(f"P2_{mname}", "gap -> preg_ret", P.gap, P.preg_ret, mk, "preditivo OPERAVEL")
R = pd.DataFrame(res)
for fam in R.familia.unique():
    s = R.familia == fam
    R.loc[s, "q_BH"] = bh(R.loc[s, "p_perm"].values)
R["estavel"] = np.sign(R.rho_H1) == np.sign(R.rho_H2)
R.to_csv(OUT / "parte2_testes.csv", index=False, sep=";", decimal=",")
for fam in R.familia.unique():
    s = R[R.familia == fam]
    print(f"\n== {fam}: {len(s)} testes; q<0,05: {(s.q_BH < 0.05).sum()}")
    print(s.sort_values("p_perm").head(14)[["relacao", "n", "rho", "p_perm", "q_BH", "rho_H1", "rho_H2"]].to_string())

# tabela de continuidade por alinhamento gap x 1o movimento
print("\n== Continuidade do restante (pts na direcao do mov ate k) por alinhamento gap x mov")
tab = []
H1 = (P.index < "2026-07-01")
for mname, ms in [("todos", mk_all), ("limpo", mk_cln)]:
    for k in KS:
        al = (np.sign(P.gap) * np.sign(P[f"mov{k}"])).values
        cont = (np.sign(P[f"mov{k}"]) * P[f"rest{k}"]).values
        grp = {"a favor": (al > 0) & ms, "contra": (al < 0) & ms, "todos": ms & np.isfinite(al)}
        for nome, sel in grp.items():
            v = cont[sel]; s_ = v
            null = (s_[None, :] * RNG.choice([-1, 1], (5000, len(s_)))).mean(axis=1)
            pp = (1 + np.sum(np.abs(null) >= abs(s_.mean()))) / 5001
            tab.append(dict(base=mname, k=k, grupo=nome, n=len(v), media_pts=v.mean(), mediana=np.median(v), pct_continua=(v > 0).mean() * 100,
                            p_signflip=pp, media_H1=cont[sel & H1].mean(), n_H1=int((sel & H1).sum()), media_H2=cont[sel & ~H1].mean(), n_H2=int((sel & ~H1).sum())))
        # diferenca contra - favor, permutacao dos rotulos
        sel = grp["contra"] | grp["a favor"]
        g = (al[sel] < 0).astype(int); c = cont[sel]
        dif = c[g == 1].mean() - c[g == 0].mean()
        nl = np.array([ (lambda gg: c[gg == 1].mean() - c[gg == 0].mean())(RNG.permutation(g)) for _ in range(5000)])
        tab.append(dict(base=mname, k=k, grupo="DIF contra-favor", n=int(sel.sum()), media_pts=dif, p_signflip=(1 + np.sum(np.abs(nl) >= abs(dif))) / 5001))
T = pd.DataFrame(tab)
T["q_BH_base"] = np.nan
for mname in ["todos", "limpo"]:
    s2 = (T.base == mname) & T.grupo.isin(["a favor", "contra", "DIF contra-favor"])
    T.loc[s2, "q_BH_base"] = bh(T.loc[s2, "p_signflip"].values)
T.to_csv(OUT / "continuidade_por_alinhamento.csv", index=False, sep=";", decimal=",")
print(T.round(3).to_string())
print("\ntamanho tipico: |rest| mediana k=1,6,24:", P.absrest1.median(), P.absrest6.median(), P.absrest24.median(), " std preg_ret:", d.preg_ret.std())

# gap vs 1o movimento: preenche o gap?
gap_fill = []
for dia, g in paths.items():
    gp = dd.loc[dia, "gap"] if not np.isnan(dd.loc[dia, "gap"]) else np.nan
    gap_fill.append(dict(data=dia))
# ---------------------------------------------------------------- Parte 3: perfil de volume
prof = pd.DataFrame({dia: g["vol"].values for dia, g in paths.items()}).T
prof = prof.fillna(0)
tot = prof.sum(axis=1)
share = prof.div(tot, axis=0)
perfil = pd.DataFrame({"hora": [f"{9 + (5 * i) // 60:02d}:{(5 * i) % 60:02d}" for i in range(NB)],
                       "media_contratos": prof.mean().values, "mediana_contratos": prof.median().values,
                       "media_share_%": share.mean().values * 100})
perfil.to_csv(OUT / "perfil_volume_m5.csv", index=False, sep=";", decimal=",")
print("\n== perfil de volume M5 (share % do volume do pregao)")
hr = lambda a, b: share.iloc[:, a:b].sum(axis=1)
blocks = {"09:00-10:00": (0, 12), "10:00-11:00": (12, 24), "11:00-12:00": (24, 36), "12:00-13:00": (36, 48), "13:00-14:00": (48, 60),
          "14:00-15:00": (60, 72), "15:00-16:00": (72, 84), "16:00-17:00": (84, 96), "17:00-18:00": (96, 108), "18:00-18:25": (108, 114)}
bt = pd.DataFrame({k: [hr(*v).mean() * 100, hr(*v).std() * 100] for k, v in blocks.items()}, index=["media%", "dp%"]).T
bt["por_barra_%"] = bt["media%"] / [(b - a) for a, b in blocks.values()]
print(bt.round(2).to_string())
bt.to_csv(OUT / "perfil_blocos_hora.csv", sep=";", decimal=",")
print("barras M5 de maior share:", perfil.sort_values("media_share_%", ascending=False).head(6)[["hora", "media_share_%"]].to_string(index=False))
print("barra min:", perfil.sort_values("media_share_%").head(3)[["hora", "media_share_%"]].to_string(index=False))

# leilao grande -> volume 1a hora e amplitude restante
Q = pd.DataFrame(index=P.index)
Q["vol_1h"] = prof.iloc[:, :12].sum(axis=1)
Q["share_1h"] = share.iloc[:, :12].sum(axis=1)
Q["vol_resto"] = prof.iloc[:, 12:].sum(axis=1)
Q["vol_dia"] = tot
Q["pre_vol"] = P.pre_vol
Q["pre_neg"] = P.pre_neg
Q["abs_gap"] = P.gap.abs()
Q["pre_vol_rel"] = P.pre_vol / P.pre_vol.rolling(20, min_periods=10).mean().shift(1)  # relativo a media movel D-1 para tras
Q["vol_1h_rel"] = Q.vol_1h / Q.vol_1h.rolling(20, min_periods=10).mean().shift(1)
amp12 = []; ret12 = []; range1h = []
for dia, g in paths.items():
    amp12.append(g.high.iloc[12:].max() - g.low.iloc[12:].min())
    ret12.append(abs(dd.loc[dia, "pregao_preco_fechamento"] - g.close.iloc[11]))
    range1h.append(g.high.iloc[:12].max() - g.low.iloc[:12].min())
Q["amp_rest_1h"] = amp12; Q["absret_rest_1h"] = ret12; Q["range_1h"] = range1h
Q["preg_ret"] = P.preg_ret
Q["mask_clean"] = P.mask_clean
Q.to_csv(OUT / "volume_1h.csv", sep=";", decimal=",")
res3 = []


def add3(nome, x, y, mk, rot):
    xv = x.values.astype(float).copy(); yv = y.values.astype(float).copy()
    xv[~mk] = np.nan; yv[~mk] = np.nan
    n, rho, p = spearman_perm(xv, yv)
    h1 = (Q.index < "2026-07-01")
    res3.append(dict(relacao=nome, n=n, rho=rho, p_perm=p, rho_H1=rho_only(np.where(h1, xv, np.nan), np.where(h1, yv, np.nan)),
                     rho_H2=rho_only(np.where(~h1, xv, np.nan), np.where(~h1, yv, np.nan)), rotulo=rot))


for mname, mk in [("todos", np.ones(len(Q), bool)), ("limpo", Q.mask_clean.values.astype(bool))]:
    s = lambda nm: f"[{mname}] {nm}"
    add3(s("pre_vol -> vol_1h"), Q.pre_vol, Q.vol_1h, mk, "preditivo OPERAVEL")
    add3(s("pre_neg -> vol_1h"), Q.pre_neg, Q.vol_1h, mk, "preditivo OPERAVEL")
    add3(s("pre_vol -> share_1h"), Q.pre_vol, Q.share_1h, mk, "preditivo OPERAVEL")
    add3(s("pre_vol_rel(vs media20) -> vol_1h_rel"), Q.pre_vol_rel, Q.vol_1h_rel, mk, "preditivo OPERAVEL")
    add3(s("|gap| -> vol_1h"), Q.abs_gap, Q.vol_1h, mk, "preditivo OPERAVEL")
    add3(s("pre_vol -> amp restante apos 10h"), Q.pre_vol, Q.amp_rest_1h, mk, "preditivo OPERAVEL")
    add3(s("pre_vol -> |ret| restante apos 10h"), Q.pre_vol, Q.absret_rest_1h, mk, "preditivo OPERAVEL")
    add3(s("vol_1h -> amp restante apos 10h"), Q.vol_1h, Q.amp_rest_1h, mk, "preditivo OPERAVEL (10:00, barras fechadas)")
    add3(s("vol_1h -> |ret| restante apos 10h"), Q.vol_1h, Q.absret_rest_1h, mk, "preditivo OPERAVEL (10:00)")
    add3(s("vol_1h_rel -> amp restante"), Q.vol_1h_rel, Q.amp_rest_1h, mk, "preditivo OPERAVEL (10:00)")
    add3(s("range_1h -> amp restante"), Q.range_1h, Q.amp_rest_1h, mk, "preditivo OPERAVEL (10:00)")
    add3(s("vol_1h -> vol_resto"), Q.vol_1h, Q.vol_resto, mk, "preditivo OPERAVEL (10:00)")
    add3(s("pre_vol -> vol_resto"), Q.pre_vol, Q.vol_resto, mk, "preditivo OPERAVEL")
    add3(s("|gap| -> amp restante"), Q.abs_gap, Q.amp_rest_1h, mk, "preditivo OPERAVEL")
R3 = pd.DataFrame(res3)
R3["q_BH"] = bh(R3.p_perm.values)
R3["estavel"] = np.sign(R3.rho_H1) == np.sign(R3.rho_H2)
R3.to_csv(OUT / "parte3_testes.csv", index=False, sep=";", decimal=",")
print("\n== Parte 3: testes", len(R3), "q<0,05:", (R3.q_BH < 0.05).sum())
print(R3.to_string())
# tercis de leilao: medias
for mname, mk in [("todos", np.ones(len(Q), bool)), ("limpo", Q.mask_clean.values.astype(bool))]:
    q = Q[mk].copy()
    q["tercil_leilao"] = pd.qcut(q.pre_vol, 3, labels=["baixo", "medio", "alto"])
    print(f"\n[{mname}] medias por tercil de volume do leilao")
    print(q.groupby("tercil_leilao")[["pre_vol", "vol_1h", "share_1h", "vol_resto", "amp_rest_1h", "absret_rest_1h", "range_1h"]].mean().round(2).to_string())
    print(q.groupby("tercil_leilao").size().to_string())
