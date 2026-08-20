"""DSR dos candidatos REAIS, e o que o PBO agregado esconde.

Dois problemas com a linha unica que `run_deflate_full.py` imprimiu.

1) O DSR foi calculado para a estrategia de maior Sharpe da matriz, que nao e
   nenhuma das que vao ao cofre. O DSR de Bailey & Lopez de Prado e definido
   para a estrategia SELECIONADA: o termo de correcao usa a dispersao dos N
   ensaios, mas o numerador tem de ser o Sharpe de quem foi escolhido. Reportar
   o DSR do maximo e responder uma pergunta que ninguem fez.

2) O PBO caiu de 0,016 (N=30) para 0,001 (N=120) — na direcao oposta do que se
   esperaria de uma correcao de multiplicidade mais honesta. Nao e milagre: o
   PBO/CSCV mede se o vencedor DENTRO da amostra fica acima da MEDIANA do
   proprio grupo fora da amostra. Ao acrescentar 90 hipoteses fracas, a mediana
   do grupo desce, e ficar acima dela fica mais facil. O PBO e uma medida de
   rank relativo ao pool, nao um valor absoluto de sobreajuste — trocar o pool
   troca a regua. Aqui os dois pools sao reportados, com essa ressalva.

Uso: .venv/Scripts/python.exe scripts/run_dsr_candidatos.py
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
E2_RES = ROOT / "scripts" / "swing_lab" / "e2_results.json"
OUT = ROOT / "scripts" / "swing_lab" / "pbo.json"

cache = json.loads(MRET.read_text(encoding="utf-8"))
M = pd.DataFrame({k: pd.Series(v["monthly"]) for k, v in cache.items()})
M = M.loc[:, M.notna().sum() > 60].dropna()
srs_all = np.array([sharpe_per_obs(M[c].to_numpy()) for c in M.columns])

e2 = [r for r in json.loads(E2_RES.read_text(encoding="utf-8"))
      if "erro" not in r and r.get("dd_gate") and r.get("n_windows")]
e2.sort(key=lambda r: r["median_cagr"], reverse=True)
top = e2[:10]

print(f"matriz: {M.shape[0]} meses x {M.shape[1]} ensaios")
print(f"SR0 esperado do maximo de {M.shape[1]} ensaios: {expected_max_sharpe(srs_all):.4f}\n")

print(f"{'candidato':<32}{'familia':<17}{'Sharpe an':>10}{'DSR':>8}{'expos':>7}{'CAGRmed':>9}")
print("-" * 83)
linhas = []
for r in top:
    c = r["classe"]
    if c not in M.columns:
        print(f"{c[:31]:<32}{'sem serie mensal':<17}")
        continue
    d = deflated_sharpe(M[c].to_numpy(), srs_all)
    linhas.append({"classe": c, "familia": r["familia"], "dsr": d.get("dsr"),
                   "sr_anual": d.get("sr_anual"), "expos": r.get("median_exposure"),
                   "median_cagr": r["median_cagr"]})
    print(f"{c[:31]:<32}{r['familia'][:16]:<17}{d.get('sr_anual', float('nan')):>10.3f}"
          f"{d.get('dsr', float('nan')):>8.4f}{r.get('median_exposure', float('nan')):>7.2f}"
          f"{r['median_cagr']:>9.2%}")
print("-" * 83)

# Quem ganha por Sharpe e por que — teste da suspeita de "Sharpe alto = pouca bolsa".
ordem = np.argsort(-srs_all)
expos_por_classe = {r["classe"]: r.get("median_exposure") for r in
                    json.loads(E2_RES.read_text(encoding="utf-8")) if "erro" not in r}
print(f"\n5 maiores Sharpes da matriz inteira (nao os escolhidos por CAGR):")
print(f"{'classe':<32}{'Sharpe an':>10}{'expos E2':>10}")
for i in ordem[:5]:
    c = M.columns[i]
    x = expos_por_classe.get(c)
    print(f"{c[:31]:<32}{srs_all[i]*np.sqrt(12):>10.3f}"
          f"{(f'{x:.2f}' if x is not None else 'nao foi a E2'):>10}")

p120 = pbo_cscv(M.to_numpy(), s_blocos=16)
cols30 = [r["classe"] for r in e2 if r["classe"] in M.columns]
p30 = pbo_cscv(M[cols30].to_numpy(), s_blocos=16)
print(f"\nPBO no pool das {len(cols30)} finalistas : {p30.get('pbo'):.3f}")
print(f"PBO no pool das {M.shape[1]} medidas     : {p120.get('pbo'):.3f}")
print("  (nulo empirico com series de media zero: mediana 0,564 / p5 0,358)")
print("  O pool das finalistas e a regua mais dura: todas ali sao boas, ficar")
print("  acima da mediana exige ganhar de quem tambem passou o funil.")

OUT.write_text(json.dumps({
    "pbo_finalistas": p30.get("pbo"), "pbo_todas": p120.get("pbo"),
    "n_ensaios": int(M.shape[1]), "n_meses": int(M.shape[0]),
    "sr0_esperado_max": float(expected_max_sharpe(srs_all)),
    "candidatos": linhas,
    "nulo_pbo_mediana": 0.564, "nulo_dsr_p95": 0.665,
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\ngravado em {OUT.name} — portao V5 le `pbo_finalistas`.")
