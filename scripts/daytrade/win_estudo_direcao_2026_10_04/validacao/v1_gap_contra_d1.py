"""
V1 - Validacao: "o gap de abertura vai CONTRA o dia anterior" (WIN@D e WDO@D, M1).

CRITERIO DE "VALIDADO" (escrito ANTES de rodar; nao muda depois)
Estatistica central: taxa de CONCORDANCIA sign(gap)==sign(retorno D-1) contra o esperado sob independencia
(esperado = pg*pr + (1-pg)*(1-pr), marginais da propria amostra). diff = concordancia - esperado (pp). "Contra" = diff<0.
(a) direcao do retorno de D-1 (close-close);  (b) direcao dos ULTIMOS 30 MIN de D-1.
Passa em cada checagem se:
 C1 rolagem   : WIN, excluindo +-1 e +-3 dias uteis da rolagem, diff<0 com p<0,05 (bicaudal, normal) nas duas exclusoes;
                e gaps de abr-out/2026 do @D batem com WINV26 (sinal igual em >=95% dos dias).
 C2 horario   : TODAS as variantes (fech. 17:55; fech. 17:00; fech. media 10 min; abertura 9:05; 9:15; 17:55+9:05)
                com diff<=-3pp e p<0,05 no WIN agrupado.
 C3 reversao  : INTERPRETATIVA (nao entra no veredito): o overnight e "especial" se a diff do gap for menor que a diff
                dos pares de blocos de 30 min adjacentes intradia (agrupado) por >=3pp com ICs nao sobrepostos;
                senao e a mesma reversao de sempre.
 C4 ano a ano : WIN, diff<0 em >=4 dos 5 anos completos (2022-2026; 2026 ate set) E agrupado p<0,05.
 C5 WDO       : agrupado diff<0 com p<0,05 E diff<0 em >=3 dos 5 anos (2022-2026).
VALIDADO = C1, C2, C4, C5 todas passam (para o achado (a); (b) julgado igual, separadamente).
INCONCLUSIVO = so' falha por margem estreita (p entre 0,05 e 0,10); NAO VALIDADO = caso contrario.
A janela 2025+ ja foi vista: nao e OOS; so' estabilidade por ano, outro ativo e artefatos contam.
"""
import math
import numpy as np, pandas as pd
from pathlib import Path
OUT = Path(__file__).parent
BASE = Path(r"C:\Users\Jeffe\Documents\study\meta\data\wdo-mt5")
FILES = {"WIN": BASE / "WIN@D_M1_202110010900_202610011717.csv", "WDO": BASE / "WDO@D_M1_202109290900_202609291020.csv"}
BLK = list(range(9 * 60 + 30, 17 * 60 + 31, 30))  # fim de blocos de 30 min
BASEV = "base (fech ultima barra; abre 1a)"


def le(m, c, t):
    i = np.searchsorted(m, t, "right") - 1
    return c[i] if i >= 0 else np.nan


def ge_open(m, o, t):
    i = np.searchsorted(m, t, "left")
    return o[i] if i < len(m) else np.nan


def build(path):
    d = pd.read_csv(path, sep="\t")
    d["dt"] = pd.to_datetime(d["<DATE>"] + " " + d["<TIME>"])
    d["day"] = d.dt.dt.normalize()
    d["min"] = d.dt.dt.hour * 60 + d.dt.dt.minute
    rows = {}
    for day, g in d.groupby("day", sort=True):
        m = g["min"].values; o = g["<OPEN>"].values; c = g["<CLOSE>"].values
        r = dict(n=len(g), t0=m[0], t1=m[-1], O=o[0], H=g["<HIGH>"].max(), L=g["<LOW>"].min(), C=c[-1])
        r.update(O905=ge_open(m, o, 545), O915=ge_open(m, o, 555),
                 C1755=le(m, c, 17 * 60 + 54), C1700=le(m, c, 16 * 60 + 59), Cavg10=c[-10:].mean(),
                 Cm30=le(m, c, m[-1] - 30), C1725=le(m, c, 17 * 60 + 24),
                 e5=le(m, c, 9 * 60 + 4), e15=le(m, c, 9 * 60 + 14), e30=le(m, c, 9 * 60 + 29))
        for k, t in enumerate(BLK):
            r[f"b{k}"] = le(m, c, t - 1)
        rows[day] = r
    D = pd.DataFrame.from_dict(rows, orient="index")
    D = D[(D.t0 < 600) & (D.n > 300)]
    if D.n.iloc[-1] < 400:
        D = D.iloc[:-1]
    return D


