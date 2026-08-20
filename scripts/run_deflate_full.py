"""Deflacao estatistica com o N REAL: as 120 hipoteses, nao as 30 finalistas.

Por que este script existe
--------------------------
`run_e2_select.py` monta a matriz do CSCV com quem chegou ao E2, porque e lah
que os retornos mensais sao calculados. Isso deixa o funil 120 -> 30 invisivel
para o PBO e para o DSR: as duas ferramentas passam a corrigir a multiplicidade
de 30 escolhas quando foram 120. O erro anda sempre no mesmo sentido — DSR alto
demais, PBO baixo demais — porque a estatistica do maximo de 120 sorteios e bem
mais extrema que a de 30.

O protocolo desta busca ja tinha escrito a regra: "N = numero REAL de hipoteses
medidas, contado pelo diario da busca, nunca estimado". Trinta seria estimado
por conveniencia de onde o dado estava.

O que faz: roda a janela FULL de TODA classe do manifesto (uma janela cada, nao
as 47), monta a matriz mensal completa e recalcula DSR e PBO sobre ela.

Entram TODAS, inclusive as que estouraram o teto de drawdown. Excluir as ruins
encurta a cauda inferior da distribuicao de Sharpe, subestima a variancia dos
ensaios e infla o DSR — a forma mais facil de mentir com esta ferramenta.

Uso: .venv/Scripts/python.exe scripts/run_deflate_full.py --jobs 6
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd

MANIFEST = ROOT / "scripts" / "swing_lab" / "e2_manifest.json"
E2_OUT = ROOT / "scripts" / "swing_lab" / "e2_results.json"
MRET = ROOT / "scripts" / "swing_lab" / "monthly_all.json"
PBO_OUT = ROOT / "scripts" / "swing_lab" / "pbo.json"


def _mensal(args: tuple[str, str, str]) -> dict:
    modulo, classe, familia = args
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from swing_lab.measure import monthly_returns_full
        cls = getattr(importlib.import_module(modulo), classe)
        s = monthly_returns_full(lambda: cls())
        return {"classe": classe, "familia": familia,
                "monthly": {str(k.date()): float(v) for k, v in s.items()}}
    except Exception:
        return {"classe": classe, "familia": familia,
                "erro": traceback.format_exc(limit=2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()

    manifesto = json.loads(MANIFEST.read_text(encoding="utf-8"))
    # O manifesto e {"descobertos": [...], "quebrados": [...]} — nao uma lista.
    achados = manifesto["descobertos"] if isinstance(manifesto, dict) else manifesto
    alvos = [(x["modulo"], x["classe"], x["familia"])
             for x in achados if "erro" not in x]

    # Reaproveita o que o E2 ja calculou; so completa o que falta.
    cache: dict[str, dict] = {}
    if MRET.exists():
        cache = json.loads(MRET.read_text(encoding="utf-8"))
    if E2_OUT.exists():
        for r in json.loads(E2_OUT.read_text(encoding="utf-8")):
            if r.get("monthly"):
                cache[r["classe"]] = {"familia": r["familia"], "monthly": r["monthly"]}

    falta = [t for t in alvos if t[1] not in cache]
    print(f"classes no manifesto: {len(alvos)}  |  em cache: {len(cache)}  |  a medir: {len(falta)}")

    if falta:
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(_mensal, t): t for t in falta}
            for i, f in enumerate(as_completed(futs), 1):
                r = f.result()
                if "erro" in r:
                    print(f"  [{i}/{len(falta)}] {r['classe'][:36]:<38} FALHOU")
                    continue
                cache[r["classe"]] = {"familia": r["familia"], "monthly": r["monthly"]}
                print(f"  [{i}/{len(falta)}] {r['classe'][:36]:<38} {len(r['monthly'])} meses")
        MRET.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    from swing_lab.deflate import deflated_sharpe, pbo_cscv, sharpe_per_obs

    M = pd.DataFrame({k: pd.Series(v["monthly"]) for k, v in cache.items()})
    M = M.loc[:, M.notna().sum() > 60].dropna()
    print(f"\nmatriz para a deflacao: {M.shape[0]} meses x {M.shape[1]} ensaios")

    srs = np.array([sharpe_per_obs(M[c].to_numpy()) for c in M.columns])
    melhor = M.columns[int(np.argmax(srs))]
    d = deflated_sharpe(M[melhor].to_numpy(), srs)
    p = pbo_cscv(M.to_numpy(), s_blocos=16)

    print(f"\nDEFLACAO COM N REAL")
    print(f"  melhor por Sharpe        : {melhor}")
    print(f"  Sharpe anual bruto       : {d.get('sr_anual', float('nan')):.3f}")
    print(f"  SR0 esperado do maximo   : {d.get('sr0_esperado_max', float('nan')):.4f}")
    print(f"  DSR                      : {d.get('dsr', float('nan')):.4f}"
          f"  (nulo empirico: mediana 0,470 / p95 0,665)")
    print(f"  PBO                      : {p.get('pbo', float('nan')):.3f}"
          f"  (nulo empirico: mediana 0,564 / p5 0,358)")
    print(f"  ensaios na deflacao      : {d.get('n_ensaios')}")

    PBO_OUT.write_text(json.dumps({
        "pbo": p.get("pbo"), "dsr": d.get("dsr"),
        "sr_anual": d.get("sr_anual"), "melhor_por_sharpe": melhor,
        "n_ensaios": int(M.shape[1]), "n_meses": int(M.shape[0]),
        "nulo_pbo_mediana": 0.564, "nulo_dsr_p95": 0.665,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ngravado em {PBO_OUT.name} — e daqui que o portao V5 le.")


if __name__ == "__main__":
    main()
