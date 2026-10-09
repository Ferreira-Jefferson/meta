import sys; sys.path.insert(0, 'ciclo3'); sys.path.insert(0, '.')
import ag2_lib as L
if __name__ == "__main__":
    ids = sys.argv[1:] or ["A2F", "A2T", "A2E", "A2V", "E1", "E1s", "E2", "E3", "G1", "F2G", "F2L", "NR", "N4T", "CFd", "CFc"]
    ids = [tuple(i.split("+")) for i in ids]
    res = L.avalia([()] + ids)
    vb = L.vec(L.base70())
    v0 = L.vec(res[()]); print("baseline reproduz cache (max |dif|):", abs(v0 - vb).max(), flush=True)
    L.tabela(ids, res, vb)
