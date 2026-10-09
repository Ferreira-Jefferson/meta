"""Rodada 15 (2026-10-08): stop da v4 (so sinais bons, 2 contratos). Entradas iguais a v4; muda so o stop.

Stop inicial: pivo (base) | pivo -/+ colchao em ATR | entrada - m*ATR | o mais apertado / mais folgado de (pivo, m*ATR) |
minima da barra de confirmacao.
Movimento: estrutura (base, ZigZag 1,5) | estrutura mais rapida (ZigZag 0,75/1,0 no M15) | chandelier (extremo desde a
entrada - m*ATR, junto com a estrutura) | zero a zero apos x*R | MME21/34 | aperto por tempo (apos N barras, sobe para a
minima das ultimas 2 barras) | aperto por indicador (Estoc14 > 80 a favor ou preco > 2 ATR da MME21 -> sobe para zero a
zero ou para a minima da ultima barra).
O stop so anda a favor; vale a partir da barra seguinte a que o define. Zera no fim do pregao. Custo 10 pts/op.
Criterio: melhora total E total/queda no IS -> vizinhos -> OOS (uma vez).
"""
import numpy as np
import pandas as pd
import melhora_mm as mm
import melhora_osc as mo
import motor
import prob as pb

N_CONTR = 2


def preparar(per):
    b, f, c = pb.montar(per)
    f = f[f.bom].copy()
    k, _ = mo.estoc(b, 14, 3)
    b = b.assign(estoc=np.asarray(k), ema21x=b.close.ewm(span=21, adjust=False).mean(), ema34x=b.close.ewm(span=34, adjust=False).mean())
    dias = {}
    for s, (_, g) in enumerate(b.groupby(b.dia.values)):
        h, l, a = g.high.to_numpy(), g.low.to_numpy(), g.atr.to_numpy()
        dias[s] = dict(o=g.open.to_numpy(), h=h, l=l, c=g.close.to_numpy(), atr=a, e21=g.ema21x.to_numpy(), e34=g.ema34x.to_numpy(),
                       est=g.estoc.to_numpy(), dia=g.index[0].normalize(),
                       piv={K: {p[3]: p for p in motor.zigzag(h, l, a, K)} for K in (0.75, 1.0, 1.5)})
    return f, dias


def simular(f, dias, cfg):
    ocup, out = {}, []
    for e in f.itertuples():
        D = dias[e.seg]; o, h, l, c = D["o"], D["h"], D["l"], D["c"]
        if e.t0 <= ocup.get(e.seg, -1): continue
        lado, lim = e.lado, c[e.t0 - 1]; atr0 = D["atr"][e.t0 - 1]
        # stop inicial
        piv = e.stop; ini = cfg.get("ini", "pivo")
        if ini == "pivo": stop = piv - lado * cfg.get("colchao", 0) * atr0
        elif ini == "atr": stop = lim - lado * cfg["m"] * atr0
        elif ini == "apertado": stop = (max if lado == 1 else min)(piv, lim - lado * cfg["m"] * atr0)
        elif ini == "folgado": stop = (min if lado == 1 else max)(piv, lim - lado * cfg["m"] * atr0)
        elif ini == "barra": stop = l[e.t0 - 1] if lado == 1 else h[e.t0 - 1]
        tf_ = None
        for t in range(e.t0, min(e.t0 + mm.TTL, len(o))):
            if (l[t] <= stop) if lado == 1 else (h[t] >= stop): break
            if (l[t] <= lim - mm.FURA) if lado == 1 else (h[t] >= lim + mm.FURA):
                tf_ = t; px = min(o[t], lim) if lado == 1 else max(o[t], lim); break
        if tf_ is None or (px - stop) * lado <= 0: continue
        R = (px - stop) * lado; ext = px; conf = D["piv"][cfg.get("K", 1.5)]
        res, ts = None, len(o) - 1
        melhor = lambda a_, b_: (max if lado == 1 else min)(a_, b_)
        for t in range(tf_, len(o)):
            ot = px if t == tf_ else o[t]
            if (l[t] <= stop) if lado == 1 else (h[t] >= stop):
                res = ((min(ot, stop) - px) if lado == 1 else (px - max(ot, stop))); ts = t; break
            ext = max(ext, h[t]) if lado == 1 else min(ext, l[t])
            novo = stop
            p = conf.get(t)
            if cfg.get("estrutura", True) and p is not None and p[0] == ("F" if lado == 1 else "T"): novo = melhor(novo, p[2])
            a = D["atr"][t]
            if "chandelier" in cfg: novo = melhor(novo, ext - lado * cfg["chandelier"] * a)
            if "zero" in cfg and (ext - px) * lado >= cfg["zero"] * R: novo = melhor(novo, px + lado * 5)
            if "ema" in cfg:
                ev = D["e21"][t] if cfg["ema"] == 21 else D["e34"][t]
                if (c[t] - ev) * lado > 0: novo = melhor(novo, ev)
            if "tempo" in cfg and t - tf_ >= cfg["tempo"]:
                novo = melhor(novo, min(l[t], l[t - 1]) if lado == 1 else max(h[t], h[t - 1]))
            if "indic" in cfg:
                est = D["est"][t]; estm = est if lado == 1 else 100 - est
                esticado = (estm > 80) if cfg["indic"][0] == "estoc" else ((c[t] - D["e21"][t]) * lado > 2 * a)
                if esticado:
                    alvo_stop = px + lado * 5 if cfg["indic"][1] == "zero" else (l[t] if lado == 1 else h[t])
                    novo = melhor(novo, alvo_stop)
            stop = novo
        if res is None: res = (c[-1] - px) * lado
        ocup[e.seg] = ts
        out.append((D["dia"], N_CONTR * (res - 10), R))
    return pd.DataFrame(out, columns=["dia", "pts", "R"])


