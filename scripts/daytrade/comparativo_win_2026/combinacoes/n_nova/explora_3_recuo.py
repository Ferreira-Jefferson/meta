"""N1 / exploratoria 3 (so' DEV): dia de TENDENCIA as 10:30 (regime do Deslocamento) + entrada no RECUO por
ordem-limite (conceito retangulo/limite) + saida da familia tendencia.

Regime: |desl| >= 0,3 ATRd e nenhuma M1 fechada do outro lado de O -/+ 0,05 ATRd (explora_1).
Entrada: limite em P = O + f*(c1029 - O), enviada as 10:30, valida ate' `ate`. f=1 = o proprio Deslocamento.
Stop: linha da abertura O -/+ 0,05 ATRd (a mercado). Saida: zera 17:50 (sem alvo) | variante TRAIL: stop recolocado
na roxa M5 -/+ 0,6 ATR(M5) a cada M5 fechada (so' aperta, nunca abaixo da linha).
Controle de selecao adversa: o mesmo dia, entrando a 'mercado' (limite = fech. 10:29, prazo 15 min) -- compara o
resultado dos dias que ENCHERAM o recuo com o resultado desses mesmos dias na entrada das 10:30.
"""
import numpy as np, pandas as pd
import dados_dev as D
from explora_lib import m1_ajustada, ohlc, lwma, sim, arred, CUSTO_PTS

x = pd.read_parquet("explora_1_dias.parquet").set_index("dia")
x = x[x.tend]
b = m1_ajustada()
m5 = ohlc(b, "5min")
c, h, l = (m5[k].to_numpy(float) for k in ("close", "high", "low"))
m5["w"] = lwma(c, 34)
pc = np.r_[np.nan, c[:-1]]
m5["atr"] = pd.Series(np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))).rolling(14).mean().to_numpy()
idx = m5.index.date


def ms(t):
    return int(pd.Timestamp(t).value // 10**6)


res = []
for dia, info in x.iterrows():
    tk = D.ticks(dia)
    aj = b.aj[b.index.date == dia].iloc[0]
    lado = int(info.lado)
    O, c0, atr = info.O - aj, info.c1029 - aj, info.atr
    linha = arred(O - lado * 0.05 * atr)
    t_env = ms(pd.Timestamp(dia) + pd.Timedelta("10:30:00"))
    t_zera = ms(pd.Timestamp(dia) + pd.Timedelta("17:50:00"))
    g = m5[(idx == dia)]
    g = g[g.index >= pd.Timestamp(dia) + pd.Timedelta("10:30:00")]
    trail = [(ms(t + pd.Timedelta(minutes=5)), arred(ww - aj - lado * 0.6 * aa)) for t, ww, aa in zip(g.index, g.w, g.atr)]
    for f in (1.0, 0.75, 0.5, 0.25):
        for ate in ("10:45", "12:00", "14:00", "16:30"):
            if f == 1.0 and ate != "10:45":
                continue
            if f < 1.0 and ate == "10:45":
                continue
            lim = arred(O + f * (c0 - O))
            ttl = ms(pd.Timestamp(dia) + pd.Timedelta(ate + ":00")) - t_env
            for saida in ("ZERA", "TRAIL"):
                o = sim(tk, t_env, lado, lim, ttl, stop=linha, t_zera=t_zera,
                        stop_trail=trail if saida == "TRAIL" else None)
                res.append(dict(dia=dia, ano=dia.year, f=f, ate=ate, saida=saida, enc=o is not None,
                                **(o or {}), stop_pts=abs(lim - linha), atr=atr))
r = pd.DataFrame(res)
r["liq"] = r.pts - CUSTO_PTS
r.to_parquet("explora_3_ops.parquet")
base = r[(r.f == 1.0) & (r.saida == "ZERA")].set_index("dia").liq


def resumo(z):
    e = z[z.enc]
    gan = e.pts[e.pts > 0]; per = -e.pts[e.pts <= 0]
    be = per.mean() / (gan.mean() + per.mean()) if len(gan) and len(per) else np.nan
    anos = e.groupby("ano").liq.sum() * 0.2
    return pd.Series(dict(dias=len(z), fill=z.enc.mean(), n=len(e), liq_op=e.liq.mean(), ep=e.pts.std() / np.sqrt(max(len(e), 1)),
                          win=(e.pts > 0).mean(), be_emp=be, stop_med=e.stop_pts.median(), rs_liq=e.liq.sum() * 0.2,
                          r22=anos.get(2022, 0), r23=anos.get(2023, 0), r24=anos.get(2024, 0),
                          base_mesmos_dias=base.reindex(e.dia).mean()))


pd.set_option("display.width", 220)
print(r.groupby(["f", "ate", "saida"]).apply(resumo).round(2).to_string())
