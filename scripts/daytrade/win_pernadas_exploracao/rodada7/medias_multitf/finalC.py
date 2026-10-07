import pickle, warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
warnings.filterwarnings("ignore")
import grid, rules


def task(seed):
    D = grid.get_data(seed); grid._cache = {}
    res = {}
    for fam in rules.FAMS:
        for w in (1, 2, 3):
            e = grid.eval_cell(D, rules.centre(fam), w, False)
            res[(fam[0], w)] = dict(n=e["n"], mean=e["mean"], t=e["t"], win=e["win"], be=e["be"], pv=e["pv"], pf=e["pf"])
    return seed, res


if __name__ == "__main__":
    out = {}
    with ProcessPoolExecutor(4) as ex:
        for f in as_completed([ex.submit(task, s) for s in range(200, 260)]):
            s, r = f.result(); out[s] = r; print("null", s, len(out), flush=True)
            pickle.dump(out, open("finalC.pkl", "wb"))
