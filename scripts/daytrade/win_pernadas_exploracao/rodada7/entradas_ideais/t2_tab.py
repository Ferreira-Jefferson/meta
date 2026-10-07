import pandas as pd, numpy as np
from base import *
df=pd.read_csv(PASTA+"geometrias_cv_janjun.csv")
pd.set_option("display.width",250)
print("n geometrias",len(df))
for c in ("N","piso","K","m","S"):
    print("\n== marginal por",c); print(df.groupby(c)[["base","be","auc","auc_mes","esp_top","acerto_top","be_top","n"]].mean().round(3).to_string())
print("\n== AUC medio por K x N"); print(df.pivot_table(index="K",columns="N",values="auc").round(3))
print("\n== esp_top por K x N"); print(df.pivot_table(index="K",columns="N",values="esp_top").round(1))
print("\n== esp_top por S x m"); print(df.pivot_table(index="S",columns="m",values="esp_top").round(1))
d=df[df.n>=250].sort_values("esp_top_suav",ascending=False)
print("\n== top 15 por esp_top suavizado (n>=250)"); print(d.head(15)[["m","S","N","piso","K","n","base","be","auc","acerto_top","be_top","esp_top","esp_top_suav","auc_suav"]].round(3).to_string(index=False))
print("\n== top 10 por AUC suavizado"); print(df[df.n>=250].sort_values("auc_suav",ascending=False).head(10)[["m","S","N","piso","K","n","base","auc","auc_suav","esp_top"]].round(3).to_string(index=False))
print("frac geometrias esp_top>0:", (df.esp_top>0).mean().round(3), "acerto_top>be_top", (df.acerto_top>df.be_top).mean().round(3))
