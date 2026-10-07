import pickle, pandas as pd
def md(d):
    nl = chr(10)
    return nl.join(["| "+" | ".join(map(str,d.columns))+" |","|"+"---|"*len(d.columns)]+["| "+" | ".join(map(str,r))+" |" for r in d.values])
R = pickle.load(open("hip_b_res.pkl","rb"))
base = R[("base",1,1)]
order = [("base",1,1)] + sorted([k for k in R if k!=("base",1,1)], key=lambda k:(["vwap","abert","oraculo"].index(k[0]),k[1],k[2]))
bj = {j[0]:j for j in base[1]}
rows=[]
for k in order:
    m,jan = R[k]
    liq=[j[1] for j in jan]
    top = max(jan,key=lambda j:j[1])[0]
    lo = sum(j[1] for j in jan if j[0]!=top); lob = sum(j[1] for j in base[1] if j[0]!=top)
    rows.append({"variante": f"{k[0]} fav{k[1]}/contra{k[2]}" if k[0]!="base" else "BASELINE 1/1",
      "liq R$":round(m["liquido_total"]),"jan+":m["janelas_pos"],"pior jan":round(m["pior_janela"]),"PF":m["PF"],"trades":m["trades"],
      "DD R$":round(m["maior_DD_R$"]),"DD%":m["maior_DD%"],"DDmed%":m["DD_medio%"],"fator rec":m["fator_recup"],
      "cx<250":m["jan_cx<250"],"cx<100":m["jan_cx<100"],"seq perd":round(m["seq_perdas_R$"]),
      "LOWO liq":round(lo),"LOWO base":round(lob)})
df=pd.DataFrame(rows); print(md(df))
# mes a mes: base, vwap 2/0, vwap 2/1, abert 2/0, oraculo 2/0
cols=[("base",1,1),("vwap",2,0),("vwap",2,1),("abert",2,0),("abert",2,1),("oraculo",2,0)]
t=pd.DataFrame({"janela":[j[0] for j in base[1]],"mercado pts":[round(j[2]) for j in base[1]]})
for c in cols: t[f"{c[0]} {c[1]}/{c[2]}"]=[round(j[1]) for j in R[c][1]]
print(); print(md(t))
