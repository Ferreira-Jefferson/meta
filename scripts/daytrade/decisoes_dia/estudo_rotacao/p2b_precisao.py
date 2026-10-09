"""P(rotacao | estado) por hora, para E1 e E2 (limiares = medianas do calendario IS, declarados). Calendario IS 937."""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
F = json.load(open(ER / "p2_feats.json")); MED = {int(k): v for k, v in json.load(open(ER / "p2_resultado.json"))["medianas"].items()}
print("hora | estado | %dias sinalizados | P(rot|sinal) | P(rot|nao sinal) | base | (IS937) ; depois 90d")
for pop, sel in (("IS937", lambda d: True), ("90d", lambda d: d in set(DIAS))):
    for H in (10, 11, 12, 13):
        ds = [d for d in F if str(H) in F[d] and sel(d)]
        y = np.array([EF[d] < 0.15 for d in ds]); m = MED[H]
        e1 = np.array([F[d][str(H)]["ef_parc"] <= m["ef_parc"] for d in ds])
        e2 = np.array([((F[d][str(H)]["ef_parc"] <= m["ef_parc"]) + (F[d][str(H)]["amp_atrd"] <= m["amp_atrd"]) + (F[d][str(H)]["cruz_vwap"] >= m["cruz_vwap"]) + (F[d][str(H)]["sobrep"] >= m["sobrep"])) >= 3 for d in ds])
        for nome, e in (("E1", e1), ("E2", e2)):
            print(f"{pop} {H}:00 {nome} | sinal {e.mean()*100:.0f}% | P(rot|sinal) {y[e].mean()*100:.0f}% | P(rot|nao) {y[~e].mean()*100:.0f}% | base {y.mean()*100:.0f}%")
