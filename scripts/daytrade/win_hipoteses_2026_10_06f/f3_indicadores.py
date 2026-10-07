"""f3: OUTROS INDICADORES como filtro de entrada (F) e como saida adicional (S) no WinCincoMedias v2.02. So' 2026.
Cada variante: rodar_janelas + 10 sementes de controle aleatorio (mesma fracao de sinais cortados / mesma taxa de inicio de saida)."""
import sys, pickle
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import numpy as np
import pandas as pd
import f3_feat as X

X.ativar(); W = X.W
SEEDS = range(10)
_D = None


def specs():
    L = []
    E = lambda t, *p: L.append(("F", t, p))
    for n, Ls in ((2, (90, 95, 98)), (7, (70, 80, 90)), (14, (65, 70, 75, 80))):
        for l in Ls: E("rsi_nao_estica", n, l)
    for n in (7, 14):
        for l in (50, 55, 60): E("rsi_forca", n, l)
    for n, k, x in ((2, 3, 20), (2, 3, 40), (7, 3, 40), (7, 5, 40), (7, 5, 50), (14, 3, 45), (14, 5, 45), (14, 5, 50)):
        E("rsi_recuo", n, k, x)
    for l in (80, 90, 95): E("stoch_nao_estica", 14, l)
    E("stoch_nao_estica", 5, 90)
    for n in (5, 14): E("stoch_cruza", n)
    for k, x in ((3, 30), (5, 30), (5, 40)): E("stoch_recuo", 14, k, x)
    for prm in ((12, 26, 9), (6, 13, 5)):
        for modo in ("h", "hs"): E("macd_a_favor", *prm, modo)
        for k in (3, 6): E("macd_cruza", *prm, k)
    for n in (5, 9, 15):
        for modo in ("pos", "sobe", "ambos"): E("trix", n, modo)
    for l in (0.8, 0.9, 1.0, 1.1): E("boll_pos", 20, l)
    for k in (1, 3): E("boll_rompe", 20, k)
    for r in (0.9, 1.0, 1.1, 1.2):
        E("boll_larg", 20, r, "exp"); E("boll_larg", 20, r, "con")
    for r in (0.9, 1.0, 1.1, 1.2):
        E("atr_ratio", r, "alto"); E("atr_ratio", r, "baixo")
    E("keltner", "dentro"); E("keltner", "fora")
    E("adx_di", "di", 0)
    for l in (15, 20, 25): E("adx_di", "adx", l); E("di_adx", l)
    E("adx_di", "sobe", 0)
    for l in (50, 70, 90): E("aroon", l)
    for n, m in ((10, 3), (10, 2), (7, 2), (14, 3), (7, 1.5)): E("st_m30", n, m)
    for n, m in ((10, 3), (10, 2), (7, 2), (7, 1.5)): E("st_h1", n, m)
    E("vwap_lado")
    for l in (1, 2, 3, 4): E("vwap_dist", l, "max")
    for l in (0.5, 1.0): E("vwap_dist", l, "min")
    S_ = lambda t, *p: L.append(("S", t, p))
    for n, xs in ((7, (50, 40, 30)), (14, (50, 45, 40))):
        for x in xs: S_("rsi_abaixo", n, x)
    for n, h in ((7, 70), (7, 80), (14, 65), (14, 70)): S_("rsi_vira", n, h)
    for n, m in ((10, 3), (10, 2), (7, 2), (14, 3), (7, 1.5)): S_("st", n, m)
    for n, m in ((10, 3), (7, 2), (10, 2)): S_("st_h1", n, m)
    for a0, am in ((0.02, 0.2), (0.01, 0.1), (0.03, 0.3), (0.04, 0.4)): S_("psar", a0, am)
    for prm in ((12, 26, 9), (6, 13, 5)): S_("macd", *prm)
    return L


def nome(s):
    return f"{s[0]}:{s[1]}({','.join(str(x) for x in s[2])})"


def mk(s):
    return (X.F if s[0] == "F" else X.S)(s[1], *s[2])


def rodar(s):
    global _D
    if _D is None:
        _D = W.carregar(2026)
    d = _D
    if s is None:
        tab, res = W.rodar_janelas(2026, dados=d)
        return s, tab, res, None, None
    f = mk(s)
    kw = dict(extra=f) if s[0] == "F" else dict(saida_extra=f)
    tab, res = W.rodar_janelas(2026, dados=d, **kw)
    if s[0] == "F":
        p = X.frac_passa(f, d)
        rl = [W.rodar_janelas(2026, dados=d, extra=X.rand_entrada(p, sd))[1]["liquido"] for sd in SEEDS]
    else:
        p = X.frac_saida(f, d)
        rl = [W.rodar_janelas(2026, dados=d, saida_extra=X.rand_saida(p, sd))[1]["liquido"] for sd in SEEDS]
    return s, tab, res, p, [float(x) for x in rl]


if __name__ == "__main__":
    todos = [None] + specs()
    print("N variantes:", len(todos) - 1, flush=True)
    R = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fut = [ex.submit(rodar, s) for s in todos]
        for i, f in enumerate(as_completed(fut)):
            s, tab, res, p, rl = f.result()
            R[s] = (tab, res, p, rl)
            print(i, "BASE" if s is None else nome(s), res["liquido"], res["janelas_pos"], res["trades"], flush=True)
    pickle.dump(R, open(AQUI / "f3_res.pkl", "wb"))
    tb, rb, _, _ = R[None]
    print("BASELINE", rb, flush=True)
    bm = dict(zip(tb.janela, tb.liquido))
    rows = []
    for s, (tab, r, p, rl) in R.items():
        if s is None:
            continue
        m = dict(zip(tab.janela, tab.liquido))
        rows.append(dict(nome=nome(s), tipo=s[0], fam=s[1], liq=float(r["liquido"]), jan=r["janelas_pos"], pior=float(r["pior"]),
                         PF=r["PF"], trades=r["trades"], DD=float(r["maior_DD"]), sem_set=float(r["liquido_sem_set"]),
                         melhores=sum(m.get(j, 0) > bm[j] for j in bm), piores=sum(m.get(j, 0) < bm[j] for j in bm),
                         p_cut=round(1 - p, 3) if s[0] == "F" else None, rand_media=round(float(np.mean(rl)), 1),
                         rand_max=round(float(np.max(rl)), 1), pct=round(100 * float(np.mean([x < r["liquido"] for x in rl])), 0)))
    df = pd.DataFrame(rows)
    df.to_csv(AQUI / "f3_resumo.csv", index=False)
    pd.set_option("display.width", 280); pd.set_option("display.max_rows", 500)
    print(df.sort_values("liq", ascending=False).to_string(index=False))
