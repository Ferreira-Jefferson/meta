import pickle, pandas as pd
pd.set_option('display.width',250)
A=pickle.load(open('finalA.pkl','rb'))
for rid in ('R10','R1','R7'):
    for w in (1,2,3):
        t=A['cmp'][(rid,w)][['grupo','n','por_dia','acerto','be_emp','esp','ic_lo','ic_hi','payoff','seq_perdas','mfe30','mae30','mfe60','mae60']].round(2)
        print('####',rid,w); print(t.to_string(index=False)); print(A['pud'][(rid,w)].round(3).to_string(index=False))
