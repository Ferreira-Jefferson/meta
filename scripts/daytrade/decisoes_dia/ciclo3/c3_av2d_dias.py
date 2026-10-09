"""Resultado por candidata nos 2 dias do agente (v3 base) e combinacoes; so usa dias de dias_usados.json."""
import sys, json
sys.path.insert(0, '.')
import c3_av2d as A
reg = A.registro()
DIAS = ["2024-04-26", "2024-07-30"]
singles = [(), ("A_F1",), ("A_F2",), ("A_F5",), ("G4",), ("E1",), ("G3",), ("CAP5",), ("B_F2",), ("B_F1",), ("A_N1",), ("G1",), ("B_N2",)]
if __name__ == "__main__":
    res = A.avalia(singles, DIAS, workers=6)
    for c in singles:
        print("+".join(c) or "BASE", {d: res[c][d]["brl"] for d in DIAS}, flush=True)
    for d in DIAS:
        for c in [("CAP5",), ("G4",)]:
            print(d, c, [(t["fonte"][:30], t["lado"], t["sinal"], t["motivo"], t["brl"]) for t in res[c][d]["trades"]])
