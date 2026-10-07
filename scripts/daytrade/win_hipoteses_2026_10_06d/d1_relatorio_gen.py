import pickle, numpy as np, pandas as pd
from pathlib import Path
P = Path(__file__).parent
T = pd.read_pickle(P/"d1_trades_base.pkl"); dfb = pd.read_pickle(P/"d1_df_base.pkl")
res = {}; [res.update(pickle.load(open(P/f"d1_res_stage{i}.pkl","rb"))) for i in (1,2)]
T["mae_a"]=T.mae/T.atr; T["mfe_a"]=T.mfe/T.atr; T["res_a"]=T.pts/T.atr
W=T[T.pnl>0]; Lo=T[T.pnl<=0]
out=[]
def pct(s): return " / ".join(f"{np.percentile(s,q):.1f}" for q in (50,75,90))
out.append("## 1. Diagnostico MAE/MFE (248 trades do baseline; MAE/MFE intrabarra, do preenchimento ate a barra da saida)\n")
out.append("| grupo | n | MAE pts p50/75/90 | MAE ATR p50/75/90 | MFE pts p50/75/90 | MFE ATR p50/75/90 | ATR medio (pts) | resultado medio (pts) |\n|---|---|---|---|---|---|---|---|")
for nome,g in (("todos",T),("vencedores",W),("perdedores",Lo),("a favor do mes",T[T.a_favor]),("neutros (regime 0)",T[~T.a_favor]),
               ("venc. a favor",W[W.a_favor]),("venc. neutros",W[~W.a_favor]),("perd. a favor",Lo[Lo.a_favor]),("perd. neutros",Lo[~Lo.a_favor])):
    out.append(f"| {nome} | {len(g)} | {pct(g.mae)} | {pct(g.mae_a)} | {pct(g.mfe)} | {pct(g.mfe_a)} | {g.atr.mean():.0f} | {g.pts.mean():.0f} |")
out.append(f"\nAcerto geral {100*(T.pnl>0).mean():.1f}% ; a favor do mes {len(T[T.a_favor])} trades (acerto {100*(T[T.a_favor].pnl>0).mean():.1f}%, pnl R$ {T[T.a_favor].pnl.sum():.0f}); neutros {len(T[~T.a_favor])} (acerto {100*(T[~T.a_favor].pnl>0).mean():.1f}%, pnl R$ {T[~T.a_favor].pnl.sum():.0f}). Barras medias de duracao: venc {W.barras.mean() if 'barras' in W and W.barras.sum() else float('nan'):.1f}.\n")
out.append("**(a) Vencedores cortados por stop inicial k x ATR** (MAE >= k ATR; ignora que o stop, ao disparar, muda a sequencia):\n\n| k | vencedores cortados | de | % | pnl desses vencedores (R$) | perdedores com MAE >= k ATR (ja' estariam no stop) |\n|---|---|---|---|---|---|")
for k in (0.5,1,1.5,2,3):
    c=W[W.mae_a>=k]; pl=Lo[Lo.mae_a>=k]
    out.append(f"| {k} | {len(c)} | {len(W)} | {100*len(c)/len(W):.0f}% | {c.pnl.sum():.0f} | {len(pl)} de {len(Lo)} |")
dev=W.mfe-W.pts
out.append(f"\n**(b) MFE devolvido pelos vencedores** (MFE - resultado): mediana {np.median(dev):.0f} pts ({np.median(dev/W.atr):.2f} ATR), p75 {np.percentile(dev,75):.0f}, p90 {np.percentile(dev,90):.0f}; MFE medio {W.mfe.mean():.0f} pts vs resultado medio {W.pts.mean():.0f} pts -> devolvem {100*(1-W.pts.mean()/W.mfe.mean()):.0f}% do MFE. Perdedores: MFE mediano {Lo.mfe.median():.0f} pts.\n")
q=Lo[Lo.mfe_a>0.5]
out.append(f"**(c) Perdedores que estiveram no lucro** (MFE > 0,5 ATR): {len(q)} de {len(Lo)} ({100*len(q)/len(Lo):.0f}%), pnl total deles R$ {q.pnl.sum():.0f}; com MFE > 1 ATR: {(Lo.mfe_a>1).sum()}.\n")
# aperta context
out.append("**Motivos de saida / duracao**: " + str(T.groupby('pnl').size().shape) if False else "")
out.append(f"Duracao (barras M30) mediana: vencedores {W.barras.median() if W.barras.max()>0 else 'n/d'}.")
# variants table
def linha(nome,st,df,r):
    m=df.set_index("janela").liquido; mb=dfb.set_index("janela").liquido
    mel=int((m.reindex(mb.index)>mb+0.005).sum()); pio=int((m.reindex(mb.index)<mb-0.005).sum())
    return (nome,r["liquido"],r["janelas_pos"],r["pior"],r["PF"],r["acerto"],r["trades"],r["maior_DD"],r["liquido_sem_set"],mel,pio)
rows=[("BASELINE",7805.2,"13/14",-117.0,1.68,40.3,248,781.5,7370.7,0,0)]
seen=set()
for nome,(st,df,r) in res.items():
    key=repr(st)
    if key in seen: continue
    seen.add(key); rows.append(linha(nome,st,df,r))
base=rows[0]; rest=sorted(rows[1:],key=lambda x:-x[1])
out.append(f"\n## 2. Variantes ({len(rest)} configuracoes unicas; {len(res)} rodadas incl. duplicatas) - ordenadas por liquido\n")
out.append("| variante | liquido R$ | janelas+ | pior | PF | acerto% | trades | DD | sem set | meses melhor/pior vs base |\n|---|---|---|---|---|---|---|---|---|---|")
for x in [base]+rest:
    out.append(f"| {x[0]} | {x[1]:.2f} | {x[2]} | {x[3]:.2f} | {x[4]} | {x[5]} | {x[6]} | {x[7]:.2f} | {x[8]:.2f} | {x[9]}/{x[10]} |")
# monthly for best
sel=["aperta N=2 k=1","aperta(2,1)+BE 1","aperta N=2 k=0.75","init k=1.5"]
mm=pd.DataFrame({"base":dfb.set_index("janela").liquido})
for s in sel:
    mm[s]=res[s][1].set_index("janela").liquido
out.append("\n## 3. Mes a mes (liquido R$)\n\n| janela | "+" | ".join(mm.columns)+" |\n|---|"+"---|"*len(mm.columns))
for j,rw in mm.iterrows(): out.append(f"| {j} | "+" | ".join(f"{v:.2f}" for v in rw)+" |")
out.append("| TOTAL | "+" | ".join(f"{v:.2f}" for v in mm.sum())+" |")
# trade-level effect of aperta(2,1): which trades changed
open(P/"d1_relatorio_parte.md","w",encoding="utf-8").write("\n".join(out))
print("\n".join(out))
