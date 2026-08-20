"""E2 — selecao. Determinístico, sem agente: importa, mede, ranqueia, defla.

Este passo NAO usa modelo de linguagem de proposito. E1 exigiu julgamento (que
hipotese vale desenhar); E2 e mecanico — rodar 47 janelas e ordenar. Deixar um
agente "escolher" aqui seria reintroduzir exatamente a contaminacao que a secao
4 do protocolo descreve: o pesquisador olhando resultado e decidindo quem passa.

TODA metrica que entra no ranking e produzida AQUI. Os agentes desenham e
implementam; eles tambem chamam `screen()` para verificar o proprio codigo, mas
o numero que ranqueia nao vem do que eles reportaram. Dois motivos: o nome do
ensaio que o agente passa nao casa com a classe no disco, e — o que importa —
metrica autorreportada e metrica que ninguem verificou. Remedir tudo com a mesma
funcao, no mesmo processo, e o que torna 120 hipoteses comparaveis.

O funil e o declarado em `run_vault_verdict.py` e nao se altera:
  descoberta por varredura -> E1 (FULL + 2 janelas) -> no maximo 30 sobreviventes
  -> E2 (47 janelas trimestrais) -> 3 melhores ao cofre, mais 2 sinteses.

Apresentacao: imprime os 10 melhores, nao os ~120 ensaios. O N completo entra
so como numero na deflacao.

Uso:
  .venv/Scripts/python.exe scripts/run_e2_select.py --descobrir
  .venv/Scripts/python.exe scripts/run_e2_select.py --e1 [--jobs 6]
  .venv/Scripts/python.exe scripts/run_e2_select.py --e1 --e2 [--jobs 6]
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import pkgutil
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
E1_OUT = ROOT / "scripts" / "swing_lab" / "e1_results.json"
E2_OUT = ROOT / "scripts" / "swing_lab" / "e2_results.json"
MAX_E2 = 30


def descobrir() -> list[dict]:
    """Varre src/strategy/lab/ e acha toda Strategy construivel sem argumento.

    Descoberta por varredura, e nao pela lista que os agentes devolveram: se um
    agente esqueceu de reportar uma hipotese que implementou, ela entra; se
    reportou uma que nao existe, ela nao entra. O disco e a fonte da verdade.
    """
    from strategy.base import Strategy
    import strategy.lab as lab

    achados: list[dict] = []
    for mod in pkgutil.walk_packages(lab.__path__, prefix="strategy.lab."):
        if not mod.name.rsplit(".", 1)[-1].startswith("hip_"):
            continue
        try:
            m = importlib.import_module(mod.name)
        except Exception as e:
            achados.append({"modulo": mod.name, "erro": f"import: {e}"})
            continue
        for nome, obj in vars(m).items():
            if not (inspect.isclass(obj) and issubclass(obj, Strategy) and obj is not Strategy):
                continue
            if obj.__module__ != mod.name:
                continue  # classe base importada, nao a hipotese deste arquivo
            if inspect.isabstract(obj):
                continue
            achados.append({
                "modulo": mod.name, "classe": nome,
                "name": getattr(obj, "name", nome),
                "familia": mod.name.split(".")[2],
            })
    return achados


def _medir_e1(args: tuple[str, str, str]) -> dict:
    """E1 numa estrategia — MEDIDO AQUI, nao lido do que o agente reportou.

    O diario `trials.jsonl` que os agentes escrevem serve de sanidade deles, mas
    o ranking nao pode depender dele: o nome do ensaio que o agente passou para
    `screen()` nao casa com a classe no disco, e mais importante, um numero
    autorreportado e um numero que ninguem verificou. Remedindo tudo com a mesma
    funcao, no mesmo processo, a comparacao entre 120 hipoteses fica limpa e
    nenhuma metrica entra no ranking sem ter sido produzida aqui.
    """
    modulo, classe, familia = args
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from swing_lab.measure import screen
        cls = getattr(importlib.import_module(modulo), classe)
        s = screen(lambda: cls(), name=f"{modulo}.{classe}", family=familia,
                   note="remedido centralmente")
        s["modulo"], s["classe"], s["familia"] = modulo, classe, familia
        return s
    except Exception:
        return {"modulo": modulo, "classe": classe, "familia": familia,
                "erro": traceback.format_exc(limit=3)}


def _medir(args: tuple[str, str, str]) -> dict:
    """Roda E2 numa estrategia. Executado em processo separado."""
    modulo, classe, familia = args
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from swing_lab.measure import monthly_returns_full, select
        cls = getattr(importlib.import_module(modulo), classe)
        s = select(lambda: cls(), name=f"{modulo}.{classe}", family=familia)
        mret = monthly_returns_full(lambda: cls())
        s["monthly"] = {str(k.date()): float(v) for k, v in mret.items()}
        s["modulo"], s["classe"], s["familia"] = modulo, classe, familia
        return s
    except Exception:
        return {"modulo": modulo, "classe": classe, "familia": familia,
                "erro": traceback.format_exc(limit=3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--descobrir", action="store_true")
    ap.add_argument("--e1", action="store_true")
    ap.add_argument("--e2", action="store_true")
    ap.add_argument("--refazer-e1", dest="refazer_e1", action="store_true")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()

    achados = descobrir()
    quebrados = [x for x in achados if "erro" in x]
    validos = [x for x in achados if "erro" not in x]

    print(f"classes descobertas: {len(validos)}  |  modulos que nao importam: {len(quebrados)}")
    for q in quebrados[:5]:
        print(f"  [X] {q['modulo']}: {q['erro'][:90]}")

    if a.descobrir:
        MANIFEST.write_text(json.dumps({"descobertos": validos, "quebrados": quebrados},
                                       indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nmanifesto em {MANIFEST.relative_to(ROOT)}. Rode com --e1 para medir a triagem.")
        return

    # ------------------------------------------------------------------ E1
    if E1_OUT.exists() and not a.refazer_e1:
        e1res = json.loads(E1_OUT.read_text(encoding="utf-8"))
        print(f"E1 lido de {E1_OUT.name} ({len(e1res)} linhas). Use --refazer-e1 para remedir.")
    else:
        tarefas1 = [(v["modulo"], v["classe"], v["familia"]) for v in validos]
        print(f"\nE1: remedindo {len(tarefas1)} hipoteses (FULL + 2 janelas), {a.jobs} processos...")
        e1res = []
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(_medir_e1, t): t for t in tarefas1}
            for i, f in enumerate(as_completed(futs), 1):
                r = f.result()
                e1res.append(r)
                tag = "ERRO" if "erro" in r else (
                    f"cagr={r.get('median_cagr', float('nan')):+.4f} "
                    f"dd={r.get('worst_dd', float('nan')):+.4f} "
                    f"{'OK' if r.get('dd_gate') else 'estourou DD'}")
                print(f"  [{i}/{len(tarefas1)}] {r['classe'][:34]:<36}{tag}")
        E1_OUT.write_text(json.dumps(e1res, indent=2, ensure_ascii=False), encoding="utf-8")

    medidos = [r for r in e1res if "erro" not in r and r.get("n")]
    falhou = [r for r in e1res if "erro" in r or not r.get("n")]
    passam = [r for r in medidos if r.get("dd_gate")]
    passam.sort(key=lambda r: r["median_cagr"], reverse=True)

    print(f"\nE1: medidos {len(medidos)}  |  falharam {len(falhou)}  "
          f"|  passam o teto de DD {len(passam)}")
    escolhidos = passam[:MAX_E2]
    if len(passam) > MAX_E2:
        print(f"  CORTADOS pelo cap de {MAX_E2}: {len(passam) - MAX_E2}. O cap e do "
              f"protocolo, nao ajuste. Pior CAGR mediano admitido: "
              f"{escolhidos[-1]['median_cagr']:+.4f}")

    if not a.e2:
        print(f"\n{len(escolhidos)} prontos para E2. Rode com --e2.")
        return

    tarefas = [(v["modulo"], v["classe"], v["familia"]) for v in escolhidos]
    resultados = []
    print(f"\nmedindo {len(tarefas)} estrategias em 47 janelas, {a.jobs} processos...")
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(_medir, t): t for t in tarefas}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            resultados.append(r)
            tag = "ERRO" if "erro" in r else f"cagr={r.get('median_cagr', float('nan')):+.4f} dd={r.get('worst_dd', float('nan')):+.4f}"
            print(f"  [{i}/{len(tarefas)}] {r['classe']:<28} {tag}")

    E2_OUT.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    _relatorio(resultados)


def _relatorio(resultados: list[dict]) -> None:
    from swing_lab.deflate import deflated_sharpe, pbo_cscv, sharpe_per_obs
    from swing_lab.measure import E2_WINDOWS, ibov_window

    ok = [r for r in resultados if "erro" not in r and r.get("n_windows")]
    if not ok:
        print("\nnenhuma estrategia mediu em E2.")
        return

    # IBOV pareado janela a janela — o portao e o indice da propria run.
    ib = [ibov_window(s) for s in E2_WINDOWS]
    ib_cagr = np.median([x["cagr"] for x in ib if x])

    passam = [r for r in ok if r["dd_gate"]]
    passam.sort(key=lambda r: r["median_cagr"], reverse=True)

    print(f"\n{'='*104}")
    print(f"E2 — 10 MELHORES de {len(ok)} medidos   (IBOV mediano nas mesmas janelas: {ib_cagr:+.2%})")
    print(f"{'='*104}")
    print(f"{'#':<3}{'estrategia':<30}{'familia':<16}{'CAGR med':>10}{'excesso':>9}"
          f"{'pior DD':>9}{'pior 12m':>9}{'expos':>7}{'>IBOV':>7}")
    print("-" * 104)
    for i, r in enumerate(passam[:10], 1):
        print(f"{i:<3}{r['classe'][:29]:<30}{r['familia'][:15]:<16}"
              f"{r['median_cagr']:>9.2%}{r['median_cagr']-ib_cagr:>+9.2%}"
              f"{r['worst_dd']:>9.2%}{r['worst_12m']:>9.2%}"
              f"{r.get('median_exposure', float('nan')):>7.2f}"
              f"{r.get('beat_ibov', 0):>4}/{r.get('n_windows', 0)}")
    print("-" * 104)
    print(f"reprovados pelo teto de DD: {len(ok) - len(passam)} de {len(ok)}")

    # Matriz T x N para o CSCV, com TODOS os medidos (nao so os aprovados:
    # excluir os ruins subestima a dispersao e infla o DSR).
    series = {r["classe"]: pd.Series(r["monthly"]) for r in ok if r.get("monthly")}
    if len(series) >= 3:
        M = pd.DataFrame(series).dropna(how="all")
        M = M.loc[:, M.notna().sum() > 60].dropna()
        if M.shape[1] >= 3 and M.shape[0] >= 40:
            srs = np.array([sharpe_per_obs(M[c].to_numpy()) for c in M.columns])
            melhor = M.columns[int(np.argmax(srs))]
            d = deflated_sharpe(M[melhor].to_numpy(), srs)
            p = pbo_cscv(M.to_numpy(), s_blocos=16)
            print(f"\nDEFLACAO (matriz {M.shape[0]}x{M.shape[1]})")
            print(f"  melhor por Sharpe        : {melhor}")
            print(f"  Sharpe anual bruto       : {d.get('sr_anual', float('nan')):.3f}")
            print(f"  SR0 esperado do maximo   : {d.get('sr0_esperado_max', float('nan')):.4f}")
            print(f"  DSR                      : {d.get('dsr', float('nan')):.4f}  (nulo: mediana 0,470 / p95 0,665)")
            print(f"  PBO                      : {p.get('pbo', float('nan')):.3f}  (nulo: mediana 0,564 / p5 0,358)")
            print(f"  ensaios na deflacao      : {d.get('n_ensaios')}")
        else:
            print(f"\nDEFLACAO: matriz {M.shape} insuficiente.")

    print(f"\n>>> 3 primeiros vao ao cofre, mais 2 sinteses. Total: 5 candidatos. <<<")


if __name__ == "__main__":
    main()
