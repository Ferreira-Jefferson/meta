import kit_pernadas as k
m1=k.carregar_m1()
ev=k.todos_eventos(m1)
ev.to_csv("eventos.csv",index=False)
f=k.features_m1(m1); f.to_csv("features_m1.csv")
print(len(ev), ev.groupby(['tf','X']).agg(n=('y','size'),cens=('y',lambda s:s.isna().sum()),taxa=('y','mean')))
print(ev.n_piv.eq(0).mean())