def prep(D, nome):
    D = D.copy()
    D["Cp"] = D.C.shift(1); D["Cp2"] = D.C.shift(2)
    D["tr"] = np.maximum(D.H - D.L, np.maximum((D.H - D.Cp).abs(), (D.L - D.Cp).abs()))
    D["atr"] = D.tr.rolling(14).mean().shift(1)
    idx = D.index
    if nome == "WIN":
        ex = []
        for y in range(2021, 2027):
            for mth in (2, 4, 6, 8, 10, 12):
                dd = pd.Timestamp(y, mth, 15); w = (2 - dd.weekday()) % 7
                cand = [dd + pd.Timedelta(days=w), dd + pd.Timedelta(days=w - 7)]
                ex.append(min(cand, key=lambda x: abs((x - dd).days)))
    else:
        ex = [g.index[0] for _, g in D.groupby([idx.year, idx.month])]
    pos = np.searchsorted(idx.values, np.array(ex, dtype="datetime64[ns]"))
    pos = pos[pos < len(idx)]
    ipos = np.arange(len(idx))
    ar = np.full(len(idx), 999)
    for p in pos:
        ar = np.where(np.abs(ipos - p) < np.abs(ar), ipos - p, ar)
    D["roll_dist"] = np.abs(ar)
    return D


def wilson(k, n):
    p = k / n; z = 1.96; den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def conc(g, r):
    ok = (g != 0) & (r != 0) & g.notna() & r.notna()
    g = g[ok]; r = r[ok]; n = len(g)
    nan = np.nan
    if n < 20:
        return dict(n=n, conc=nan, esp=nan, diff=nan, lo=nan, hi=nan, p=nan, pgu_ru=nan, pgu_rd=nan)
    sg = g > 0; sr = r > 0; k = int((sg == sr).sum())
    pg, pr = sg.mean(), sr.mean(); esp = pg * pr + (1 - pg) * (1 - pr)
    z = (k / n - esp) / math.sqrt(esp * (1 - esp) / n); p = math.erfc(abs(z) / math.sqrt(2))
    lo, hi = wilson(k, n)
    return dict(n=n, conc=k / n * 100, esp=esp * 100, diff=(k / n - esp) * 100, lo=(lo - esp) * 100, hi=(hi - esp) * 100,
                p=p, pgu_ru=sg[sr].mean() * 100, pgu_rd=sg[~sr].mean() * 100)


def variantes(D):
    V = {}
    def mk(nome, Cc, Oo, ref):
        V[nome] = (Oo - Cc.shift(1), Cc.shift(1) - Cc.shift(2), Cc.shift(1) - ref.shift(1))
    mk(BASEV, D.C, D.O, D.Cm30)
    mk("fech 17:55", D.C1755, D.O, D.C1725)
    mk("fech 17:00", D.C1700, D.O, D.C1700)  # (b) nao se aplica
    mk("fech media 10min", D.Cavg10, D.O, D.Cm30)
    mk("abre 9:05", D.C, D.O905, D.Cm30)
    mk("abre 9:15", D.C, D.O915, D.Cm30)
    mk("fech 17:55 + abre 9:05", D.C1755, D.O905, D.C1725)
    return V


def tabela_var(D, mask, rot, so_base=None):
    out = []
    for nome, (g, ra, rb) in variantes(D).items():
        if so_base is True and nome != BASEV: continue
        if so_base is False and nome == BASEV: continue
        for lab, rr in (("a", ra), ("b", rb)):
            if nome == "fech 17:00" and lab == "b": continue
            s = conc(g[mask], rr[mask]); s.update(rot=rot, variante=nome, achado=lab); out.append(s)
    return out


res = {}
for ativo in ("WIN", "WDO"):
    D = prep(build(FILES[ativo]), ativo).dropna(subset=["atr", "Cp2"]).copy()
    D["ano"] = D.index.year
    res[ativo] = D
    print(ativo, len(D), D.index[0].date(), D.index[-1].date(), "t1 moda", D.t1.mode()[0], flush=True)

lin = []
for ativo, D in res.items():
    for rot, mask in (("todos", D.roll_dist > -1), ("sem rolagem +-1", D.roll_dist > 1), ("sem rolagem +-3", D.roll_dist > 3)):
        lin += [dict(x, ativo=ativo) for x in tabela_var(D, mask, rot, True)]
    lin += [dict(x, ativo=ativo) for x in tabela_var(D, D.roll_dist > -1, "variantes", False)]
T = pd.DataFrame(lin); T.to_csv(OUT / "v1_checagens_1_2.csv", sep=";", decimal=",", index=False)
print(T.round(3).to_string(), flush=True)

# C1b WINV26 x @D
v = pd.read_csv(BASE / "WINV26_M1_202604151210_202610011824.csv", sep="\t")
v["dt"] = pd.to_datetime(v["<DATE>"] + " " + v["<TIME>"]); v["day"] = v.dt.dt.normalize()
gv = v.groupby("day"); V = pd.DataFrame({"O": gv["<OPEN>"].first(), "C": gv["<CLOSE>"].last(), "n": gv.size()})
V = V[V.n > 300]; V["gapV"] = V.O - V.C.shift(1)
D = res["WIN"]; j = V.join((D.O - D.Cp).rename("gapD"), how="inner").dropna()
j["sinal_igual"] = np.sign(j.gapV) == np.sign(j.gapD); j["dif"] = (j.gapV - j.gapD).abs()
j["roll_dist"] = D.roll_dist.reindex(j.index)
j.to_csv(OUT / "v1_winv26_vs_arquivoD.csv", sep=";", decimal=",")
print("WINV26 vs @D:", dict(n=len(j), sinal_igual_pct=j.sinal_igual.mean() * 100, dif_mediana=j.dif.median(), dif_max=j.dif.max(),
                            n_dif_gt_100=int((j.dif > 100).sum())), flush=True)
