"""Roda os 10 stops x 5 janelas de selecao (NUNCA datas de 2025-10-01..2025-12-31). Salva trades em out/trades_<stop>_<janela>.pkl"""
import sys, pickle
from datetime import date
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
OUT = Path(__file__).resolve().parent / "out"
STOPS = [300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500]
JAN = {"2022": (date(2022,1,1), date(2022,12,31)), "2023": (date(2023,1,1), date(2023,12,31)),
       "2024": (date(2024,1,1), date(2024,12,31)), "2025": (date(2025,1,1), date(2025,9,30)),
       "2026": (date(2026,1,2), date(2026,10,5))}
_c = {}

def unidade(stop, jan):
    import port_win_gap_barra1 as P
    if "m" not in _c:
        _c["m"] = P.m1_total(); _c["g"] = P.ticks_fn(_c["m"]); _c["t"] = sorted(set(_c["m"].index.date))
    i, f = JAN[jan]
    assert not (date(2025,10,1) <= i <= date(2025,12,31)) and not (date(2025,10,1) <= f <= date(2025,12,31))
    dias = [d for d in _c["t"] if i <= d <= f]
    assert not any(date(2025,10,1) <= d <= date(2025,12,31) for d in dias)
    tr, s, q, dg = P.rodar(dias, _c["m"], _c["g"], stop=float(stop))
    pickle.dump(tr, open(OUT / f"trades_{stop}_{jan}.pkl", "wb"))
    return stop, jan, len(tr), round(sum(x["rs"] for x in tr) - 2 * len(tr), 2)

if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(unidade, s, j) for j in JAN for s in STOPS]
        for f in as_completed(fs):
            print(*f.result(), flush=True)
