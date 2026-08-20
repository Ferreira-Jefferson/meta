"""Progresso da busca de swing. Le disco e diario; nao roda backtest nenhum.

Uso: .venv/Scripts/python.exe scripts/swing_lab/progress.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "src" / "strategy" / "lab"
LEDGER = ROOT / "scripts" / "swing_lab" / "trials.jsonl"
WF = Path(os.path.expanduser("~")) / ".claude" / "projects"

FAMILIAS = ("iliquidez", "baixa_vol", "reversao", "carry_cdi", "trend_ts",
            "risk_targeting", "dd_control", "macro_gate", "breadth_setor",
            "preco_qualidade", "execucao", "construcao")


def _agentes() -> tuple[set[str], dict[str, str]]:
    """Familias concluidas e ativas, lidas do journal do workflow mais recente."""
    dirs = sorted(WF.glob("*/*/subagents/workflows/wf_*"), key=os.path.getmtime)
    if not dirs:
        return set(), {}
    d = dirs[-1]
    j = d / "journal.jsonl"
    if not j.exists():
        return set(), {}
    rows = []
    for linha in j.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(linha))
        except json.JSONDecodeError:
            pass
    feitos = {r["agentId"] for r in rows if r.get("type") == "result"}
    todos = {r["agentId"] for r in rows if r.get("type") == "started"}
    fam = {}
    for aid in todos:
        p = d / f"agent-{aid}.jsonl"
        if not p.exists():
            continue
        with open(p, encoding="utf-8", errors="ignore") as fh:
            cabeca = fh.read(6000)
        # O prompt esta JSON-encodado dentro do .jsonl, entao as aspas viram
        # \\" — casar por classe negada e mais robusto que contar escapes.
        m = re.search(r'familia de hipoteses [^a-zA-Z]{0,4}([a-z_]+)', cabeca)
        fam[aid] = m.group(1) if m else "?"
    return {fam.get(a, "?") for a in feitos}, fam


def main() -> None:
    arquivos = collections.Counter()
    for p in glob.glob(str(LAB / "*" / "hip_*.py")):
        arquivos[Path(p).parent.name] += 1

    medidos = collections.Counter()
    passam = collections.Counter()
    if LEDGER.exists():
        for linha in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if r.get("stage") != "E1":
                continue
            f = r.get("family", "?").replace("_probe", "").replace("_smoke", "")
            medidos[f] += 1
            if r.get("dd_gate"):
                passam[f] += 1

    feitas, _ = _agentes()

    print(f"{'familia':<18}{'arquivos':>9}{'medidos':>9}{'passam DD':>11}{'agente':>12}")
    print("-" * 59)
    for f in FAMILIAS:
        est = "concluida" if f in feitas else "rodando"
        print(f"{f:<18}{arquivos.get(f, 0):>9}{medidos.get(f, 0):>9}"
              f"{passam.get(f, 0):>11}{est:>12}")
    print("-" * 59)
    print(f"{'TOTAL':<18}{sum(arquivos.values()):>9}{sum(medidos.values()):>9}"
          f"{sum(passam.values()):>11}{f'{len(feitas)}/12':>12}")
    print("\nNota: 'medidos'/'passam DD' sao AUTO-REPORTADOS pelos agentes.")
    print("O ranking oficial vem de `run_e2_select.py --e1`, que remede tudo.")


if __name__ == "__main__":
    main()
