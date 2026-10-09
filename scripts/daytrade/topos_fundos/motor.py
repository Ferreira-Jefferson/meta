"""Estagios da escada de topos e fundos no WIN, varios tempos graficos (pesquisa: 2022-01 a 2025-09).

Regras fixadas antes de rodar (2026-10-08):
- Base WIN$N sem leiloes (M1) reamostrada a partir das 09:00: M5, M15, M30, H1, H4 (09-13, 13-17, 17-fim) e D1.
- Segmento: modo "dia" = um pregao (zera no fim do dia); modo "multi" = um contrato (de um vencimento ao
  proximo; WIN$N nao e ajustado, entao nenhuma operacao ou pivo atravessa a virada). Primeiro TR do segmento = H-L.
- Pivos: ZigZag K x ATR(14) (ATR conhecido antes da barra), confirmado sem look-ahead, reiniciado por segmento.
- Estagio no fundo F_k confirmado (compra): 0 se F_k <= F_{k-1}; 1 se F_k > F_{k-1}; +1 para cada par anterior
  em que o fundo E o topo intermediario tambem subiram (cap 6). Venda = espelho em topos.
- Entrada na abertura seguinte a confirmacao. Stop no pivo.
  E1: stop sobe a cada novo pivo do lado; sem alvo; sai no fim do segmento.
  E2: alvo fixo 1R, 2R, 3R com stop fixo (R = entrada - stop); sem alvo atingido sai no fim do segmento.
- Nulo: 5 entradas sorteadas por evento (mesmo TF/modo/K, mesmo lado, mesmo stop em ATR, mesmo manejo).
- Custo para a coluna liquida: 10 pts por operacao (1 tick de deslize em cada ponta).
"""
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
import numpy as np
import pandas as pd

SRC = "data/win_sem_leiloes/m1_WIN$N_2022_2025.parquet"
OUT = "scripts/daytrade/topos_fundos/res/"
INI, FIM = "2022-01-01", "2025-10-01"
ATR_N, CUSTO, RS = 14, 10.0, (1, 2, 3)


def vencimentos():
    v = []
    for y in range(2021, 2027):
        for m in (2, 4, 6, 8, 10, 12):
            d15 = date(y, m, 15)
            dif = (2 - d15.weekday())  # quarta = 2
            if dif > 3: dif -= 7
            if dif < -3: dif += 7
            v.append(pd.Timestamp(d15 + timedelta(days=dif)))
    return v


def barras(tf):
    m1 = pd.read_parquet(SRC)
    m1 = m1[(m1.index >= INI) & (m1.index < FIM)]
    agg = dict(open="first", high="max", low="min", close="last", real_volume="sum")
    if tf == "D1":
        b = m1.resample("1D").agg(agg).dropna()
    elif tf == "H4":
        dia = m1.index.normalize(); h = m1.index.hour
        bloco = np.where(h < 13, 0, np.where(h < 17, 1, 2))
        k = dia + pd.to_timedelta(np.array([9, 13, 17])[bloco], unit="h")
        b = m1.groupby(k).agg(agg)
    else:
        b = m1.resample(tf.replace("M", "") + "min" if tf[0] == "M" else "60min", offset="0min").agg(agg).dropna()
    b = b.dropna()
    b["dia"] = b.index.normalize()
    v = vencimentos()
    b["contrato"] = np.searchsorted(np.array(v, dtype="datetime64[ns]"), b.dia.values, side="right")
    for n in (9, 21, 34, 100, 200):
        b[f"ema{n}"] = b.close.ewm(span=n, adjust=False).mean()
    return b


def com_atr(b, seg):
    pc = b.close.shift(1).where(seg == seg.shift(1))
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    return tr.groupby(b.contrato).transform(lambda s: s.rolling(ATR_N, min_periods=5).mean().shift(1))


def zigzag(h, l, atr, K):
    piv, dirc, hi_i, lo_i = [], 0, 0, 0
    for t in range(len(h)):
        if np.isnan(atr[t]):
            hi_i = lo_i = t; continue
        if h[t] >= h[hi_i]: hi_i = t
        if l[t] <= l[lo_i]: lo_i = t
        a = atr[t] * K
        if dirc != -1 and hi_i < t and h[hi_i] - l[t] >= a:
            piv.append(("T", hi_i, h[hi_i], t, atr[t])); dirc, lo_i = -1, t
        elif dirc != 1 and lo_i < t and h[t] - l[lo_i] >= a:
            piv.append(("F", lo_i, l[lo_i], t, atr[t])); dirc, hi_i = 1, t
    return piv


def trail(o, h, l, c, conf, t0, lado, stop):
    ent, mfe = o[t0], 0.0
    for t in range(t0, len(o)):
        if lado == 1 and l[t] <= stop: return min(o[t], stop) - ent, mfe, t
        if lado == -1 and h[t] >= stop: return ent - max(o[t], stop), mfe, t
        mfe = max(mfe, (h[t] - ent) if lado == 1 else (ent - l[t]))
        p = conf.get(t)
        if p is not None:
            if lado == 1 and p[0] == "F" and p[2] > stop: stop = p[2]
            if lado == -1 and p[0] == "T" and p[2] < stop: stop = p[2]
    return (c[-1] - ent) * lado, mfe, len(o) - 1


