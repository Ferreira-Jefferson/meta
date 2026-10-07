"""Estudo C: 'inicio' x 'fim' de movimento e o papel do volume (WIN, estrategia WMA34/SMMA34, stop/alvo 300/600).

Ajuste: 2026-06/07/08. Teste: 2026-09/05/04. Nada anterior a 2026-04.
Medidas de 'esticado' no fechamento da vela do sinal (sem futuro), na direcao do sinal:
  a = distancia vela->roxa em pontos (compra: low-WMA; venda: WMA-high)
  b = numero de velas M5 seguidas (incl. a do sinal) com fechamento do mesmo lado da roxa
  c = retorno acumulado do close das ultimas 12 velas M5 na direcao do sinal
Tercis (cortes) calculados SO' no ajuste e aplicados ao teste.
Parte 4: todas as barras M5 (dir = sinal de close-open), reversao = -dir*(close[t+k]-close[t]), k=3,6, dentro do dia.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_ema8_wma8_sim_m1 as sim  # noqa: E402
import win_volume_razao_py as vr  # noqa: E402
from core.indicators import lwma  # noqa: E402

AJUSTE = ["2026-06", "2026-07", "2026-08"]
TESTE = ["2026-09", "2026-05", "2026-04"]
STOP, ALVO = 300.0, 600.0
DIAS = [2, 4, 10, 20]
FAIXAS = [("<0,7", 0, 0.7), ("0,7-1,0", 0.7, 1.0), ("1,0-1,5", 1.0, 1.5), (">=1,5", 1.5, 1e9)]
CACHE = vr.CACHE
rng = np.random.default_rng(7)


def medidas(d: pd.DataFrame) -> pd.DataFrame:
    """Medidas por barra M5 (sem direcao ainda): close-roxa, lado, corrida, ret12."""
    w = lwma(d.close, 34)
    lado = np.sign(d.close - w).fillna(0)
    run = lado.groupby((lado != lado.shift()).cumsum()).cumcount() + 1
    out = pd.DataFrame({"w": w, "lado": lado, "run": run.where(lado != 0, 0),
                        "ret12": d.close - d.close.shift(12)}, index=d.index)
    return out


def worker(mes: str) -> pd.DataFrame:
    f = CACHE / f"hC_trades_{mes}_{int(STOP)}_{int(ALVO)}.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["t_entrada", "t_saida", "t_sinal"])
    m1 = sim.preparar(mes, limpa=True, so_roxa=True)
    tr = sim.simular(m1, STOP, ALVO)
    d = vr.ler_m5_volume()
    m = medidas(d)
    tr["t_sinal"] = tr["t_entrada"] - pd.Timedelta(minutes=5)
    i = tr["t_sinal"]
    dr = tr["dir"].to_numpy()
    w = m["w"].reindex(i).to_numpy()
    hi, lo = d["high"].reindex(i).to_numpy(), d["low"].reindex(i).to_numpy()
    tr["a"] = np.where(dr == 1, lo - w, w - hi)
    tr["b"] = m["run"].reindex(i).to_numpy()
    tr["c"] = dr * m["ret12"].reindex(i).to_numpy()
    for k in DIAS:
        tr[f"r{k}"] = vr.razao_volume(d, k, "semana").reindex(i).to_numpy()
    tr["mes"] = mes
    tr.to_csv(f, index=False)
    return tr


# ---------------- estatistica ----------------
def boot_mean(vals: np.ndarray, dias: np.ndarray, n=1000):
    """IC95 da media por bootstrap de DIAS (razao de somas)."""
    if len(vals) == 0:
        return (np.nan, np.nan)
    u, inv = np.unique(dias, return_inverse=True)
    s = np.bincount(inv, weights=vals, minlength=len(u))
    c = np.bincount(inv, minlength=len(u)).astype(float)
    idx = rng.integers(0, len(u), (n, len(u)))
    m = s[idx].sum(1) / np.maximum(c[idx].sum(1), 1)
    return tuple(np.percentile(m, [2.5, 97.5]))


def be_emp(rs: np.ndarray):
    g, p = rs[rs > 0], -rs[rs < 0]
    if len(g) == 0 or len(p) == 0:
        return np.nan
    return p.mean() / (g.mean() + p.mean())


def lin(g: pd.DataFrame) -> str:
    n = len(g)
    if n == 0:
        return "n=0"
    rs = g["rs"].to_numpy()
    lo, hi = boot_mean(rs, g["dia"].astype(str).to_numpy(), 400)
    ac = (rs > 0).mean()
    mot = g["mot"].value_counts().to_dict()
    s = (f"n={n:3d} R$/op={rs.mean():7.2f} IC[{lo:6.2f};{hi:6.2f}] acerto={ac*100:4.1f}% BE={be_emp(rs)*100:4.1f}% "
         f"saidas={mot.get('alvo',0)}a/{mot.get('stop',0)}s/{mot.get('trail',0)}t/{mot.get('zera',0)}z")
    return s + ("  [sem poder: n<60]" if n < 60 else "")


def tercil(x: pd.Series, cortes):
    return pd.cut(x, [-np.inf, cortes[0], cortes[1], np.inf], labels=["T1", "T2", "T3"])


def faixa(r: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=r.index, dtype=object)
    for nome, lo, hi in FAIXAS:
        out[(r >= lo) & (r < hi)] = nome
    return out


def perm_diff(g: pd.DataFrame, col: str, n=3000):
    """diff de R$/op T3-T1 e p-valor por embaralhamento dos rotulos de tercil (nulo)."""
    a = g[g[col] == "T3"]["rs"].to_numpy()
    b = g[g[col] == "T1"]["rs"].to_numpy()
    if len(a) < 5 or len(b) < 5:
        return np.nan, np.nan
    obs = a.mean() - b.mean()
    pool = np.concatenate([a, b])
    cnt = 0
    for _ in range(n):
        rng.shuffle(pool)
        cnt += abs(pool[:len(a)].mean() - pool[len(a):].mean()) >= abs(obs)
    return obs, (cnt + 1) / (n + 1)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    meses = AJUSTE + TESTE
    res = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        fut = {ex.submit(worker, m): m for m in meses}
        for f in as_completed(fut):
            res[fut[f]] = f.result()
            print(f"mes {fut[f]}: {len(res[fut[f]])} ops", flush=True)
    aj = pd.concat([res[m] for m in AJUSTE], ignore_index=True)
    te = pd.concat([res[m] for m in TESTE], ignore_index=True)
    print(f"\nAJUSTE n={len(aj)} | TESTE n={len(te)}  (stop/alvo {STOP:.0f}/{ALVO:.0f})", flush=True)
    print("Geral ajuste:", lin(aj), "\nGeral teste :", lin(te), flush=True)

    # ---- tercis no ajuste
    cortes = {}
    for k, nome in [("a", "dist. roxa (pts)"), ("b", "velas seguidas"), ("c", "ret 12 velas (pts)")]:
        q = aj[k].quantile([1 / 3, 2 / 3]).to_numpy()
        # b e' discreto: garante cortes distintos
        cortes[k] = (q[0], q[1])
        print(f"\nCortes {k} [{nome}] (ajuste): T1<= {q[0]:.1f} < T2 <= {q[1]:.1f} < T3", flush=True)
        for rot, g in [("AJUSTE", aj), ("TESTE", te)]:
            g = g.copy()
            g["t"] = tercil(g[k], cortes[k])
            print(f"  {rot}", flush=True)
            for t in ["T1", "T2", "T3"]:
                print(f"    {t}: {lin(g[g['t'] == t])}", flush=True)
            g["tt"] = g["t"].astype(str)
            diff, p = perm_diff(g, "tt")
            print(f"    T3-T1 = {diff:.2f} R$/op, p(embaralhado)={p:.3f}", flush=True)
    for df in (aj, te):
        for k in "abc":
            df["t" + k] = tercil(df[k], cortes[k]).astype(str)

    # ---- volume x esticado
    for k in DIAS:
        print(f"\n=== Parte 3: Dias={k} | razao de volume na vela do sinal, por tercil de esticado ===", flush=True)
        for m in "abc":
            for rot, g in [("AJ", aj), ("TE", te)]:
                g = g.copy()
                g["f"] = faixa(g[f"r{k}"])
                for t in ["T1", "T3"]:
                    for nome, _, _ in FAIXAS:
                        s = g[(g["t" + m] == t) & (g["f"] == nome)]
                        if len(s) == 0:
                            continue
                        print(f"  [{m}] {rot} {t} vol {nome:8s}: {lin(s)}", flush=True)
            if k != 2:
                continue
        # volume geral sem esticado
        for rot, g in [("AJ", aj), ("TE", te)]:
            g = g.copy()
            g["f"] = faixa(g[f"r{k}"])
            for nome, _, _ in FAIXAS:
                print(f"  [geral] {rot} vol {nome:8s}: {lin(g[g['f'] == nome])}", flush=True)

    # ---- Parte 4: todas as barras M5
    d = vr.ler_m5_volume()
    m = medidas(d)
    d = d.join(m)
    d["dir"] = np.sign(d.close - d.open)
    d["a"] = np.where(d["dir"] == 1, d.close - d.w, d.w - d.close)  # dist do fechamento, na direcao
    d["a"] = np.where(d["dir"] == 1, d.low - d.w, d.w - d.high)
    d["b"] = np.where(d["lado"] == d["dir"], d["run"], 0)
    d["c"] = d["dir"] * d["ret12"]
    dia = pd.Series(d.index.date, index=d.index)
    for kk in (3, 6):
        fut_c = d.close.groupby(dia).shift(-kk)
        d[f"rev{kk}"] = -d["dir"] * (fut_c - d.close)
    for k in DIAS:
        d[f"r{k}"] = vr.razao_volume(d, k, "semana")
    mes = pd.Series(d.index.strftime("%Y-%m"), index=d.index)
    d["dia"] = dia.astype(str)
    sel = d[(d["dir"] != 0) & d["w"].notna() & d["c"].notna()]
    ajb, teb = sel[mes.reindex(sel.index).isin(AJUSTE)], sel[mes.reindex(sel.index).isin(TESTE)]
    print(f"\n=== Parte 4: todas as barras M5 | ajuste n={len(ajb)} teste n={len(teb)} ===", flush=True)
    print("(rev>0 = reverteu; P(rev)=fracao com reversao>0; media em pts; IC95 bootstrap por dia; NULO = media geral)", flush=True)
    for k in (2, 20):
        for mm in "abc":
            q = ajb[mm].quantile([1 / 3, 2 / 3]).to_numpy()
            if mm == "b":  # corrida discreta e muitas barras com 0: cortes pelo ajuste so' entre positivas
                q = ajb[ajb[mm] > 0][mm].quantile([1 / 3, 2 / 3]).to_numpy()
            print(f"\n[{mm}] Dias={k} cortes ajuste: {q[0]:.1f} / {q[1]:.1f}", flush=True)
            for rot, g in [("AJ", ajb), ("TE", teb)]:
                g = g.copy()
                g["t"] = tercil(g[mm], q).astype(str)
                g["f"] = faixa(g[f"r{k}"])
                for h in (3, 6):
                    base = g[f"rev{h}"].dropna()
                    print(f"  {rot} h={h}: geral media={base.mean():.2f} P(rev)={(base>0).mean()*100:.1f}% n={len(base)}", flush=True)
                    for t in ["T1", "T3"]:
                        for nome, _, _ in FAIXAS:
                            s = g[(g["t"] == t) & (g["f"] == nome)].dropna(subset=[f"rev{h}"])
                            if len(s) < 10:
                                continue
                            v = s[f"rev{h}"].to_numpy()
                            lo, hi = boot_mean(v, s["dia"].to_numpy(), 400)
                            print(f"    {t} vol {nome:8s}: n={len(s):4d} media={v.mean():6.1f} IC[{lo:6.1f};{hi:6.1f}] "
                                  f"P(rev)={(v>0).mean()*100:4.1f}%"
                                  + ("  [sem poder]" if len(s) < 60 else ""), flush=True)


if __name__ == "__main__":
    main()
