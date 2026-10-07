"""N2 -- RDT (Recuo no Dia de Tendencia), implementacao EXATA do PREREGISTRO.md (+ DECISAO DO ORQUESTRADOR).

Uso:  python n2_rdt.py dev    -> grade de 12 celulas no DEV, escolha pela regra pre-registrada, controle aleatorio
      python n2_rdt.py val    -> VAL UMA vez, so' com a celula congelada (le n2_celula_congelada.json; recusa se o
                                 hash deste arquivo nao bate com o gravado no PREREGISTRO ou se o VAL ja rodou)
Regras: O = abertura da 1a M1; ATRd = media simples do TR de 14 D1 FECHADAS (serie ajustada por diferenca);
decisao as 10:30 com M1 fechadas ate' 10:29; sinal se |desl|>=k e nenhuma M1 fechada do outro lado de O -/+ 0,05 ATRd;
limite a favor em O+f*(c1029-O) (grade de 5), valida ate' `ate`; stop a mercado em O -/+ 0,05 ATRd; sem alvo; zera >=17:50;
1 contrato, 1 op/dia, R$0,20/pt, custo R$2/op, capital R$1.000 corrido. Execucao do Testador (ticks sinteticos 4/M1).
Caixa/DD medidos sobre o caixa FECHADO operacao a operacao (com custo).
"""
import sys, json, hashlib
from pathlib import Path
import numpy as np, pandas as pd
import dados_dev as D
from explora_lib import m1_ajustada, sim, arred, CUSTO_PTS

AQUI = Path(__file__).resolve().parent
RS = 0.20
CAP = 1000.0
FOLGA = 0.05
GRADE = [(f, ate, k) for k in (0.3, 0.4) for ate in ("12:00", "14:00") for f in (0.25, 0.5, 0.75)]
_TK = {}


