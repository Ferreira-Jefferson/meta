import sys; sys.path.insert(0,'ciclo3'); sys.path.insert(0,'.')
import base, pandas as pd
for dia in sys.argv[1:]:
    for t,ctx in base.contextos(dia):
        if t.hour*60+t.minute in (555,570,585,600,675,735,765,750):
            h=ctx.hoje
            gap=float(h.open.iloc[0]-ctx.diario.close.iloc[-1])
            print(dia,t.time(),'atrd',round(ctx.atrd),'atr15',round(ctx.atr15),'gap',round(gap),'ampl/atrd',round((h.high.max()-h.low.min())/ctx.atrd,2),'desloc/atrd',round((h.close.iloc[-1]-h.open.iloc[0])/ctx.atrd,2), 'ontem',ctx.diario.close.iloc[-1],ctx.diario.low.iloc[-1],ctx.diario.high.iloc[-1])
