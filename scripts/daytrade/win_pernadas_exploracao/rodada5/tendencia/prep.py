import pickle, numpy as np
from base import *

if __name__ == "__main__":
    d = carrega()
    F, didx = features(d)
    FL = filtros(d)
    sl = dias_slices(d)
    days = list(d.d.unique())
    pickle.dump(dict(d=d[["d", "o", "h", "l", "c", "min"]].reset_index(drop=True), F=F, FL=FL, sl=sl, days=days),
                open("prep.pkl", "wb"))
    print(len(d), len(days), days[0], days[-1])
    m = d.d.values >= "2026.01.01"
    for k, v in F.items():
        print(k, "up %.2f down %.2f zero %.2f" % ((v[m] > 0).mean(), (v[m] < 0).mean(), (v[m] == 0).mean()))
    print({k: round(float(v.mean()), 2) for k, v in FL.items()})