def ms(t):
    return int(pd.Timestamp(t).value // 10**6)


def preparar():
    """Por dia (DEV e VAL): O, c1029, atr, desl, cruzou -- tudo causal ate' 10:29. Precos devolvidos em CRU."""
    b = m1_ajustada()
    dts = b.index.date
    d1 = b.groupby(dts).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
    pc = d1.c.shift(1)
    tr = np.fmax(d1.h - d1.l, np.fmax((d1.h - pc).abs(), (d1.l - pc).abs()))
    d1["atr"] = tr.rolling(14).mean().shift(1)
    out = {}
    hh = pd.Timestamp("10:30").time()
    for dia, g in b.groupby(dts):
        if not (D.BLOCOS["DEV"][0] <= dia <= D.BLOCOS["VAL"][1]):
            continue
        atr = d1.loc[dia, "atr"]
        am = g[g.index.time < hh]
        if not np.isfinite(atr) or len(am) == 0:
            continue
        O, c0, aj = am.open.iloc[0], am.close.iloc[-1], am.aj.iloc[0]
        desl = (c0 - O) / atr
        lado = int(np.sign(desl))
        cruz = (am.close < O - FOLGA * atr).any() if lado > 0 else (am.close > O + FOLGA * atr).any()
        out[dia] = dict(O=O - aj, c0=c0 - aj, atr=atr, desl=desl, lado=lado, cruz=bool(cruz))
    return out


def ticks(dia):
    if dia not in _TK:
        _TK[dia] = D.ticks(dia)
    return _TK[dia]


def t_(dia, hhmm):
    return ms(pd.Timestamp(dia) + pd.Timedelta(hhmm + ":00"))


def opera(dia, lado, limite, stop, ate):
    t_env, t_zera = t_(dia, "10:30"), t_(dia, "17:50")
    return sim(ticks(dia), t_env, lado, limite, t_(dia, ate) - t_env, stop=stop, t_zera=t_zera)


def eh_sinal(x, k):
    return x["lado"] != 0 and abs(x["desl"]) >= k and not x["cruz"]


def rodar_celula(dias, info, f, ate, k):
    ops, sinais = [], 0
    for dia in dias:
        x = info.get(dia)
        if x is None or not eh_sinal(x, k):
            continue
        sinais += 1
        lado = x["lado"]
        lim = arred(x["O"] + f * (x["c0"] - x["O"]))
        stp = arred(x["O"] - lado * FOLGA * x["atr"])
        o = opera(dia, lado, lim, stp, ate)
        if o:
            ops.append(dict(dia=dia, lado=lado, limite=lim, stop=stp, stop_pts=abs(lim - stp), **o))
    return pd.DataFrame(ops), sinais


def metricas(ops, dias, sinais):
    """ops com pts; dias = pregoes do bloco. Tudo em R$."""
    m = dict(sinais=sinais, ops=len(ops))
    if not len(ops):
        return dict(m, liq0=0.0, liq=0.0, pf=np.nan, dd=0.0, caixa_min=CAP, mes_pos_tot=0, mes_pos_ops=0, meses=0,
                    meses_ops=0, tri_pos=0, tri=0, anos={}, sem2=0.0, quebrou=False)
    ops = ops.sort_values("t_sai").copy()
    ops["rs0"] = ops.pts * RS
    ops["rs"] = (ops.pts - CUSTO_PTS) * RS
    cx = CAP + ops.rs.cumsum()
    pico = np.maximum.accumulate(np.r_[CAP, cx.to_numpy()])[1:]
    g = ops.rs[ops.rs > 0].sum(); p = -ops.rs[ops.rs <= 0].sum()
    dd_ = pd.to_datetime(ops.dia)
    meses = pd.PeriodIndex(sorted({pd.Timestamp(d).to_period("M") for d in dias}))
    pm = ops.groupby(dd_.dt.to_period("M")).rs.sum().reindex(meses)
    tris = pd.PeriodIndex(sorted({pd.Timestamp(d).to_period("Q") for d in dias}))
    pt = ops.groupby(dd_.dt.to_period("Q")).rs.sum().reindex(tris)
    top2 = ops.rs.nlargest(2).sum()
    return dict(m, liq0=ops.rs0.sum(), liq=ops.rs.sum(), pf=(g / p if p > 0 else np.inf), dd=float((pico - cx).max()),
                caixa_min=float(min(CAP, cx.min())), mes_pos_tot=int((pm > 0).sum()), mes_pos_ops=int((pm.dropna() > 0).sum()),
                meses=len(meses), meses_ops=int(pm.notna().sum()), tri_pos=int((pt > 0).sum()), tri=len(tris),
                anos={int(a): round(float(v), 0) for a, v in ops.groupby(dd_.dt.year).rs.sum().items()},
                sem2=float(ops.rs.sum() - top2), quebrou=bool(cx.min() <= 0), pm=pm, pt=pt, tab=ops)


def controle(dias, info, sinais_dias, f, ate, k, n=200, seed=12345):
    """200 sorteios: por mes, mesmo n de pregoes sinalizados, sorteados entre os pregoes do mes; lado sorteado;
    geometria em ATR: limite a (1-f)*d ATRd contra o lado a partir de c1029 e stop (f*d+0,05) ATRd alem do limite;
    d de um dia de sinal real sorteado. Mesma validade e mesma zeragem."""
    rng = np.random.default_rng(seed)
    ds = np.array([abs(info[d]["desl"]) for d in sinais_dias])
    por_mes = {}
    for d in dias:
        if d in info:
            por_mes.setdefault(pd.Timestamp(d).to_period("M"), []).append(d)
    cont = {}
    for d in sinais_dias:
        mes = pd.Timestamp(d).to_period("M")
        cont[mes] = cont.get(mes, 0) + 1
    res = []
    for _ in range(n):
        liq = 0.0
        for mes, c in cont.items():
            pool = por_mes.get(mes, [])
            esc = rng.choice(len(pool), size=min(c, len(pool)), replace=False)
            for i in esc:
                dia = pool[i]; x = info[dia]
                lado = int(rng.choice([-1, 1])); d = rng.choice(ds)
                lim = arred(x["c0"] - lado * (1 - f) * d * x["atr"])
                stp = arred(lim - lado * (f * d + FOLGA) * x["atr"])
                o = opera(dia, lado, lim, stp, ate)
                if o:
                    liq += (o["pts"] - CUSTO_PTS) * RS
        res.append(liq)
    return np.array(res)


def linha(nome, m):
    pf = "inf" if m["pf"] == np.inf else f"{m['pf']:.2f}"
    q = "QUEBROU" if m["quebrou"] else ""
    return (f"{nome:20s} ops {m['ops']:3d} sin {m['sinais']:3d} | liq0 {m['liq0']:7.0f} liq {m['liq']:7.0f} PF {pf:>5s} "
            f"DD {m['dd']:5.0f} cxmin {m['caixa_min']:5.0f} | mes+ {m['mes_pos_tot']}/{m['meses']} ({m['mes_pos_ops']}/{m['meses_ops']} c/op) "
            f"tri+ {m['tri_pos']}/{m['tri']} | sem2 {m['sem2']:6.0f} | anos {m['anos']} {q}")


def sha():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def modo_dev():
    info = preparar()
    dias = D.dias("DEV")
    print(f"DEV {len(dias)} pregoes; com dado utilizavel {sum(d in info for d in dias)}", flush=True)
    R, rows = {}, []
    arq = AQUI / "n2_dev_ops.csv"
    if arq.exists():
        arq.unlink()
    for (f, ate, k) in GRADE:
        ops, sin = rodar_celula(dias, info, f, ate, k)
        m = metricas(ops, dias, sin); R[(f, ate, k)] = (m, ops)
        print(linha(f"f{f} ate{ate} k{k}", m), flush=True)
        rows.append(dict(f=f, ate=ate, k=k, **{a: b for a, b in m.items() if a not in ("pm", "pt", "tab", "anos")},
                         anos=json.dumps(m["anos"])))
        if len(ops):
            ops.assign(f=f, ate=ate, k=k).to_csv(arq, mode="a", header=not arq.exists(), index=False)
    pd.DataFrame(rows).to_csv(AQUI / "n2_dev_grade.csv", index=False)
    fs, ates = (0.25, 0.5, 0.75), ("12:00", "14:00")

    def pos(c):
        return R[c][0]["liq"] > 0
    elig = []
    for (f, ate, k), (m, ops) in R.items():
        viz = [(fs[i], ate, k) for i in (fs.index(f) - 1, fs.index(f) + 1) if 0 <= i < 3] + [(f, a, k) for a in ates if a != ate]
        ok = m["liq"] > 0 and all(pos(v) for v in viz) and m["caixa_min"] >= 500
        print(f"elegivel f{f} {ate} k{k}: liq>0 {m['liq'] > 0} vizinhos+ {all(pos(v) for v in viz)} cxmin>=500 {m['caixa_min'] >= 500} -> {ok}", flush=True)
        if ok:
            lucdd = m["liq"] / m["dd"] if m["dd"] > 0 else np.inf
            stm = float(ops.stop_pts.median()) * RS
            elig.append(((-lucdd, stm), (f, ate, k), lucdd, stm))
    if not elig:
        print("NENHUMA CELULA ELEGIVEL -> RDT REFUTADA no DEV", flush=True)
        return
    elig.sort(key=lambda z: z[0])
    for e in elig:
        print(f"  elegivel {e[1]} lucro/DD {e[2]:.2f} stop mediano R${e[3]:.0f}", flush=True)
    esc = elig[0][1]
    m, ops = R[esc]
    print("ESCOLHIDA", esc, flush=True)
    sinais_dias = [d for d in dias if d in info and eh_sinal(info[d], esc[2])]
    c = controle(dias, info, sinais_dias, *esc)
    pct = float((c < m["liq"]).mean() * 100)
    print(f"controle DEV 200 sorteios: media {c.mean():.0f} p50 {np.percentile(c, 50):.0f} p90 {np.percentile(c, 90):.0f} "
          f"p95 {np.percentile(c, 95):.0f} max {c.max():.0f}; RDT liq {m['liq']:.0f} -> percentil {pct:.1f}; sem as 2 melhores {m['sem2']:.0f}", flush=True)
    json.dump(dict(celula=dict(f=esc[0], ate=esc[1], k=esc[2]), dev_liq=m["liq"], dev_percentil=pct,
                   dev_p90=float(np.percentile(c, 90)), dev_p95=float(np.percentile(c, 95)), dev_sem2=m["sem2"]),
              open(AQUI / "n2_dev_escolha.json", "w"), indent=1)
    print("refutada no DEV?", pct < 90 or m["sem2"] <= 0, flush=True)


def modo_val():
    cong = json.load(open(AQUI / "n2_celula_congelada.json"))
    pre = (AQUI / "PREREGISTRO.md").read_text(encoding="utf-8")
    assert cong["sha256"] == sha() and cong["sha256"] in pre, "hash do script nao bate com o congelado -- VAL recusado"
    trava = AQUI / "n2_val_resultado.json"
    assert not trava.exists(), "VAL ja rodou -- nao roda de novo"
    f, ate, k = cong["f"], cong["ate"], cong["k"]
    info = preparar(); dias = D.dias("VAL")
    print(f"VAL {len(dias)} pregoes; celula f{f} {ate} k{k}", flush=True)
    ops, sin = rodar_celula(dias, info, f, ate, k)
    m = metricas(ops, dias, sin)
    print(linha("VAL", m), flush=True)
    sinais_dias = [d for d in dias if d in info and eh_sinal(info[d], k)]
    c = controle(dias, info, sinais_dias, f, ate, k)
    p95 = float(np.percentile(c, 95)); pct = float((c < m["liq"]).mean() * 100)
    print(f"controle VAL: media {c.mean():.0f} p50 {np.percentile(c, 50):.0f} p95 {p95:.0f}; RDT {m['liq']:.0f} percentil {pct:.1f}", flush=True)
    if m["ops"]:
        m["tab"].to_csv(AQUI / "n2_val_ops.csv", index=False)
        print("\nPOR MES (R$ com custo)", flush=True); print(m["pm"].round(0).to_string(), flush=True)
        print("\nPOR TRIMESTRE", flush=True); print(m["pt"].round(0).to_string(), flush=True)
    crit = {"liq_custo>0": m["liq"] > 0, "tri_pos>=3de5": m["tri_pos"] >= 3, "PF>=1.2": bool(m["pf"] >= 1.2),
            "nao_quebrou": not m["quebrou"], "acima_p95_controle": m["liq"] > p95}
    for a, v in crit.items():
        print(f"  {a}: {'PASSA' if v else 'FALHA'}", flush=True)
    json.dump(dict(crit={a: bool(v) for a, v in crit.items()}, liq=m["liq"], liq0=m["liq0"], pf=float(m["pf"]), ops=m["ops"],
                   percentil=pct, p95=p95, tri_pos=m["tri_pos"], mes_pos_tot=m["mes_pos_tot"], mes_pos_ops=m["mes_pos_ops"]),
              open(trava, "w"), indent=1)
    print("VEREDITO:", "APROVADA" if all(crit.values()) else "REFUTADA", flush=True)


if __name__ == "__main__":
    {"dev": modo_dev, "val": modo_val}[sys.argv[1]]()
