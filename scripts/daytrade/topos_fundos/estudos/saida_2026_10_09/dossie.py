"""Estudo de saída/trailing da v4.1 (2026-10-09), etapa 1: dossiês dos dias de DESCOBERTA.

Sorteia 40 pregões do IS com operação (semente fixa). Para cada operação gera:
  - uma linha em operacoes.csv: contexto ANTES da entrada (barra de confirmação, só passado) + o que aconteceu
  - barras_<data>.csv: M15 do pregão anterior e do pregão, com médias, estocástico, volume e o stop ativo
  - <data>.png: gráfico das mesmas barras
Os outros pregões do IS ficam guardados para o teste (dias_teste.txt). OOS e virgem não são tocados.
Uso: python dossie.py <pasta_saida>
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import estrategia  # noqa: E402
import indicadores as ind  # noqa: E402
import operacao  # noqa: E402
import stop  # noqa: E402

N_DESCOBERTA, SEMENTE = 40, 20261009


def colunas(b):
    x = pd.DataFrame(index=b.index)
    for n in (9, 21, 38): x[f"mme{n}"] = ind.mme(b.close, n)
    x["mms17"], x["mms34"], x["mms72o"] = ind.mms(b.close, 17), ind.mms(b.close, 34), ind.mms(b.open, 72)
    x["estoc14"] = ind.estocastico(b, 14, 3)
    d = b.close.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    x["ifr14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    v = b.real_volume.astype(float)
    x["vol_rel20"] = v / v.rolling(20).mean().shift(1)
    hhmm = b.index.strftime("%H%M")
    x["vol_rel_hora"] = v / v.groupby(hhmm).transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))
    tp = (b.high + b.low + b.close) / 3
    x["vwap"] = (tp * v).groupby(b.dia).cumsum() / v.groupby(b.dia).cumsum()
    x["h1_tend"] = h1_tend(b)
    return x


def h1_tend(b):
    c = b.close.resample("60min").last().dropna()
    t = ind.tendencia(c); t.index = t.index + pd.Timedelta("60min")
    return t.reindex(b.index, method="ffill").fillna(0)


def contexto(b, x, dias, tr):
    """Uma linha por operação: tudo medido no fechamento da barra de confirmação (pos), lado-ajustado (+ = a favor)."""
    dia_hl = b.groupby("dia").agg(hi=("high", "max"), lo=("low", "min"), cl=("close", "last"), op=("open", "first"))
    ant = dia_hl.shift(1)
    linhas = []
    for e in tr.itertuples():
        D = dias[e.seg]; L = e.lado; t = e.pos - D["ini"]; atr = D["atr"][t]; c = D["close"][t]
        r = x.iloc[e.pos]; hi, lo = D["high"][:t + 1].max(), D["low"][:t + 1].min()
        a = ant.loc[D["dia"]]
        piv = [p for p in D["piv"] if p[3] <= t]
        perna = abs(piv[-2][2] - piv[-3][2]) / atr if len(piv) >= 3 else np.nan  # impulso anterior
        corr = abs(piv[-1][2] - piv[-2][2]) / abs(piv[-2][2] - piv[-3][2]) if len(piv) >= 3 else np.nan
        fav = lambda v: (c - v) / atr * L
        linhas.append(dict(
            data=D["dia"].date(), lado="compra" if L == 1 else "venda", hora_entrada=b.index[D["ini"] + e.t_ent].strftime("%H:%M"),
            hora_saida=b.index[D["ini"] + e.t_sai].strftime("%H:%M"), barras_na_posicao=e.t_sai - e.t_ent, motivo=e.motivo,
            px=e.px, saida=e.saida, stop_ini=e.stop_ini, R_pts=e.R, R_atr=e.R / atr, mov_pts=e.mov, mov_R=e.mov / e.R,
            mfe_R=e.mfe / e.R, mae_R=e.mae / e.R, devolvido_R=(e.mfe - e.mov) / e.R, pts_2c=e.pts,
            # contexto antes da entrada
            atr_m15=atr, estagio=None, hora_conf=b.index[e.pos].strftime("%H:%M"),
            dist_abertura_atr=fav(D["open"][0]), amplitude_dia_atr=(hi - lo) / atr,
            pos_no_range_dia=((c - lo) / (hi - lo) if L == 1 else (hi - c) / (hi - lo)) if hi > lo else np.nan,
            gap_atr=(D["open"][0] - a.cl) / atr * L if a.cl == a.cl else np.nan,
            dist_max_ant_atr=(c - (a.hi if L == 1 else a.lo)) / atr * L if a.hi == a.hi else np.nan,
            dist_mme9_atr=fav(r.mme9), dist_mme21_atr=fav(r.mme21), dist_mme38_atr=fav(r.mme38),
            dist_mms72o_atr=fav(r.mms72o), mms17_34_atr=(r.mms17 - r.mms34) / atr * L, dist_vwap_atr=fav(r.vwap),
            inclin_mme21_atr=(x.mme21.iloc[e.pos] - x.mme21.iloc[e.pos - 3]) / atr * L,
            estoc14=r.estoc14 if L == 1 else 100 - r.estoc14, ifr14=r.ifr14 if L == 1 else 100 - r.ifr14,
            vol_rel20=r.vol_rel20, vol_rel_hora=r.vol_rel_hora, h1_tend=r.h1_tend * L,
            perna_anterior_atr=perna, correcao_frac=corr, pivos_no_dia=len(piv)))
    return pd.DataFrame(linhas)


def stops_por_barra(D, e, mover):
    """Reconstrói o stop ativo em cada barra da posição (mesma regra da operação)."""
    from types import SimpleNamespace
    s = np.full(len(D["open"]), np.nan); st = e.stop_ini
    p = SimpleNamespace(lado=e.lado, px=e.px, R=e.R, ext=e.px, pior=e.px, t_ent=e.t_ent)
    for t in range(e.t_ent, e.t_sai + 1):
        s[t] = st
        p.ext = max(p.ext, D["high"][t]) if e.lado == 1 else min(p.ext, D["low"][t])
        st = mover(st, t, p, D)
    return s


def grafico(arq, g, stops, e, D, b):
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(14, 8), sharex=True, gridspec_kw=dict(height_ratios=[4, 1, 1]))
    n = len(g); xs = np.arange(n)
    for i, (o, h, l, c) in enumerate(zip(g.open, g.high, g.low, g.close)):
        cor = "#2a9d55" if c >= o else "#c8423a"
        a1.vlines(i, l, h, color=cor, lw=0.8); a1.add_patch(plt.Rectangle((i - 0.3, min(o, c)), 0.6, max(abs(c - o), 1), color=cor))
    for col, cor in (("mms17", "#e09f1f"), ("mms34", "#7b4fc9"), ("mme38", "#1f77b4"), ("mms72o", "#555555"), ("vwap", "#999999")):
        a1.plot(xs, g[col], color=cor, lw=1, label=col)
    a1.plot(xs, stops, color="black", lw=1.5, ls="--", label="stop")
    k0 = g.index.get_loc(b.index[D["ini"]])  # 1ª barra do pregão
    a1.axvline(k0 - 0.5, color="#bbbbbb", lw=1)
    ie, isai = k0 + e.t_ent, k0 + e.t_sai
    a1.scatter([ie], [e.px], marker="^" if e.lado == 1 else "v", s=120, color="blue", zorder=5)
    a1.scatter([isai], [e.saida], marker="x", s=120, color="black", zorder=5)
    a1.set_title(f"{D['dia'].date()}  {'COMPRA' if e.lado == 1 else 'VENDA'}  entrada {e.px:.0f}  saída {e.saida:.0f} ({e.motivo})  "
                 f"mov {e.mov:+.0f} pts = {e.mov / e.R:+.2f}R  MFE {e.mfe / e.R:.2f}R")
    a1.legend(loc="upper left", fontsize=7, ncol=6)
    a2.bar(xs, g.real_volume, color="#888888"); a2.set_ylabel("vol")
    a3.plot(xs, g.estoc14, color="#444444"); a3.axhline(70, ls=":", c="r"); a3.axhline(30, ls=":", c="g"); a3.set_ylabel("estoc14")
    tick = list(range(0, n, 4)); a3.set_xticks(tick); a3.set_xticklabels([g.index[i].strftime("%d %H:%M") for i in tick], rotation=90, fontsize=7)
    fig.tight_layout(); fig.savefig(arq, dpi=80); plt.close(fig)


def main(saida):
    out = Path(saida); out.mkdir(parents=True, exist_ok=True)
    b, dias, s = estrategia.preparar("IS")
    tr = operacao.operar(s, dias, stop.inicial_v41, stop.estrutura)
    datas = np.array(sorted(tr.dia.unique()))
    rng = np.random.default_rng(SEMENTE)
    desc = set(rng.choice(datas, N_DESCOBERTA, replace=False))
    (out / "dias_teste.txt").write_text("\n".join(str(pd.Timestamp(d).date()) for d in datas if d not in desc))
    trd = tr[tr.dia.isin(desc)].reset_index(drop=True)
    x = colunas(b)
    ctx = contexto(b, x, dias, trd)
    ctx["estagio"] = s.set_index("pos").loc[trd.pos, "est"].to_numpy()
    ctx.to_csv(out / "operacoes.csv", index=False, float_format="%.3f")
    bx = pd.concat([b[["open", "high", "low", "close", "real_volume", "atr"]], x], axis=1)
    for e in trd.itertuples():
        D = dias[e.seg]
        a = dias[e.seg - 1]["ini"] if e.seg > 0 else D["ini"]
        g = bx.iloc[a:D["ini"] + len(D["open"])].copy()
        st = np.r_[np.full(D["ini"] - a, np.nan), stops_por_barra(D, e, stop.estrutura)]
        g["stop_ativo"] = st; g["pregao"] = np.where(np.arange(len(g)) < D["ini"] - a, "anterior", "operacao")
        g["na_posicao"] = False; g.iloc[D["ini"] - a + e.t_ent:D["ini"] - a + e.t_sai + 1, g.columns.get_loc("na_posicao")] = True
        nome = f"{D['dia'].date()}_{e.t_ent:02d}"
        g.round(2).to_csv(out / f"barras_{nome}.csv")
        grafico(out / f"{nome}.png", g, st, e, D, b)
    r = operacao.resumo(trd)
    print(f"descoberta: {len(desc)} pregões, {len(trd)} operações, total {r['total']:+.0f}, acerto {r['acerto']:.0%}; teste: {len(datas) - len(desc)} pregões")


if __name__ == "__main__":
    main(sys.argv[1])
