"""Ferramentas da exploratoria N1 (so' bloco DEV). Nada aqui e' o backtest final da N2.

- serie ajustada por diferenca (so' para INDICADORES): no dia de vencimento do WIN (quarta mais proxima do dia 15
  dos meses pares) o WIN$N troca de contrato; o degrau open(D)-close(D-1) e' descontado de todo o historico
  anterior. Como LWMA/SMMA/EMA sao lineares, o indicador no dia D sobre a serie ajustada = indicador "sem degrau".
  Precos de execucao continuam CRUS (o deslocamento e' constante dentro do dia).
- sim de uma operacao sobre os ticks sinteticos (4/M1) com as regras do Testador: limite enche ao tocar no preco
  do limite (a partir do tick seguinte ao envio); stop executa no last do tick que toca/atravessa; saida a mercado
  executa no last do tick.
"""
from datetime import date, timedelta
import numpy as np, pandas as pd
import dados_dev as D

TICK = 5.0
CUSTO_PTS = 10.0   # R$2/op = 10 pts a R$0,20/pt


def vencimentos(anos=range(2021, 2026)):
    out = set()
    for a in anos:
        for m in (2, 4, 6, 8, 10, 12):
            d15 = date(a, m, 15)
            cands = [d15 + timedelta(days=k) for k in range(-3, 4)]
            out.add(min((c for c in cands if c.weekday() == 2), key=lambda c: abs((c - d15).days)))
    return out


def m1_ajustada() -> pd.DataFrame:
    b = D.m1().copy()
    dts = b.index.date
    ds = sorted(set(dts))
    venc = vencimentos()
    o = b.open.groupby(dts).first(); c = b.close.groupby(dts).last()
    ajuste = pd.Series(0.0, index=ds)
    for i in range(1, len(ds)):
        if ds[i] in venc:
            ajuste.iloc[:i] += o.iloc[i] - c.iloc[i - 1]   # sobe o passado ate' o contrato novo
    a = pd.Series(dts).map(ajuste).to_numpy()
    for k in ("open", "high", "low", "close"):
        b[k] = b[k] + a
    b["aj"] = a
    return b


def lwma(c, n):
    w = np.arange(1, n + 1, dtype=float); out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1:] = np.correlate(c, w, "valid") / w.sum()
    return out


def smma(c, n):
    out = np.full(len(c), np.nan)
    if len(c) < n:
        return out
    v = c[:n].mean(); out[n - 1] = v
    for i in range(n, len(c)):
        v = (v * (n - 1) + c[i]) / n; out[i] = v
    return out


def ohlc(m1, freq):
    return m1.resample(freq, closed="left", label="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "real_volume": "sum", "aj": "first"}).dropna()


def arred(v):
    return round(v / TICK) * TICK


def sim(tk, t_env, lado, limite, ttl_ms, stop=None, alvo=None, t_zera=None, saidas_ms=None, stop_trail=None):
    """Uma operacao. tk = (t, p, v, real). Ordem-limite enviada em t_env (ms), valida ate' t_env+ttl_ms.
    stop/alvo em PRECO absoluto (cru). saidas_ms: instantes (ms) em que o EA manda sair a mercado (1o tick >= t).
    stop_trail: lista [(t_ms, novo_stop)] -- stop recolocado a partir de t_ms (so' aperta).
    Retorna dict ou None (nao encheu)."""
    t, p = tk[0], tk[1]
    i0 = np.searchsorted(t, t_env, side="right")          # tick seguinte ao envio
    i1 = np.searchsorted(t, t_env + ttl_ms, side="left")
    if i0 >= i1:
        return None
    seg = p[i0:i1]
    hit = np.nonzero(seg <= limite)[0] if lado > 0 else np.nonzero(seg >= limite)[0]
    if not len(hit):
        return None
    f = i0 + hit[0]
    pe = limite
    # eventos de saida a partir do tick f+1
    n = len(t)
    j0 = f + 1
    fim = n - 1 if t_zera is None else min(n - 1, np.searchsorted(t, t_zera, side="left"))
    cand = [(fim, p[fim], "zera")]
    stops = [(t[f], stop)] if stop is not None else []
    if stop_trail:
        stops += [(tt, s) for tt, s in stop_trail if tt > t[f]]
    # stop por segmentos (nivel vale do inicio do segmento em diante)
    nivel = None
    for k, (tt, s) in enumerate(stops):
        if s is None:
            continue
        nivel = s if nivel is None else (max(nivel, s) if lado > 0 else min(nivel, s))
        a = max(j0, np.searchsorted(t, tt, side="left"))
        b = np.searchsorted(t, stops[k + 1][0], side="left") if k + 1 < len(stops) else fim + 1
        if a >= b:
            continue
        sg = p[a:b]
        h = np.nonzero(sg <= nivel)[0] if lado > 0 else np.nonzero(sg >= nivel)[0]
        if len(h):
            cand.append((a + h[0], p[a + h[0]], "stop")); break
    if alvo is not None and j0 <= fim:
        sg = p[j0:fim + 1]
        h = np.nonzero(sg >= alvo)[0] if lado > 0 else np.nonzero(sg <= alvo)[0]
        if len(h):
            cand.append((j0 + h[0], alvo, "alvo"))
    if saidas_ms is not None:
        for tt in saidas_ms:
            if tt > t[f]:
                k = np.searchsorted(t, tt, side="left")
                if k <= fim:
                    cand.append((k, p[k], "regra"))
                break
    k, px, mot = min(cand, key=lambda x: x[0])
    return dict(t_ent=int(t[f]), t_sai=int(t[k]), pe=float(pe), px=float(px), motivo=mot, pts=float(lado * (px - pe)))
