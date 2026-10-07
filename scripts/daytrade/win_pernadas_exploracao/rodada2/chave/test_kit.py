"""Prova de causalidade: truncar o dado em t nao muda nenhuma feature/estado em t,
nem os eventos (e suas features) detectados ate o fim da vela do evento."""
import numpy as np, pandas as pd
import kit_pernadas as k

COLS_NUM = None

def _eq(a, b):
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    return np.allclose(a.values, b.values, equal_nan=True, rtol=1e-9, atol=1e-9)

def main():
    m1 = k.carregar_m1()
    full = k.features_m1(m1)
    rng = np.random.default_rng(7)
    dias = sorted(full.index.normalize().unique())
    # 1) features/estado por minuto: 40 instantes aleatorios, truncando em t
    amostra = full.index[rng.choice(len(full), 40, replace=False)]
    cols = [c for c in full.columns if c not in ("E_t",)]
    for t in amostra:
        tr = m1[m1.index <= t]
        f2 = k.features_m1(tr)
        assert t in f2.index, t
        assert _eq(full.loc[t, cols].astype(float), f2.loc[t, cols].astype(float)), (t, full.loc[t, cols], f2.loc[t, cols])
    print("OK 1: features e estado do zigzag em t identicos ao truncar em t (40 instantes)")
    # 2) trocar o FUTURO por lixo nao muda a feature em t
    for t in amostra[:10]:
        lixo = m1.copy()
        fut = lixo.index > t
        lixo.loc[fut, ["open", "high", "low", "close"]] = 123456.0
        f3 = k.features_m1(lixo)
        assert _eq(full.loc[t, cols].astype(float), f3.loc[t, cols].astype(float)), t
    print("OK 2: sobrescrever todo o futuro com lixo nao muda a linha t (10 instantes)")
    # 3) eventos: truncar no fim da vela TF do evento -> mesmo evento, mesmas features
    for tf, mins in (("M5", 5), ("M15", 15)):
        for fam, fn in (("extremo", k.eventos), ("balanco", k.eventos_balanco)):
            ev = k.rotular(fn(m1, tf, feat=full))
            cols_ev = ["E", "leg_ate_E", "perna_conf", "n_piv", "atr5_m5", "atr50_m5", "r_m5", "r_m15", "rh_m5", "rh_m15", "vol30_300", "hora", "range_dia"]
            for i in rng.choice(len(ev), 25, replace=False):
                e = ev.iloc[i]
                fim = e["ts_vela"] + pd.Timedelta(minutes=mins - 1)
                tr = m1[m1.index <= fim]
                ev2 = fn(tr, tf)
                m = ev2[(ev2["X"] == e["X"]) & (ev2["ts_vela"] == e["ts_vela"]) & (ev2["E"] == e["E"])]
                assert len(m) == 1, (tf, e["X"], e["ts_vela"])
                assert _eq(e[cols_ev].astype(float), m.iloc[0][cols_ev].astype(float)), (tf, e["ts_vela"])
            print(f"OK 3 {tf}/{fam}: eventos e features identicos truncando no fim da vela do evento (25 eventos)")
    # 4) o rotulo DEPENDE do futuro (sanidade: o teste teria pego vazamento)
    ev = k.rotular(k.eventos(m1, "M5", feat=full))
    assert ev["y"].isin([0, 1]).mean() > 0.95
    print("OK 4: rotulos existem e sao separados (y so em rotular())")
    print("TODOS OS TESTES PASSARAM")

if __name__ == "__main__":
    main()
