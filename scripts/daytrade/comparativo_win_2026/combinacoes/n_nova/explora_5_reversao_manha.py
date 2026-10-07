"""N1 / exploratoria 5 (so' DEV): a unica reversao com direcao que replicou (VR5 < 1 na 1a hora; reversao M1 lag-1)
-- vale como gatilho de uma 2a candidata de frequencia maior?

1) descritiva: retorno M5 seguinte condicionado ao retorno M5 atual, por faixa horaria (correlacao lag-1 de M5).
2) fade com limite: M5 fechada com |corpo| >= q*ATR14(M5) entre 9:10 e 10:25 -> limite CONTRA o impulso em
   fech + dir*e*ATR (estende mais um pouco), prazo 10 min, stop e+s ATR alem, alvo no meio do corpo do impulso.
"""
import numpy as np, pandas as pd
import dados_dev as D
from explora_lib import m1_ajustada, ohlc, sim, arred, CUSTO_PTS

b = m1_ajustada()
m5 = ohlc(b, "5min")
c, h, l, o = (m5[k].to_numpy(float) for k in ("close", "high", "low", "open"))
pc = np.r_[np.nan, c[:-1]]
m5["atr"] = pd.Series(np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))).rolling(14).mean().to_numpy()
m5["ret"] = c - o
dev = set(D.dias("DEV"))
m5 = m5[[d in dev for d in m5.index.date]]
m5["prox"] = m5.groupby(m5.index.date).ret.shift(-1)
m5["hora"] = m5.index.hour + (m5.index.minute >= 30) * 0.5
print("corr(ret M5, ret M5 seguinte) por meia hora:")
print(m5.groupby("hora").apply(lambda z: pd.Series(dict(n=len(z), corr=z.ret.corr(z.prox),
      prox_dado_grande=(-np.sign(z.ret) * z.prox)[z.ret.abs() >= z.atr].mean()))).round(3).to_string())


def ms(t):
    return int(pd.Timestamp(t).value // 10**6)


res = []
for dia in sorted(dev):
    g = m5[m5.index.date == dia]
    g = g[(g.index.time >= pd.Timestamp("09:10").time()) & (g.index.time <= pd.Timestamp("10:25").time())]
    if g.empty:
        continue
    tk = D.ticks(dia); aj = b.aj[b.index.date == dia].iloc[0]
    for q in (1.0, 1.5):
        livre = 0
        for t, r in g.iterrows():
            if abs(r.ret) < q * r.atr or not np.isfinite(r.atr):
                continue
            t_env = ms(t + pd.Timedelta(minutes=5))
            if t_env < livre:
                continue
            imp = np.sign(r.ret); lado = -int(imp)
            for e, s in ((0.0, 1.0), (0.5, 1.0)):
                lim = arred(r.close - aj + imp * e * r.atr)
                alvo = arred((r.open + r.close) / 2 - aj)
                stop = arred(lim - lado * s * r.atr)
                op = sim(tk, t_env, lado, lim, 10 * 60000, stop=stop, alvo=alvo,
                         t_zera=ms(pd.Timestamp(dia) + pd.Timedelta("17:50:00")))
                if op:
                    res.append(dict(dia=dia, ano=dia.year, q=q, e=e, s=s, **op))
                    if e == 0.0:
                        livre = op["t_sai"]
r = pd.DataFrame(res)
r["liq"] = r.pts - CUSTO_PTS
print(r.groupby(["q", "e", "s"]).apply(lambda z: pd.Series(dict(n=len(z), pts=z.pts.mean(), ep=z.pts.std() / np.sqrt(len(z)),
      liq=z.liq.mean(), win=(z.pts > 0).mean(), rs=z.liq.sum() * .2))).round(2).to_string())
print(r.groupby(["q", "e", "s", "ano"]).liq.mean().unstack().round(1).to_string())