def alvo_fixo(o, h, l, c, t0, lado, stop):
    """Para 1R, 2R, 3R: resultado em R (stop -1, alvo +n, fim = parcial)."""
    ent = o[t0]; R = (ent - stop) * lado
    out = []
    if R <= 0: return [np.nan] * len(RS)
    for n in RS:
        alvo, r = ent + lado * n * R, None
        for t in range(t0, len(o)):
            bate_s = l[t] <= stop if lado == 1 else h[t] >= stop
            if bate_s: r = ((min(o[t], stop) if lado == 1 else max(o[t], stop)) - ent) * lado / R; break
            if (h[t] >= alvo) if lado == 1 else (l[t] <= alvo): r = (max(o[t], alvo) - ent if lado == 1 else ent - min(o[t], alvo)) / R; break
        out.append(r if r is not None else (c[-1] - ent) * lado / R)
    return out


def estagio(piv, i):
    """Estagio no pivo i (fundo -> compra; topo -> venda)."""
    tipo = piv[i][0]; lado = 1 if tipo == "F" else -1
    mesmos = [j for j in range(i, -1, -1) if piv[j][0] == tipo]  # i, anterior do mesmo tipo, ...
    if len(mesmos) < 2: return lado, None
    def melhor(a, b): return (a > b) if lado == 1 else (a < b)
    if not melhor(piv[mesmos[0]][2], piv[mesmos[1]][2]): return lado, 0
    s = 1
    for q in range(1, len(mesmos) - 1):
        a, b = mesmos[q - 1], mesmos[q]   # pivos do tipo: a (mais novo), b
        c_ = mesmos[q + 1]
        # topo (oposto) entre b e a deve superar o oposto entre c_ e b
        op_ab = piv[a - 1][2]; op_bc = piv[b - 1][2]
        if a - 1 <= b or b - 1 <= c_: break
        if melhor(piv[b][2], piv[c_][2]) and melhor(op_ab, op_bc):
            s += 1
            if s >= 6: break
        else: break
    return lado, s


def unidade(tf, modo, K, seed=7):
    b = barras(tf)
    seg = b.dia if modo == "dia" else b.contrato
    b["atr"] = com_atr(b, seg)
    grupos = [g for _, g in b.groupby(seg.values)]
    arrs = []
    for g in grupos:
        o, h, l, c, a = (g[x].to_numpy() for x in ("open", "high", "low", "close", "atr"))
        piv = zigzag(h, l, a, K)
        arrs.append((g, o, h, l, c, a, piv, {p[3]: p for p in piv}))
    ev = []
    for gi, (g, o, h, l, c, a, piv, conf) in enumerate(arrs):
        for i in range(len(piv)):
            lado, s = estagio(piv, i)
            t0 = piv[i][3] + 1
            if s is None or t0 >= len(o): continue
            stop = piv[i][2]; ref = piv[i][4]
            if (o[t0] - stop) * lado <= 0: continue  # abriu alem do stop
            res, mfe, ts = trail(o, h, l, c, conf, t0, lado, stop)
            rr = alvo_fixo(o, h, l, c, t0, lado, stop)
            # quantos pivos a escada ainda fez depois
            ext, ult = 0, {}
            for j in range(i - 1, -1, -1):
                ult.setdefault(piv[j][0], piv[j][2])
                if len(ult) == 2: break
            ult[piv[i][0]] = piv[i][2]
            for p in piv[i + 1:]:
                if p[0] in ult and ((p[2] > ult[p[0]]) if lado == 1 else (p[2] < ult[p[0]])):
                    ult[p[0]] = p[2]; ext += 1
                else: break
            ev.append(dict(tf=tf, modo=modo, K=K, seg=gi, i=i, t0=t0, ts=ts, lado=lado, est=s,
                           quando=g.index[t0], ano=g.index[t0].year, hora=g.index[t0].hour,
                           entrada=o[t0], stop=stop, atr=ref, R=(o[t0] - stop) * lado,
                           res=res, mfe=mfe, barras=ts - t0, ext=ext, r1=rr[0], r2=rr[1], r3=rr[2]))
    ev = pd.DataFrame(ev)
    # nulo
    rng = np.random.default_rng(seed)
    pool = [(gi, t) for gi, x in enumerate(arrs) for t in range(len(x[1])) if not np.isnan(x[5][t])]
    nu = []
    if len(ev):
        for e in ev.itertuples():
            for j in rng.integers(0, len(pool), 5):
                gi, t = pool[j]
                g, o, h, l, c, a, piv, conf = arrs[gi]
                stop = o[t] - e.lado * (e.R / e.atr) * a[t]
                res, mfe, _ = trail(o, h, l, c, conf, t, e.lado, stop)
                rr = alvo_fixo(o, h, l, c, t, e.lado, stop)
                nu.append(dict(lado=e.lado, est=e.est, ano=e.ano, res=res, res_atr=res / a[t], mfe=mfe,
                               r1=rr[0], r2=rr[1], r3=rr[2], atr=a[t]))
    nu = pd.DataFrame(nu)
    nome = f"{tf}_{modo}_K{K}"
    ev.to_pickle(OUT + f"ev_{nome}.pkl"); nu.to_pickle(OUT + f"nu_{nome}.pkl")
    b.to_pickle(OUT + f"barras_{tf}_{modo}.pkl")
    return nome, len(ev)


UNIDADES = [(tf, modo, K) for K in (1.5, 3.0)
            for tf, modos in (("M5", ("dia", "multi")), ("M15", ("dia", "multi")), ("M30", ("dia", "multi")),
                              ("H1", ("multi",)), ("H4", ("multi",)), ("D1", ("multi",)))
            for modo in modos]

if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    with ProcessPoolExecutor(max_workers=6) as ex:
        fs = {ex.submit(unidade, *u): u for u in UNIDADES}
        for f in as_completed(fs):
            try:
                print(*f.result(), flush=True)
            except Exception as e:
                print("ERRO", fs[f], repr(e), flush=True)
