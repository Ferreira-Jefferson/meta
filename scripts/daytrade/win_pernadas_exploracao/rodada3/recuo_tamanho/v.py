import pandas as pd,sys
pd.set_option("display.width",250);pd.set_option("display.max_rows",2000)
t=pd.read_pickle(f"tab_{sys.argv[1]}.pkl")
print(t[(t.z.abs()>=2)&(t.dim!="all")].round(3).to_string())
for d in ["ab","hb","ob","db"]:
    x=t[(t.dim==d)&(t.m=="NH")].pivot(index="lv",columns="sub",values="exc").round(3)
    n=t[(t.dim==d)&(t.m=="NH")].pivot(index="lv",columns="sub",values="n")
    print(d,"excesso NH vs nulo");print(x);print(n)
