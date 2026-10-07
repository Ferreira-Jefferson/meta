"""Z7 - dias extremos (G1 gap, G2 dia seguinte a pregao largo). Pre-registro no TODO.md."""
import sys, numpy as np, pandas as pd
from pathlib import Path
from datetime import date, timedelta
ROOT = Path(__file__).resolve().parents[5]
B = ROOT/"scripts/daytrade/comparativo_win_2026"; C = B/"combinacoes"; OUT = Path(__file__).parent
def p(*a): print(*a, flush=True)
def venc(ano, mes):
    t15 = date(ano, mes, 15); mql = (t15.weekday()+1) % 7
    dif = 3-mql
    if dif > 3: dif -= 7
    if dif < -3: dif += 7
    return t15+timedelta(days=dif)
rolagens = set()
for a in range(2021, 2027):
    for m in (2,4,6,8,10,12): rolagens.add(venc(a,m))   # empirico: o WIN$N salta NO dia do vencimento (gap 1,2-1,6 ATR so' nessas datas), nao no seguinte

# M1 -> diarias
m = pd.concat([pd.read_parquet(ROOT/"data/comparativo_win_2026/m1_WIN$N_2022_2025.parquet"),
               pd.read_parquet(ROOT/"data/comparativo_win_2026/m1_WIN$N.parquet")])
m = m[~m.index.duplicated(keep="first")].sort_index()
m = m[m.index.time <= pd.Timestamp("18:25").time()]
m["d"] = m.index.date
g = m.groupby("d")
D = pd.DataFrame({"o": g.open.first(), "h": g.high.max(), "l": g.low.min(), "c": g.close.last()})
D = D[(D.index >= date(2021,12,1)) & (D.index <= date(2026,10,5))]
dias = list(D.index)
# roll: dia seguinte ao vencimento = 1o pregao >= rolagem que ainda nao... (a data util seguinte ao vencimento)
roll_dias = set()
for r in rolagens:
    nxt = [d for d in dias if d >= r]
    if nxt and (nxt[0]-r).days < 4: roll_dias.add(nxt[0])
pc = D.c.shift(1)
D["gap"] = (D.o-pc).abs(); D["gap_s"] = D.o-pc
D["roll"] = [d in roll_dias for d in D.index]
amp = D.h-D.l
tr = np.maximum.reduce([amp, (D.h-pc).abs(), (D.l-pc).abs()])
tr = pd.Series(np.where(D.roll, amp, tr), index=D.index)   # no dia de rolagem o TR ignora o gap artificial
D["amp"] = amp
D["atr"] = tr.shift(1).rolling(14).mean()
D["gap_atr"] = D.gap/D.atr
D["amp_atr"] = D.amp/D.atr
D["amp_ant_atr"] = D.amp_atr.shift(1)   # ATR usado e' o do pregao extremo (14 anteriores a ele)
D["ant"] = pd.Series(dias, index=D.index).shift(1)
D = D[D.index >= date(2022,1,1)]
p("pregoes", len(D), "rolagens no periodo", sum(1 for d in roll_dias if d >= date(2022,1,1)))
p("05/10/2026:", D.loc[date(2026,10,5), ["o","gap_s","gap_atr"]].to_dict())

# trades
F = {"cinco": [C/"y_tempos/cinco/trades/cinco_M120_2022_2025.csv", B/"resultados/WinCincoMedias.csv"],
     "desloc": [C/"x_fixas/x0b/resultados_2022_2025/WinDeslocamentoMatinal.csv", B/"resultados/WinDeslocamentoMatinal.csv"],
     "win_c1": [C/"y_tempos/win/trades/Win_c1_M60_2225.csv", B/"resultados/Win_c1.csv"],
     "win": [C/"y_tempos/win/trades/Win_M60_2225.csv", B/"resultados/Win.csv"],
     "ret34": [C/"z5_f3_varredura/trades/k0.5_2022_2025.csv", B/"resultados/WinRetanguloEma34.csv"]}
T = []
for r, fs in F.items():
    for f in fs:
        t = pd.read_csv(f, usecols=["entrada","saida","rs"], dtype=str)
        t["entrada"]=pd.to_datetime(t.entrada.str.slice(0,19)); t["saida"]=pd.to_datetime(t.saida.str.slice(0,19)); t["rs"]=t.rs.astype(float); t["robo"] = r; T.append(t)
T = pd.concat(T, ignore_index=True)
T = T[T.entrada.dt.date <= date(2026,10,5)]
T["dia"] = T.entrada.dt.date; T["ano"] = T.entrada.dt.year
T["liq"] = T.rs-2.0
exc = T[T.entrada.dt.date != T.saida.dt.date]
p("trades", len(T), "que atravessam a noite:", len(exc))
if len(exc): p(exc.head(10).to_string())
sem_pregao = sorted(set(T.dia)-set(D.index)); p("dias de trade sem pregao na base:", sem_pregao)
robos = list(F)
tab = T.groupby(["ano","robo"]).liq.sum().unstack().reindex(columns=robos).fillna(0)
tab["SOMA"] = tab.sum(axis=1); anos = list(tab.index)
base = tab.SOMA
# matriz dia x robo de liquido
dr = T.groupby(["dia","robo"]).liq.sum().unstack().reindex(columns=robos).fillna(0)
dr = dr.reindex(D.index).fillna(0)
dr_soma = dr.sum(axis=1)
ano_d = pd.Series([d.year for d in D.index], index=D.index)

