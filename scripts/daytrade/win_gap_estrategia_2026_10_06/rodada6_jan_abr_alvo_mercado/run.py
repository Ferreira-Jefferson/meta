"""Rodada 6: 48 celulas, so' 2026-01-02..2026-04-30. Salva out/cel_<stop>_<mult>.pkl = dict(real, c, v) (c=+1 forcado, v=-1 forcado)."""
import sys, pickle
from datetime import date
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
OUT = Path(__file__).resolve().parent / "out"
STOPS = list(range(400, 1501, 100)); MULTS = [2, 3, 4, 0]   # 0 = sem alvo
INI, FIM = date(2026, 1, 2), date(2026, 4, 30)
_c = {}

def unidade(stop, mult):
    import port_win_gap_barra1 as P
    if "m" not in _c:
        _c["m"] = P.m1_total(); _c["g"] = P.ticks_fn(_c["m"]); _c["t"] = sorted(set(_c["m"].index.date))
    dias = [d for d in _c["t"] if INI <= d <= FIM]
    assert dias and min(dias) >= INI and max(dias) <= FIM
    am = float(mult) if mult else None
    r = {}
    for k, lf in (("real", None), ("c", 1), ("v", -1)):
        r[k] = P.rodar(dias, _c["m"], _c["g"], stop=float(stop), lado_forcado=lf, alvo_mult=am)[0]
    pickle.dump(r, open(OUT / f"cel_{stop}_{mult}.pkl", "wb"))
    return stop, mult, len(r["real"]), round(sum(x["rs"] for x in r["real"]) - 5 * len(r["real"]), 2)

if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(unidade, s, m) for m in MULTS for s in STOPS]
        for f in as_completed(fs):
            print(*f.result(), flush=True)
