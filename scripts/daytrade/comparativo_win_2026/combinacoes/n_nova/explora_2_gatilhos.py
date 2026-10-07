"""N1 / exploratoria 2 (so' DEV): gatilho rapido da familia TENDENCIA (roxa M5) e da familia RETANGULO (borda da
faixa da manha) separados pelo REGIME do dia as 10:30 (explora_1).

G_TEND (conceito Win): M5 fechada inteira alem da LWMA34 (roxa), SMMA34 (verde) do outro lado da roxa, idade da onda
  <= 9 velas. Ordem-limite no fechamento da vela do sinal, prazo 10 min. Stop = roxa -/+ 0,6 ATR14(M5), recolocado a
  cada M5 fechada (so' aperta). Sai a mercado na abertura da M5 seguinte a uma M5 que FECHA do lado errado da roxa.
  Zera 17:50. Sem entrada >= 16:30. Uma posicao por vez.
  Classes: MANHA (sinal < 10:30), A_FAVOR (dia TEND e sinal do lado do desl), CONTRA (TEND, lado oposto), NEUTRO.
G_RET (conceito retangulo): depois das 10:30, limite de venda na maxima da manha e de compra na minima (uma de cada
  por dia, valida ate' 16:30); stop = borda + s*W (W = largura da manha), alvo = borda -/+ a*W. Zera 17:50.
Custo: 10 pts/op (R$2). R$ = pts * 0,20.
"""
import numpy as np, pandas as pd
import dados_dev as D
from explora_lib import m1_ajustada, ohlc, lwma, smma, sim, arred, CUSTO_PTS

x = pd.read_parquet("explora_1_dias.parquet").set_index("dia")
b = m1_ajustada()
m5 = ohlc(b, "5min")
c, h, l = (m5[k].to_numpy(float) for k in ("close", "high", "low"))
w, s = lwma(c, 34), smma(c, 34)
pc = np.r_[np.nan, c[:-1]]
tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
atr = pd.Series(tr).rolling(14).mean().to_numpy()
lado_r = np.sign(c - w)
run = np.ones(len(c), int)
for i in range(1, len(c)):
    run[i] = run[i - 1] + 1 if lado_r[i] == lado_r[i - 1] else 1
sig = np.where((l > w) & (s < w) & (run <= 9), 1, np.where((h < w) & (s > w) & (run <= 9), -1, 0))
m5["w"], m5["atr"], m5["sig"], m5["lado_r"] = w, atr, sig, lado_r
idx_dia = m5.index.date


def ms(t):
    return int(pd.Timestamp(t).value // 10**6)


res = []
for dia in x.index:
    tk = D.ticks(dia)
    info = x.loc[dia]
    aj = b.aj[b.index.date == dia].iloc[0]          # serie ajustada = crua + aj
    g = m5[idx_dia == dia]
    t_zera = ms(pd.Timestamp(dia) + pd.Timedelta("17:50:00"))
    livre = 0
    for k in range(len(g) - 1):
        r = g.iloc[k]
        t_fech = g.index[k] + pd.Timedelta(minutes=5)
        if r.sig == 0 or t_fech.time() >= pd.Timestamp("16:30").time() or ms(t_fech) < livre:
            continue
        lado = int(r.sig)
        lim = arred(r.close - aj)
        stop0 = arred(r.w - aj - lado * 0.6 * r.atr)
        # trilha do stop e saida pela roxa a partir das M5 seguintes
        fut = g.iloc[k + 1:]
        trail = [(ms(t + pd.Timedelta(minutes=5)), arred(ww - aj - lado * 0.6 * aa)) for t, ww, aa in zip(fut.index, fut.w, fut.atr)]
        contra = fut.index[(fut.lado_r.to_numpy() != lado)]
        saidas = [ms(t + pd.Timedelta(minutes=5)) for t in contra]
        o = sim(tk, ms(t_fech), lado, lim, 10 * 60000, stop=stop0, t_zera=t_zera, saidas_ms=saidas, stop_trail=trail)
        if o is None:
            continue
        livre = o["t_sai"]
        hora = pd.Timestamp(o["t_ent"], unit="ms")
        if hora.time() < pd.Timestamp("10:30").time():
            cl = "MANHA"
        elif info.tend:
            cl = "A_FAVOR" if lado == info.lado else "CONTRA"
        else:
            cl = "NEUTRO"
        res.append(dict(g="TEND", dia=dia, ano=dia.year, classe=cl, lado=lado, **o))

# --- G_RET
for a_fr, s_fr in ((0.5, 0.5), (1.0, 0.5)):
    for dia in x.index:
        info = x.loc[dia]
        aj = b.aj[b.index.date == dia].iloc[0]
        W = info.Ham - info.Lam
        if W <= 0:
            continue
        tk = D.ticks(dia)
        t_env = ms(pd.Timestamp(dia) + pd.Timedelta("10:30:00"))
        ttl = ms(pd.Timestamp(dia) + pd.Timedelta("16:30:00")) - t_env
        t_zera = ms(pd.Timestamp(dia) + pd.Timedelta("17:50:00"))
        for lado, borda in ((-1, info.Ham - aj), (1, info.Lam - aj)):
            lim = arred(borda)
            o = sim(tk, t_env, lado, lim, ttl, stop=arred(lim - lado * s_fr * W), alvo=arred(lim + lado * a_fr * W), t_zera=t_zera)
            if o is None:
                continue
            cl = "NEUTRO" if not info.tend else ("A_FAVOR" if lado == info.lado else "CONTRA")
            res.append(dict(g=f"RET a{a_fr} s{s_fr}", dia=dia, ano=dia.year, classe=cl, lado=lado, **o))

r = pd.DataFrame(res)
r["liq"] = r.pts - CUSTO_PTS
r.to_parquet("explora_2_ops.parquet")


def resumo(z):
    gan = z.pts[z.pts > 0]; per = -z.pts[z.pts <= 0]
    be = per.mean() / (gan.mean() + per.mean()) if len(gan) and len(per) else np.nan
    return pd.Series(dict(n=len(z), pts_op=z.pts.mean(), liq_op=z.liq.mean(), ep=z.pts.std() / np.sqrt(len(z)),
                          win=(z.pts > 0).mean(), be_emp=be, rs_liq=z.liq.sum() * 0.2))


pd.set_option("display.width", 200)
print(r.groupby(["g", "classe"]).apply(resumo).round(3))
print()
print(r.groupby(["g", "classe", "ano"]).liq.mean().unstack().round(1))
