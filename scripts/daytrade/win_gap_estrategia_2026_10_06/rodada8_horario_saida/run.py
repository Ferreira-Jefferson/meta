"""Rodada 8: saida por horario, stop 1200, sem alvo. Zeragem a mercado no horario H (em vez de 18:20).
Janelas: jan-abr/2026 e mai-ago/2026, cada uma conta propria de R$1.000. 1 contrato, R$5 por saida a mercado."""
import sys, pickle
from datetime import date
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade")
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
from win_gap_estrategia_2026_10_06.rodada7_mai_ago.run import resumo  # mesma conta da rodada 7
OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
HORAS = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "18:20"]
JANELAS = {"jan-abr": (date(2026, 1, 2), date(2026, 4, 30)), "mai-ago": (date(2026, 5, 1), date(2026, 8, 31))}
_c = {}

def unidade(hora, jan):
    import port_win_gap_barra1 as P
    if "m" not in _c:
        _c["m"] = P.m1_total(); _c["g"] = P.ticks_fn(_c["m"]); _c["t"] = sorted(set(_c["m"].index.date))
    h, mi = map(int, hora.split(":")); P.P["flatten_min"] = h * 60 + mi
    ini, fim = JANELAS[jan]
    dias = [d for d in _c["t"] if ini <= d <= fim]
    tr = P.rodar(dias, _c["m"], _c["g"], stop=1200.0)[0]
    pickle.dump(tr, open(OUT / f"{jan}_{hora.replace(':', '')}.pkl", "wb"))
    return hora, jan, resumo(tr)

if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(unidade, h, j) for j in JANELAS for h in HORAS]
        for f in as_completed(fs):
            print(*f.result(), flush=True)
