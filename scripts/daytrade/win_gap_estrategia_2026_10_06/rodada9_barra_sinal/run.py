"""Rodada 9: tamanho da barra de sinal (= tempo grafico do sinal), stop 1200, sem alvo, zera 18:20.
A barra de sinal vai das 09:00 ate 09:00+L; ordem limite no fecho dela, validade 25 min a partir do fecho (igual ao M5).
Janelas jan-abr/2026 e mai-ago/2026, R$1.000 cada, 1 contrato, R$5 por saida a mercado."""
import sys, pickle
from datetime import date
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade")
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
from win_gap_estrategia_2026_10_06.rodada7_mai_ago.run import resumo
OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
BARRAS = [1, 2, 3, 5, 10, 15, 20, 30, 60]
JANELAS = {"jan-abr": (date(2026, 1, 2), date(2026, 4, 30)), "mai-ago": (date(2026, 5, 1), date(2026, 8, 31))}
_c = {}

def unidade(L, jan):
    import port_win_gap_barra1 as P
    if "m" not in _c:
        _c["m"] = P.m1_total(); _c["g"] = P.ticks_fn(_c["m"]); _c["t"] = sorted(set(_c["m"].index.date))
    ini, fim = JANELAS[jan]
    dias = [d for d in _c["t"] if ini <= d <= fim]
    tr, _, _, diag = P.rodar(dias, _c["m"], _c["g"], stop=1200.0, barra_min=L)
    pickle.dump(tr, open(OUT / f"{jan}_M{L}.pkl", "wb"))
    r = resumo(tr); r["sinais"] = diag.get("sinais"); r["nao_encheu"] = diag.get("nao_encheu")
    return L, jan, r

if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(unidade, L, j) for j in JANELAS for L in BARRAS]
        for f in as_completed(fs):
            print(*f.result(), flush=True)
