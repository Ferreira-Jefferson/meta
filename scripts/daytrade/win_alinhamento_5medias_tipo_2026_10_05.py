"""WIN melhor atual (alinhamento + inclinacao, saida na quebra, M5, WINV26):
5 medias 9/21/34/100/200 e tipo de media (EMA/SMA/WMA/SMMA). Pedido do
dono, 2026-10-05. Linha ATUAL = EMA 21/50/200."""
import importlib.util as u
from pathlib import Path

AQUI = Path(__file__).resolve().parent
s = u.spec_from_file_location("base", AQUI / "win_alinhamento_3emas_candle_2026_10_05.py")
b = u.module_from_spec(s); s.loader.exec_module(b)

V26 = b.RAIZ / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
TIPOS = ("EMA", "SMA", "WMA", "SMMA")
CONJ = [(21, 50, 200), (9, 21, 34, 100, 200)]


def main():
    d = b.ler(V26, "M5")
    for jn, a, z in b.JANELAS:
        L = []
        for p in CONJ:
            for t in TIPOS:
                nome = f"{t} {'/'.join(map(str, p))}"
                if (t, p) == ("EMA", (21, 50, 200)):
                    nome = "ATUAL " + nome
                L.append(b.linha(nome, *b.simula(d, "reentra", "quebra", a, z, periodos=p, tipo=t)))
        print(f"\n=== WINV26 M5 | {jn} ===", flush=True)
        print(b.tabela(L, extras=b.EX), flush=True)


if __name__ == "__main__":
    main()
