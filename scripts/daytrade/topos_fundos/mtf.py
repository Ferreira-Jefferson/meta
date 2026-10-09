"""Estado de outros tempos graficos (M5, M30, H1, H4) no momento de cada sinal da escada M15 (estagio >= 1, SEM filtros).

So barras FECHADAS ate o fim da barra de confirmacao do M15. Pivos ZigZag 1,5 ATR por contrato (nao atravessa vencimento).
Tudo normalizado pelo lado do sinal (+ = a favor). Saida: res_conf/mtf_<periodo>.pkl com resultado (pts, ATR, d vs acaso).
"""
import numpy as np
import pandas as pd
import motor
import confirma

K = 1.5


def agrega(b, chave, passo):
    g = b.groupby(chave)
    a = pd.DataFrame(dict(open=g.open.first(), high=g.high.max(), low=g.low.min(), close=g.close.last(),
                          real_volume=g.real_volume.sum(), contrato=g.contrato.first(), dia=g.dia.first()))
    a["fim"] = g.apply(lambda x: x.index.max()) + pd.Timedelta(passo)
    return a.sort_index()


def preparar_tf(a):
    a = a.copy()
    pc = a.close.shift(1).where(a.contrato == a.contrato.shift(1))
    tr = pd.concat([a.high - a.low, (a.high - pc).abs(), (a.low - pc).abs()], axis=1).max(axis=1)
    a["atr"] = tr.groupby(a.contrato).transform(lambda s: s.rolling(14, min_periods=5).mean())
    for n in (9, 21, 34, 72):
        a[f"ema{n}"] = a.close.ewm(span=n, adjust=False).mean()
    d = a.close.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    a["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    # pivos por contrato, com o instante em que ficam conhecidos
    piv = []
    for _, g in a.groupby("contrato"):
        z = motor.zigzag(g.high.to_numpy(), g.low.to_numpy(), g.atr.shift(1).to_numpy(), K)
        for tp, ip, px, ic, _ in z:
            piv.append(dict(tipo=tp, quando=g.fim.iloc[ic], preco=px, contrato=g.contrato.iloc[0]))
    return a, pd.DataFrame(piv).sort_values("quando").reset_index(drop=True)


def estado(a, piv, t, lado, preco_fundo):
    """Estado do TF no instante t (fim da barra M15 de confirmacao)."""
    i = a.fim.searchsorted(t, side="right") - 1
    if i < 30: return None
    r = a.iloc[i]
    ten = 1 if (r.close > r.ema34 and r.ema9 > r.ema21) else (-1 if (r.close < r.ema34 and r.ema9 < r.ema21) else 0)
    p = piv[(piv.quando <= t) & (piv.contrato == r.contrato)].tail(6)
    T = p[p.tipo == "T"].preco.to_numpy(); F = p[p.tipo == "F"].preco.to_numpy()
    if len(T) >= 2 and len(F) >= 2:
        esc = 1 if (T[-1] > T[-2] and F[-1] > F[-2]) else (-1 if (T[-1] < T[-2] and F[-1] < F[-2]) else 0)
    else: esc = 0
    ult = p.tipo.iloc[-1] if len(p) else ""
    niveis = p.preco.to_numpy()
    dist_piv = np.min(np.abs(niveis - preco_fundo)) / r.atr if len(niveis) else np.nan
    return dict(ten=ten * lado, esc=esc * lado, rsi=(r.rsi if lado == 1 else 100 - r.rsi),
                dist_ema34=(r.close - r.ema34) / r.atr * lado, inc34=np.sign(r.ema34 - a.ema34.iloc[i - 3]) * lado,
                fundo_x_ema34=abs(preco_fundo - r.ema34) / r.atr, fundo_x_ema72=abs(preco_fundo - r.ema72) / r.atr,
                fundo_x_pivo=dist_piv, ultimo_pivo_favor=(ult == ("F" if lado == 1 else "T")),
                barras_desde_pivo=(i - a.fim.searchsorted(p.quando.iloc[-1], side="left")) if len(p) else np.nan,
                atr=r.atr)


def montar(per):
    R = confirma.PER[per]["out"]
    b15 = pd.read_pickle(R + "barras_M15_dia.pkl"); b5 = pd.read_pickle(R + "barras_M5_dia.pkl")
    ev = pd.read_pickle(R + "ev_M15_dia_K1.5.pkl"); nu = pd.read_pickle(R + "nu_M15_dia_K1.5.pkl")
    ev["d"] = ev.res / ev.atr - nu.res_atr.to_numpy().reshape(-1, 5).mean(axis=1)
    f0 = pd.read_pickle(R + "feat0_M15_dia_K1.5.pkl")
    ev = ev.join(f0.set_index("idx")[["H07", "H13"]], how="left")
    ev = ev[ev.est >= 1]
    b5i = b5.copy(); b5i["fim"] = b5i.index + pd.Timedelta("5min")
    tfs = {}
    tfs["M5"] = preparar_tf(agrega(b5, b5.index, "5min"))
    tfs["M30"] = preparar_tf(agrega(b15, b15.index.floor("30min"), "15min"))
    tfs["H1"] = preparar_tf(agrega(b15, b15.index.floor("60min"), "15min"))
    h = b15.index.hour; bloco = np.where(h < 13, 9, np.where(h < 17, 13, 17))
    tfs["H4"] = preparar_tf(agrega(b15, b15.index.normalize() + pd.to_timedelta(bloco, unit="h"), "15min"))
    dias = [g for _, g in b15.groupby(b15.dia.values)]
    rows = []
    for e in ev.itertuples():
        g = dias[e.seg]; tc = g.index[e.t0 - 1] + pd.Timedelta("15min")
        r = dict(idx=e.Index, ano=e.ano, quando=tc, lado=e.lado, est=e.est, pts=e.res, ra=e.res / e.atr, d=e.d,
                 atr15=e.atr, hora=tc.hour + tc.minute / 60, H07=e.H07, H13=e.H13,
                 pos_dia=(g.close.iloc[e.t0 - 1] - g.open.iloc[0]) / e.atr * e.lado)
        ok = True
        for nome, (a, piv) in tfs.items():
            s = estado(a, piv, tc, e.lado, e.stop)
            if s is None: ok = False; break
            for k, v in s.items(): r[f"{nome}_{k}"] = v
        if ok: rows.append(r)
    out = pd.DataFrame(rows)
    out.to_pickle(R + f"mtf_{per}.pkl")
    return out


if __name__ == "__main__":
    for per in ("pesquisa", "reserva"):
        t = montar(per); print(per, len(t), flush=True)
