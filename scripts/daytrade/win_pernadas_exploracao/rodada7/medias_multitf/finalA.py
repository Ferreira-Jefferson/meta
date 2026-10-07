"""Etapa A: por regra congelada e janela (desc=1, conf=2, set=3): M1, familia (12 celulas), comparacoes, filtros."""
import sys, pickle, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import grid, rules, core, compare

WINS = {1: "descoberta jan-jun", 2: "confirmacao jul-ago", 3: "set/26"}


def main():
    D = grid.get_data(); grid._cache = {}
    out = dict(central={}, fam={}, cmp={}, pud={}, filt={}, rows={})
    for fam in rules.FAMS:
        rid = fam[0]
        for w in (1, 2, 3):
            c = rules.centre(fam)
            out["central"][(rid, w)] = grid.eval_cell(D, c, w, True)
            rr, nsig, nfill, ninv = grid.run_trades(D, c["cfg"], c["geom"], "ENC", w, "same", collect=True)
            out["rows"][(rid, w)] = rr
            fr = []
            for fc in rules.family_cells(fam):
                e = grid.eval_cell(D, fc, w, False); e["x"] = fc["value"]; fr.append(e)
            out["fam"][(rid, w)] = fr
            t, p, k = compare.compare(D, c["cfg"], c["geom"], w, nrand=20)
            out["cmp"][(rid, w)] = t; out["pud"][(rid, w)] = p
            print(rid, w, "ok", flush=True)
    pickle.dump(out, open("finalA.pkl", "wb"))
    # guarda dados auxiliares para filtros
    aux = dict(m=D.m, v2x=D.v2x, zz=D.zz, win=D.win, day=D.day, date=D.date)
    pickle.dump(aux, open("aux.pkl", "wb"))


if __name__ == "__main__":
    main()
