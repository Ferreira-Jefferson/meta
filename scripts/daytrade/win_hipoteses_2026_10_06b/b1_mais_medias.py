"""B1 - MAIS MEDIAS (so' 2026). Variantes de `periodos` x `inclina` contra a baseline."""
import sys, io
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as w

BASE = (9, 21, 34, 100, 200)
PERIODOS = [BASE,
    BASE + (300,), BASE + (300, 400), BASE + (300, 400, 500), BASE + (300, 500, 800),
    BASE + (250,), BASE + (400,), BASE + (600,), BASE + (500,), BASE + (800,),
    (9, 21, 34, 55, 100, 200), (9, 21, 34, 100, 150, 200, 300),
    (9, 21, 34, 55, 100, 200, 300), (9, 21, 34, 55, 100, 150, 200, 300),
    (9, 21, 34, 55, 100, 150, 200, 300, 400), (9, 21, 34, 100, 200, 300, 400, 500, 600),
    (9, 21, 34, 100, 200, 400), (9, 21, 34, 100, 200, 250, 300),
]

def variantes():
    out, vistos = [], set()
    for p in PERIODOS:
        opts = {"todas": None,
                "orig5": tuple(i for i, x in enumerate(p) if x in BASE),
                "rap3": (0, 1, 2),
                "rap5": (0, 1, 2, 3, 4)}
        for nome, inc in opts.items():
            if inc is not None and len(inc) == len(p):
                inc = None
            key = (p, inc)
            if key in vistos: continue
            vistos.add(key)
            kw = dict(periodos=p)
            if inc is not None: kw["inclina"] = inc
            out.append((f"{'/'.join(map(str,p))} | incl={nome}", kw))
    return out

def run(i, nome, kw):
    df, r = w.rodar_janelas(2026, "5min", **kw)
    return i, nome, kw, df, r

def main():
    vs = variantes()
    print(f"{len(vs)} variantes", flush=True)
    res = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fs = [ex.submit(run, i, n, kw) for i, (n, kw) in enumerate(vs)]
        for f in as_completed(fs):
            i, n, kw, df, r = f.result()
            res[i] = (n, kw, df, r)
            print(f"{n:55s} liq {r['liquido']:9.2f} jan {r['janelas_pos']:>5} pior {r['pior']:8.2f} PF {r['PF']} tr {r['trades']} DD {r['maior_DD']:.2f} semset {r['liquido_sem_set']:.2f}", flush=True)
    b = res[0][2].set_index("janela").liquido
    print("\n=== RESUMO (ordem de definicao) ===")
    print("variante | liquido | jan+ | pior | PF | trades | DD | sem_set | meses melhor/pior vs base")
    for i in sorted(res):
        n, kw, df, r = res[i]
        s = df.set_index("janela").liquido
        mel = int((s > b).sum()); pio = int((s < b).sum())
        print(f"{n} | {r['liquido']:.2f} | {r['janelas_pos']} | {r['pior']:.2f} | {r['PF']} | {r['trades']} | {r['maior_DD']:.2f} | {r['liquido_sem_set']:.2f} | {mel}/{pio}")
    # mes a mes das 5 melhores por liquido
    top = sorted(res, key=lambda i: -res[i][3]["liquido"])[:6]
    print("\n=== MES A MES (baseline + top liquido) ===")
    import pandas as pd
    tab = pd.DataFrame({("BASE" if i == 0 else res[i][0]): res[i][2].set_index("janela").liquido for i in dict.fromkeys([0] + top)})
    print(tab.to_string())
    print("\nkwargs top:")
    for i in top: print(res[i][0], res[i][1])

if __name__ == "__main__":
    main()
