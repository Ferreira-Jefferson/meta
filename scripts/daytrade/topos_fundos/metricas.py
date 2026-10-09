"""Painel completo de metricas: v3, v4 original (2 nos bons/1 nos outros), so sinais bons 1x e 2x. IS, OOS e tudo junto.
Serie diaria inclui os pregoes sem operacao (zero). WIN: R$0,20 por ponto por contrato. Custo 10 pts/op ja descontado."""
import numpy as np
import pandas as pd
import prob as pb


def serie(per):
    b, f, c = pb.montar(per)
    base = pb.sim(f, c); so = pb.sim(f[f.bom], c)
    dias = pd.DatetimeIndex(sorted(v[0] for v in c.values()))
    def diaria(tr, w):
        d = pd.Series(tr.pts.to_numpy() * w, index=[c[s][0] for s in f.loc[tr.row].seg]).groupby(level=0).sum()
        return d.reindex(dias, fill_value=0.0)
    bom_b = f.bom.to_numpy()[base.row]
    V = {"v3 (todas, 1 contrato)": (base, np.ones(len(base))),
         "v4 original (2 nos bons, 1 nos outros)": (base, np.where(bom_b, 2, 1)),
         "só sinais bons, 1 contrato": (so, np.ones(len(so))),
         "só sinais bons, 2 contratos": (so, 2 * np.ones(len(so)))}
    out = {}
    for k, (tr, w) in V.items():
        out[k] = dict(trades=tr.pts.to_numpy() * w, contratos=w, dia=diaria(tr, w))
    return out


def metricas(trades, contratos, dia):
    t = np.asarray(trades); d = dia
    eq = d.cumsum(); pico = eq.cummax(); sub = pico - eq; dd = sub.max()
    # tempo submerso mais longo (pregoes)
    sub_flag = (sub > 0).astype(int); grp = (sub_flag != sub_flag.shift()).cumsum()
    dur = sub_flag.groupby(grp).sum().max()
    perdas = (t <= 0).astype(int); g2 = (perdas != np.r_[0, perdas[:-1]]).cumsum()
    seq = pd.Series(perdas).groupby(g2).sum().max()
    mes = d.groupby(d.index.to_period("M")).sum()
    ativos = d[d != 0]
    sharpe = d.mean() / d.std() * np.sqrt(252) if d.std() > 0 else np.nan
    neg = d[d < 0]; sortino = d.mean() / np.sqrt((neg ** 2).sum() / len(d)) * np.sqrt(252) if len(neg) else np.nan
    gan, per = t[t > 0], t[t <= 0]
    return {"operações": len(t), "contratos médios": np.mean(contratos), "total pts": t.sum(), "total R$": t.sum() * 0.2,
            "pts por operação": t.mean(), "acerto %": 100 * (t > 0).mean(), "ganho médio / perda média": gan.mean() / -per.mean(),
            "fator de lucro": gan.sum() / -per.sum(), "maior queda pts": dd, "maior queda R$": dd * 0.2,
            "total ÷ maior queda": t.sum() / dd, "pregões até recuperar (pior)": dur, "pior dia pts": d.min(),
            "pior mês pts": mes.min(), "meses positivos %": 100 * (mes > 0).mean(), "dias com operação positivos %": 100 * (ativos > 0).mean(),
            "maior sequência de perdas (ops)": seq, "Sharpe anual": sharpe, "Sortino anual": sortino,
            "capital mínimo R$ (queda + margem)": dd * 0.2 + 100 * np.max(contratos)}


def main():
    S = {per: serie(per) for per in ("pesquisa", "reserva")}
    tab = {}
    for per, rot in (("pesquisa", "IS"), ("reserva", "OOS")):
        for k, v in S[per].items():
            tab[(rot, k)] = metricas(v["trades"], v["contratos"], v["dia"])
    for k in S["pesquisa"]:
        a, b = S["pesquisa"][k], S["reserva"][k]
        tab[("TUDO", k)] = metricas(np.r_[a["trades"], b["trades"]], np.r_[a["contratos"], b["contratos"]], pd.concat([a["dia"], b["dia"]]))
    t = pd.DataFrame(tab)
    t.to_pickle("scripts/daytrade/topos_fundos/res_conf/metricas.pkl")
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 20)
    for rot in ("IS", "OOS", "TUDO"):
        x = t[rot].copy(); x.columns = ["v3", "v4 orig", "bons 1x", "bons 2x"]
        print(f"\n===== {rot}"); print(x.round(2).to_string())


if __name__ == "__main__":
    main()
