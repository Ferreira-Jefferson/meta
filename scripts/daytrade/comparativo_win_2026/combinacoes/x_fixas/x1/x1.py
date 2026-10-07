"""X1 -- UNANIMIDADE. Pre-registro em combinacoes/TODO.md (secao X1). Uso:
   python x1.py dev                 -> U1..U4 no DEV (2022-01-03..2024-06-28), grava dev_tabela.md
   python x1.py conf <U1|U2|U3|U4>  -> VAL (2024-07-01..2025-09-30) e 2026 (2026-01-02..2026-10-05), sem mudar nada
"""
from __future__ import annotations
import importlib.util, os, sys
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
COMB = AQUI.parents[1]
BASE = COMB.parent
sys.path.insert(0, str(COMB / "f0_fundacao"))
os.environ["DADOS_VAL_MODO"] = "continuo"


def _carrega(nome, caminho):
    sp = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


import saida as S  # noqa: E402  (importa o dados.py real de 2026; usamos so' S._um)
D26 = S.D
DV = _carrega("dados_val_x1", COMB / "x_fixas" / "x0" / "dados_val.py")

VOT = ["Win", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]
CELULAS = {"U1": dict(stop=2.0, alvo=None, quebra=True), "U2": dict(stop=1.5, alvo=3.0, quebra=False),
           "U3": dict(stop=2.0, alvo=2.0, quebra=False), "U4": dict(stop=1.0, alvo=2.0, quebra=False)}
PERIODOS = {"DEV": (date(2022, 1, 3), date(2024, 6, 28), "cont"), "VAL": (date(2024, 7, 1), date(2025, 9, 30), "cont"),
            "2026": (date(2026, 1, 2), date(2026, 10, 5), "2026")}
CUSTO, CAPITAL, RS_PONTO, MIN = 2.0, 1000.0, 0.20, 60000
PRAZO = 3 * MIN


def atr_m5(m1):
    b = m1.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    pc = b.close.shift(1)
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = (b.high - b.low).iloc[0]
    a = tr.ewm(alpha=1 / 14, adjust=False).mean()
    fecha = (b.index + pd.Timedelta(minutes=5)).values.astype("datetime64[ms]").astype(np.int64)
    return fecha, a.to_numpy()


def fill(t, p, i_ini, i_fim, lado, lim):
    seg = p[i_ini:i_fim]
    if not len(seg):
        return None
    m = seg <= lim if lado > 0 else seg >= lim
    k = int(np.argmax(m))
    return i_ini + k if m[k] else None


