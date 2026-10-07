"""N1 / exploratoria 6b (grade N x f, saida EMA4) -- copia da 6 (so' DEV): o mecanismo da candidata 1 (impulso -> limite no recuo de 50% -> stop na origem
do impulso -> segura) com o impulso vindo da familia lenta (5 EMAs 2/4/6/17/33 no M30, alinhadas e subindo --
conceito WinCincoMedias SEM o filtro do mes, que nao validou em 2025). Teste de generalidade / frequencia.

Sinal na M30 fechada (9:30..15:00). Origem = minima (compra) das ultimas N M30 fechadas; topo = fech. do sinal.
Limite em origem + f*(topo-origem), prazo 60 min; stop = origem -/+ 0,1*ATR14(M30). Saida: ZERA 17:50 | EMA4
(M30 fecha do outro lado da EMA4 -> sai na abertura da seguinte). Uma posicao por vez.
"""
import numpy as np, pandas as pd
import dados_dev as D
from explora_lib import m1_ajustada, ohlc, sim, arred, CUSTO_PTS

b = m1_ajustada()
m30 = ohlc(b, "30min")
c, h, l = (m30[k].to_numpy(float) for k in ("close", "high", "low"))
E = {p: pd.Series(c).ewm(span=p, adjust=False).mean().to_numpy() for p in (2, 4, 6, 17, 33)}
up = np.all([E[a] > E[bb] for a, bb in ((2, 4), (4, 6), (6, 17), (17, 33))], axis=0) & np.all([np.r_[False, np.diff(E[p]) > 0] for p in E], axis=0)
dn = np.all([E[a] < E[bb] for a, bb in ((2, 4), (4, 6), (6, 17), (17, 33))], axis=0) & np.all([np.r_[False, np.diff(E[p]) < 0] for p in E], axis=0)
pc = np.r_[np.nan, c[:-1]]
m30["atr"] = pd.Series(np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))).rolling(14).mean().to_numpy()
m30["sig"] = np.where(up, 1, np.where(dn, -1, 0)); m30["e4"] = E[4]
dev = set(D.dias("DEV"))


def ms(t):
    return int(pd.Timestamp(t).value // 10**6)


res = []
for dia in sorted(dev):
    g = m30[m30.index.date == dia]
    tk = D.ticks(dia); aj = b.aj[b.index.date == dia].iloc[0]
    t_zera = ms(pd.Timestamp(dia) + pd.Timedelta("17:50:00"))
    for N in (3, 6):
        for f in (0.33, 0.5, 0.67):
            for saida in ("EMA4",):
                livre = 0
                for k in range(len(g)):
                    r = g.iloc[k]; t_f = g.index[k] + pd.Timedelta(minutes=30)
                    if r.sig == 0 or not (pd.Timestamp("09:30").time() <= t_f.time() <= pd.Timestamp("15:00").time()):
                        continue
                    if ms(t_f) < livre:
                        continue
                    lado = int(r.sig)
                    pos = m30.index.get_loc(g.index[k])
                    jan = m30.iloc[pos - N + 1:pos + 1]
                    orig = (jan.low.min() if lado > 0 else jan.high.max()) - aj
                    topo = r.close - aj
                    lim = arred(orig + f * (topo - orig)); stop = arred(orig - lado * 0.1 * r.atr)
                    fut = g.iloc[k + 1:]
                    sai = [ms(t + pd.Timedelta(minutes=30)) for t, cc, ee in zip(fut.index, fut.close, fut.e4) if lado * (cc - ee) < 0]
                    o = sim(tk, ms(t_f), lado, lim, 60 * 60000, stop=stop, t_zera=t_zera,
                            saidas_ms=sai if saida == "EMA4" else None)
                    if o:
                        livre = o["t_sai"]
                        res.append(dict(dia=dia, ano=dia.year, N=N, f=f, saida=saida, stop_pts=abs(lim - stop), **o))
r = pd.DataFrame(res); r["liq"] = r.pts - CUSTO_PTS


def resumo(z):
    gan = z.pts[z.pts > 0]; per = -z.pts[z.pts <= 0]
    return pd.Series(dict(n=len(z), pts=z.pts.mean(), ep=z.pts.std() / np.sqrt(len(z)), liq=z.liq.mean(), win=(z.pts > 0).mean(),
                          be=per.mean() / (gan.mean() + per.mean()), stop=z.stop_pts.median(), rs=z.liq.sum() * .2))


print(r.groupby(["N", "f", "saida"]).apply(resumo).round(2).to_string())
print(r.groupby(["N", "f", "saida", "ano"]).liq.sum().mul(.2).unstack().round(0).to_string())
# classe do regime das 10:30 (explora_1) para cada operacao
x = pd.read_parquet("explora_1_dias.parquet").set_index("dia")
r["hora"] = pd.to_datetime(r.t_ent, unit="ms").dt.time
r["cl"] = [("MANHA" if hh < pd.Timestamp("10:30").time() else ("NEUTRO" if not x.loc[d].tend else
           ("A_FAVOR" if lado == x.loc[d].lado else "CONTRA"))) if d in x.index else "?"
           for d, hh, lado in zip(r.dia, r.hora, np.sign(r.px - r.pe) * np.sign(r.pts).replace(0, 1))]
