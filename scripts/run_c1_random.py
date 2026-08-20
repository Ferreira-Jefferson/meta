"""C1 — o criterio de escolha carrega informacao, ou eu poderia ter sorteado?

O funil desta busca tem um degrau frageil: E1 mede 3 janelas e decide quem
merece as 47 de E2. Se a ordem produzida por 3 janelas nao tiver relacao com a
ordem produzida por 47, o corte de 120 para 30 foi um sorteio com etapas — e
todo o ranking final e o ranking de quem teve sorte na triagem.

Este controle nao roda backtest: usa os numeros ja medidos e responde duas
perguntas.

  (a) CORRELACAO DE ORDEM entre E1 e E2 nas 30 que rodaram as duas etapas.
      Spearman perto de zero significa criterio sem informacao.

  (b) SORTEIO PAREADO: 300 vezes, escolher 3 ao acaso entre as 30 finalistas e
      comparar o CAGR mediano de E2 com o das 3 escolhidas pelo criterio. A
      fracao de sorteios que empata ou ganha e o valor-p do criterio.

Spearman e calculado a mao (media dos ranks em empates) porque nao ha scipy no
ambiente — o resto do projeto ja passou por isso com o inverso da normal.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

E1 = json.loads((ROOT / "scripts/swing_lab/e1_results.json").read_text(encoding="utf-8"))
E2 = json.loads((ROOT / "scripts/swing_lab/e2_results.json").read_text(encoding="utf-8"))


def ranks(x: np.ndarray) -> np.ndarray:
    """Ranks com media em empates, sem scipy."""
    ordem = np.argsort(x)
    r = np.empty(len(x), dtype=float)
    r[ordem] = np.arange(1, len(x) + 1, dtype=float)
    for v in np.unique(x):
        m = x == v
        if m.sum() > 1:
            r[m] = r[m].mean()
    return r


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = ranks(a), ranks(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d > 0 else float("nan")


e1 = {r["classe"]: r for r in E1 if "erro" not in r}
e2 = {r["classe"]: r for r in E2 if "erro" not in r and r.get("n_windows")}
comuns = sorted(set(e1) & set(e2))

a = np.array([e1[c]["median_cagr"] for c in comuns])
b = np.array([e2[c]["median_cagr"] for c in comuns])
rho = spearman(a, b)

print(f"(a) CORRELACAO DE ORDEM E1 -> E2, {len(comuns)} estrategias")
print(f"    Spearman                 : {rho:+.3f}")
print(f"    Pearson dos CAGR         : {np.corrcoef(a, b)[0,1]:+.3f}")
print(f"    CAGR mediano E1 (dessas) : {np.median(a):+.2%}")
print(f"    CAGR mediano E2 (dessas) : {np.median(b):+.2%}")

# Quanto o topo de E1 se manteve no topo de E2
top3_e1 = [c for c in sorted(comuns, key=lambda c: -e1[c]["median_cagr"])[:3]]
top3_e2 = [c for c in sorted(comuns, key=lambda c: -e2[c]["median_cagr"])[:3]]
print(f"    top-3 por E1             : {', '.join(x[:26] for x in top3_e1)}")
print(f"    top-3 por E2             : {', '.join(x[:26] for x in top3_e2)}")
print(f"    intersecao dos top-3     : {len(set(top3_e1) & set(top3_e2))} de 3")

# (b) sorteio pareado
passam = [c for c in comuns if e2[c]["dd_gate"]]
escolhidas = sorted(passam, key=lambda c: -e2[c]["median_cagr"])[:3]
alvo = float(np.median([e2[c]["median_cagr"] for c in escolhidas]))

rng = np.random.default_rng(20260820)
sorteios = np.array([
    np.median([e2[c]["median_cagr"] for c in rng.choice(passam, size=3, replace=False)])
    for _ in range(300)
])
p = float((sorteios >= alvo).mean())

print(f"\n(b) SORTEIO PAREADO, 300 escolhas de 3 entre as {len(passam)} que passam o teto de DD")
print(f"    criterio (top-3 por E2)  : {alvo:+.2%}")
print(f"    sorteio: mediana         : {np.median(sorteios):+.2%}")
print(f"    sorteio: p95             : {np.percentile(sorteios, 95):+.2%}")
print(f"    sorteio: maximo          : {sorteios.max():+.2%}")
print(f"    fracao que iguala ou bate: {p:.3f}")
print("\n    ATENCAO: este p e circular por construcao — o criterio ordena pelo")
print("    MESMO numero que o teste compara, entao ele mede so o quanto o topo")
print("    se separa do grupo, nao se a escolha se sustenta fora da amostra.")
print("    O item (a) e o que responde essa pergunta.")