def roda(cel, per, votos_all):
    c = CELULAS[cel]
    d0, d1, fonte = PERIODOS[per]
    mod = D26 if fonte == "2026" else DV
    m1 = mod.m1()
    fecha, atr = atr_m5(m1)
    dias = sorted(d for d in set(m1.index.date) if d0 <= d <= d1)
    votos = votos_all[fonte]
    trades, flips = [], []
    for dia in dias:
        g = m1[m1.index.date == dia]
        if len(g) < 30:
            continue
        v = votos.reindex(g.index)[[f"{n}.voto" for n in VOT]].fillna(0).to_numpy()
        s = np.where((v == 1).all(1), 1, np.where((v == -1).all(1), -1, 0))
        prev = np.r_[0, s[:-1]]
        trans = np.where((s != 0) & (s != prev))[0]
        if not len(trans):
            continue
        tm = g.index.values.astype("datetime64[ms]").astype(np.int64)
        cl = g.close.to_numpy(float)
        t, p, _v, _r = mod.ticks(dia)
        t = np.asarray(t, np.int64)
        p = np.asarray(p, float)
        dia0 = tm[0] - (tm[0] % 86400000)
        lim_abre, lim_fecha = dia0 + (9 * 60 + 5) * MIN, dia0 + (17 * 60 + 30) * MIN
        zera_ms = min(dia0 + (17 * 60 + 50) * MIN, tm[-1] + MIN - 5 * MIN)
        iz_zera = int(np.searchsorted(t, zera_ms, "left"))
        busy = -1
        for i in trans:
            send = tm[i] + MIN
            if send < lim_abre or send > lim_fecha or send < busy:
                continue
            lado = int(s[i])
            lim = cl[i]
            ja = np.searchsorted(fecha, send, "right") - 1
            if ja < 0:
                continue
            A = atr[ja]
            sp = max(5.0, round(c["stop"] * A / 5) * 5)
            ap = max(5.0, round(c["alvo"] * A / 5) * 5) if c["alvo"] else None
            i_ini = int(np.searchsorted(t, send, "left"))
            i_fim = int(np.searchsorted(t, send + PRAZO, "left"))
            k = fill(t, p, i_ini, i_fim, lado, lim)
            if k is None or t[k] > lim_fecha:
                busy = send + PRAZO
                continue
            i0 = int(np.searchsorted(t, t[k], "right"))
            iz, mot_m = iz_zera, "zera"
            if c["quebra"]:
                jm = int(np.searchsorted(tm, t[k], "right")) - 1  # M1 que contem o fill
                quebr = np.where(s[jm:] != lado)[0]
                if len(quebr):
                    ix_ = int(np.searchsorted(t, tm[jm + quebr[0]] + MIN, "left"))
                    if ix_ < iz_zera:
                        iz, mot_m = ix_, "quebra"
            ix, px, mot = S._um(t, p, i0, iz, lado, lim, sp, ap, True)
            if mot == "zera":
                mot = mot_m
            rs = lado * (px - lim) * RS_PONTO
            trades.append(dict(estrategia=f"X1_{cel}", entrada=str(D26.ts(int(t[k]))), saida=str(D26.ts(int(t[ix]))),
                               lado=lado, qtd=1.0, preco_entrada=lim, preco_saida=float(px), motivo=mot,
                               pontos=lado * (px - lim), rs=round(rs, 2)))
            busy = int(t[ix])
            # oposto (sorteio de lado): mesmo horario/limite/stops/instante de saida planejado
            ko = fill(t, p, i_ini, i_fim, -lado, lim)
            ro = np.nan
            if ko is not None and t[ko] <= lim_fecha:
                io = int(np.searchsorted(t, t[ko], "right"))
                _, pxo, _ = S._um(t, p, io, iz, -lado, lim, sp, ap, True)
                ro = -lado * (pxo - lim) * RS_PONTO
            flips.append((round(rs, 2), ro))
    return pd.DataFrame(trades), np.array(flips, float).reshape(-1, 2)


def metricas(df):
    if df.empty:
        return dict(ops=0)
    r = df.rs.to_numpy(float)
    rc = r - CUSTO
    eq = CAPITAL + np.cumsum(rc)
    pico = np.maximum.accumulate(np.r_[CAPITAL, eq])[1:]
    dd = float((pico - eq).max())
    net = float(rc.sum())
    g, pr = rc[rc > 0], rc[rc < 0]
    mes = pd.Series(rc, index=pd.to_datetime(df.saida).dt.to_period("M")).groupby(level=0).sum()
    q = np.where(eq <= 0)[0]
    return dict(ops=len(r), liq_sem=float(r.sum()), liq_com=net, acerto=float((rc > 0).mean() * 100),
                payoff=float(g.mean() / -pr.mean()) if len(g) and len(pr) else np.nan,
                fl=float(g.sum() / -pr.sum()) if len(pr) else np.nan, dd=dd, fr=net / dd if dd else np.nan,
                mes_pos=int((mes > 0).sum()), meses=len(mes),
                quebra=str(df.saida.iloc[q[0]])[:10] if len(q) else "nao")


def por_ano(df):
    if df.empty:
        return {}
    rc = df.rs - CUSTO
    return rc.groupby(pd.to_datetime(df.saida).dt.year).agg(["size", "sum"]).round(0).astype(int).to_dict("index")


def linha(nome, m):
    if not m.get("ops"):
        return f"| {nome} | 0 | - |"

    def f(x, d=0):
        return "n/d" if x != x else f"{x:,.{d}f}"
    return (f"| {nome} | {m['ops']} | {f(m['liq_sem'])} | {f(m['liq_com'])} | {f(m['acerto'],1)}% | {f(m['payoff'],2)} | "
            f"{f(m['fl'],2)} | {f(m['dd'])} | {f(m['fr'],2)} | {m['mes_pos']}/{m['meses']} | {m['quebra']} |")


