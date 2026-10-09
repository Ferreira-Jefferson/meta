"""Passo 1/2: (i) motor novo sem candidatas == v3 nos 70 dias; (ii) cada candidata isolada sobre o v3 vs delta relatado."""
import sys, json, pickle
sys.path.insert(0, '.')
import numpy as np
import ev4, cfg4
from cfg4 import cfg3
from concurrent.futures import ProcessPoolExecutor, as_completed

RELATADO = {"D1": 4.98, "D2": 2.32, "D3": 1.37, "D4": 1.40, "D5": 3.68, "D6": 1.97, "D7": 2.75, "D8": 5.03, "D9": 3.33, "D10": 3.95,
            "D11": 2.58, "D12": 1.78, "D13": 6.93, "D14": 4.85, "D15": 5.29, "D16": 7.35}


def _v3(dia):
    r = cfg3.resultado_dia(dia, cfg3.monta(cfg4.V3))
    return dia, r


if __name__ == "__main__":
    # (i) identidade com o motor de cfg3
    with ProcessPoolExecutor(6) as ex:
        ref = {}
        for f in as_completed([ex.submit(_v3, d) for d in ev4.DIAS]):
            d, r = f.result(); ref[d] = r
    R = ev4.avalia([()], verbose=False)[()]
    dif = [d for d in ev4.DIAS if ref[d]["brl"] != R[d]["brl"] or ref[d]["trades"] != R[d]["trades"]]
    print("IDENTIDADE v4(sem cand) vs cfg3.roda v3 nos 70 dias: dias diferentes =", len(dif), dif, flush=True)
    vb = ev4.vec(R)
    print(f"v3 70 dias: total {vb.sum():.2f}  rep {ev4.repond(vb):.2f}  pior dia {vb.min():.2f}", flush=True)
    # cache do ciclo 3 (50 dias) e do agente ag2 (70 dias)
    c3 = pickle.load(open(cfg4.RAIZ / "ciclo3" / "cache.pkl", "rb"))
    k = ("C4", "C6", "C7", "C8")
    d50 = [d for d, _ in cfg3.dias50()]
    print("vs cache ciclo3 (50 dias) max|dif| =", max(abs(c3[(k, d)]["brl"] - R[d]["brl"]) for d in d50), flush=True)
    # (ii) isoladas
    res = ev4.avalia([(i,) for i in cfg4.ORDEM])
    out = {}
    print("\nid | d_rep relatado | d_rep port | dif | d_nd | d_dir | d c0-2 | d c3 | pior/melhor | pior_dia | LOO min", flush=True)
    for i in cfg4.ORDEM:
        v = ev4.vec(res[(i,)]); l = ev4.linha(v, vb); out[i] = l
        dif_ = l["d_rep"] - RELATADO[i]
        print(f"{i:4s} | {RELATADO[i]:+6.2f} | {l['d_rep']:+6.2f} | {dif_:+5.2f}{' <<<' if abs(dif_) > 0.10 else ''} | {l['d_nd']:+6.2f} | {l['d_dir']:+6.2f} | {l['d012']:+8.1f} | {l['d3']:+7.1f} | {l['pior']}/{l['melhor']} | {l['pior_dia']:.1f} | {l['lodo_min']:+.2f} ({l['lodo_dia']})", flush=True)
    json.dump(dict(identidade_dias_dif=dif, base=dict(total=float(vb.sum()), rep=float(ev4.repond(vb))), isoladas=out, relatado=RELATADO),
              open("p_confere.json", "w"), indent=1)
