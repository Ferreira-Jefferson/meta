"""Testa H01-H13 (HIPOTESES.md) nos eventos de estagio >= 1 do motor.

Medida por evento: d = resultado em ATR - media das 5 entradas sorteadas DO PROPRIO evento (mesmo lado, mesmo stop
em ATR, mesmo manejo). Para cada hipotese: d medio por grupo, e a diferenca (grupo previsto melhor - pior) com IC 95%,
nas duas metades (2022-23 e 2024-25) e por lado. Passa se: IC da diferenca exclui 0 no sentido previsto no total E
o sinal se repete nas duas metades E nos dois lados.
"""
import numpy as np
import pandas as pd
import motor

R = "scripts/daytrade/topos_fundos/res/"
UNIDS = [("M5", "dia"), ("M15", "dia"), ("M5", "multi"), ("M15", "multi"), ("M30", "multi"), ("H1", "multi")]
HTF = {"M5": "60min", "M15": "60min", "M30": "240min", "H1": "1D"}


def features(tf, modo, K=1.5, min_est=1):
    nome = f"{tf}_{modo}_K{K}"
    ev = pd.read_pickle(R + f"ev_{nome}.pkl"); nu = pd.read_pickle(R + f"nu_{nome}.pkl")
    ev["d"] = ev.res / ev.atr - nu.res_atr.to_numpy().reshape(-1, 5).mean(axis=1)
    b = pd.read_pickle(R + f"barras_{tf}_{modo}.pkl")
    seg = b.dia if modo == "dia" else b.contrato
    grupos = [g for _, g in b.groupby(seg.values)]
    # tempo grafico superior: close > EMA34 e EMA9 > EMA21 na ultima barra superior FECHADA
    c = b.close.resample(HTF[tf]).last().dropna()
    up = (c > c.ewm(span=34, adjust=False).mean()) & (c.ewm(span=9, adjust=False).mean() > c.ewm(span=21, adjust=False).mean())
    dn = (c < c.ewm(span=34, adjust=False).mean()) & (c.ewm(span=9, adjust=False).mean() < c.ewm(span=21, adjust=False).mean())
    htf = pd.Series(np.where(up, 1, np.where(dn, -1, 0)), index=c.index + pd.Timedelta(HTF[tf]))  # disponivel no fim
    atr_med = b.atr.rolling(250, min_periods=50).median().shift(1)
    abertura_dia = b.groupby("dia").open.transform("first")
    linhas = []
    cache = {}
    for e in ev[ev.est >= min_est].itertuples():
        if e.seg not in cache:
            g = grupos[e.seg]
            cache[e.seg] = (g, motor.zigzag(g.high.to_numpy(), g.low.to_numpy(), g.atr.to_numpy(), K))
        g, piv = cache[e.seg]
        i, lado = e.i, e.lado
        if i < 2: continue  # precisa de fundo, topo e fundo anteriores
        Fk, Tk1, Fk1 = piv[i], piv[i - 1], piv[i - 2]   # (compra) fundo atual, topo anterior, fundo anterior
        AI = abs(Tk1[2] - Fk1[2]); AC = abs(Tk1[2] - Fk[2])
        nI = max(Tk1[1] - Fk1[1], 1); nC = max(Fk[1] - Tk1[1], 1)
        c_ = Fk[3]; atr = e.atr
        v = g.real_volume.to_numpy()
        Vi = v[Fk1[1]:Tk1[1] + 1].mean(); Vc = v[Tk1[1]:Fk[1] + 1].mean()
        mv = np.median(v[max(0, c_ - 50):c_]) if c_ > 5 else np.nan
        ema34 = g.ema34.iloc[c_]; ema100 = g.ema100.iloc[c_]
        t_conf = g.index[c_]
        h = htf.asof(t_conf) if t_conf >= htf.index[0] else np.nan
        # H10: compra stop no topo anterior + 5 pts, valida 20 barras, cancela se perder o fundo
        o, hi, lo, cl = (g[x].to_numpy() for x in ("open", "high", "low", "close"))
        nivel = Tk1[2] + 5 * lado; t_disp, r10 = None, 0.0
        for t in range(c_ + 1, min(c_ + 21, len(o))):
            if (lo[t] <= Fk[2]) if lado == 1 else (hi[t] >= Fk[2]): break
            if (hi[t] >= nivel) if lado == 1 else (lo[t] <= nivel):
                t_disp = t; break
        if t_disp is not None:
            px = max(o[t_disp], nivel) if lado == 1 else min(o[t_disp], nivel)
            oo = o.copy(); oo[t_disp] = px
            res, _, _ = motor.trail(oo, hi, lo, cl, {p[3]: p for p in piv}, t_disp, lado, Fk[2])
            r10 = res / atr
        hora = t_conf.hour + t_conf.minute / 60
        linhas.append(dict(
            idx=e.Index, ano=e.ano, lado=lado, d=e.d, res_atr=e.res / atr,
            H01=AC / AI if AI else np.nan, H02=nC / nI, H03=((AI / atr) / nI) / max((AC / atr) / nC, 1e-9),
            H04=Vc / Vi if Vi else np.nan, H05=v[Fk[1]] / mv if mv else np.nan, H06=AI / atr,
            H07=h * lado if h == h else np.nan,
            H08=((Fk[2] - ema34) / atr) * lado, H08b=(ema34 > ema100) == (lado == 1),
            H09=hora, H10=r10, H10disp=t_disp is not None,
            H11=e.R / atr, H12=atr / atr_med.loc[t_conf] if atr_med.loc[t_conf] == atr_med.loc[t_conf] else np.nan,
            H13=((g.close.iloc[c_] - abertura_dia.loc[t_conf]) / atr) * lado,
            falha=None))
    return pd.DataFrame(linhas)


