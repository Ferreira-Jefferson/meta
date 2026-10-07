"""Replay de ticks WINV26 (set/ago 2026): base (Teste 13 = PARAMS_PADRAO) vs base + filtro EMA, varrendo periodo e modo.
M1 vem do CSV exportado (nao precisa do MT5); ticks do cache data/cache_win_ticks/WINV26.
Uso: python run_replay.py"""
import sys, os, json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_ema as rp
OUT = Path(__file__).resolve().parent
CSV = rp.ROOT / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
JAN = {"set": (date(2026, 9, 1), date(2026, 9, 30)), "ago": (date(2026, 8, 1), date(2026, 8, 31))}

def m1_csv(ativo, inicio, fim):
    d = pd.read_csv(CSV, sep="\t")
    d.index = pd.to_datetime(d["<DATE>"] + " " + d["<TIME>"], format="%Y.%m.%d %H:%M:%S")
    d = d.rename(columns={"<OPEN>": "open", "<HIGH>": "high", "<LOW>": "low", "<CLOSE>": "close"})[["open", "high", "low", "close"]].astype(float).sort_index()
    return d[(d.index >= pd.Timestamp(inicio - timedelta(days=7))) & (d.index < pd.Timestamp(fim + timedelta(days=1)))]

def met(t):
    if t.empty: return dict(n=0, win=0, liq=0, dd=0, pf=0, op=0, be=0)
    t = t.sort_values("tx"); eq = t.rs.cumsum(); dd = float((eq.cummax().clip(lower=0) - eq).max())
    g = t.rs[t.rs > 0]; l = -t.rs[t.rs < 0]
    be = l.mean() / (g.mean() + l.mean()) * 100 if len(g) and len(l) else float("nan")
    return dict(n=len(t), win=round(100 * (t.rs > 0).mean(), 1), liq=round(t.rs.sum(), 2), dd=round(dd, 2),
                pf=round(g.sum() / l.sum(), 2) if l.sum() else None, op=round(t.rs.mean(), 2), be=round(be, 1))

def unidade(nome, jan, params):
    rp.carregar_m1 = m1_csv
    ini, fim = JAN[jan]
    r = rp.replay(ini, fim, 0.0, "fixa", params, "WINV26")
    t = pd.DataFrame(r["trades"])
    t.to_csv(OUT / f"replay_trades_{nome}_{jan}.csv", index=False)
    rss = None
    try:
        import psutil; rss = round(psutil.Process().memory_info().rss / 1e6)
    except Exception: pass
    return nome, jan, met(t), len(r["dias_sem_ticks"]), rss

if __name__ == "__main__":
    var = [("base", {})]
    for per in (50, 100, 150, 200):
        var.append((f"ema{per}_close", dict(ema_periodo=per, ema_modo="close")))
        var.append((f"ema{per}_vela", dict(ema_periodo=per, ema_modo="vela")))
    res = []
    with ProcessPoolExecutor(4) as ex:
        fu = {ex.submit(unidade, n, j, p): (n, j) for n, p in var for j in JAN}
        for f in as_completed(fu):
            n, j, m, sem, rss = f.result(); res.append(dict(variante=n, janela=j, sem_ticks=sem, **m))
            print(n, j, m, "sem_ticks", sem, "RSS_MB", rss, flush=True)
            pd.DataFrame(res).to_csv(OUT / "replay_resultados.csv", index=False)