regras = {}
for k in (1.0,1.5,2.0):
    regras[f"G1_k{k}"] = (D.gap_atr >= k) & ~D.roll
for mm in (2.0,2.5):
    regras[f"G2_m{mm}"] = D.amp_ant_atr.shift(0) >= mm
notas_dia = {date(2022,10,2):"eleicao 1o turno (domingo)", date(2022,10,3):"dia seguinte a eleicao 1o turno",
 date(2022,10,31):"dia seguinte a eleicao 2o turno 2022", date(2022,10,28):"vespera 2o turno",
 date(2024,10,7):"dia seguinte a municipal 1o turno", date(2024,10,28):"dia seguinte a municipal 2o turno",
 date(2026,10,5):"dia seguinte ao 1o turno 2026 (gap real +9,2%)", date(2022,2,24):"invasao da Ucrania (global)", date(2024,8,5):"crash global (yen carry)", date(2025,4,4):"tarifas EUA (global)", date(2025,4,8):"dia apos crash tarifas"}
rng = np.random.default_rng(20261006)
rows = []; blk_rows = []; out = []
pools = {a: np.where(ano_d.values == a)[0] for a in anos}
for nome, mask in regras.items():
    mask = mask.fillna(False)
    bl = D.index[mask.values]
    p(f"\n=== {nome}: {len(bl)} dias bloqueados")
    for d in bl:
        r = D.loc[d]
        nt = int((T.dia == d).sum()); pl = dr_soma.loc[d]
        nota = notas_dia.get(d, "")
        if d in notas_dia or (d+timedelta(days=1)) in notas_dia: nota = nota or "vespera/posterior de evento eleitoral"
        blk_rows.append(dict(regra=nome, data=d, gap_pts=r.gap_s, gap_atr=round(r.gap_atr,2), amp_atr=round(r.amp_atr,2),
                             amp_ant_atr=round(r.amp_ant_atr,2) if pd.notna(r.amp_ant_atr) else None, n_ops=nt, liq_removido=round(pl,1), nota=nota))
    nb = {a: int(((ano_d.values == a) & mask.values).sum()) for a in anos}
    p("por ano:", nb)
    rem = dr_soma[mask.values].groupby(ano_d[mask.values]).sum().reindex(anos).fillna(0)
    novo = base-rem
    delta = -rem
    anos_melhor = int((delta > 0).sum())
    # sorteio
    sims = np.zeros(1000); sims_ano = np.zeros((1000, len(anos)))
    v = dr_soma.values
    for s in range(1000):
        for i, a in enumerate(anos):
            n = nb[a]
            if n: sims_ano[s, i] = -v[rng.choice(pools[a], n, replace=False)].sum()
    sims = sims_ano.sum(axis=1); real = delta.sum()
    pct = (sims < real).mean()*100
    pct_ano = [(sims_ano[:, i] < delta.loc[a]).mean()*100 for i, a in enumerate(anos)]
    p("delta soma por ano:", delta.round(0).to_dict(), "total", round(real,1), "anos melhores", anos_melhor, "percentil", pct)
    row = dict(regra=nome, **{f"dias_{a}": nb[a] for a in anos}, **{f"base_{a}": round(base[a],1) for a in anos},
               **{f"regra_{a}": round(novo[a],1) for a in anos}, **{f"delta_{a}": round(delta[a],1) for a in anos},
               base_total=round(base.sum(),1), regra_total=round(novo.sum(),1), delta_total=round(real,1),
               anos_melhores=anos_melhor, percentil=round(pct,1), sorteio_p50=round(np.median(sims),1), sorteio_p95=round(np.percentile(sims,95),1))
    # por robo
    for rb in robos:
        remr = dr[rb][mask.values].groupby(ano_d[mask.values]).sum().reindex(anos).fillna(0)
        for a in anos: row[f"delta_{rb}_{a}"] = round(-remr[a],1)
        row[f"delta_{rb}_total"] = round(-remr.sum(),1)
        row[f"anos_melhores_{rb}"] = int(((-remr) > 0).sum())
    rows.append(row)
R = pd.DataFrame(rows); R.to_csv(OUT/"resultado.csv", index=False)
BL = pd.DataFrame(blk_rows); BL.to_csv(OUT/"dias_bloqueados.csv", index=False)
tab.round(1).to_csv(OUT/"base_por_ano_robo.csv")
p("\nBASE por ano x robo (liq c/ custo R$2)"); p(tab.round(0).to_string())
p(R[["regra","anos_melhores","delta_total","percentil"]+[f"delta_{a}" for a in anos]].to_string())
p("\nDIAS BLOQUEADOS"); p(BL.to_string())
if len(sys.argv) > 1 and sys.argv[1] == "diag":
    for a in range(2022, 2027):
        for mes in (2,4,6,8,10,12):
            v = venc(a, mes)
            if v > date(2026,10,5): continue
            ds = [d for d in D.index if abs((d-v).days) <= 4]
            p(v, [(str(d)[5:], round(float(D.loc[d,'gap_atr']),2)) for d in ds])
