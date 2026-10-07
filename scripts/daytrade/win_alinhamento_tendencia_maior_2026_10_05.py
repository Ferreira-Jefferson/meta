"""WIN melhor atual (EMAs 21/50/200, saida na quebra, M5, WINV26 12/08+):
as entradas estao a favor da tendencia de tempo MAIOR? Pedido do dono, 2026-10-05.

Para cada entrada, classifica a favor/contra usando so' informacao ja'
FECHADA no instante da entrada (barra maior conta a partir do fim dela)."""
import importlib.util as u
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
s = u.spec_from_file_location("base", AQUI / "win_alinhamento_3emas_candle_2026_10_05.py")
b = u.module_from_spec(s); s.loader.exec_module(b)

V26 = b.RAIZ / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
INI = pd.Timestamp("2026-08-12")


def rs(m1, regra):
    return m1.resample(regra).agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()


def lado_emas(d, per, fim_barra):
    e = [d["c"].ewm(span=p, adjust=False).mean() for p in per]
    up = np.logical_and.reduce([e[i] > e[i + 1] for i in range(len(e) - 1)])
    dn = np.logical_and.reduce([e[i] < e[i + 1] for i in range(len(e) - 1)])
    sr = pd.Series(np.where(up, 1, np.where(dn, -1, 0)), index=d.index + fim_barra)
    return sr


def main():
    m1 = b.ler(V26, "M1")
    m5 = b.ler(V26, "M5")
    trades, _ = b.simula(m5, "reentra", "quebra", INI)
    df = pd.DataFrame(trades, columns=["pnl", "dia", "pts", "t", "lado", "t_saida", "qty"])

    dia = m1.groupby(m1.index.normalize()).agg(ab=("o", "first"), fe=("c", "last"))
    dia["fe_ontem"] = dia["fe"].shift()
    dia["ema20d_ontem"] = dia["fe"].ewm(span=20, adjust=False).mean().shift()
    dia["fe_ontem2"] = dia["fe"].shift(2)
    d0 = df["t"].dt.normalize()
    px = df["t"].map(lambda t: m5["o"].asof(t))  # abertura da barra de entrada (ja' conhecida)

    def asof(sr, ts):
        sr = sr.sort_index()
        return ts.map(lambda t: sr.asof(t))

    lentes = {
        "dia: preco vs abertura do dia": np.sign(px.values - dia.loc[d0, "ab"].values),
        "ontem: preco vs fechamento D-1": np.sign(px.values - dia.loc[d0, "fe_ontem"].values),
        "D-1 vs D-2 (dia anterior subiu?)": np.sign(dia.loc[d0, "fe_ontem"].values - dia.loc[d0, "fe_ontem2"].values),
        "diario: fech D-1 vs EMA20 diaria": np.sign(dia.loc[d0, "fe_ontem"].values - dia.loc[d0, "ema20d_ontem"].values),
        "M15 EMAs 21>50>200": asof(lado_emas(rs(m1, "15min"), (21, 50, 200), pd.Timedelta("15min")), df["t"]).values,
        "H1 EMAs 21>50": asof(lado_emas(rs(m1, "60min"), (21, 50), pd.Timedelta("60min")), df["t"]).values,
        "H1 EMAs 21>50>200": asof(lado_emas(rs(m1, "60min"), (21, 50, 200), pd.Timedelta("60min")), df["t"]).values,
    }
    print(f"base: {len(df)} trades, liquido R$ {df.pnl.sum():.2f}, win {100*(df.pnl>0).mean():.1f}%\n", flush=True)
    rows = []
    for nome, sinal in lentes.items():
        rel = np.where(sinal == df["lado"].values, "a favor", np.where(sinal == -df["lado"].values, "contra", "neutro"))
        for k in ("a favor", "contra", "neutro"):
            g = df[rel == k]
            if not len(g):
                continue
            gan = g.pts[g.pts > 0]; per = -g.pts[g.pts < 0]
            be = per.mean() / (gan.mean() + per.mean()) * 100 if len(gan) and len(per) else np.nan
            rows.append({"lente": nome, "grupo": k, "n": len(g), "%": round(100 * len(g) / len(df), 1),
                         "win%": round(100 * (g.pnl > 0).mean(), 1), "BE%": round(be, 1),
                         "pts/op": round(g.pts.mean(), 1), "liquido R$": round(g.pnl.sum(), 2)})
    print(pd.DataFrame(rows).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
