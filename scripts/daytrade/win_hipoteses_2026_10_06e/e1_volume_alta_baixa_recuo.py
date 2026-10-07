"""e1: volume de alta x baixa (ideia 1) e volume do recuo x impulso (ideia 2) como filtro de entrada do WinCincoMedias. So' 2026.
Cada variante roda com volume e com 2 controles de preco (range h-l; corpo |c-o|), mesmo N/L."""
import sys, pickle, itertools
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "daytrade"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_cinco_medias as W
import e1_candidatas as E

AQUI = Path(__file__).resolve().parent
_D = None


def specs():
    out = []
    for base in ("v", "rng", "corpo"):
        for N in (3, 5, 8, 13):
            for L in (0.5, 0.55, 0.6, 0.65):
                for pond in (False, True):
                    out.append(("ab", base, N, L, pond))
        for N in (3, 5, 8, 13):
            for L in (0.6, 0.8, 1.0):
                for modo in ("baixo", "alto"):
                    out.append(("rc", base, N, L, modo))
    return out


def nome(s):
    if s[0] == "ab":
        return f"AB_{s[1]}_N{s[2]}_L{s[3]}_{'pond' if s[4] else 'simples'}"
    return f"RC_{s[1]}_N{s[2]}_L{s[3]}_{s[4]}"


def rodar(s):
    global _D
    if _D is None:
        _D = W.carregar(2026)
    d = _D
    if s is None:
        f = None
    elif s[0] == "ab":
        f = lambda x: E.feat_alta_baixa(x, s[2], s[3], s[4], s[1])
    else:
        f = lambda x: E.feat_recuo(x, s[2], s[3], s[4], s[1])
    tab, res = W.rodar_janelas(2026, dados=d, extra=f)
    return s, tab, res


if __name__ == "__main__":
    todos = [None] + specs()
    R = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fut = [ex.submit(rodar, s) for s in todos]
        for i, f in enumerate(as_completed(fut)):
            s, tab, res = f.result()
            R[s] = (tab, res)
            print(i, "BASE" if s is None else nome(s), res["liquido"], res["janelas_pos"], res["trades"], flush=True)
    pickle.dump(R, open(AQUI / "e1_res.pkl", "wb"))
    tb, rb = R[None]
    print("BASELINE", rb)
    base_m = dict(zip(tb.janela, tb.liquido))
    rows = []
    for s, (tab, r) in R.items():
        if s is None:
            continue
        m = dict(zip(tab.janela, tab.liquido))
        melh = sum(m.get(j, 0) > base_m[j] for j in base_m)
        pior_m = sum(m.get(j, 0) < base_m[j] for j in base_m)
        rows.append(dict(nome=nome(s), tipo=s[0], base=s[1], liq=r["liquido"], jan=r["janelas_pos"], pior=r["pior"],
                         PF=r["PF"], trades=r["trades"], DD=r["maior_DD"], sem_set=r["liquido_sem_set"],
                         melhores=melh, piores=pior_m))
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(AQUI / "e1_resumo.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print(df.sort_values("liq", ascending=False).to_string(index=False))
