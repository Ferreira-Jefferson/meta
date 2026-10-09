"""Avalia as propostas dos dias 2022-04-13 e 2022-05-17 (+ grupo) sobre o v3 nos 70 dias de dias_usados.json.
Uso: python analises/c3_2022_04_13_avalia.py [saida.json]   (cache em C3_CACHE, se definido). Roda de dentro de decisoes_dia/."""
import sys, os, json, pickle
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
import numpy as np
from regras import c3_grupo_2022_04_13 as g, c3_2022_04_13 as ca, c3_2022_05_17 as cb

MODS = ("regras.c3_grupo_2022_04_13", "regras.c3_2022_04_13", "regras.c3_2022_05_17")
SINGLE = ["G1c_alvo_0.5R_rot", "G1d_alvo_1R_rot", "G1e_alvo_0.5R_ef0.15", "G2b_trava_0.5R_rot", "G2c_trava_0.5R_lock60_rot", "G5_fade_borda_rot", "G6_continuacao_cedo",
          "G3_veto_borda_rot"] + [f"G3n_venda_ef{e}_f{f}" for e in (0.06, 0.1, 0.15) for f in (0.2, 0.3, 0.4)] + \
         [f"G4n_cont_ef{e}_amp{a}" for e in (0.06, 0.08, 0.1) for a in (0.25, 0.35, 0.45)] + \
         list(ca.CAND) + list(cb.CAND)
COMBOS = [("G3n_venda_ef0.1_f0.3", "G4n_cont_ef0.08_amp0.35"), ("G3n_venda_ef0.1_f0.3", "G4n_cont_ef0.08_amp0.35", "b_A2_condicional"),
          ("G4n_cont_ef0.08_amp0.35", "b_A2_condicional")]


def lodo(v, b, dias, g_):
    """min do delta reponderado deixando cada dia de fora."""
    import json as _j
    ef = _j.load(open(RAIZ / "ciclo3" / "ef_todos.json")); fr = sum(e >= 0.25 for e in ef.values()) / len(ef)
    dire = np.array([ef[d] >= 0.25 for d in dias]); out = []
    for i in range(len(dias)):
        m = np.ones(len(dias), bool); m[i] = False
        rep = lambda x: fr * x[m & dire].mean() + (1 - fr) * x[m & ~dire].mean()
        out.append(rep(v) - rep(b))
    return min(out), dias[int(np.argmin(out))]


if __name__ == "__main__":
    saida = sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / "analises" / "c3_2022_04_13_70dias.json")
    cp = os.environ.get("C3_CACHE"); cache = pickle.load(open(cp, "rb")) if cp and os.path.exists(cp) else {}
    cfgs = [()] + [(i,) for i in SINGLE] + [tuple(c) for c in COMBOS]
    R = g.avalia(cfgs, modulos=MODS, cache=cache)
    if cp: pickle.dump(cache, open(cp, "wb"))
    dias = [d for d, _ in g.dias70()]
    b = np.array([R[()][d]["brl"] for d in dias])
    print(f"v3 base nos 70 dias: R$ {b.sum():.2f}", flush=True)
    tab = {}
    for c in cfgs[1:]:
        m = g.metricas(R[c], R[()]); v = np.array([R[c][d]["brl"] for d in dias]); lm, ld = lodo(v, b, dias, g)
        m.update(lodo_min=lm, lodo_dia=ld, dia_0413=R[c]["2022-04-13"]["brl"], dia_0517=R[c]["2022-05-17"]["brl"])
        tab["+".join(c)] = m
        print(f"{'+'.join(c):55s} d_rep {m['d_rep']:+7.2f} d_dir {m['d_dir']:+7.2f} d_nd {m['d_nd']:+7.2f} d_c3 {m['d_c3']:+8.1f} (ext {m['d_c3_ext']:+7.1f}) "
              f"d_tot {m['d_total']:+8.1f} p/m {m['piora']}/{m['melhora']} lodo_min {lm:+6.2f} dias {m['dia_0413']:+.0f}/{m['dia_0517']:+.0f}", flush=True)
    json.dump(tab, open(saida, "w"), indent=1, default=float)
