"""Sorteia 10 pregões do período de ESCOLHA (IS, jan/22-set/25) para a base de decisões.
OOS (out/25-out/26) e virgem (out-dez/21) ficam intocados para testar depois."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "topos_fundos"))
import dados

SEED = 20261009
b = dados.m15("IS")
dias = sorted({str(d.date()) for d in b.dia})
dias = [d for d in dias if d >= "2022-03-01"]  # >= 2 meses de historico antes
escolha = sorted(np.random.default_rng(SEED).choice(dias, 10, replace=False).tolist())
json.dump({"seed": SEED, "periodo": "IS", "dias": escolha}, open(Path(__file__).with_name("dias.json"), "w"), indent=1)
print(escolha)
