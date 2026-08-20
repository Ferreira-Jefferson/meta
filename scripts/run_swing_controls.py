"""Controle C2 — exposicao pareada. Obrigatorio antes de qualquer veredito.

A pergunta que este controle responde
-------------------------------------
Um candidato com MaxDD melhor que o campeao pode ter conseguido isso de duas
formas muito diferentes: por DESENHO (escolhe melhor, diversifica melhor) ou
por simplesmente ficar menos tempo na bolsa. A segunda nao vale nada, porque
qualquer pessoa consegue de graca deixando parte do dinheiro no CDI — sem robo,
sem risco de execucao, sem imposto de trade.

Este projeto ja errou exatamente aqui uma vez: k=10 sleeves mostrou MaxDD
-19,9% contra -36,7% e parecia uma melhoria enorme, mas a exposicao media caia
de 72,7% para 40,3% e uma mistura estatica de k=5 com Selic na MESMA exposicao
ganhava em retorno, pior janela e pior 12 meses.

A triagem desta busca acendeu a luz vermelha de novo: as primeiras hipoteses de
baixa volatilidade medidas apresentaram exposicao de 0,20 a 0,45 contra 0,585 do
campeao na mesma janela. Sem este controle, a familia inteira passaria por
merito que nao tem.

O metodo
--------
Para cada candidato mede-se a exposicao media `x`. Constroi-se a mistura
estatica `x` no CAMPEAO (mesmo pool largo, mesma aritmetica) e `1-x` na Selic
diaria, e comparam-se as duas nas MESMAS janelas de E2.

A mistura e ESTATICA, sem rebalanceamento, e isso FAVORECE o candidato: uma
mistura rebalanceada teria risco um pouco menor. Logo um empate ja e resultado
ruim para o candidato.

Criterio, declarado antes: o candidato sobrevive a C2 se bater a mistura de
mesma exposicao em CAGR mediano E em pior janela. Se perder em qualquer um dos
dois, o ganho de risco dele e caixa parado, nao desenho.

Uso: .venv/Scripts/python.exe scripts/run_swing_controls.py --c2
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd

from backtest.costs import cash_yield_series
from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion
from swing_lab.measure import (
    E2_WINDOWS, FULL_END, FULL_START, INITIAL, SELIC_E, panels, wide_pool,
)

E2_RES = ROOT / "scripts" / "swing_lab" / "e2_results.json"
OUT = ROOT / "scripts" / "swing_lab" / "c2_results.json"


class CampeaoLargo(LiquidChampion):
    """O campeao no MESMO pool largo dos candidatos. A referencia da busca.

    Nao sao os numeros publicados do campeao: aqueles vem do pool de 63 nomes de
    `data/raw/`, que e survivorship-selected e mais generoso. Comparar candidato
    do pool largo com campeao do pool estreito mediria a diferenca de pool, nao
    a diferenca de desenho.
    """

    name = "campeao_largo"
    candidate = False
    universe_tickers = tuple(wide_pool())


def _curva(factory, start: str, end: str) -> pd.Series:
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC_E)
    return run_bt(panels(), factory(), cfg, start=start, end=end).equity_curve


def _metricas(eq: pd.Series) -> dict:
    if len(eq) < 250:
        return {}
    anos = (eq.index[-1] - eq.index[0]).days / 365.25
    tot = eq.iloc[-1] / eq.iloc[0]
    return {
        "cagr": float(tot ** (1.0 / anos) - 1.0) if anos > 0 and tot > 0 else -1.0,
        "dd": float(max_drawdown(eq)),
        "w12": float((eq / eq.shift(252) - 1.0).min()),
    }


def mistura_estatica(campeao: pd.Series, x: float) -> pd.Series:
    """Curva de `x` no campeao e `1-x` na Selic, peso fixo, sem rebalancear."""
    selic = cash_yield_series(SELIC_E, campeao.index)
    if selic is None:
        raise RuntimeError(f"Selic nao carregou de {SELIC_E}")
    r_acao = campeao.pct_change().fillna(0.0)
    r_mix = x * r_acao + (1.0 - x) * selic.reindex(campeao.index).fillna(0.0)
    return INITIAL * (1.0 + r_mix).cumprod()


def por_janelas(curva: pd.Series) -> dict:
    linhas = []
    for s in E2_WINDOWS:
        e = min(s + pd.DateOffset(years=5), pd.Timestamp(FULL_END))
        m = _metricas(curva.loc[str(s.date()):str(e.date())])
        if m:
            linhas.append(m)
    if not linhas:
        return {}
    return {
        "median_cagr": float(np.median([r["cagr"] for r in linhas])),
        "worst_cagr": float(min(r["cagr"] for r in linhas)),
        "worst_dd": float(min(r["dd"] for r in linhas)),
        "worst_12m": float(min(r["w12"] for r in linhas)),
        "n": len(linhas),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c2", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    if not E2_RES.exists():
        print(f"{E2_RES.name} nao existe. Rode scripts/run_e2_select.py --e1 --e2 primeiro.")
        return

    res = json.loads(E2_RES.read_text(encoding="utf-8"))
    ok = [r for r in res if "erro" not in r and r.get("dd_gate") and r.get("n_windows")]
    ok.sort(key=lambda r: r["median_cagr"], reverse=True)
    alvos = ok[:a.top]
    if not alvos:
        print("nenhum candidato passou o teto de DD em E2 — C2 nao se aplica.")
        return

    print("medindo a curva FULL do campeao no pool largo (referencia)...")
    campeao = _curva(lambda: CampeaoLargo(), FULL_START, FULL_END)
    base = por_janelas(campeao)
    print(f"campeao largo: CAGR mediano {base['median_cagr']:+.2%}  "
          f"pior janela {base['worst_cagr']:+.2%}  pior DD {base['worst_dd']:+.2%}")

    saida = []
    print(f"\n{'='*118}")
    print("C2 — EXPOSICAO PAREADA: candidato vs mistura estatica campeao+Selic de MESMA exposicao")
    print(f"{'='*118}")
    print(f"{'candidato':<30}{'expos':>7}{'CAGR cand':>11}{'CAGR mix':>10}"
          f"{'pior cand':>11}{'pior mix':>10}{'DD cand':>9}{'DD mix':>9}{'veredito':>14}")
    print("-" * 118)
    for r in alvos:
        x = r.get("median_exposure")
        if x is None or not np.isfinite(x) or x <= 0:
            print(f"{r['classe'][:29]:<30}{'s/exp':>7}  exposicao indisponivel — C2 nao conclui")
            continue
        x = float(min(max(x, 0.01), 1.0))
        mix = por_janelas(mistura_estatica(campeao, x))
        venceu = (r["median_cagr"] > mix["median_cagr"]
                  and r["worst_cagr"] > mix["worst_cagr"])
        vd = "sobrevive" if venceu else "caixa parado"
        saida.append({"classe": r["classe"], "familia": r["familia"], "exposicao": x,
                      "candidato": {k: r[k] for k in ("median_cagr", "worst_cagr", "worst_dd", "worst_12m")},
                      "mistura": mix, "sobrevive_c2": venceu})
        print(f"{r['classe'][:29]:<30}{x:>7.2f}{r['median_cagr']:>11.2%}{mix['median_cagr']:>10.2%}"
              f"{r['worst_cagr']:>11.2%}{mix['worst_cagr']:>10.2%}"
              f"{r['worst_dd']:>9.2%}{mix['worst_dd']:>9.2%}{vd:>14}")
    print("-" * 118)
    print(f"sobrevivem a C2: {sum(1 for s in saida if s['sobrevive_c2'])} de {len(saida)}")
    print("\nA mistura e estatica (sem rebalancear), o que FAVORECE o candidato.")
    print("Empate ja e resultado ruim para o candidato.")

    OUT.write_text(json.dumps({"campeao_largo": base, "candidatos": saida},
                              indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
