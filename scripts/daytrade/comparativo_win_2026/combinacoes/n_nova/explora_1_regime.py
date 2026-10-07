"""N1 / exploratoria 1 (so' DEV 2022-01-03..2024-06-28): o estado do dia as 10:30 como REGIME.

Por dia: abertura O (1a M1), ATRd = media simples do TR das 14 D1 fechadas (serie ajustada por diferenca),
deslocamento as 10:30 = (fech. da M1 10:29 - O)/ATRd, cruzou = alguma M1 fechada do outro lado de O -/+ 0,05 ATRd.
Classe: TEND (|desl| >= 0,3 e nao cruzou) -- lado = sinal do desl; NEUTRO (o resto).
Mede, a partir das 10:30 ate' 17:50: retorno a favor do lado (ATRd), amplitude, e para NEUTRO o comportamento da
faixa da manha (max/min 9:00-10:29): quantas vezes o preco volta ao meio depois de tocar uma borda.
Saida: explora_1_dias.parquet (uma linha por dia, reaproveitada pelas outras exploratorias).
"""
import numpy as np, pandas as pd
import dados_dev as D
from explora_lib import m1_ajustada

b = m1_ajustada()
dts = b.index.date
d1 = b.groupby(dts).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
pc = d1.c.shift(1)
tr = np.fmax(d1.h - d1.l, np.fmax((d1.h - pc).abs(), (d1.l - pc).abs()))
d1["atr"] = tr.rolling(14).mean().shift(1)          # 14 D1 FECHADAS

linhas = []
for dia in D.dias("DEV"):
    g = b[dts == dia]
    atr = d1.loc[dia, "atr"]
    O = g.open.iloc[0]
    am = g[g.index.time < pd.Timestamp("10:30").time()]
    pm = g[(g.index.time >= pd.Timestamp("10:30").time()) & (g.index.time < pd.Timestamp("17:50").time())]
    if len(am) < 80 or len(pm) < 100 or not np.isfinite(atr):
        continue
    c1029 = am.close.iloc[-1]
    desl = (c1029 - O) / atr
    lado = int(np.sign(desl))
    cruzou = (am.close < O - 0.05 * atr).any() if lado > 0 else (am.close > O + 0.05 * atr).any()
    tend = abs(desl) >= 0.3 and not cruzou
    Ham, Lam = am.high.max(), am.low.min()
    fwd = (pm.close.iloc[-1] - c1029) / atr
    mfe_up = (pm.high.max() - c1029) / atr; mfe_dn = (c1029 - pm.low.min()) / atr
    # rompimento da faixa da manha depois das 10:30
    rompe_cima = pm.high.max() > Ham; rompe_baixo = pm.low.min() < Lam
    linhas.append(dict(dia=dia, ano=dia.year, atr=atr, desl=desl, lado=lado, cruzou=bool(cruzou), tend=tend,
                       larg_am=(Ham - Lam) / atr, fwd=fwd, fwd_favor=lado * fwd, amp_pm=(pm.high.max() - pm.low.min()) / atr,
                       mfe_favor=mfe_up if lado > 0 else mfe_dn, mae_favor=mfe_dn if lado > 0 else mfe_up,
                       rompe_cima=rompe_cima, rompe_baixo=rompe_baixo, rompe_ambos=rompe_cima and rompe_baixo,
                       c1029=c1029, O=O, Ham=Ham, Lam=Lam))
x = pd.DataFrame(linhas)
x.to_parquet("explora_1_dias.parquet")
print("dias DEV usados", len(x))
print("\n== classe do dia as 10:30 (TEND = |desl|>=0,3 ATR e nao cruzou) ==")
for nome, s in (("TEND", x[x.tend]), ("NEUTRO", x[~x.tend])):
    print(f"{nome:7s} n={len(s):4d}  fwd a favor do desl (ATR): media {s.fwd_favor.mean():+.3f} "
          f"ep {s.fwd_favor.std()/np.sqrt(len(s)):.3f}  P(>0) {np.mean(s.fwd_favor>0):.1%}  "
          f"amplitude pm {s.amp_pm.mean():.2f}  larg manha {s.larg_am.mean():.2f}  rompe 2 bordas {s.rompe_ambos.mean():.1%}  "
          f"rompe nenhuma {np.mean(~s.rompe_cima & ~s.rompe_baixo):.1%}")
print("\n== por ano, TEND: fwd a favor ==")
print(x[x.tend].groupby("ano").fwd_favor.agg(["count", "mean"]).round(3))
print("\n== por ano, NEUTRO: fwd a favor do desl (mesmo pequeno) ==")
print(x[~x.tend].groupby("ano").fwd_favor.agg(["count", "mean"]).round(3))
print("\n== faixa de |desl| (todas as classes) ==")
x["fx"] = pd.cut(x.desl.abs(), [0, .1, .2, .3, .5, .8, 5])
print(x.groupby(["fx", "cruzou"], observed=True).agg(n=("fwd_favor", "size"), fwd=("fwd_favor", "mean"),
                                                    amp=("amp_pm", "mean")).round(3))
