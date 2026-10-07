import core, pickle, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
NS = 150
def run(s):
    d = core.ler(); t = core.tudo(d, sim=True, seed=s); return s, t
if __name__ == "__main__":
    res = {}
    with ProcessPoolExecutor(4) as ex:
        fs = [ex.submit(run, s) for s in range(NS)]
        for f in as_completed(fs):
            s, t = f.result(); res[s] = t
            if len(res) % 10 == 0: print(len(res), flush=True)
    pickle.dump(res, open("sims.pkl", "wb"))
