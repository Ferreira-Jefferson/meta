"""E2 das sinteses, medido centralmente pela mesma funcao das 120."""
from __future__ import annotations

import importlib
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

ALVOS = [("strategy.lab.sintese.hip_01", "IliquidezGrupoComQualidade5A", "sintese"),
         ("strategy.lab.sintese.hip_02", "IliquidezGrupoComRiscoOrcado", "sintese")]
E2_OUT = ROOT / "scripts" / "swing_lab" / "e2_sintese.json"


def medir(args):
    modulo, classe, familia = args
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from swing_lab.measure import monthly_returns_full, select
        cls = getattr(importlib.import_module(modulo), classe)
        s = select(lambda: cls(), name=f"{modulo}.{classe}", family=familia)
        m = monthly_returns_full(lambda: cls())
        s["monthly"] = {str(k.date()): float(v) for k, v in m.items()}
        s["modulo"], s["classe"], s["familia"] = modulo, classe, familia
        return s
    except Exception:
        return {"classe": classe, "erro": traceback.format_exc(limit=3)}


if __name__ == "__main__":
    out = []
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(medir, a) for a in ALVOS]):
            r = f.result()
            out.append(r)
            if "erro" in r:
                print(f"{r['classe']}: FALHOU\n{r['erro']}")
            else:
                print(f"{r['classe']:<34} CAGRmed {r['median_cagr']:>7.2%} "
                      f"piorDD {r['worst_dd']:>8.2%} pior12m {r['worst_12m']:>8.2%} "
                      f"expos {r.get('median_exposure', float('nan')):>5.2f} "
                      f">IBOV {r.get('beat_ibov')}/{r.get('n_windows')} "
                      f"DDgate={r['dd_gate']}")
    E2_OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