CAB = ("| célula | ops | líq s/ custo | líq c/ custo | acerto | payoff | fator lucro | maior queda | fator recup. | meses+ | quebra |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|")


def carrega_votos():
    return {"cont": pd.read_parquet(COMB / "x_fixas" / "x0" / "votos_cont.parquet"),
            "2026": pd.read_parquet(COMB / "f0_fundacao" / "votos.parquet")}


def originais(per):
    d0, d1, fonte = PERIODOS[per]
    # corrigido 2026-10-06: o X0 original (x0/continuo) deixava Cinco e Desloc dormir overnight nos dias de 17:54;
    # x0b/resultados_2022_2025 tem a zeragem no fim real do pregao (Win, Win_c1 e RetEma34 sao copias identicas).
    pasta = COMB / "x_fixas" / "x0b" / "resultados_2022_2025" if fonte == "cont" else BASE / "resultados"
    out = {}
    for n in ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34"]:
        x = pd.read_csv(pasta / f"{n}.csv")
        dd = pd.to_datetime(x.saida).dt.date
        x = x[(dd >= d0) & (dd <= d1)]
        out[n] = (len(x), float(x.rs.sum()), float(x.rs.sum() - CUSTO * len(x)))
    return out


def percentil(flips, real_liq, n=1000):
    if not len(flips):
        return np.nan
    rng = np.random.default_rng(12345)
    mk = rng.random((n, len(flips))) < 0.5
    esc = np.where(mk, flips[:, 0][None, :], flips[:, 1][None, :])
    liq = np.where(np.isnan(esc), 0.0, esc - CUSTO).sum(1)
    return float((liq < real_liq).mean() * 100)


if __name__ == "__main__":
    modo = sys.argv[1]
    V = carrega_votos()
    if modo == "dev":
        out = [CAB]
        det = []
        for cel in CELULAS:
            df, fl = roda(cel, "DEV", V)
            m = metricas(df)
            out.append(linha(cel, m))
            det.append(f"{cel} por ano (ops, líq c/ custo): {por_ano(df)}")
            df.to_csv(AQUI / "trades" / f"dev_{cel}.csv", index=False)
            print(linha(cel, m), por_ano(df), flush=True)
        (AQUI / "dev_tabela.md").write_text("\n".join(out) + "\n\n" + "\n".join(det) + "\n", encoding="utf-8")
    else:
        cel = sys.argv[2]
        res = ["# X1 resultado\n", f"Célula congelada: {cel} ({CELULAS[cel]})\n"]
        for per in ["VAL", "2026"]:
            df, fl = roda(cel, per, V)
            m = metricas(df)
            df.to_csv(AQUI / "trades" / f"{per}_{cel}.csv", index=False)
            pct = percentil(fl, m.get("liq_com", 0))
            orig = originais(per)
            pior = min(v[2] for v in orig.values())
            pior4 = min(orig[n][2] for n in VOT)
            liq = m.get("liq_com", 0)
            res += [f"\n## {per}\n", CAB, linha(cel, m), f"\nPor ano: {por_ano(df)}\n",
                    "Originais no período (ops / líq s/ custo / líq c/ custo):\n"]
            res += [f"- {n}: {o[0]} / {o[1]:,.0f} / {o[2]:,.0f}" for n, o in orig.items()]
            res += [f"\nPior original (5): {pior:,.0f}; pior dos 4 votantes: {pior4:,.0f}. X1 líq c/ custo {liq:,.0f} -> "
                    f"{'RENDE MAIS' if liq > pior else 'NAO rende mais'} que o pior (5); "
                    f"{'RENDE MAIS' if liq > pior4 else 'NAO rende mais'} que o pior dos 4.",
                    f"Percentil vs sorteio de lado (1.000, mesmo horário): {pct:.1f}\n"]
            if len(df):
                mes = (df.rs - CUSTO).groupby(pd.to_datetime(df.saida).dt.to_period("M")).agg(["size", "sum"]).round(0)
                res += ["Por mês (ops, líq c/ custo):", ""] + [f"- {k}: {int(r['size'])} / {r['sum']:,.0f}" for k, r in mes.iterrows()]
            print(per, linha(cel, m), "pct", pct, flush=True)
        (AQUI / "resultado.md").write_text("\n".join(res), encoding="utf-8")
