import pandas as pd
from metricas import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)
M = carrega()
rows = []
for s in STOPS:
    for j in JANS:
        x = M[s, j]
        rows.append(dict(stop=s, jan=j, n=x["n"], liq=round(x["liq"]), win=round(x["win"], 1), payoff=round(x["payoff"], 2), pf=round(x["pf"], 2),
                         ddRS=round(x["dd"]), ddp=round(x["ddp"], 1), rf=round(x["rf"], 2), smin=round(x["smin"]), quebrou=x["quebrou"] and x["data_quebra"],
                         seq=x["seqperd"], pior_mes=round(x["pior_mes"]), mes_pos=round(x["mes_pos"])))
T = pd.DataFrame(rows); T.to_csv(OUT / "tabela_por_stop_janela.csv", index=False)
print(T.to_string(index=False))
A = agrega(M); df, esc = ranking(A)
df.round(3).to_csv(OUT / "ranking.csv")
print(df.round(3).to_string()); print("ESCOLHIDO", esc)
