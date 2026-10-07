"""Hipotese D: qual detector de tendencia, em tempo real, reproduz 'a direcao do mes'?

Escolha de dados (declarada): direcao dos detectores vem do arquivo diario/M5 AJUSTADO
(WIN@D_M5, ajuste por diferenca, 2021-2026) - SO para direcao, nunca para preco de
execucao. Detectores diarios usam apenas pregoes ENCERRADOS (D-1 para tras) e valem
para todo o pregao D. Detectores intradiarios (semana ancorada, H1) usam so barras
fechadas. No diagnostico (trades), o valor e lido na barra t-30min (t = barra de
preenchimento; o sinal esta entre t-25 e t-5 min) => sem look-ahead. Na simulacao o
hook usa o valor no fechamento da propria barra do sinal.
Etapa 1: diagnostico nos 988 trades do baseline. Etapa 2: simula com bloqueio do lado contra.
"""
import importlib.util as u
from pathlib import Path
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
_s = u.spec_from_file_location("kit", AQUI.parent / "win_melhor_kit.py")
kit = u.module_from_spec(_s)
_s.loader.exec_module(kit)


def log(*a):
    print(*a, flush=True)


def carrega_adj():
    d = pd.read_csv(kit.DADOS / "WIN@D_M5_202110010900_202610011715.csv", sep="\t")
    d.columns = [c.strip("<>") for c in d.columns]
    d.index = pd.to_datetime(d["DATE"] + " " + d["TIME"], format="%Y.%m.%d %H:%M:%S")
    return d.rename(columns={"OPEN": "o", "HIGH": "h", "LOW": "l", "CLOSE": "c"})[["o", "h", "l", "c"]]


ADJ = carrega_adj()
DIA = ADJ.groupby(ADJ.index.normalize()).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
DN = ADJ.index.normalize()


def diario_para_m5(sd):
    """sd indexado por dia (valor calculado no fechamento do dia). Vale a partir do dia seguinte."""
    sh = sd.shift(1)
    return pd.Series(sh.reindex(DN).values, index=ADJ.index)


def sgn(x):
    return np.sign(x)


def monta_detectores():
    D = {}
    c = DIA.c
    for N in (3, 5, 10, 20):
        D[f"ret{N}d"] = ("ret_N_pregoes", N, diario_para_m5(sgn(c - c.shift(N))))
    for N in (10, 20, 50):
        e = c.ewm(span=N, adjust=False).mean()
        D[f"emaslope{N}"] = ("incl_EMA_diaria", N, diario_para_m5(sgn(e.diff())))
    wk = ADJ.index.to_period("W-SUN")
    wopen = ADJ.o.groupby(wk).transform("first")
    D["semana_ancorada"] = ("semana_ancorada", 0, sgn(ADJ.c - wopen))
    mes = DIA.index.to_period("M")
    mo = DIA.o.groupby(mes).first()
    mc = DIA.c.groupby(mes).last()
    dirm = sgn(mc - mo)
    prev = pd.Series(dirm.shift(1).reindex(DN.to_period("M")).values, index=ADJ.index)
    D["mes_anterior"] = ("mes_anterior", 0, prev)
    for N in (10, 20, 50):
        hh = DIA.h.rolling(N).max()
        ll = DIA.l.rolling(N).min()
        pos = (c - ll) / (hh - ll)
        D[f"donchpos{N}"] = ("donchian_posicao", N, diario_para_m5(sgn(pos - 0.5)))
        up = c > DIA.h.rolling(N).max().shift(1)
        dn = c < DIA.l.rolling(N).min().shift(1)
        st = pd.Series(np.where(up, 1.0, np.where(dn, -1.0, np.nan)), index=c.index).ffill()
        D[f"donchestado{N}"] = ("donchian_estado", N, diario_para_m5(st))
    h1 = ADJ.c.groupby([ADJ.index.normalize(), ADJ.index.hour]).last()
    h1.index = [pd.Timestamp(d) + pd.Timedelta(hours=h) + pd.Timedelta(minutes=55) for d, h in h1.index]
    for f, sl in ((21, 50), (9, 21), (50, 200)):
        sg = sgn(h1.ewm(span=f, adjust=False).mean() - h1.ewm(span=sl, adjust=False).mean())
        D[f"h1ema{f}_{sl}"] = ("H1_EMAs", f, sg.reindex(ADJ.index, method="ffill"))
    for N in (5, 10, 20):
        er = (c - c.shift(N)).abs() / c.diff().abs().rolling(N).sum()
        for thr in (0.0, 0.25):
            sg = sgn(c - c.shift(N)).where(er > thr, 0.0)
            D[f"er{N}_t{thr}"] = (f"ER_Kaufman_t{thr}", N, diario_para_m5(sg))

    def maj(names, k):
        m = pd.concat([D[n][2] for n in names], axis=1)
        sm = m.sum(axis=1)
        return sgn(sm).where(sm.abs() >= k, 0.0)
    D["conc_unan(ret10,emaslope20,semana)"] = ("concordancia", 3, maj(["ret10d", "emaslope20", "semana_ancorada"], 3))
    D["conc_maj(ret10,emaslope20,h1ema21_50)"] = ("concordancia", 2, maj(["ret10d", "emaslope20", "h1ema21_50"], 2))
    D["conc_maj(ret5d,donchpos20,semana)"] = ("concordancia", 2, maj(["ret5d", "donchpos20", "semana_ancorada"], 2))
    D["conc_unan(ret5d,donchpos20)"] = ("concordancia", 2, maj(["ret5d", "donchpos20"], 2))
    return D


