import sys, json
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "ciclo3"))
import numpy as np
import p4_validacao as p4

j = json.load(open(AQUI / "resultado_2025.json"))
dias, usados, R = j["dias"], set(j["usados"]), j["R"]
novos = [d for d in dias if d not in usados]
V = ("v1", "v2", "v3", "v4")


def linha(v, ds):
    e = p4.estat(R[v], ds)
    return f"| {v} | {len(ds)} | {e['total']:+.0f} | {e['por_dia']:+.1f} | {e['ops']} | {e['acerto_pct']}% | {e['fator_lucro']} | {e['pior_dia']:.0f} | {e['dias_pos']}/{e['dias_neg']} |"


for nome, ds in (("2025 inteiro", dias), ("só dias nunca vistos", novos), ("só dias usados nos ciclos", sorted(usados))):
    print(f"\n{nome}\n| versão | pregões | total R$ | R$/dia | ops | acerto | FP | pior dia | dias +/− |\n|---|---|---|---|---|---|---|---|---|")
    for v in V: print(linha(v, ds))

print("\npor mês (2025 inteiro, R$)\n| mês | " + " | ".join(V) + " |\n|---|" + "---|" * len(V))
for m in sorted({d[:7] for d in dias}):
    ds = [d for d in dias if d.startswith(m)]
    print(f"| {m} | " + " | ".join(f"{sum(R[v][d]['brl'] for d in ds):+.0f}" for v in V) + " |")

print("\ncaixa R$2.000 (1-2 contratos, para < R$1.000), 2025 cronológico")
for v in V:
    c = p4.caixa(R[v], dias)
    # maior queda do caixa
    cx = np.array([h[3] for h in c["hist"]]); dd = float((np.maximum.accumulate(np.r_[2000, cx]) - np.r_[2000, cx]).max())
    print(f"{v}: final {c['final']:.0f} | mínimo {c['minimo']:.0f} | maior queda {dd:.0f} | parou {c['parou']}")
for v in ("v3", "v4"):
    x = np.array([R[v][d]["brl"] for d in novos])
    print(f"{v} nos nunca vistos: IC95 R$/dia por bootstrap",
          np.round(np.percentile([np.random.default_rng(i).choice(x, len(x)).mean() for i in range(5000)], [2.5, 97.5]), 1))
