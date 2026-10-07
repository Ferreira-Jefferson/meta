"""Etapa B: M1 x ticks lado a lado (mesmos sinais, mesmos dias com ticks)."""
import os, pickle, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import grid, rules, core, ticks


def main():
    D = grid.get_data(); grid._cache = {}
    items = []
    for fam in rules.FAMS:
        for fc in rules.family_cells(fam):
            cfg, geom = fc["cfg"], fc["geom"]
            evs = grid.events_for(D, cfg)
            for s in (1, -1):
                idx = evs[s]["ENC"]
                if len(idx) == 0: continue
                a, a15 = grid.feats(D, cfg, idx, s)
                items.append(dict(rid=fam[0], cell=fc["value"], s=s, idx=idx, a=a, a15=a15, geom=geom,
                                  central=(fc["value"].startswith("x0.5|K5"))))
    days_all = np.unique(D.day[D.win > 0])
    have = {d: os.path.exists(ticks.TDIR + D.date[np.flatnonzero(D.day == d)[0]].replace(".", "-") + ".pkl") for d in days_all}
    res = {}   # (rid, cell, win, 'm1'|'tk') -> list rows
    for d in days_all:
        if not have[d]: continue
        for it in items:
            sel = np.flatnonzero(D.day[it["idx"]] == d)
            if len(sel) == 0: continue
            idx = it["idx"][sel]; a = {k: v[sel] for k, v in it["a"].items()}; a15 = it["a15"][sel]
            w = int(D.win[idx[0]])
            r1 = core.sim_events(D, idx, it["s"], a, a15, it["geom"])["rows"]
            r2, _ = ticks.sim_ticks(D, idx, it["s"], a, a15, it["geom"])
            for nm, r in (("m1", r1), ("tk", r2)):
                res.setdefault((it["rid"], it["cell"], w, nm), []).append(r)
        if int(d) % 20 == 0: print("dia", d, flush=True)
    out = {k: (np.vstack(v) if v else np.zeros((0, 6))) for k, v in res.items()}
    pickle.dump(out, open("finalB.pkl", "wb"))


if __name__ == "__main__":
    main()
