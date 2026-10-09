import sys; sys.path.insert(0, '.')
import numpy as np, json
import av, cfg3, an

if __name__ == "__main__":
    atuais = []
    pool = list(cfg3.ORDEM)
    hist = []
    passo = 0
    while True:
        passo += 1
        grupos = {cfg3.CAND[i][3] for i in atuais if cfg3.CAND[i][3]}
        cand = [c for c in pool if c not in atuais and not (cfg3.CAND[c][3] and cfg3.CAND[c][3] in grupos)]
        res = av.avalia([atuais] + [atuais + [c] for c in cand], an.DIAS)
        kb = tuple(sorted(atuais, key=cfg3.ORDEM.index))
        vb = an.vec(res[kb])
        print(f"\n=== passo {passo}: base {atuais or 'v2'}  rep={an.repond(vb):.2f}  total={vb.sum():.1f}  pior_dia={vb.min():.1f}", flush=True)
        ok = []
        for c in cand:
            k = tuple(sorted(atuais + [c], key=cfg3.ORDEM.index))
            v = an.vec(res[k]); l = an.linha(v, vb)
            a = l['d_rep'] > 1e-9
            b = l['d_nd'] >= -1e-9
            cc = l['d01'] > 1e-9 and l['d2'] > 1e-9
            d = v.min() >= vb.min() - 50
            passa = a and b and cc and d
            print(f"  {c:5s} d_rep={l['d_rep']:+7.2f} d_dir={l['d_dir']:+7.2f} d_nd={l['d_nd']:+6.2f} d_ruim={l['d_ruim']:+6.2f} d01={l['d01']:+8.1f} d2={l['d2']:+8.1f} "
                  f"pior/melh={l['pior']}/{l['melhor']} pior_dia={l['pior_dia']:.1f}  a={int(a)} b={int(b)} c={int(cc)} d={int(d)} {'PASSA' if passa else ''}", flush=True)
            if passa: ok.append((l['d_rep'], c))
        hist.append(dict(passo=passo, base=list(atuais), rep=float(an.repond(vb)), total=float(vb.sum()), passam=[(float(x), c) for x, c in ok]))
        if not ok: break
        ok.sort(reverse=True)
        print(f"  -> entra {ok[0][1]} (d_rep {ok[0][0]:+.2f})", flush=True)
        atuais.append(ok[0][1])
    print("\nSELECAO FINAL:", atuais)
    json.dump(dict(final=atuais, hist=hist), open("p3_selecao.json", "w"), indent=1)
