"""V1: relatorio do VAL a partir dos arquivos (trades_val/, controles_val/, filtro_2026.csv). NAO roda o VAL.
Uso: python v1_relatorio.py  ->  resultado.md, resultado.csv"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

AQ = Path(__file__).resolve().parent
CUSTO, CAP = 2.0, 1000.0
CAND = {
    "C1": ("Win_c1", "B filtro tabela", "filtro"), "C2": ("WinCincoMedias", "A1 consenso comum", "filtro"),
    "C3": ("WinDeslocamentoMatinal", "A1 consenso individual", "filtro"), "C4": ("WinDeslocamentoMatinal", "A1 consenso comum", "filtro"),
    "C5": ("Win", "E V2b", "saida"), "C6": ("Win", "E V1a", "saida"), "C7": ("Win", "E V1b", "saida"),
    "C8": ("WinCincoMedias", "E V3b", "saida"), "C9": ("WinCincoMedias", "E V3a", "saida"),
    "C10": ("WinDeslocamentoMatinal", "E V3a", "saida"), "C11": ("WinDeslocamentoMatinal", "E V3b", "saida"),
    "C12": ("WinRetanguloEma34", "B resize pela nota", "resize"), "C13": ("ConsensoGatilho", "A2 gatilho de consenso", "nova"),
}
ORIG = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
TRIM = ["2024T3", "2024T4", "2025T1", "2025T2", "2025T3"]
MES = [f"{y}-{m:02d}" for y, m in [(2024, k) for k in range(7, 13)] + [(2025, k) for k in range(1, 10)]]


def le(p):
    t = pd.read_csv(p)
    t["entrada"] = pd.to_datetime(t.entrada, format="mixed"); t["saida"] = pd.to_datetime(t.saida, format="mixed")
    if "qtd" not in t: t["qtd"] = 1.0
    return t.sort_values(["saida", "entrada"], kind="stable").reset_index(drop=True)


def trim(ts):
    return f"{ts.year}T{(ts.month - 1) // 3 + 1}"


def metricas(t, custo=CUSTO):
    r = (t.rs - custo * t.qtd).to_numpy()
    if len(r) == 0:
        return dict(ops=0, liq=0.0, acerto=np.nan, payoff=np.nan, pf=np.nan, dd=0.0, fr=np.nan, saldo_min=CAP, quebra="")
    saldo = CAP + np.cumsum(r)
    pico = np.maximum.accumulate(np.r_[CAP, saldo])[1:]
    dd = float((pico - saldo).max())
    g, p = r[r > 0], -r[r < 0]
    q = np.flatnonzero(saldo <= 0)
    liq = float(r.sum())
    return dict(ops=len(r), liq=liq, acerto=100 * float((r > 0).mean()),
                payoff=float(g.mean() / p.mean()) if len(g) and len(p) else np.nan,
                pf=float(g.sum() / p.sum()) if len(p) and len(g) else (np.inf if len(g) else 0.0),
                dd=dd, fr=liq / dd if dd > 0 else np.nan, saldo_min=float(min(saldo.min(), CAP)),
                quebra=str(t.saida.iloc[q[0]].date()) if len(q) else "")


def por(t, chave, rotulos, custo):
    r = (t.rs - custo * t.qtd)
    s = r.groupby(t.saida.map(chave)).sum()
    return [float(s.get(k, 0.0)) for k in rotulos]


def holm(p, m=None):
    p = np.asarray(p, float); n = len(p); m = m or n
    o = np.argsort(p); adj = np.empty(n); run = 0.0
    for i, j in enumerate(o):
        run = max(run, min(1.0, (m - i) * p[j])); adj[j] = run
    return adj


def f2(x, nd=1):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:,.{nd}f}".replace(",", " ")


def main():
    seg = pd.read_csv(AQ / "filtro_2026.csv")
    ids = [c for c in seg.id if (AQ / "controles_val" / f"{c}.npy").exists() and (AQ / "trades_val" / f"{c}.csv").exists() and seg.set_index("id").segue[c]]
    orig = {r: le(AQ / "trades_val" / f"orig_{r}.csv") for r in ORIG}
    om = {r: metricas(orig[r]) for r in ORIG}
    om0 = {r: metricas(orig[r], 0.0) for r in ORIG}
    pior = min(om[r]["liq"] for r in ORIG)
    pior_nome = min(ORIG, key=lambda r: om[r]["liq"])
    linhas, det = [], {}
    for c in ids:
        robo, desc, tipo = CAND[c]
        t = le(AQ / "trades_val" / f"{c}.csv"); ctrl = np.load(AQ / "controles_val" / f"{c}.npy")
        m, m0 = metricas(t), metricas(t, 0.0)
        o = om[robo] if tipo != "nova" else None
        o0 = om0[robo] if tipo != "nova" else None
        real = m["liq"] - o["liq"] if tipo != "nova" else m["liq"]
        pb = (1 + int((ctrl >= real - 1e-9).sum())) / (len(ctrl) + 1)
        det[c] = dict(t=t, robo=robo, tipo=tipo)
        linhas.append(dict(id=c, robo=robo, regra=desc, tipo=tipo, ops=m["ops"], liq_sem=round(m0["liq"], 2), liq_com=round(m["liq"], 2),
                           orig_ops=o["ops"] if o else None, orig_liq_sem=round(o0["liq"], 2) if o else None, orig_liq_com=round(o["liq"], 2) if o else None,
                           delta_com=round(real, 2) if tipo != "nova" else None, delta_sem=round(m0["liq"] - o0["liq"], 2) if o else None,
                           acerto=round(m["acerto"], 1), orig_acerto=round(o["acerto"], 1) if o else None,
                           payoff=round(m["payoff"], 2), orig_payoff=round(o["payoff"], 2) if o else None,
                           pf=round(m["pf"], 2), orig_pf=round(o["pf"], 2) if o else None,
                           dd=round(m["dd"], 1), orig_dd=round(o["dd"], 1) if o else None,
                           fr=round(m["fr"], 3), orig_fr=round(o["fr"], 3) if o else None,
                           saldo_min=round(m["saldo_min"], 1), quebra=m["quebra"], orig_quebra=o["quebra"] if o else None,
                           ctrl_p50=round(float(np.median(ctrl)), 1), ctrl_p95=round(float(np.percentile(ctrl, 95)), 1), p_bruto=round(pb, 4)))
    df = pd.DataFrame(linhas)
    df["p_holm"] = np.round(holm(df.p_bruto), 4)
    df["p_holm_m13"] = np.round(holm(df.p_bruto, 13), 4)
    cls, cls_estrita_bruta = [], []
    for r in df.itertuples():
        if r.tipo != "nova":
            if r.delta_com > 0 and r.p_holm < 0.05: k = "APROVADA"
            elif r.delta_com > 0 and r.fr > r.orig_fr and r.p_bruto < 0.10: k = "PROMISSORA"
            else: k = "REFUTADA"
            cls.append(k); cls_estrita_bruta.append(k)
        else:
            t = det[r.id]["t"]
            tq = por(t, trim, TRIM, CUSTO)
            base = (r.liq_com > pior) and (r.quebra == "") and (r.pf >= 1.2) and (sum(x > 0 for x in tq) >= 3)
            cls.append("APROVADA" if base and r.p_bruto <= 0.05 and r.p_holm < 0.05 else "REFUTADA")
            cls_estrita_bruta.append("APROVADA" if base and r.p_bruto <= 0.05 else "REFUTADA")
    df["classe"] = cls; df["classe_p_bruto"] = cls_estrita_bruta
    df.to_csv(AQ / "resultado.csv", index=False)

    L = []
    P = L.append
    P("# V1 — validação das candidatas no VAL (2024-07-01 → 2025-09-30), rodada única")
    P("")
    P("Regras, janela, testes e critérios: `CONGELADAS.md` e `../PREREGISTRO_V.md`. Todas as candidatas foram refeitas SEM o WdoRetangulo; as 13 regras reproduziram 100% do CSV da frente em 2026 com ele (ver `reproducao_2026.csv`). 3 caíram em 2026 sem o WdoRetangulo (C2, C3, C6) e não chegaram ao VAL; as outras 10 chegaram.")
    P("")
    P(f"Capital R$1.000 a partir de 2024-07-01, custo R$2/op, 1 contrato. Pior original no VAL (com custo): **{pior_nome} {f2(pior, 0)}**. Holm sobre {len(df)} candidatas (coluna `p Holm`; `p Holm m=13` trata as 3 que caíram como p=1).")
    P("")
    P("## Resultado")
    P("")
    P("| id | robô | regra | ops | líq. com custo | original | Δ com custo | FR cand | FR orig | p bruto | p Holm | classe |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in df.itertuples():
        P(f"| {r.id} | {r.robo} | {r.regra} | {r.ops} | {f2(r.liq_com, 0)} | {f2(r.orig_liq_com, 0)} | {f2(r.delta_com, 0)} | {f2(r.fr, 2)} | {f2(r.orig_fr, 2)} | {r.p_bruto:.3f} | {r.p_holm:.3f} | **{r.classe}** |")
    P("")
    P("C5 e C7 são a mesma regra sem o WdoRetangulo (a outra família é só o WinRetanguloEma34): mesmas operações, mesmo Δ e mesmo p.")
    P("")
    P("## Indicadores completos (com custo R$2/op; sem custo no CSV)")
    P("")
    P("| id | acerto % (cand / orig) | payoff | fator de lucro | maior queda R$ | fator de recuperação | saldo mínimo | quebra (cand / orig) | sorteio p50 / p95 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for r in df.itertuples():
        P(f"| {r.id} | {f2(r.acerto)} / {f2(r.orig_acerto)} | {f2(r.payoff, 2)} / {f2(r.orig_payoff, 2)} | {f2(r.pf, 2)} / {f2(r.orig_pf, 2)} | {f2(r.dd, 0)} / {f2(r.orig_dd, 0)} | {f2(r.fr, 2)} / {f2(r.orig_fr, 2)} | {f2(r.saldo_min, 0)} | {r.quebra or '-'} / {r.orig_quebra or '-'} | {f2(r.ctrl_p50, 0)} / {f2(r.ctrl_p95, 0)} |")
    P("")
    P("## Os 5 originais no VAL")
    P("")
    P("| robô | ops | líq. sem custo | líq. com custo | acerto % | payoff | fator de lucro | maior queda | fator de recuperação | quebra |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for rb in ORIG:
        o, o0 = om[rb], om0[rb]
        P(f"| {rb} | {o['ops']} | {f2(o0['liq'], 0)} | {f2(o['liq'], 0)} | {f2(o['acerto'])} | {f2(o['payoff'], 2)} | {f2(o['pf'], 2)} | {f2(o['dd'], 0)} | {f2(o['fr'], 2)} | {o['quebra'] or '-'} |")
    if "C13" in det:
        t = det["C13"]["t"]; r = df[df.id == "C13"].iloc[0]
        tq = por(t, trim, TRIM, CUSTO)
        P("")
        P(f"## C13 — critérios de nova: líquido {f2(r.liq_com, 0)} {'>' if r.liq_com > pior else '<='} pior original ({f2(pior, 0)}); quebra {r.quebra or 'não'}; fator de lucro {r.pf} (≥1,2: {r.pf >= 1.2}); trimestres positivos {sum(x > 0 for x in tq)}/5; p bruto {r.p_bruto} (≤0,05: {r.p_bruto <= 0.05}); p Holm {r.p_holm} (<0,05: {r.p_holm < 0.05}); classe estrita **{r.classe}**, só com p bruto **{r.classe_p_bruto}**")
    P("")
    P("## Tabelas por mês e por trimestre (mês/trimestre da SAÍDA; R$)")
    for r in df.itertuples():
        t, rb = det[r.id]["t"], r.robo
        P("")
        P(f"### {r.id} — {r.robo} · {r.regra}" + ("" if r.tipo == "nova" else f"  (original = {rb} sem a regra)"))
        P("")
        cab = "| período | cand. sem custo | cand. com custo |" + ("" if r.tipo == "nova" else " orig. sem custo | orig. com custo |")
        P(cab); P("|---|---|---|" + ("" if r.tipo == "nova" else "---|---|"))
        for nome, ch, rot in (("mês", lambda s: f"{s.year}-{s.month:02d}", MES), ("trimestre", trim, TRIM)):
            a0, a2 = por(t, ch, rot, 0.0), por(t, ch, rot, CUSTO)
            if r.tipo != "nova":
                b0, b2 = por(orig[rb], ch, rot, 0.0), por(orig[rb], ch, rot, CUSTO)
            for i, k in enumerate(rot):
                P(f"| {k} | {f2(a0[i], 0)} | {f2(a2[i], 0)} |" + ("" if r.tipo == "nova" else f" {f2(b0[i], 0)} | {f2(b2[i], 0)} |"))
            tot = f"| **total {nome}s** | {f2(sum(a0), 0)} | {f2(sum(a2), 0)} |" + ("" if r.tipo == "nova" else f" {f2(sum(b0), 0)} | {f2(sum(b2), 0)} |")
            if nome == "trimestre": P(tot)
    (AQ / "resultado.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    pd.set_option("display.width", 250)
    print(df[["id", "robo", "regra", "ops", "liq_com", "orig_liq_com", "delta_com", "fr", "orig_fr", "p_bruto", "p_holm", "p_holm_m13", "classe", "classe_p_bruto"]].to_string(index=False))
    print("pior original:", pior_nome, pior)


if __name__ == "__main__":
    main()
