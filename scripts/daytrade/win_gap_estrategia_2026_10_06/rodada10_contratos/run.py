"""Rodada 10: contratos fixos (1) x automaticos pela tabela do saldo do EA (EA_SPEC sec. 3), stop 1200, sem alvo, M5, zera 18:20.
Trades gerados pelo replay da pagina com saldo enorme (sem corte por quebra) e redimensionados aqui, operacao a operacao.
Cada ano recomeca com R$1.000. Custo R$5 por contrato por saida a mercado. Para de operar com saldo < R$100 (margem)."""
import sys, pickle
from datetime import date
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\comparativo_win_2026")
OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
JANELAS = {"2022": (date(2022, 1, 1), date(2022, 12, 31)), "2023": (date(2023, 1, 1), date(2023, 12, 31)),
           "2024": (date(2024, 1, 1), date(2024, 12, 31)), "2025 (até set)": (date(2025, 1, 1), date(2025, 9, 30)),
           "2026 (até 05/10)": (date(2026, 1, 1), date(2026, 10, 5))}
CUSTO, MARGEM = 5.0, 100.0
_c = {}

def contratos_auto(s):
    if s < 100: return 0
    if s < 800: return 1
    if s < 2400: return 2
    if s < 6667: return 3
    if s < 16667: return 4
    return 5

def simula(tr, modo):
    saldo, pico, dd, ddp, smin, n, ganhos, perdas, vit, qs = 1000.0, 1000.0, 0.0, 0.0, 1000.0, 0, 0.0, 0.0, 0, []
    quebra = None
    for x in tr:
        q = 1 if modo == "fixo" else contratos_auto(saldo)
        if saldo < MARGEM or q == 0:
            quebra = quebra or x["entrada"][:10]; break
        v = q * (x["rs"] - CUSTO)
        saldo += v; n += 1; qs.append(q)
        ganhos += max(v, 0); perdas += max(-v, 0); vit += v > 0
        pico = max(pico, saldo); dd = max(dd, pico - saldo); ddp = max(ddp, (pico - saldo) / pico * 100); smin = min(smin, saldo)
    return dict(n=n, liq=round(saldo - 1000, 2), final=round(saldo, 2), win=round(100 * vit / max(n, 1), 1),
                pf=round(ganhos / perdas, 2) if perdas else None, dd=round(dd, 2), ddp=round(ddp, 1),
                rf=round((saldo - 1000) / dd, 2) if dd else None, smin=round(smin, 2), quebra=quebra,
                q_med=round(sum(qs) / len(qs), 2) if qs else 0, q_max=max(qs) if qs else 0)

def unidade(nome):
    import port_win_gap_barra1 as P
    if "m" not in _c:
        _c["m"] = P.m1_total(); _c["g"] = P.ticks_fn(_c["m"]); _c["t"] = sorted(set(_c["m"].index.date))
    ini, fim = JANELAS[nome]
    dias = [d for d in _c["t"] if ini <= d <= fim]
    tr = P.rodar(dias, _c["m"], _c["g"], stop=1200.0, saldo0=1e9)[0]
    pickle.dump(tr, open(OUT / f"trades_{nome[:4]}.pkl", "wb"))
    return nome, simula(tr, "fixo"), simula(tr, "auto")

if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(unidade, j) for j in JANELAS]
        for f in as_completed(fs):
            nome, a, b = f.result()
            print(nome, "| FIXO 1:", a, "| AUTO:", b, flush=True)
