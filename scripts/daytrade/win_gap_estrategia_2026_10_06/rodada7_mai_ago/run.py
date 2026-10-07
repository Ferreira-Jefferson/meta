"""Rodada 7: 1300 e 1400 com alvo 2x a mercado (+ referencias sem alvo e 1200 atual), 2026-05-01..2026-08-31.
Mesma convencao da rodada 6: 1 contrato, R$1.000, R$5 por saida a mercado (stop/alvo/18:20)."""
import sys, pickle
from datetime import date
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
CELS = [(1300, 2), (1400, 2), (1300, 0), (1400, 0), (1200, 0)]   # 0 = sem alvo
INI, FIM = date(2026, 5, 1), date(2026, 8, 31)
CUSTO = 5.0
_c = {}

def unidade(stop, mult):
    import port_win_gap_barra1 as P
    if "m" not in _c:
        _c["m"] = P.m1_total(); _c["g"] = P.ticks_fn(_c["m"]); _c["t"] = sorted(set(_c["m"].index.date))
    dias = [d for d in _c["t"] if INI <= d <= FIM]
    tr = P.rodar(dias, _c["m"], _c["g"], stop=float(stop), lado_forcado=None, alvo_mult=float(mult) if mult else None)[0]
    pickle.dump(tr, open(OUT / f"cel_{stop}_{mult}.pkl", "wb"))
    return stop, mult, resumo(tr)

def resumo(tr):
    saldo, pico, dd, smin, seq, s = 1000.0, 1000.0, 0.0, 1000.0, 0, 0
    meses, ex = {}, {}
    for x in tr:
        v = x["rs"] - CUSTO
        saldo += v; pico = max(pico, saldo); dd = max(dd, pico - saldo); smin = min(smin, saldo)
        s = s + 1 if v < 0 else 0; seq = max(seq, s)
        m = x["entrada"][:7]; meses[m] = meses.get(m, 0) + v
        ex[x["motivo"]] = ex.get(x["motivo"], 0) + 1
    liq = saldo - 1000; g = [x["rs"] - CUSTO for x in tr]
    ganhos = sum(v for v in g if v > 0); perdas = -sum(v for v in g if v < 0)
    return dict(n=len(tr), liq=round(liq, 2), win=round(100 * sum(v > 0 for v in g) / max(len(g), 1), 1),
                pf=round(ganhos / perdas, 2) if perdas else None, dd=round(dd, 2), rf=round(liq / dd, 2) if dd else None,
                smin=round(smin, 2), seq=seq, pior=round(min(g), 2) if g else None, saidas=ex,
                meses={k: round(v, 2) for k, v in sorted(meses.items())})

if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(unidade, s, m) for s, m in CELS]
        for f in as_completed(fs):
            print(*f.result(), flush=True)
