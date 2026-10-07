"""Demo (a): direcao aleatoria em dados reais de 2026 -> nenhuma geometria alvo/stop paga o custo.
Entrada no fechamento da barra (limite assumido preenchido), direcao sorteada (long e short ambos),
stop primeiro se a mesma M1 tocar os dois; fim do pregao = saida a mercado no ultimo close."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import motor as m

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"

def carrega():
    df = pd.read_csv(CSV, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df = df[df["date"].astype(str).str.startswith("2026")].copy()   # SO 2026
    df["dt"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df["dia"] = df["dt"].dt.date
    df["min"] = df["dt"].dt.hour * 60 + df["dt"].dt.minute
    return df

def relogio(df):
    amp = (df["high"] - df["low"]).values
    dst = np.array([m.dst_eua(d) for d in df["dia"]])
    return m.indice_vol_horario(df["min"].values, amp, dst), amp

GEOS_T = [50, 100, 150, 250, 500]
GEOS_S = [50, 100, 150, 250, 500]

def roda(df, n_por_dia=25, seed=1):
    rng = np.random.default_rng(seed)
    linhas = {(t, s): [] for t in GEOS_T for s in GEOS_S}   # (dia, resultado_pts, tocou_alvo, tocou_stop)
    for dia, g in df.groupby("dia"):
        H, L, C, mn = g["high"].values, g["low"].values, g["close"].values, g["min"].values
        cand = np.where((mn >= 9 * 60 + 30) & (mn <= 16 * 60 + 30))[0]
        if len(cand) < 5: continue
        ent = rng.choice(cand, size=min(n_por_dia, len(cand)), replace=False)
        for i in ent:
            e = C[i]
            fh = H[i + 1:] - e   # excursao a favor (long)
            fl = e - L[i + 1:]   # excursao contra (long)
            fim_long = C[-1] - e
            for lado in (1, -1):
                fav, con, fim = (fh, fl, fim_long) if lado == 1 else (fl, fh, -fim_long)
                for (t, s) in linhas:
                    a = np.argmax(fav >= t) if (fav >= t).any() else 10**9
                    b = np.argmax(con >= s) if (con >= s).any() else 10**9
                    if b <= a and b < 10**9:   # stop primeiro (empate = stop)
                        r = -(s + m.DESLIZE_STOP_PTS) - m.CUSTO_PTS; k = 2
                    elif a < 10**9:
                        r = t - m.CUSTO_PTS; k = 1
                    else:
                        r = fim - m.CUSTO_PTS; k = 0
                    linhas[(t, s)].append((dia, r, k))
    return linhas

def main():
    df = carrega()
    idx, amp = relogio(df)
    print(f"2026: {len(df)} barras M1, {df['dia'].nunique()} pregoes, {df['dia'].min()} a {df['dia'].max()}")
    linhas = roda(df)
    rows = []
    for (t, s), L in linhas.items():
        d = pd.DataFrame(L, columns=["dia", "r", "k"])
        por_dia = d.groupby("dia")["r"].mean()
        e = d["r"].mean(); se = por_dia.std() / np.sqrt(len(por_dia))
        g, p = m.ganho_perda(t, s)
        rows.append(dict(alvo=t, stop=s, n=len(d), win=(d.k == 1).mean(), stop_pct=(d.k == 2).mean(),
                         fim_pct=(d.k == 0).mean(), nulo=m.nulo_p(t, s), be=m.breakeven_p(g, p),
                         esp_pts=e, ic95=1.96 * se, custo_pts_por_op=-(e) if False else None,
                         esp_brl=e * m.VALOR_PONTO))
    r = pd.DataFrame(rows)
    # custo pesa: custo total por op (pts) esperado = 2 + 5*P(stop); relativo ao alvo
    r["custo_pts"] = m.CUSTO_PTS + m.DESLIZE_STOP_PTS * r["stop_pct"]
    r["custo_%alvo"] = 100 * r["custo_pts"] / r["alvo"]
    r["be-nulo_pp"] = 100 * (r["be"] - r["nulo"])
    r.drop(columns=["custo_pts_por_op"]).to_csv("demo_a_resultado.csv", index=False, sep=";", decimal=",")
    pd.set_option("display.width", 250)
    print(r.drop(columns=["custo_pts_por_op"]).round(3).to_string(index=False))
    print("\nmax esperanca (pts):", r.esp_pts.max().round(2), "| celulas com esp>0:", int((r.esp_pts > 0).sum()),
          "| com limite inferior IC>0:", int((r.esp_pts - r.ic95 > 0).sum()), "de", len(r))
    # relogio
    print("\nRELOGIO (indice de amplitude M1, media 1 no regime)")
    for reg in (True, False):
        print("DST-EUA" if reg else "inverno-EUA", {f"{b//60:02d}:{b%60:02d}": round(v, 2) for (rg, b), v in sorted(idx.items()) if rg == reg})
    json.dump({f"{int(k[0])}|{k[1]}": v for k, v in idx.items()}, open("indice_vol.json", "w"))
    print("amplitude M1 media (pts):", round(float(amp.mean()), 1))

if __name__ == "__main__":
    main()
