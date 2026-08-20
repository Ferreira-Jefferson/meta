"""DSR/PBO finais, N=122 (120 hipoteses + 2 sinteses), sobre os 5 candidatos reais.

Substitui `run_dsr_candidatos.py`: aquele tinha N=120 e nao incluia as sinteses,
que sao ensaios tao validos quanto qualquer hipotese — foram medidas depois de
ver o resultado das outras, o que as torna MAIS expostas a sobreajuste, nao
menos, e por isso tem que entrar na deflacao.

MacroGatedBreakout saiu dos candidatos (estourou o teto de DD com capital raso,
ver `capital_pequeno.json`) mas continua na MATRIZ da deflacao — ela foi um
ensaio de verdade, tirar da matriz so porque falhou depois inflaria o DSR dos
que sobraram.

Uso: .venv/Scripts/python.exe scripts/run_dsr_final.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd

from swing_lab.deflate import deflated_sharpe, expected_max_sharpe, pbo_cscv, sharpe_per_obs

MRET = ROOT / "scripts" / "swing_lab" / "monthly_all.json"
OUT = ROOT / "scripts" / "swing_lab" / "pbo_final.json"

CANDIDATOS = ["Hip06IliquidezRelativaAoGrupo", "LongHorizonRiskAdjustedReturn",
              "Hip03ExcluiTopoLiquidez", "IliquidezGrupoComQualidade5A",
              "IliquidezGrupoComRiscoOrcado"]

cache = json.loads(MRET.read_text(encoding="utf-8"))
M = pd.DataFrame({k: pd.Series(v["monthly"]) for k, v in cache.items()})
M = M.loc[:, M.notna().sum() > 60].dropna()
srs_all = np.array([sharpe_per_obs(M[c].to_numpy()) for c in M.columns])

print(f"matriz: {M.shape[0]} meses x {M.shape[1]} ensaios (N real, com as 2 sinteses)")
print(f"SR0 esperado do maximo de {M.shape[1]} ensaios: {expected_max_sharpe(srs_all):.4f}\n")

print(f"{'candidato':<32}{'Sharpe an':>10}{'DSR':>8}")
print("-" * 50)
linhas = []
for c in CANDIDATOS:
    if c not in M.columns:
        print(f"{c[:31]:<32}  sem serie mensal")
        continue
    d = deflated_sharpe(M[c].to_numpy(), srs_all)
    linhas.append({"classe": c, "dsr": d.get("dsr"), "sr_anual": d.get("sr_anual")})
    print(f"{c[:31]:<32}{d.get('sr_anual', float('nan')):>10.3f}{d.get('dsr', float('nan')):>8.4f}")
print("-" * 50)
print("(nulo empirico com series de media zero: DSR mediana 0,470 / p95 0,665)")

pbo_cands = pbo_cscv(M[[c for c in CANDIDATOS if c in M.columns]].to_numpy(), s_blocos=16)
pbo_all = pbo_cscv(M.to_numpy(), s_blocos=16)
print(f"\nPBO no pool dos {len(CANDIDATOS)} candidatos finais : {pbo_cands.get('pbo'):.3f}")
print(f"PBO no pool completo (N={M.shape[1]})         : {pbo_all.get('pbo'):.3f}")
print("(nulo empirico: mediana 0,564 / p5 0,358)")

OUT.write_text(json.dumps({
    "n_ensaios": int(M.shape[1]), "n_meses": int(M.shape[0]),
    "pbo_candidatos": pbo_cands.get("pbo"), "pbo_pool_completo": pbo_all.get("pbo"),
    "candidatos": linhas, "nulo_pbo_mediana": 0.564, "nulo_dsr_p95": 0.665,
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\ngravado em {OUT.name}")