print(j[j.dif > 100].to_string(), flush=True)
V["ret1"] = V.C.shift(1) - V.C.shift(2)
print("WINV26 efeito (a) contrato unico:", conc(V.gapV, V.ret1), flush=True)

# C4/C5 ano a ano
lin = []
for ativo, D in res.items():
    g, ra, rb = variantes(D)[BASEV]
    for ano, idx in D.groupby("ano").groups.items():
        for lab, rr in (("a", ra), ("b", rb)):
            s = conc(g.loc[idx], rr.loc[idx]); s.update(ativo=ativo, ano=ano, achado=lab); lin.append(s)
Y = pd.DataFrame(lin); Y.to_csv(OUT / "v1_ano_a_ano.csv", sep=";", decimal=",", index=False)
print(Y.round(3).to_string(), flush=True)

# C3 reversao intradia vs overnight
lin = []
for ativo, D in res.items():
    g, ra, rb = variantes(D)[BASEV]
    s = conc(g, rb); s.update(ativo=ativo, par="overnight: ult30min D-1 -> gap"); lin.append(s)
    s = conc(g, ra); s.update(ativo=ativo, par="overnight: ret D-1 -> gap"); lin.append(s)
    B = D[[f"b{k}" for k in range(len(BLK))]].copy(); B.insert(0, "O", D.O)
    G = []; R = []
    for k in range(1, len(BLK) - 1):
        r1 = B.iloc[:, k] - B.iloc[:, k - 1]; r2 = B.iloc[:, k + 1] - B.iloc[:, k]
        s = conc(r2, r1); s.update(ativo=ativo, par=f"intradia blocos 30min #{k}->#{k+1}"); lin.append(s)
        G.append(r2.reset_index(drop=True)); R.append(r1.reset_index(drop=True))
    Gc = pd.concat(G, ignore_index=True); Rc = pd.concat(R, ignore_index=True)
    s = conc(Gc, Rc); s.update(ativo=ativo, par="intradia blocos 30min AGRUPADO"); lin.append(s)
    lin.append(dict(ativo=ativo, par="corr(gap/ATR, ult30/ATR) overnight", conc=(g / D.atr).corr(rb / D.atr)))
    lin.append(dict(ativo=ativo, par="corr(bloco30 seguinte, anterior) intradia agrupado", conc=Gc.corr(Rc)))
R3 = pd.DataFrame(lin); R3.to_csv(OUT / "v1_reversao_intradia.csv", sep=";", decimal=",", index=False)
print(R3.round(3).to_string(), flush=True)

# C6 magnitude e transmissao
lin = []
for ativo, D in res.items():
    g = D.O - D.Cp; ra = D.Cp - D.Cp2
    for nome, cond in (("D-1 alta", ra > 0), ("D-1 baixa", ra < 0), ("todos", ra == ra)):
        sub = D[cond]; gg = g[cond]
        lin.append(dict(ativo=ativo, cond=nome, n=len(sub), gap_medio_pts=gg.mean(), gap_medio_atr=(gg / sub.atr).mean(),
                        gap_abs_med_pts=gg.abs().median(), gap_abs_med_atr=(gg.abs() / sub.atr).median(), atr_med=sub.atr.median(),
                        efeito_pts_vs_todos=gg.mean() - g.mean()))
    ok = g != 0
    for h, col in ((5, "e5"), (15, "e15"), (30, "e30")):
        fav = ((D[col] - D.O) * np.sign(g))[ok]
        k = int((fav > 0).sum()); n = int((fav != 0).sum()); lo, hi = wilson(k, n)
        lin.append(dict(ativo=ativo, cond=f"gap -> primeiros {h}min a favor do gap", n=n, taxa=k / n * 100,
                        ic=f"[{lo*100:.1f};{hi*100:.1f}]", ret_favor_medio_pts=fav.mean(), ret_favor_atr=(fav / D.atr[ok]).mean()))
    for nome, cond in (("gap contra D-1", (np.sign(g) == -np.sign(ra)) & ok), ("gap a favor de D-1", (np.sign(g) == np.sign(ra)) & ok)):
        r = ((D.e30 - D.O) * np.sign(g))[cond]; k = int((r > 0).sum()); n = int((r != 0).sum()); lo, hi = wilson(k, n)
        lin.append(dict(ativo=ativo, cond=f"{nome}: 30min a favor do gap", n=n, taxa=k / n * 100,
                        ic=f"[{lo*100:.1f};{hi*100:.1f}]", ret_favor_medio_pts=r.mean()))
M = pd.DataFrame(lin); M.to_csv(OUT / "v1_magnitude_transmissao.csv", sep=";", decimal=",", index=False)
print(M.round(3).to_string(), flush=True)
