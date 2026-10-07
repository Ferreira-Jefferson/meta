"""Vizinhanca da EMA 9/21/34/100/200 (M5, WINV26 12/08+): mexe uma media por vez
e mostra o IC 95% dos pts/op da celula central. Pedido implicito do dono
(variar parametros), 2026-10-05."""
import importlib.util as u
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
s = u.spec_from_file_location("base", AQUI / "win_alinhamento_3emas_candle_2026_10_05.py")
b = u.module_from_spec(s); s.loader.exec_module(b)
V26 = b.RAIZ / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
C = (9, 21, 34, 100, 200)
OPCOES = [(5, 7, 9, 11, 13), (15, 18, 21, 25), (30, 34, 40, 50), (72, 89, 100, 120), (150, 200, 250, 300)]


def main():
    d = b.ler(V26, "M5")
    a, z = b.JANELAS[0][1], b.JANELAS[0][2]
    tr, eq = b.simula(d, "reentra", "quebra", a, z, periodos=C)
    pts = np.array([t[2] for t in tr])
    se = pts.std(ddof=1) / np.sqrt(len(pts))
    print(f"centro {C}: pts/op {pts.mean():.1f}  IC95% [{pts.mean()-1.96*se:.1f} ; {pts.mean()+1.96*se:.1f}]  n={len(pts)}", flush=True)
    for i, ops in enumerate(OPCOES):
        L = []
        for v in ops:
            p = list(C); p[i] = v; p = tuple(p)
            if any(x >= y for x, y in zip(p, p[1:])):
                continue
            L.append(b.linha(("* " if p == C else "  ") + "/".join(map(str, p)), *b.simula(d, "reentra", "quebra", a, z, periodos=p)))
        print(f"\n=== varia media {i+1} ===", flush=True)
        print(b.tabela(L, extras=b.EX), flush=True)


if __name__ == "__main__":
    main()
