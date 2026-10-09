"""Sorteio dos 50 dias NOVOS da rodada v5 (seed 20261012, registrada em RODADAS.md ANTES de rodar). Pool = pool_restante de rodada_v4_dias.json."""
import json
from pathlib import Path
import numpy as np
EXP = Path(__file__).resolve().parents[1]
SEED, N = 20261012, 50
v4 = json.load(open(EXP / "rodada_v4_dias.json", encoding="utf-8"))
pool = [d for d in v4["pool_restante"] if d != "2026-10-05"]
per = {}
for p in ("OOS", "IS"):
    per[p] = sorted(Path(f).stem for f in (EXP.parent / "sessoes_dec" / p).glob("20*.json"))
cand = {p: [d for d in per[p] if d in set(pool)] for p in per}
tot = sum(len(v) for v in cand.values())
n_oos = round(N * len(cand["OOS"]) / tot)
n = {"OOS": n_oos, "IS": N - n_oos}
rng = np.random.default_rng(SEED)
dias = []
for p in ("OOS", "IS"):
    dias += [dict(data=str(d), periodo=p) for d in sorted(rng.choice(cand[p], n[p], replace=False))]
esc = {x["data"] for x in dias}
out = dict(seed=SEED, metodo="sorteio simples dentro de cada periodo, proporcional; numpy default_rng(seed).choice(pool ordenado, n, replace=False); pool = pool_restante da v4",
           candidatos={k: len(v) for k, v in cand.items()}, n=n, dias=sorted(dias, key=lambda x: x["data"]),
           pool_restante=sorted(d for p in cand for d in cand[p] if d not in esc))
(EXP / "rodada_v5_dias.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(out["candidatos"], n, len(out["pool_restante"]))
