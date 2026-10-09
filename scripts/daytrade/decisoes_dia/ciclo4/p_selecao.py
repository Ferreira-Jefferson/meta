"""Selecao para frente do ciclo 4 (criterios (a)-(e) do PREREGISTRO.md, nos 70 dias de dias_usados.json). Log: p_selecao.log; json: p_selecao.json."""
import sys, json
sys.path.insert(0, '.')
import numpy as np
import ev4, cfg4

if __name__ == "__main__":
    atuais, hist, passo = [], [], 0
    while True:
        passo += 1
        grupos = {cfg4.CAND[i][2] for i in atuais if cfg4.CAND[i][2]}
        cand = [c for c in cfg4.ORDEM if c not in atuais and not (cfg4.CAND[c][2] and cfg4.CAND[c][2] in grupos)]
        res = ev4.avalia([atuais] + [atuais + [c] for c in cand])
        vb = ev4.vec(res[cfg4.chave(atuais)])
        print(f"\n=== passo {passo}: base v3+{atuais}  rep={ev4.repond(vb):.2f}  total={vb.sum():.1f}  pior_dia={vb.min():.1f}", flush=True)
        ok, linhas = [], {}
        for c in cand:
            v = ev4.vec(res[cfg4.chave(atuais + [c])]); l = ev4.linha(v, vb)
            a = l['d_rep'] > 1e-9
            b = l['d_nd'] >= -1e-9
            cc = l['d012'] > 1e-9 and l['d3'] >= -1e-9
            d = l['pior_dia'] >= vb.min() - 50
            e = l['lodo_min'] > 1e-9
            passa = a and b and cc and d and e
            linhas[c] = dict(l, a=bool(a), b=bool(b), c=bool(cc), d=bool(d), e=bool(e), passa=bool(passa))
            print(f"  {c:4s} d_rep={l['d_rep']:+7.2f} d_nd={l['d_nd']:+6.2f} d_dir={l['d_dir']:+7.2f} d012={l['d012']:+8.1f} d3={l['d3']:+7.1f} "
                  f"pior/melh={l['pior']}/{l['melhor']} pior_dia={l['pior_dia']:.1f} lodo_min={l['lodo_min']:+.2f}({l['lodo_dia']})  "
                  f"a={int(a)} b={int(b)} c={int(cc)} d={int(d)} e={int(e)} {'PASSA' if passa else ''}", flush=True)
            if passa: ok.append((l['d_rep'], c))
        hist.append(dict(passo=passo, base=list(atuais), rep=float(ev4.repond(vb)), total=float(vb.sum()), cand=linhas, passam=[(float(x), c) for x, c in ok]))
        if not ok: break
        ok.sort(reverse=True)
        print(f"  -> entra {ok[0][1]} (d_rep {ok[0][0]:+.2f})", flush=True)
        atuais.append(ok[0][1])
    print("\nSELECAO FINAL:", atuais, flush=True)
    json.dump(dict(final=atuais, hist=hist), open("p_selecao.json", "w"), indent=1)
