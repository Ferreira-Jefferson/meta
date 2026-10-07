import pickle, exc
from concurrent.futures import ProcessPoolExecutor, as_completed
if __name__ == "__main__":
    tasks = [(m, m, -1, 0) for m in range(1, 10)]
    out = {}
    with ProcessPoolExecutor(4) as pool:
        fs = {pool.submit(exc.run_task, a): a for a in tasks}
        for f in as_completed(fs):
            s, w, df, R = f.result(); out[w[0]] = (df, R); print("mes", w[0], len(df), flush=True)
    pickle.dump(out, open("real_meses.pkl", "wb"))
