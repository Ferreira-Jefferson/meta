"""Execução do robô: uma posição por vez por pregão, entrada limitada, stop plugável, zera no fim do pregão.

Entrada: ordem limitada no close da barra de confirmação, válida por VALIDADE barras; só enche se o preço passar
FURA pts além do limite (fila); preço = o limite, ou a abertura se ela já vier melhor. Cancela se o stop for tocado
antes. Saída: stop (pelo pior entre a abertura e o stop) ou close da última barra do pregão. Sem alvo.
Resultado em pts: CONTRATOS x (movimento - CUSTO).
"""
from types import SimpleNamespace
import numpy as np
import pandas as pd

FURA, VALIDADE, CUSTO, CONTRATOS = 10, 3, 10, 2


def entrada_limitada(D, t0, lado, lim, stop):
    o, h, l = D["open"], D["high"], D["low"]
    for t in range(t0, min(t0 + VALIDADE, len(o))):
        if (l[t] <= stop) if lado == 1 else (h[t] >= stop): return None
        if (l[t] <= lim - FURA) if lado == 1 else (h[t] >= lim + FURA):
            return t, (min(o[t], lim) if lado == 1 else max(o[t], lim))
    return None


def operar(sinais, dias, inicial, mover):
    """sinais em ordem (seg, t0). Devolve um DataFrame com uma linha por operação."""
    livre_apos, out = {}, []
    for s in sinais.itertuples():
        if s.t0 <= livre_apos.get(s.seg, -1): continue
        D = dias[s.seg]; o, h, l, c = D["open"], D["high"], D["low"], D["close"]
        lado = s.lado
        stop = stop_ini = inicial(s, D)
        ent = entrada_limitada(D, s.t0, lado, c[s.t0 - 1], stop)
        if ent is None: continue
        t_ent, px = ent
        if (px - stop) * lado <= 0: continue
        p = SimpleNamespace(lado=lado, px=px, R=(px - stop) * lado, ext=px, pior=px, t_ent=t_ent)
        saida, t_sai, motivo = c[-1], len(o) - 1, "fim"
        for t in range(t_ent, len(o)):
            ot = px if t == t_ent else o[t]
            if (l[t] <= stop) if lado == 1 else (h[t] >= stop):
                saida, t_sai, motivo = (min(ot, stop) if lado == 1 else max(ot, stop)), t, "stop"
                break
            p.ext = max(p.ext, h[t]) if lado == 1 else min(p.ext, l[t])
            p.pior = min(p.pior, l[t]) if lado == 1 else max(p.pior, h[t])
            stop = mover(stop, t, p, D)
        livre_apos[s.seg] = t_sai
        mov = (saida - px) * lado
        out.append(dict(dia=D["dia"], seg=s.seg, pos=s.pos, lado=lado, t_ent=t_ent, t_sai=t_sai, px=px, saida=saida,
                        stop_ini=stop_ini, R=p.R, mfe=(p.ext - px) * lado, mae=(px - p.pior) * lado, motivo=motivo,
                        mov=mov, pts=CONTRATOS * (mov - CUSTO)))
    return pd.DataFrame(out)


def resumo(tr):
    x = tr.pts.to_numpy() if len(tr) else np.zeros(0)
    eq = np.cumsum(x); dd = (np.maximum.accumulate(eq) - eq).max() if len(x) else 0.0
    return dict(ops=len(x), total=x.sum(), pts_op=x.mean() if len(x) else np.nan, acerto=(x > 0).mean() if len(x) else np.nan,
                dd=dd, total_dd=x.sum() / dd if dd else np.nan, reais=x.sum() * 0.2)
