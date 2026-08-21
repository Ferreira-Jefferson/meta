"""H3 — as empresas da watchlist se ADAPTAM a estrategia, ou era so hindsight?

A pergunta
----------
A watchlist oficial de sete papeis foi escolhida em 2026 maximizando 2010-2026, e
`run_champion_counterfactual.py` mostrou que sem esse privilegio o capital cai de
R$ 70 mil para R$ 3,7-5,5 mil. A conclusao registrada foi "era hindsight".

Mas isso NAO fecha a questao levantada agora: pode existir uma caracteristica
real e persistente nessas empresas — uma tendencia limpa, pouco ruido, momentum
que nao reverte — que faca elas responderem bem a ESTA estrategia
especificamente. Se existir, ela e detectavel sem saber o futuro, e a watchlist
deixaria de ser sorte para virar sinal.

Protocolo, declarado antes de rodar
-----------------------------------
Se a caracteristica for real, ela e PERSISTENTE: uma empresa que se adapta bem a
estrategia se adapta nas duas metades do historico, independentemente. Se for
hindsight, a empresa vai bem so na metade que alimentou a escolha de 2026 — que
sao as duas, o que exige o cuidado abaixo.

Rodo a estrategia do campeao em CADA papel do pool, isoladamente, em duas
metades que nao se sobrepoem:

  metade A   2010-01-01 a 2017-12-31
  metade B   2018-01-01 a 2026-08-18

e comparo os DOIS RANKINGS. Tres medidas, todas declaradas agora:

  1. correlacao de Spearman entre o ranking de A e o de B. Alta = a
     caracteristica persiste; perto de zero = o desempenho de um papel numa
     metade nao diz nada sobre a outra, e "empresa boa para a estrategia" nao
     existe como propriedade estavel.
  2. sobreposicao dos top-7 de cada metade. Se as duas metades elegem gente
     diferente, escolher pelo passado nao ajuda.
  3. onde a WATCHLIST OFICIAL aparece em cada ranking. Este e o teste decisivo
     da hipotese: se WEGE3 e companhia estao no topo das DUAS metades, ha algo
     real nelas. Se estao no topo de uma so, foi a metade que a selecao de 2026
     enxergou melhor.

Criterio de decisao, escrito antes do resultado: a hipotese sobrevive se a
correlacao de Spearman for >= 0,30 E a watchlist oficial tiver rank mediano
melhor que a mediana do pool nas DUAS metades. Se passar so numa, e hindsight
com verniz. Se a correlacao for negativa, e reversao — o oposto da hipotese.

Vies residual declarado: o pool vem de `data/raw/`, que so tem empresas vivas
em 2026. Quem quebrou entre 2010 e hoje nao esta aqui, e isso favorece as duas
metades igualmente — nao muda a comparacao ENTRE elas, que e o que este script
mede.

Uso: .venv/Scripts/python.exe scripts/run_hypothesis_company_fit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

import run_walk_forward as wf

from backtest.runner import run as run_bt
from core.config import BENCHMARK, WATCHLIST, BacktestConfig
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

SELIC = "data/raw/selic.parquet"
INITIAL = 1000.0
METADES = [("A", "2010-01-01", "2017-12-31"), ("B", "2018-01-01", "2026-08-18")]


def cfg() -> BacktestConfig:
    return BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC)


def um_papel(ticker: str, start: str, end: str, bench) -> float | None:
    """Capital final da estrategia operando SO este papel, nesta metade.

    Papel isolado, e nao carteira, de proposito: a pergunta e sobre a EMPRESA
    se adaptar a estrategia. Medir em carteira misturaria a resposta com
    interacao entre papeis e com a ordem em que a busca greedy os encontra.
    """
    try:
        universe = {ticker: wf.panel(ticker), BENCHMARK: bench}
        r = run_bt(universe, DipTop1Portfolio(), cfg(), start=start, end=end)
        return float(r.metrics["final_capital"])
    except Exception:
        return None


def main() -> None:
    bench = wf.panel(BENCHMARK)
    pool = wf.candidate_pool(0.0, "2026-08-18")
    print(f"\nH3 — adaptacao das empresas a estrategia")
    print(f"pool: {len(pool)} papeis com historico completo 2010-2026\n")

    resultados: dict[str, dict[str, float]] = {}
    for nome, ini, fim in METADES:
        print(f"metade {nome} ({ini[:7]} a {fim[:7]})...", flush=True)
        col = {}
        for i, t in enumerate(pool, 1):
            v = um_papel(t, ini, fim, bench)
            if v is not None:
                col[t] = v
            if i % 15 == 0:
                print(f"  {i}/{len(pool)}", flush=True)
        resultados[nome] = col
        print(f"  {len(col)} papeis medidos\n", flush=True)

    comuns = sorted(set(resultados["A"]) & set(resultados["B"]))
    a = pd.Series({t: resultados["A"][t] for t in comuns})
    b = pd.Series({t: resultados["B"][t] for t in comuns})
    ra = a.rank(ascending=False)
    rb = b.rank(ascending=False)
    # Pearson SOBRE OS RANKS e a definicao de Spearman — evita a dependencia
    # de scipy, que nao esta instalada neste ambiente.
    rho = float(ra.corr(rb))

    top_a = set(a.sort_values(ascending=False).head(7).index)
    top_b = set(b.sort_values(ascending=False).head(7).index)
    oficial = [t for t in WATCHLIST if t in comuns]

    print(f"{'=' * 88}\nRESULTADO — {len(comuns)} papeis nas duas metades\n{'=' * 88}")
    print(f"\n1. correlacao de Spearman entre os rankings das duas metades: {rho:+.3f}")
    print(f"\n2. sobreposicao dos top-7: {len(top_a & top_b)} de 7")
    print(f"   metade A: {sorted(t.replace('.SA','') for t in top_a)}")
    print(f"   metade B: {sorted(t.replace('.SA','') for t in top_b)}")

    n = len(comuns)
    print(f"\n3. onde a watchlist oficial aparece (rank de {n}; menor = melhor)")
    print(f"   {'papel':10s} {'rank A':>8s} {'rank B':>8s} {'cap A':>12s} {'cap B':>12s}")
    for t in oficial:
        print(f"   {t.replace('.SA',''):10s} {int(ra[t]):>8d} {int(rb[t]):>8d} "
              f"R$ {a[t]:>9,.0f} R$ {b[t]:>9,.0f}")
    med_a = float(np.median([ra[t] for t in oficial]))
    med_b = float(np.median([rb[t] for t in oficial]))
    print(f"   {'MEDIANA':10s} {med_a:>8.1f} {med_b:>8.1f}")
    print(f"   mediana do pool inteiro: {(n + 1) / 2:.1f} nas duas metades, por construcao")

    passa_rho = rho >= 0.30
    passa_a = med_a < (n + 1) / 2
    passa_b = med_b < (n + 1) / 2
    print(f"\n{'=' * 88}\nCRITERIO DECLARADO ANTES DE RODAR\n{'=' * 88}")
    print(f"  Spearman >= 0,30 .................. {rho:+.3f}  -> {'SIM' if passa_rho else 'NAO'}")
    print(f"  watchlist melhor que a mediana em A  {med_a:.1f} < {(n+1)/2:.1f}  -> {'SIM' if passa_a else 'NAO'}")
    print(f"  watchlist melhor que a mediana em B  {med_b:.1f} < {(n+1)/2:.1f}  -> {'SIM' if passa_b else 'NAO'}")
    if passa_rho and passa_a and passa_b:
        veredito = "HIPOTESE SOBREVIVE — ha caracteristica persistente"
    elif passa_a != passa_b:
        veredito = "HINDSIGHT COM VERNIZ — a watchlist so vai bem numa das metades"
    elif rho < 0:
        veredito = "REVERSAO — o oposto da hipotese"
    else:
        veredito = "HIPOTESE REFUTADA"
    print(f"\n  {veredito}")


if __name__ == "__main__":
    main()