def diag(res, D):
    rows = []
    jan_dir = [np.sign(r["mercado_pts"]) for r in res]
    cand = {"ORACULO": ("oraculo", 0, None)}
    cand.update(D)
    for nome, (fam, par, ser) in cand.items():
        F, C = [], []
        N0 = ok = ev = 0
        for i, r in enumerate(res):
            tr = r["trades"]
            if not len(tr):
                continue
            if ser is None:
                dd = np.full(len(tr), jan_dir[i])
            else:
                ts = (tr.t - pd.Timedelta(minutes=30)).values
                pos = ser.index.searchsorted(ts, side="right") - 1
                dd = np.nan_to_num(ser.values[np.clip(pos, 0, None)], nan=0.0)
            fav = tr.lado.values == dd
            con = (tr.lado.values == -dd) & (dd != 0)
            N0 += int((dd == 0).sum())
            pf, pc = tr.pts[fav], tr.pts[con]
            F.append(pf)
            C.append(pc)
            if len(pf) and len(pc):
                ev += 1
                ok += int(pf.mean() > pc.mean())
        F = pd.concat(F)
        C = pd.concat(C)
        rows.append(dict(detector=nome, familia=fam, parametro=par, n_fav=len(F), n_contra=len(C), neutro=N0,
                         pct_favor=100 * len(F) / max(len(F) + len(C), 1),
                         pts_favor=F.mean() if len(F) else np.nan, pts_contra=C.mean() if len(C) else np.nan,
                         diff=(F.mean() - C.mean()) if len(F) and len(C) else np.nan,
                         jan_certas=f"{ok}/{ev}", jan_ok=ok, jan_ev=ev))
    return pd.DataFrame(rows)


def liq_janelas(res):
    return np.array([r["eq"].iloc[-1] - kit.b.CAP0 for r in res])


def sim(m5, base_liq, ser):
    def val(seg):
        return ser.reindex(seg.index).fillna(0.0).values
    r = kit.rodar_meses(m5, permite_long=lambda seg: val(seg) >= 0, permite_short=lambda seg: val(seg) <= 0)
    rs = kit.resumo(r)
    dlt = liq_janelas(r) - base_liq
    rs.update(dict(delta_vs_base=round(float(dlt.sum()), 1), janelas_melhor=f"{(dlt > 0).sum()}/{len(dlt)}",
                   LOWO_min_delta=round(float(min(dlt.sum() - d for d in dlt)), 1)))
    return rs


def main():
    m5 = kit.carregar_m5()
    base = kit.rodar_meses(m5)
    base_liq = liq_janelas(base)
    rb = kit.resumo(base)
    log("BASELINE", rb)
    D = monta_detectores()
    dg = diag(base, D)
    ntests = len(D)
    log(f"\nETAPA 1 - diagnostico ({ntests} detectores + oraculo)")
    cols = ["detector", "n_fav", "n_contra", "neutro", "pct_favor", "pts_favor", "pts_contra", "diff", "jan_certas"]
    log(dg[cols].round(1).to_string(index=False))
    dg.to_csv(AQUI / "hip_d_diag.csv", index=False, sep=";")
    d2 = dg[dg.detector != "ORACULO"]
    fam = d2.groupby("familia").agg(diff_medio=("diff", "mean"), diff_min=("diff", "min"), jan_media=("jan_ok", "mean"), n=("diff", "size"))
    fam = fam.sort_values("diff_medio", ascending=False)
    log("\nFamilias:\n" + fam.round(1).to_string())
    top = list(fam.index)  # simula TODOS os detectores (evita escolha post-hoc)
    log("Simulando todos os detectores + oraculo")
    linhas = [("BASELINE", dict(rb, delta_vs_base=0.0, janelas_melhor="-", LOWO_min_delta=0.0))]
    for nome, (f, p, ser) in D.items():
        if f in top:
            r = sim(m5, base_liq, ser)
            linhas.append((nome, r))
            log(nome, r)
            ntests += 1
    class _Orac:
        pass
    def orac(seg):
        g = seg.groupby(seg.index.to_period("M"))
        dm = np.sign(g.c.last() - g.o.first())
        return pd.Series(dm.reindex(seg.index.to_period("M")).values, index=seg.index)
    def sim_o(m5, base_liq):
        r = kit.rodar_meses(m5, permite_long=lambda seg: orac(seg).values >= 0, permite_short=lambda seg: orac(seg).values <= 0)
        rs = kit.resumo(r); dlt = liq_janelas(r) - base_liq
        rs.update(dict(delta_vs_base=round(float(dlt.sum()), 1), janelas_melhor=f"{(dlt > 0).sum()}/{len(dlt)}",
                       LOWO_min_delta=round(float(min(dlt.sum() - d for d in dlt)), 1)))
        return rs
    linhas.append(("ORACULO (dir. do mes)", sim_o(m5, base_liq)))
    out = pd.DataFrame([dict(variante=n, **r) for n, r in linhas])
    out.to_csv(AQUI / "hip_d_sim.csv", index=False, sep=";")
    log("\nETAPA 2\n" + out.to_string(index=False))
    log(f"\nTOTAL de configuracoes avaliadas: {ntests}")


if __name__ == "__main__":
    main()
