"""gera.py -- motor de eventos da SEQUENCIA DE RECUOS (WIN, 2026). Definicoes congeladas.

Por config (T, div) e sorteio (0 = real, 1..N = nulo embaralhado) grava out/ev_T{T}_d{div}_{modo}{draw}.pkl
com 2 tabelas: recuos (1 linha por recuo >= m) e tentativas (1 linha por 'bounce' confirmado = entrada candidata).

Definicoes (por direcao; a de baixa e a de alta espelhada, q = -preco):
- caminho dentro da vela: alta minima->maxima, baixa maxima->minima (2 pontos/vela).
- origem o = minimo corrente (reseta a cada novo minimo ou a cada morte); H = maxima desde a origem.
- m = T/div. RECUO = queda >= m a partir de H (confirmado no ponto em que atinge H-m).
- ELEGIVEL = recuo com A = H-o >= T (pernada de T ja confirmada quando o recuo comeca).
- recuo SUCEDE quando o preco supera H; MORRE quando H-p >= T (zigzag-T vira) ou p<=o.
- tentativa: dentro do recuo, fundo L; 'bounce' = preco volta L+m (entrada candidata, stop em L, risco = p-L);
  a tentativa FALHA se o preco faz novo fundo abaixo de L (nova tentativa depois); SUCEDE se supera H.
- 'supera de primeira' = primeiro bounce confirmado e H superada antes de novo fundo abaixo de L1.
"""
import sys, os, pickle, time
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def carrega():
    df = pd.read_csv(CSV, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df = df[df["date"] >= "2025.12.15"].copy()   # so aquecimento de ATR; nada anterior a 2026 vira resultado
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df = df[df.ts < "2026-10-01"]
    df["dia"] = df.ts.dt.normalize()
    df["min"] = df.ts.dt.hour * 60 + df.ts.dt.minute
    dias = {}
    for d, g in df.groupby("dia"):
        dias[d] = dict(min=g["min"].values.astype(np.int32), o=g.open.values.astype(float), h=g.high.values.astype(float),
                       l=g.low.values.astype(float), c=g.close.values.astype(float))
    rng = {d: float(np.mean(v["h"] - v["l"])) for d, v in dias.items()}
    ds = sorted(dias)
    atr = {}
    for i, d in enumerate(ds):
        if i >= 5:
            atr[d] = float(np.mean([rng[x] for x in ds[i - 5:i]]))
    ds26 = [d for d in ds if d >= pd.Timestamp("2026-01-01")]
    return dias, atr, ds26


def embaralha(v, rs, modo):
    n = len(v["o"])
    blk = v["min"] // 30
    perm = np.arange(n)
    ini = 0
    for i in range(1, n + 1):
        if i == n or blk[i] != blk[ini]:
            a = ini + 1 if ini == 0 else ini
            if i - a > 1:
                perm[a:i] = a + rs.permutation(i - a)
            ini = i
    if modo == "raw":
        return dict(min=v["min"], o=v["o"][perm], h=v["h"][perm], l=v["l"][perm], c=v["c"][perm])
    o, h, l, c = v["o"], v["h"], v["l"], v["c"]
    gap = np.zeros(n); gap[1:] = o[1:] - c[:-1]
    dh, dl, dc = h - o, l - o, c - o
    gp, dhp, dlp, dcp = gap[perm], dh[perm], dl[perm], dc[perm]
    no = np.empty(n); nc = np.empty(n)
    prev = o[0]
    for i in range(n):
        no[i] = prev + gp[i]
        nc[i] = no[i] + dcp[i]
        prev = nc[i]
    return dict(min=v["min"], o=no, h=no + dhp, l=no + dlp, c=nc)


def caminho(v):
    o, h, l, c = v["o"], v["h"], v["l"], v["c"]
    up = c >= o
    a = np.where(up, l, h); b = np.where(up, h, l)
    P = np.empty(2 * len(o)); P[0::2] = a; P[1::2] = b
    TM = np.repeat(v["min"], 2)
    return P, TM


def maquina(P, TM, T, m, sgn, dia, REC, TRD):
    q = P * sgn
    n = len(q)
    o = H = q[0]; Hi = 0; pb = q[0]
    inrec = False; ktot = 0
    epoch_rows = []
    cur = None
    nbounce = 0; sub = None; L = U = 0.0; first_ok = None
    ep = 0

    def fecha_epoch(Hfinal, causa):
        for r in epoch_rows:
            r["alcance"] = Hfinal - r["H"]
            r["causa_fim"] = causa
        epoch_rows.clear()

    for i in range(n):
        p = q[i]
        if p <= o:
            if cur is not None:
                cur["res"] = "M"; cur["i_fim"] = i; cur["att"] = max(1, nbounce); cur["depth"] = H - pb
                cur["first_ok"] = first_ok if first_ok is not None else np.nan
                cur = None
            fecha_epoch(H, "orig")
            o = H = p; Hi = i; pb = p; inrec = False; ktot = 0; nbounce = 0; sub = None; first_ok = None
            ep += 1
            continue
        if p > H:
            if inrec:
                cur["res"] = "S"; cur["i_fim"] = i
                cur["att"] = max(1, nbounce + 1 if sub == "down" else nbounce)
                if nbounce >= 1:
                    cur["first_ok"] = first_ok if first_ok is not None else 1.0
                cur["depth"] = H - pb
                cur = None; inrec = False; nbounce = 0; sub = None; first_ok = None
            H = p; Hi = i; pb = p
            continue
        if p < pb:
            pb = p
        if not inrec:
            if H - p >= m:
                inrec = True; ktot += 1
                A = H - o
                cur = dict(dia=dia, sgn=sgn, ep=ep, k_total=ktot, A=A, H=H, o=o, i_H=Hi, i_conf=i, tconf=int(TM[i]), tH=int(TM[Hi]),
                           elig=bool(A >= T), res=None, alcance=np.nan, depth=np.nan, att=np.nan, first_ok=np.nan,
                           i_fim=-1, causa_fim=None, tfim=-1)
                REC.append(cur); epoch_rows.append(cur)
                sub = "down"; L = pb; nbounce = 0; first_ok = None
        if inrec:
            if H - p >= T:
                cur["res"] = "M"; cur["i_fim"] = i; cur["att"] = max(1, nbounce); cur["depth"] = H - pb
                cur["first_ok"] = first_ok if first_ok is not None else np.nan
                cur = None
                fecha_epoch(H, "T")
                o = H = p; Hi = i; pb = p; inrec = False; ktot = 0; nbounce = 0; sub = None; first_ok = None
                ep += 1
                continue
            if sub == "down":
                if p < L:
                    L = p
                elif p >= L + m:
                    sub = "up"; nbounce += 1
                    TRD.append(dict(dia=dia, sgn=sgn, ep=ep, k_total=ktot, j=nbounce, A=cur["A"], H=H, o=o, L=L,
                                    entry=L + m, risk=m, pconf=p, i=i, tmin=int(TM[i]), r=H - L, elig=cur["elig"]))
            else:
                if p < L:
                    if first_ok is None and nbounce == 1:
                        first_ok = 0.0
                    sub = "down"; L = p
    if cur is not None:
        cur["res"] = "C"; cur["att"] = max(1, nbounce); cur["depth"] = H - pb
        cur["first_ok"] = first_ok if first_ok is not None else np.nan
    fecha_epoch(H, "fim")


def pos_trades(P, TRD0, sgn):
    q = P * sgn
    for t in TRD0:
        i = t["i"]; seg = q[i:]
        L = t["L"]
        if len(seg) == 0:
            t["mfe"] = 0.0; t["stop"] = 0; t["fimR"] = 0.0; t["i_stop"] = -1; continue
        below = seg < L
        if below.any():
            k = int(np.argmax(below)); t["stop"] = 1; t["i_stop"] = i + k
            t["mfe"] = (max(seg[:k].max(), t["entry"]) - t["entry"]) / t["risk"] if k > 0 else 0.0
            t["fimR"] = -1.0
        else:
            t["stop"] = 0; t["i_stop"] = -1
            t["mfe"] = (max(seg.max(), t["entry"]) - t["entry"]) / t["risk"]
            t["fimR"] = (q[-1] - t["entry"]) / t["risk"]


def unidade(args):
    T, div, modo, draw = args
    m = T / div
    dias, atr, ds26 = carrega()
    rs = np.random.default_rng(1000 + draw)
    REC, TRD = [], []
    for d in ds26:
        v = dias[d]
        if modo != "real":
            v = embaralha(v, rs, modo)
        P, TM = caminho(v)
        for sgn in (1, -1):
            r0, t0 = [], []
            maquina(P, TM, T, m, sgn, d, r0, t0)
            pos_trades(P, t0, sgn)
            a = atr.get(d, np.nan)
            for r in r0:
                r["atr"] = a; r["tfim"] = int(TM[r["i_fim"]]) if r["i_fim"] >= 0 else -1
            for t in t0:
                t["atr"] = a
            REC += r0; TRD += t0
    return T, div, modo, draw, pd.DataFrame(REC), pd.DataFrame(TRD)


def sequencia(rec):
    if len(rec) == 0:
        return rec
    rec = rec.sort_values(["dia", "sgn", "ep", "k_total"]).reset_index(drop=True)
    g = rec.groupby(["dia", "sgn", "ep"], sort=False)
    rec["k_elig"] = g["elig"].cumsum()
    rec.loc[~rec["elig"], "k_elig"] = 0
    rec["r_prev"] = g["depth"].shift(1)
    rec["r_prev2"] = g["depth"].shift(2)
    rec["tfim_prev"] = g["tfim"].shift(1)
    return rec


if __name__ == "__main__":
    ndraw = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    configs = [(T, dv) for T in (250, 500, 750) for dv in (5, 4, 8)]
    jobs = []
    for T, dv in configs:
        jobs.append((T, dv, "real", 0))
        for dr in range(1, ndraw + 1):
            jobs.append((T, dv, "chain", dr))
    for dr in range(1, 11):
        jobs.append((750, 5, "raw", dr))
    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(unidade, j) for j in jobs]
        for f in as_completed(futs):
            T, dv, modo, dr, rec, trd = f.result()
            rec = sequencia(rec)
            with open(os.path.join(OUT, f"ev_T{T}_d{dv}_{modo}{dr}.pkl"), "wb") as fh:
                pickle.dump((rec, trd), fh)
            done += 1
            print(f"[{done}/{len(jobs)}] T{T} div{dv} {modo}{dr}: rec={len(rec)} trd={len(trd)} t={time.time()-t0:.0f}s", flush=True)
