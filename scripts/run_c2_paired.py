"""C2 corrigido — exposicao pareada de verdade. Substitui o C2 de run_swing_controls.py.

O erro que este arquivo corrige
-------------------------------
A primeira versao montou a mistura como `x*campeao + (1-x)*Selic`, tratando a
curva do campeao como se fosse 100% bolsa. Nao e: o campeao roda exposicao ~0,58
e o resto do patrimonio dele JA rende Selic dentro da propria curva. Misturar com
peso x sobre essa curva da exposicao efetiva `x * x_campeao` — a 0,46 pedido,
saiu 0,27 entregue.

O efeito e sistematico e sempre no mesmo sentido: a mistura fica com menos bolsa
e mais Selic do que o pedido, a Selic nunca e negativa, e a "pior janela" da
mistura sobe artificialmente. Foi exatamente onde as 10 candidatas reprovaram —
todas ganhavam o CAGR mediano por 5 a 11 pontos e perdiam so na pior janela.

Correcao: `w = x_candidato / x_campeao`, limitado a 1,0 (sem alavancagem), de
modo que `w * x_campeao = x_candidato`. Quando o candidato tem exposicao MAIOR
que a do campeao, w bate no teto e a comparacao passa a ser contra o campeao
cheio — o que e o certo, porque nao existe como pedir mais bolsa ao campeao sem
alavancar, e registrar isso e mais honesto que fingir pareamento.

Segunda correcao, de consistencia: as candidatas foram medidas rodando o
backtest DE NOVO em cada janela (comecando de R$1.000, sem posicao). A versao
anterior cortava uma unica curva FULL do campeao em pedacos, o que mede o
campeao "ja posicionado e ja composto desde 2010" contra o candidato "comecando
do zero" — janelas diferentes de fato. Aqui o campeao roda fresco nas mesmas 47
janelas, pela mesma funcao.

O CRITERIO NAO MUDOU e continua declarado antes de medir: o candidato sobrevive
se bater a mistura de mesma exposicao em CAGR mediano E em pior janela. A
mistura segue estatica, sem rebalanceamento, o que favorece o candidato.

Uso: .venv/Scripts/python.exe scripts/run_c2_paired.py
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

from backtest.costs import cash_yield_series
from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion
from swing_lab.measure import (
    ANOS, E2_WINDOWS, FULL_END, INITIAL, SELIC_E, _exposure, panels, wide_pool,
)

E2_RES = ROOT / "scripts" / "swing_lab" / "e2_results.json"
OUT = ROOT / "scripts" / "swing_lab" / "c2_paired.json"


class CampeaoLargo(LiquidChampion):
    """O campeao no MESMO pool largo dos candidatos — a referencia da busca."""

    name = "campeao_largo"
    candidate = False
    universe_tickers = tuple(wide_pool())


def _metricas(eq: pd.Series) -> dict | None:
    if len(eq) < 250:
        return None
    anos = (eq.index[-1] - eq.index[0]).days / 365.25
    tot = eq.iloc[-1] / eq.iloc[0]
    return {
        "cagr": float(tot ** (1.0 / anos) - 1.0) if anos > 0 and tot > 0 else -1.0,
        "dd": float(max_drawdown(eq)),
        "w12": float((eq / eq.shift(252) - 1.0).min()),
    }


def campeao_por_janela() -> tuple[list[pd.Series], float]:
    """Roda o campeao fresco em cada janela de E2. Devolve curvas e exposicao mediana."""
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC_E)
    p = panels()
    curvas, expos = [], []
    for i, s in enumerate(E2_WINDOWS, 1):
        e = min(s + pd.DateOffset(years=ANOS), pd.Timestamp(FULL_END))
        r = run_bt(p, CampeaoLargo(), cfg, start=str(s.date()), end=str(e.date()))
        if len(r.equity_curve) < 250:
            continue
        curvas.append(r.equity_curve)
        expos.append(_exposure(r))
        print(f"  campeao [{i}/{len(E2_WINDOWS)}] {s.date()} expos={expos[-1]:.3f}")
    return curvas, float(np.nanmedian(expos))


def mistura(eq: pd.Series, w: float, selic: pd.Series) -> pd.Series:
    """`w` no campeao e `1-w` na Selic, peso fixo, sem rebalancear."""
    r = w * eq.pct_change().fillna(0.0) + (1.0 - w) * selic.reindex(eq.index).fillna(0.0)
    return INITIAL * (1.0 + r).cumprod()


def resume(linhas: list[dict]) -> dict:
    return {
        "median_cagr": float(np.median([x["cagr"] for x in linhas])),
        "worst_cagr": float(min(x["cagr"] for x in linhas)),
        "worst_dd": float(min(x["dd"] for x in linhas)),
        "worst_12m": float(min(x["w12"] for x in linhas)),
        "n": len(linhas),
    }


def main() -> None:
    res = json.loads(E2_RES.read_text(encoding="utf-8"))
    ok = [r for r in res if "erro" not in r and r.get("dd_gate") and r.get("n_windows")]
    ok.sort(key=lambda r: r["median_cagr"], reverse=True)
    alvos = ok[:10]

    print("rodando o campeao fresco nas 47 janelas (referencia da exposicao)...")
    curvas, x_ref = campeao_por_janela()
    base = resume([m for m in (_metricas(c) for c in curvas) if m])
    print(f"\ncampeao largo: exposicao mediana {x_ref:.3f} | CAGR mediano "
          f"{base['median_cagr']:+.2%} | pior janela {base['worst_cagr']:+.2%} "
          f"| pior DD {base['worst_dd']:+.2%}")

    selics = {id(c): cash_yield_series(SELIC_E, c.index) for c in curvas}

    saida = []
    print(f"\n{'='*126}")
    print("C2 CORRIGIDO — candidato vs campeao diluido a MESMA exposicao efetiva")
    print(f"{'='*126}")
    print(f"{'candidato':<30}{'x_cand':>7}{'w':>6}{'CAGR cand':>11}{'CAGR mix':>10}"
          f"{'pior cand':>11}{'pior mix':>10}{'DD cand':>9}{'DD mix':>9}{'veredito':>15}")
    print("-" * 126)
    for r in alvos:
        x_c = r.get("median_exposure")
        if x_c is None or not np.isfinite(x_c) or x_c <= 0:
            print(f"{r['classe'][:29]:<30}  exposicao indisponivel — C2 nao conclui")
            continue
        w = float(min(x_c / x_ref, 1.0))
        linhas = [m for m in (_metricas(mistura(c, w, selics[id(c)])) for c in curvas) if m]
        mix = resume(linhas)
        venceu = (r["median_cagr"] > mix["median_cagr"]
                  and r["worst_cagr"] > mix["worst_cagr"])
        teto = "*" if x_c / x_ref > 1.0 else ""
        vd = ("sobrevive" if venceu else "caixa parado") + teto
        saida.append({"classe": r["classe"], "familia": r["familia"],
                      "x_cand": float(x_c), "w": w, "w_no_teto": bool(teto),
                      "candidato": {k: r[k] for k in
                                    ("median_cagr", "worst_cagr", "worst_dd", "worst_12m")},
                      "mistura": mix, "sobrevive_c2": venceu})
        print(f"{r['classe'][:29]:<30}{x_c:>7.2f}{w:>6.2f}{r['median_cagr']:>11.2%}"
              f"{mix['median_cagr']:>10.2%}{r['worst_cagr']:>11.2%}{mix['worst_cagr']:>10.2%}"
              f"{r['worst_dd']:>9.2%}{mix['worst_dd']:>9.2%}{vd:>15}")
    print("-" * 126)
    print(f"sobrevivem a C2: {sum(1 for s in saida if s['sobrevive_c2'])} de {len(saida)}")
    print("* w bateu o teto de 1,0: candidato mais exposto que o campeao, comparacao "
          "contra o campeao cheio.")
    print("A mistura e estatica (sem rebalancear), o que FAVORECE o candidato.")

    OUT.write_text(json.dumps({"campeao_largo": base, "x_campeao": x_ref,
                               "candidatos": saida}, indent=2, ensure_ascii=False),
                   encoding="utf-8")


if __name__ == "__main__":
    main()
