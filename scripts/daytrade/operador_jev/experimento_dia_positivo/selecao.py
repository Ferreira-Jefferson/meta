"""Escolhe os dias do experimento "perguntas para o dia positivo" a partir da rodada JA FEITA do Jev
(sessoes_dec/OOS e sessoes_dec/IS, limiar 0,3, jev-1.13-20260917) -- nao chama a API.

Bons = maiores resultados do Jev; ruins = menores. Alternando no ranking, metade vai para TREINO
(dias que os agentes estudam para criar as perguntas) e metade para VALIDACAO (o Jev novo roda so
nesses, nunca vistos na criacao). Grava referencia.json com o resultado atual de cada dia."""
import glob, json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
dias = []
for per in ("OOS", "IS"):
    for f in sorted(glob.glob(str(AQUI.parent / "sessoes_dec" / per / "20*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        r = d["resumo"]
        dias.append(dict(data=d["data"], periodo=per, ops=r["ops"], brl=round(r["total"], 2),
                         pts=r.get("pts"), acerto=r.get("acerto"), trades=d["trades"]))
operou = [x for x in dias if x["ops"] > 0]
bons = sorted([x for x in operou if x["brl"] > 0], key=lambda x: -x["brl"])[:20]
ruins = sorted([x for x in operou if x["brl"] < 0], key=lambda x: x["brl"])[:20]
ref = {"origem": "rodada jev-1.13-20260917, limiar 0,3, 54 perguntas (commit 5e10809)",
       "treino": {"bons": bons[1::2], "ruins": ruins[1::2]},
       "validacao": {"bons": bons[0::2], "ruins": ruins[0::2]}}
json.dump(ref, open(AQUI / "referencia.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for g in ("treino", "validacao"):
    for k in ("bons", "ruins"):
        xs = ref[g][k]
        print(g, k, sum(x["brl"] for x in xs), [(x["data"], x["periodo"], x["brl"]) for x in xs])
