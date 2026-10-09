"""Sorteio dos 50 dias NOVOS da rodada v4 (seed registrada ANTES de rodar). Mesmo metodo da v3: sorteio simples dentro de cada periodo (OOS/IS),
tamanho proporcional ao n de candidatos; candidatos = dias com sessao v1 (sessoes_dec/{OOS,IS}) menos os 40 da v2 (referencia.json) e os 50 da v3
(rodada_v3_dias.json) e menos dias com dado anomalo (salto fechamento->abertura > 3 ATR diario: so 2026-10-05, que ja esta na v3, e que o MT5 confirma como real)."""
import glob
import json
from pathlib import Path
import numpy as np

AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
PAI = EXP.parent
SEED = 20261011
N = 50
ANOMALOS = {"2026-10-05"}

ref = json.load(open(EXP / "referencia.json", encoding="utf-8"))
v2 = {x["data"] for g in ("treino", "validacao") for k in ("bons", "ruins") for x in ref[g][k]}
v3 = {x["data"] for x in json.load(open(EXP / "rodada_v3_dias.json", encoding="utf-8"))["dias"]}
cand = {}
for per in ("OOS", "IS"):
    ds = sorted(Path(f).stem for f in glob.glob(str(PAI / "sessoes_dec" / per / "20*.json")))
    cand[per] = [d for d in ds if d not in v2 and d not in v3 and d not in ANOMALOS]
tot = sum(len(v) for v in cand.values())
n_oos = round(N * len(cand["OOS"]) / tot)
n = {"OOS": n_oos, "IS": N - n_oos}
rng = np.random.default_rng(SEED)
dias = []
for per in ("OOS", "IS"):
    esc = rng.choice(cand[per], n[per], replace=False)
    dias += [dict(data=str(d), periodo=per) for d in sorted(esc)]
out = dict(seed=SEED, metodo="sorteio aleatorio simples dentro de cada periodo (OOS/IS), tamanho proporcional ao n de candidatos; numpy.random.default_rng(seed).choice(candidatos_ordenados, n, replace=False); "
                          "candidatos = dias com sessao v1 em sessoes_dec/{OOS,IS} menos os 40 da v2, os 50 da v3 e os de dado anomalo (2026-10-05)",
           candidatos={k: len(v) for k, v in cand.items()}, n=n, dias=sorted(dias, key=lambda x: x["data"]),
           pool_restante=sorted([d for per in cand for d in cand[per] if d not in {x["data"] for x in dias}]))
(EXP / "rodada_v4_dias.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(v2), len(v3), out["candidatos"], n, len(out["pool_restante"]))
print([d["data"] for d in out["dias"]])
