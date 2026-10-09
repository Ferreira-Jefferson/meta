import sys, json; sys.path.insert(0, '.')
import numpy as np, pandas as pd
import cfg3, base, av

neg = json.load(open("ciclo3_negativos_bruto.json"))
MAX = 600.0
out = []
for n in neg:
    d = n["dia"]; m1 = base.carrega(d, 0); dt = pd.Timestamp(d)
    m1d = m1[m1.index.normalize() == dt]
    fim = m1d.index[m1d["ultima_continua"]].max() if m1d["ultima_continua"].any() else m1d.index.max()
    m15 = base._m15(m1d)
    best = None
    for ts, r in m15.iterrows():
        t = ts + pd.Timedelta(minutes=15)
        if t > fim: continue
        p = float(r.close)
        j = m1d[m1d.index >= t]
        for lado in ("compra", "venda"):
            sg = 1 if lado == "compra" else -1
            ent = None; ext = None
            for tt, x in zip(j.index, j.itertuples()):
                if ent is None:
                    if tt >= t + base.VALIDADE: break
                    if (x.low <= p - base.FURA) if sg == 1 else (x.high >= p + base.FURA): ent = tt
                    continue
                if (x.low <= p - MAX) if sg == 1 else (x.high >= p + MAX): break
                e = x.high if sg == 1 else x.low
                if ext is None or (e - ext) * sg > 0: ext = e
                if tt >= fim: break
            if ent is None or ext is None: continue
            pts = (ext - p) * sg - base.CUSTO
            if best is None or pts > best["pts"]: best = dict(t=str(t.time()), lado=lado, preco=p, pts=round(pts, 1), brl=round(pts * 0.2, 1))
    # o que o v3 fez nessa hora
    tb = pd.Timestamp(d + " " + best["t"])
    pos = [x for x in n["trades"] if pd.Timestamp(d + " " + x["ent"]) <= tb <= pd.Timestamp(d + " " + x["sai"])]
    lg = [x for x in n["log"] if x["t"] == best["t"]]
    out.append(dict(dia=d, tipo=n["tipo"], ef=n["ef"], brl=n["brl"], v2=n["v2"], v1=n["v1"], melhor=best, posicao_aberta=[(x["fonte"][:40], x["lado"]) for x in pos],
                    log_na_hora=lg, trades=[(x["fonte"][:42], x["lado"], x["sinal"], x["motivo"], x["brl"]) for x in n["trades"]]))
json.dump(out, open("p5_negativos.json", "w"), indent=1, default=str)
for o in out:
    print(o["dia"], o["tipo"], o["ef"], "v3", o["brl"], "v2", o["v2"], "v1", o["v1"])
    for t in o["trades"]: print("   ", t)
    print("   melhor:", o["melhor"], "| pos aberta:", o["posicao_aberta"], "| log:", [(x["fazer"], x["vetos"], x["nota"]) for x in o["log_na_hora"]])
