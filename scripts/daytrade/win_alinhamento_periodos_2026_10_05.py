"""WIN melhor atual (alinhamento + inclinacao, saida na quebra, M5, WINV26):
periodos maiores — pedido do dono 2026-10-05: 34/100/200 e 34/100/300,
mais vizinhanca para ver se e' plato ou ponto isolado."""
import importlib.util as u
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
s = u.spec_from_file_location("base", AQUI / "win_alinhamento_3emas_candle_2026_10_05.py")
b = u.module_from_spec(s); s.loader.exec_module(b)

V26 = b.RAIZ / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
PEDIDOS = [(21, 50, 200), (34, 100, 200), (34, 100, 300)]
VIZ = [(f, m, sl) for f in (21, 34, 50) for m in (72, 100, 144) for sl in (200, 250, 300, 400)
       if (f, m, sl) not in PEDIDOS and f < m < sl]


def main():
    d = b.ler(V26, "M5")
    for jn, a, z in b.JANELAS:
        L = [b.linha(("ATUAL " if p == (21, 50, 200) else "") + "/".join(map(str, p)),
                     *b.simula(d, "reentra", "quebra", a, z, periodos=p)) for p in PEDIDOS]
        print(f"\n=== PEDIDO | WINV26 M5 | {jn} ===", flush=True)
        print(b.tabela(L, extras=b.EX), flush=True)
    a, z = b.JANELAS[0][1], b.JANELAS[0][2]
    G = [b.linha("/".join(map(str, p)), *b.simula(d, "reentra", "quebra", a, z, periodos=p)) for p in VIZ]
    print("\n=== VIZINHANCA | WINV26 M5 | liq 12/08+ ===", flush=True)
    print(b.tabela(G, extras=b.EX), flush=True)
    print(f"positivas: {sum(g.liquido_brl > 0 for g in G)}/{len(G)}", flush=True)


if __name__ == "__main__":
    main()
