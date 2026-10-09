import sys; sys.path.insert(0, '.')
import numpy as np, json
import av, cfg3, an
if __name__ == "__main__":
    configs = [[]] + [[c] for c in cfg3.ORDEM]
    res = av.avalia(configs, an.DIAS)
    vb = an.vec(res[()])
    print("v2 total", round(vb.sum(), 2), "(esperado 4678.77)")
    print("frac3", an.FR3, "frac2", an.FR2)
    print("v2: rep", round(an.repond(vb), 2), "dir", round(vb[an.EST2 == 'dir'].mean(), 2), "nd", round(vb[an.EST2 == 'nd'].mean(), 2),
          "ruim", round(vb[an.EST3 == 'ruim'].mean(), 2), "int", round(vb[an.EST3 == 'int'].mean(), 2), "rep3", round(an.repond3(vb), 2))
    out = {}
    print("id | total | rep | d_rep | dir | nd | d_dir | d_nd | d_ruim | d01 | d2 | pior/melhor | pior_dia | lodo(min,max,dia)")
    for c in cfg3.ORDEM:
        v = an.vec(res[(c,)]); l = an.linha(v, vb); out[c] = l
        print(c, round(l['total'], 1), round(l['rep'], 2), round(l['d_rep'], 2), round(l['dir'], 1), round(l['nd'], 2), round(l['d_dir'], 2),
              round(l['d_nd'], 2), round(l['d_ruim'], 2), round(l['d01'], 1), round(l['d2'], 1), f"{l['pior']}/{l['melhor']}",
              round(l['pior_dia'], 1), tuple(round(x, 2) if not isinstance(x, str) else x for x in l['lodo']), flush=True)
    json.dump({k: {a: (list(b) if isinstance(b, tuple) else (float(b) if not isinstance(b, (int, str)) else b)) for a, b in v.items()} for k, v in out.items()},
              open("p2_isoladas.json", "w"), indent=1)
