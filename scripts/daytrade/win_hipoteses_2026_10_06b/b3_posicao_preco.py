"""b3 - posicao do preco em relacao as medias (WIN M5, so' 2026). Zonas novas via patch de
zona_ok em memoria (win_cinco_medias.py nao e' editado). Zonas novas:
  entre34_100 : fechamento entre EMA34 e EMA100 (recuo profundo)
  d9max<k>    : |c-EMA9| <= k*ATR14 (nao entrar esticado)    d9min<k>: >= k*ATR
  d21max<k>   : |c-EMA21| <= k*ATR14
  acima_todas : fechamento alem das 5 EMAs (inclui EMA9)
"""
import sys, itertools, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as w

_orig = w.zona_ok

def atr14(d):
    pc = d["c"].shift(1)
    tr = pd.concat([d.h - d.l, (d.h - pc).abs(), (d.l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(14, min_periods=1).mean()

def zona_ext(d, periodos, zona):
    if zona is None or zona in ("corpo>m1", "candle>m1", "entre12", "entre23", "toque2"):
        return _orig(d, periodos, zona)
    es = w.emas(d["c"], periodos); c = d["c"]
    if zona == "entre34_100":
        return (np.asarray((c <= es[2]) & (c > es[3]), bool), np.asarray((c >= es[2]) & (c < es[3]), bool))
    if zona == "acima_todas":
        return (np.asarray(c > es[0], bool), np.asarray(c < es[0], bool))
    a = atr14(d)
    for pre, ix, mx in (("d9max", 0, True), ("d9min", 0, False), ("d21max", 1, True)):
        if zona.startswith(pre):
            k = float(zona[len(pre):]); dist = (c - es[ix]).abs() / a
            m = (dist <= k) if mx else (dist >= k)
            m = np.asarray(m, bool); return m, m
    raise KeyError(zona)

w.zona_ok = zona_ext

INCL = {"todas": None, "1234": (1, 2, 3, 4), "234": (2, 3, 4), "34": (3, 4), "nenhuma": ()}
_D = None
def run(key):
    global _D
    if _D is None: _D = w.carregar(2026, "5min")
    zona, il = key
    df, r = w.rodar_janelas(2026, "5min", dados=_D, zona=zona, inclina=INCL[il])
    return key, df, r

def grade():
    g = [(None, "todas")]
    for z in ("corpo>m1", "candle>m1", "entre12", "entre23", "toque2", "entre34_100", "acima_todas"):
        g += [(z, i) for i in INCL]
    g += [(None, i) for i in INCL if i != "todas"]
    for z in ("d9max0.25", "d9max0.5", "d9max0.75", "d9max1.0", "d9max1.5", "d9max2.0",
              "d9min0.25", "d9min0.5", "d9min1.0", "d21max0.5", "d21max1.0", "d21max1.5", "d21max2.0", "d21max3.0"):
        g += [(z, i) for i in ("todas", "234", "nenhuma")]
    return g

if __name__ == "__main__":
    base_df, base = w.rodar_janelas(2026, "5min")
    assert base["liquido"] == 7490.10 and base["trades"] == 413, base
    print("BASELINE OK", base, flush=True)
    bm = base_df.set_index("janela").liquido
    out = {}
    with ProcessPoolExecutor(6) as ex:
        fs = [ex.submit(run, k) for k in grade()]
        for f in as_completed(fs):
            k, df, r = f.result()
            melh = int((df.set_index("janela").liquido.reindex(bm.index).fillna(0) > bm).sum())
            r["meses_melhor"] = melh; out[k] = (df, r)
            print(f"{k[0]!s:14} {k[1]:8} liq {r['liquido']:9.2f} jan {r['janelas_pos']:>5} pior {r['pior']:8.2f} "
                  f"tr {r['trades']:4d} PF {r['PF']} DD {r['maior_DD']:7.2f} semSet {r['liquido_sem_set']:8.2f} melh {melh}", flush=True)
    ks = sorted(out, key=lambda k: -out[k][1]["liquido"])
    print("\n=== ORDENADO ===")
    for k in ks:
        r = out[k][1]
        print(f"{k[0]!s:14} {k[1]:8} {r['liquido']:9.2f} {r['janelas_pos']:>5} {r['pior']:8.2f} {r['trades']:4d} {r['PF']} {r['maior_DD']:7.2f} {r['liquido_sem_set']:8.2f} {r['meses_melhor']}", flush=True)
    print("N variantes:", len(out))
    for k in ks[:3]:
        print("\nMES A MES", k); m = out[k][0].set_index("janela")
        print(pd.DataFrame({"base": bm, "var": m.liquido, "trades": m.trades}).to_string())
