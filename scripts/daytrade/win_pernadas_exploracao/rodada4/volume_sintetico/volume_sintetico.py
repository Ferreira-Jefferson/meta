"""Volume sintetico para o WIN: medidas de participacao normalizadas pelo horario, calculaveis em tempo real.

Insumos (so 2026): M1 (OPEN/HIGH/LOW/CLOSE/TICKVOL/VOL) e, de mar a set, ticks de negocio -> tabela por minuto
(minutos_ticks.pkl, feita por prep_ticks.py).  Tudo abaixo usa apenas informacao ate o fechamento do minuto.

Medidas por vela (colunas):
  tickvol, vol            M1 (existem o ano todo)
  nt                      negocios do minuto (ticks, mar+)
  tsz  = vol/tickvol      tamanho medio por "tick" do MT5 ; tszn = vol/nt tamanho medio do negocio
  dt                      delta pela REGRA DO TICK (contratos, assinado)      [mar+]
  dn                      delta em nº de negocios pela regra do tick           [mar+]
  dclv = vol*(2c-h-l)/(h-l)    delta ponderado pela posicao do fechamento no range da vela   [ano todo]
  dsgn = vol*sign(c-o)*|c-o|/(h-l)   delta ponderado pelo corpo/range                         [ano todo]
Normalizacao: x_rel = x / media do MESMO minuto (janela +-2 min) nos 20 pregoes anteriores (min 12), so 2026.
Delta relativo: delta / base de vol do slot.
"""
import io, numpy as np, pandas as pd
CSV="C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
HERE="C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/volume_sintetico"
NPREV=20; MINP=12

def load_m1(m0=1,m1=9):
    keep=[]
    with open(CSV,encoding="utf-8") as f:
        hdr=f.readline()
        for ln in f:
            if ln.startswith("2026.") and m0<=int(ln[5:7])<=m1: keep.append(ln)   # nunca le 2025
    d=pd.read_csv(io.StringIO(hdr+"".join(keep)),sep="\t")
    d.columns=[c.strip("<>").lower() for c in d.columns]
    d["mn"]=d["time"].str[:2].astype(int)*60+d["time"].str[3:5].astype(int)
    return d.drop(columns=["time","spread"])

def candle_measures(d):
    rng=(d.high-d.low).replace(0,np.nan)
    d["tsz"]=d.vol/d.tickvol.replace(0,np.nan)
    d["dclv"]=(d.vol*(2*d.close-d.high-d.low)/rng).fillna(0.0)
    d["dsgn"]=(d.vol*np.sign(d.close-d.open)*(d.close-d.open).abs()/rng).fillna(0.0)
    return d

def merge_ticks(d,path=HERE+"/minutos_ticks.pkl"):
    t=pd.read_pickle(path); t=t[t.fonte=="WIN@D"].drop(columns=["fonte","dr","drn"],errors="ignore")
    d=d.merge(t,on=["date","mn"],how="left")
    d["tszn"]=d.v/d.nt
    return d

def baseline(d,col,nprev=NPREV,minp=MINP,half=2):
    """media do mesmo minuto (janela +-half) nos nprev pregoes anteriores. Retorna serie alinhada a d."""
    pv=d.pivot_table(index="date",columns="mn",values=col,aggfunc="first").sort_index()
    sm=pv.T.rolling(2*half+1,center=True,min_periods=2).mean().T
    b=sm.rolling(nprev,min_periods=minp).mean().shift(1)
    return b.stack(future_stack=True).rename("b").reset_index().merge(d[["date","mn"]],on=["date","mn"],how="right")["b"].values

def add_rel(d):
    for c in ["tickvol","vol","nt","tsz","tszn"]:
        if c in d: d[c+"_rel"]=d[c]/baseline(d,c)
    bv=baseline(d,"vol")
    for c in ["dt","dclv","dsgn"]:
        if c in d: d[c+"_rel"]=d[c]/bv
    return d

def prepara():
    d=load_m1(); d=candle_measures(d); d=merge_ticks(d); d=add_rel(d)
    return d.sort_values(["date","mn"]).reset_index(drop=True)

if __name__=="__main__":
    d=prepara(); d.to_pickle(HERE+"/candles.pkl"); print(d.shape, d.isna().mean().round(3).to_dict())
