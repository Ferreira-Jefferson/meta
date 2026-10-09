import sys, json; sys.path.insert(0,'.')
import numpy as np
import av, cfg3
if __name__ == "__main__":
    j=json.load(open("p4_resultados.json")); dias=j["out"]["dias"]; est=np.array([j["out"]["estratos"][d] for d in dias])
    ids=["C8","C7","C6","C4"]
    res=av.avalia([ids, ids+["C10a"], ids+["C10b"], ids+["C2b2"], ids+["C1"]], dias, verbose=False)
    for k,v in res.items():
        arr=np.array([v[d]["brl"] for d in dias]); print("POSTHOC (informativo, nada adotado)",k,round(arr.sum(),1),"dias neg",int((arr<0).sum()),"ruim",round(arr[est=="ruim"].sum(),1),"int",round(arr[est=="int"].sum(),1))