# (nome, funcao de grupo -> rotulo, grupo previsto melhor, grupo previsto pior)
REG = [
    ("H01 retracao", lambda x: pd.cut(x.H01, [-1, .382, .618, 99], labels=["<38", "38-62", ">62"]), "38-62", ">62"),
    ("H02 duracao corr/imp", lambda x: pd.cut(x.H02, [-1, .5, 1.5, 1e9], labels=["curta", "media", "longa"]), "curta", "longa"),
    ("H03 veloc imp/corr", lambda x: pd.cut(x.H03, [-1, 1, 2, 1e9], labels=["<1", "1-2", ">2"]), ">2", "<1"),
    ("H04 vol corr/imp", lambda x: pd.cut(x.H04, [-1, .8, 1.2, 1e9], labels=["seca", "meio", "pesada"]), "seca", "pesada"),
    ("H05 vol barra fundo", lambda x: pd.cut(x.H05, [-1, 1, 2, 1e9], labels=["<1", "1-2", ">2"]), ">2", "<1"),
    ("H06 impulso ATR", lambda x: pd.cut(x.H06, [-1, 3, 6, 1e9], labels=["<3", "3-6", ">6"]), ">6", "<3"),
    ("H07 TF superior", lambda x: x.H07.map({1: "a favor", 0: "neutro", -1: "contra"}), "a favor", "contra"),
    ("H08 fundo x EMA34", lambda x: pd.cut(x.H08, [-1e9, -.5, .5, 1e9], labels=["abaixo", "toque", "acima"]), "toque", "abaixo"),
    ("H09 hora", lambda x: pd.cut(x.H09, [0, 10, 17, 24], labels=["1a hora", "meio", "fim"]), "meio", "1a hora"),
    ("H11 stop R/ATR", lambda x: pd.cut(x.H11, [-1, 1.5, 2.5, 1e9], labels=["<1.5", "1.5-2.5", ">2.5"]), "<1.5", ">2.5"),
    ("H12 regime vol", lambda x: pd.cut(x.H12, [-1, .8, 1.25, 1e9], labels=["baixa", "normal", "alta"]), "alta", "baixa"),
    ("H13 vs abertura dia", lambda x: np.where(x.H13 > 0, "a favor", "contra"), "a favor", "contra"),
]


def dif(df, col, a, b):
    A, B = df[df.g == a].d, df[df.g == b].d
    if len(A) < 20 or len(B) < 20: return np.nan, np.nan
    return A.mean() - B.mean(), 1.96 * np.sqrt(A.var() / len(A) + B.var() / len(B))


def main():
    saidas = []
    for tf, modo in UNIDS:
        f = features(tf, modo)
        f.to_pickle(R + f"feat_{tf}_{modo}.pkl")
        for nome, fn, melhor, pior in REG:
            if nome.startswith("H09") and modo == "multi" and tf == "H1": continue
            x = f.copy(); x["g"] = fn(x)
            x = x.dropna(subset=["g"])
            df_, ic = dif(x, "d", melhor, pior)
            h1, _ = dif(x[x.ano <= 2023], "d", melhor, pior); h2, _ = dif(x[x.ano >= 2024], "d", melhor, pior)
            c, _ = dif(x[x.lado == 1], "d", melhor, pior); v, _ = dif(x[x.lado == -1], "d", melhor, pior)
            ns = x.g.value_counts().to_dict()
            passa = df_ - ic > 0 and h1 > 0 and h2 > 0 and c > 0 and v > 0
            saidas.append(dict(unid=f"{tf}_{modo}", hip=nome, melhor=melhor, pior=pior, n_melhor=ns.get(melhor, 0),
                               n_pior=ns.get(pior, 0), dif=df_, ic=ic, m22_23=h1, m24_25=h2, compra=c, venda=v, PASSA=passa))
            print(saidas[-1]["unid"], nome, round(df_, 2), "+-", round(ic, 2), "PASSA" if passa else "", flush=True)
        # H10: rompimento x confirmacao, por sinal (nao disparado = 0), ambos contra o proprio nulo do evento
        base = f.res_atr; rup = f.H10
        dd = rup - base
        saidas.append(dict(unid=f"{tf}_{modo}", hip="H10 rompimento x confirmacao (por sinal)", melhor="rompe", pior="confirma",
                           n_melhor=int(f.H10disp.sum()), n_pior=len(f), dif=dd.mean(), ic=1.96 * dd.std() / np.sqrt(len(dd)),
                           m22_23=dd[f.ano <= 2023].mean(), m24_25=dd[f.ano >= 2024].mean(),
                           compra=dd[f.lado == 1].mean(), venda=dd[f.lado == -1].mean(),
                           PASSA=dd.mean() - 1.96 * dd.std() / np.sqrt(len(dd)) > 0))
        print(saidas[-1]["unid"], "H10", round(dd.mean(), 2), "disparo", round(f.H10disp.mean(), 2), flush=True)
    t = pd.DataFrame(saidas); t.to_pickle(R + "hipoteses.pkl")
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(t.round(2).to_string(index=False))
    print("PASSARAM:", int(t.PASSA.sum()), "de", len(t))


if __name__ == "__main__":
    main()
