import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
P1 = json.load(open(ER / "p1_fontes.json")); P2 = json.load(open(ER / "p2_resultado.json")); P3 = json.load(open(ER / "p3_resumo.json"))
f = lambda x: f"{x:+,.0f}".replace(",", ".")
c = lambda x: f"{x:+.2f}".replace(".", ",")
print("### T1 fontes\n| fonte | rot n | rot R$ | rot acerto | int n | int R$ | dir n | dir R$ | fora(int+dir) R$ |\n|---|---|---|---|---|---|---|---|---|")
for r in sorted(P1, key=lambda r: r["brl_rot"]):
    nome = r["fonte"].replace("�", "?")
    ac = "-" if r["n_rot"] == 0 else f"{r['ac_rot']*100:.0f}%"
    print(f"| {nome} | {r['n_rot']} | {f(r['brl_rot'])} | {ac} | {r['n_int']} | {f(r['brl_int'])} | {r['n_dir']} | {f(r['brl_dir'])} | {f(r['brl_fora'])} |")
print("\n### T2 AUC\n| populacao | feature | 10h | 11h | 12h | 13h |\n|---|---|---|---|---|---|")
for pop in ("IS937", "90d"):
    for k in list(SINAL) + ["voto>=3de4"]:
        v = [[l for l in P2["linhas"] if l["pop"] == pop and l["H"] == H and l["feat"] == k][0]["auc"] for H in (10, 11, 12, 13)]
        print(f"| {pop} | {k} | " + " | ".join(f"{x:.2f}".replace(".", ",") for x in v) + " |")
print("\n### T3 usos\n| uso | estado | total R$ | rep R$/dia | d rep | d nd/dia | d rot/dia | d 40 aleat R$ | pior/melhor dia | LOO min | trades |\n|---|---|---|---|---|---|---|---|---|---|---|")
for l in P3:
    print(f"| {l['uso']} | {l['estado']} | {l['total']:.0f} | {l['rep']:.1f} | {c(l['d_rep'])} | {c(l['d_nd'])} | {c(l['d_rot'])} | {f(l['d_40'])} | {l['pior']}/{l['melhor']} | {c(l['lodo_min'])} | {l['trades']} |")