def resumo(t):
    x = t.pts.to_numpy(); eq = np.cumsum(x); dd = (np.maximum.accumulate(eq) - eq).max()
    return dict(ops=len(x), total=x.sum(), op=x.mean(), acerto=(x > 0).mean(), dd=dd, t_dd=x.sum() / dd, risco_medio=t.R.mean())


VARS = {"BASE v4 (pivô + estrutura 1,5)": {}}
for k in (0.1, 0.25): VARS[f"inicial: pivô + colchão {k} ATR"] = dict(colchao=k)
for k in (-0.1, -0.2): VARS[f"inicial: pivô apertado {abs(k)} ATR"] = dict(colchao=k)
for m in (1.0, 1.5, 2.0, 2.5, 3.0): VARS[f"inicial: entrada − {m} ATR"] = dict(ini="atr", m=m)
for m in (1.0, 1.5, 2.0): VARS[f"inicial: mais apertado de (pivô, {m} ATR)"] = dict(ini="apertado", m=m)
for m in (2.0, 3.0): VARS[f"inicial: mais folgado de (pivô, {m} ATR)"] = dict(ini="folgado", m=m)
VARS["inicial: mínima da barra de confirmação"] = dict(ini="barra")
for K in (0.75, 1.0): VARS[f"movimento: estrutura mais rápida (ZigZag {K})"] = dict(K=K)
VARS["movimento: sem mover (stop fixo no pivô)"] = dict(estrutura=False)
for m in (1.5, 2.0, 2.5, 3.0, 4.0): VARS[f"movimento: chandelier {m} ATR + estrutura"] = dict(chandelier=m)
for x in (0.5, 1.0, 1.5, 2.0): VARS[f"movimento: zero a zero após {x}R"] = dict(zero=x)
for n in (21, 34): VARS[f"movimento: segue a MME{n}"] = dict(ema=n)
for n in (8, 12, 16, 24): VARS[f"movimento: aperta após {n} barras"] = dict(tempo=n)
for ind in (("estoc", "zero"), ("estoc", "barra"), ("dist", "zero"), ("dist", "barra")):
    VARS[f"indicador: {'Estoc > 80' if ind[0] == 'estoc' else 'preço > 2 ATR da MME21'} → {'zero a zero' if ind[1] == 'zero' else 'mínima da barra'}"] = dict(indic=ind)


def main():
    fI, dI = preparar("pesquisa"); fO, dO = preparar("reserva")
    rows = []
    for nome, cfg in VARS.items():
        a = resumo(simular(fI, dI, cfg)); o = resumo(simular(fO, dO, cfg))
        rows.append(dict(variante=nome, **{f"IS_{k}": v for k, v in a.items()}, **{f"OOS_{k}": v for k, v in o.items()}))
        print(f"{nome:52s} IS ops {a['ops']:3d} total {a['total']:+7.0f} DD {a['dd']:5.0f} t/DD {a['t_dd']:5.2f} acerto {a['acerto']:.0%} | "
              f"OOS ops {o['ops']:3d} total {o['total']:+7.0f} DD {o['dd']:5.0f} t/DD {o['t_dd']:5.2f}", flush=True)
    t = pd.DataFrame(rows); b0 = t.iloc[0]
    t["passa_IS"] = (t.IS_total > b0.IS_total) & (t.IS_t_dd > b0.IS_t_dd)
    t["passa_OOS"] = t.passa_IS & (t.OOS_total > b0.OOS_total) & (t.OOS_t_dd > b0.OOS_t_dd)
    t.to_pickle("scripts/daytrade/topos_fundos/res_conf/stops.pkl")
    print("\npassam IS:", list(t[t.passa_IS].variante)); print("passam IS e OOS:", list(t[t.passa_OOS].variante))


if __name__ == "__main__":
    main()
