"""N1 / exploratoria 4 (so' DEV): o regime 'dia de tendencia' em outros horarios de decisao, para saber se a
candidata do recuo pode operar com mais frequencia que ~4 dias/mes.

Para T em {10:30, 11:30, 12:30, 13:30}: desl_T = (fech. da M1 anterior a T - O)/ATRd; sinal se |desl_T| >= k e
nenhuma M1 fechada desde 9:00 do outro lado de O -/+ 0,05 ATRd. Conta so' o 1o horario que sinaliza no dia.
Mede: fwd ate' 17:50 a favor (ATRd) e a ordem do recuo f=0,5 (limite em O + 0,5*(c_T - O), valida 90 min,
stop na linha, zera 17:50).
"""
import numpy as np, pandas as pd
import dados_dev as D
from explora_lib import m1_ajustada, sim, arred, CUSTO_PTS

x = pd.read_parquet("explora_1_dias.parquet").set_index("dia")
b = m1_ajustada()
dts = b.index.date


def ms(t):
    return int(pd.Timestamp(t).value // 10**6)


res = []
for dia, info in x.iterrows():
    g = b[dts == dia]
    aj = g.aj.iloc[0]; O = g.open.iloc[0]; atr = info.atr
    tk = None
    for k in (0.3, 0.5):
        for T in ("10:30", "11:30", "12:30", "13:30"):
            tT = pd.Timestamp(dia) + pd.Timedelta(T + ":00")
            am = g[g.index < tT]
            cT = am.close.iloc[-1]
            desl = (cT - O) / atr
            lado = int(np.sign(desl))
            cruz = (am.close < O - 0.05 * atr).any() if lado > 0 else (am.close > O + 0.05 * atr).any()
            if abs(desl) < k or cruz:
                continue
            pm = g[(g.index >= tT) & (g.index.time < pd.Timestamp("17:50").time())]
            fwd = lado * (pm.close.iloc[-1] - cT) / atr
            tk = tk or D.ticks(dia)
            linha = arred(O - aj - lado * 0.05 * atr)
            lim = arred(O - aj + 0.5 * (cT - O))
            o = sim(tk, ms(tT), lado, lim, 90 * 60000, stop=linha, t_zera=ms(pd.Timestamp(dia) + pd.Timedelta("17:50:00")))
            res.append(dict(dia=dia, ano=dia.year, k=k, T=T, fwd=fwd, enc=o is not None, liq=(o["pts"] - CUSTO_PTS) if o else np.nan))
            break   # so' o 1o horario do dia
r = pd.DataFrame(res)
print(r.groupby(["k", "T"]).agg(dias=("fwd", "size"), fwd=("fwd", "mean"), fwd_ep=("fwd", lambda s: s.std() / np.sqrt(len(s))),
                                fill=("enc", "mean"), n=("enc", "sum"), liq_op=("liq", "mean"),
                                rs=("liq", lambda s: s.sum() * 0.2)).round(3).to_string())
print(r.groupby(["k", "T", "ano"]).liq.sum().mul(0.2).unstack().round(0).to_string())
