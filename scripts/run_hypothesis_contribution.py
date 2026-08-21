"""H1 — e se em vez de R$ 1.000 parados houver R$ 100 por mes entrando?

A pergunta
----------
Todo numero deste projeto foi medido numa conta FECHADA: R$ 1.000 no dia zero e
mais nada. Isso nao e como ninguem investe. Com R$ 100 por mes ao longo de 16
anos entram R$ 19.900 de dinheiro novo contra R$ 1.000 de capital inicial — o
aporte passa a ser 95% do dinheiro, e a composicao do robo deixa de ser a parte
principal da historia.

Duas coisas mudam, e elas sao independentes:

  1. RETORNO. `cagr` sobre a curva de patrimonio deixa de significar qualquer
     coisa (dinheiro novo empurra a curva para cima sem nada ter rendido). As
     medidas honestas passam a ser a COTA — patrimonio dividido por cotas, onde
     cada aporte compra cotas ao valor do dia — e a TIR, que e o que o dono
     efetivamente ganhou sobre o dinheiro que colocou, quando colocou.
  2. VIABILIDADE. O campeao quer cinco posicoes simultaneas e o lote minimo na
     corretora e de 100 acoes. Com R$ 1.000 e lote 100 ele nao compra nada; a
     medicao oficial usa `lot_size=1`, que e uma ficcao conveniente. Com aporte
     a conta cresce e em algum momento passa a caber em lotes. QUANDO?

Protocolo, declarado antes de rodar
-----------------------------------
PARTE 1 — retorno, nivel 3 do protocolo (48 janelas do holdout, pareado).
Mesmas 48 janelas de 5 anos com inicio mensal 2010-01 a 2013-12. Tres bracos:

  fechada        R$ 1.000, sem aporte (a referencia de todo o diario)
  aporte 100     R$ 1.000 + R$ 100 no primeiro pregao de cada mes
  IBOV com aporte  os MESMOS fluxos comprando indice — este e o benchmark
                 correto para uma conta que aporta, e nao o IBOV comprado de
                 uma vez. Comparar uma conta que faz preco medio contra um
                 indice comprado a vista seria trocar duas variaveis.

Criterio declarado agora: o aporte MELHORA a estrategia se a TIR mediana com
aporte ficar acima da TIR mediana do IBOV com os mesmos fluxos, em maioria das
48 janelas. E o aporte nao PIORA a estrategia se a cota (CAGR e MaxDD) ficar
estatisticamente igual a da conta fechada — a cota tem de ser quase identica por
construcao, e uma divergencia grande aqui e sinal de que o dinheiro novo esta
mudando as decisoes (via `size_hint`, que e fracao do caixa), nao de que o
aporte "rende mais".

PARTE 2 — viabilidade, janela FULL, `lot_size=100` (o lote real da corretora).
Bracos de R$ 0, R$ 100 e R$ 500 por mes. A pergunta nao e retorno, e se a conta
consegue existir: quantos trades acontecem, e quanto tempo leva para o
patrimonio passar dos ~R$ 25 mil que os cinco sleeves exigem para caber em
lotes.

Vies residual declarado: aporte de valor NOMINAL fixo em 16 anos de inflacao
brasileira nao e um aporte real constante — R$ 100 de 2010 valem mais que R$ 100
de 2026. O teste mede o que o dono faria (deposita 100 por mes), nao poder de
compra constante. Corrigir por IPCA mudaria a resposta da Parte 2 (a conta
cresceria mais rapido no comeco) e quase nada na Parte 1.

Uso: .venv/Scripts/python.exe scripts/run_hypothesis_contribution.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

import run_holdout_frozen as hf

from backtest.metrics import cagr, irr_annual, max_drawdown
from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from strategy.liquid_champion import LiquidChampion

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
ANOS = 5
APORTE = 100.0
FIM_FULL = "2026-08-18"


def cfg(aporte: float, lote: int = 1) -> BacktestConfig:
    return BacktestConfig(initial_capital=INITIAL, lot_size=lote,
                          cash_yield_path=SELIC, monthly_contribution=aporte)


def robo(u, start: pd.Timestamp, end: pd.Timestamp, aporte: float, lote: int = 1) -> dict | None:
    r = run_bt(u, LiquidChampion(), cfg(aporte, lote),
               start=str(start.date()), end=str(end.date()))
    eq = r.equity_curve
    if len(eq) < 250:
        return None
    cota = r.unit_curve if r.unit_curve is not None and len(r.unit_curve) else eq
    return {
        "final": float(eq.iloc[-1]),
        "aportado": float(r.metrics.get("contributed_total", 0.0)),
        "irr": float(r.metrics.get("irr", r.metrics["cagr"])),
        "cagr_cota": float(r.metrics.get("cagr_unit", r.metrics["cagr"])),
        "dd_cota": float(r.metrics.get("max_drawdown_unit", r.metrics["max_drawdown"])),
        "trades": len(r.trades),
    }


def ibov_com_aporte(start: pd.Timestamp, end: pd.Timestamp, aporte: float) -> dict:
    """Compra indice com os MESMOS fluxos: R$ 1.000 no dia 1 e R$ 100 por mes.

    Sem lote e sem custo, de proposito — e o benchmark mais GENEROSO possivel
    para o indice. Se o robo ganhar deste, ganhou da versao facil do adversario.
    """
    c = hf.panel(BENCHMARK)["close"].loc[str(start.date()):str(end.date())].dropna()
    if len(c) < 250:
        return {}
    cotas = INITIAL / float(c.iloc[0])
    fluxos: list[tuple[object, float]] = [(c.index[0].date(), -INITIAL)]
    mes_ant = (c.index[0].year, c.index[0].month)
    valores = []
    for d, px in c.items():
        mes = (d.year, d.month)
        if aporte > 0 and mes != mes_ant:
            cotas += aporte / float(px)
            fluxos.append((d.date(), -aporte))
        mes_ant = mes
        valores.append(cotas * float(px))
    serie = pd.Series(valores, index=c.index)
    # A "cota" do indice e o proprio preco normalizado: o indice nao tem caixa
    # nem decisao, entao patrimonio/cotas e exatamente o preco.
    preco_norm = c / float(c.iloc[0]) * INITIAL
    fluxos.append((c.index[-1].date(), float(serie.iloc[-1])))
    return {
        "final": float(serie.iloc[-1]),
        "aportado": float(sum(-v for _, v in fluxos[1:-1])),
        "irr": irr_annual(fluxos),
        "cagr_cota": cagr(preco_norm),
        "dd_cota": max_drawdown(preco_norm),
        "trades": 0,
    }


def resumo(nome: str, rows: list[dict]) -> None:
    if not rows:
        print(f"{nome:22s} sem janelas validas")
        return
    g = lambda k: np.array([r[k] for r in rows])
    print(f"{nome:22s} {len(rows):3d} "
          f"R$ {np.median(g('final')):>9,.0f} "
          f"R$ {np.median(g('aportado')):>8,.0f} "
          f"{np.median(g('irr')) * 100:>7.2f}% "
          f"{np.percentile(g('irr'), 5) * 100:>7.2f}% "
          f"{np.median(g('cagr_cota')) * 100:>8.2f}% "
          f"{min(g('dd_cota')) * 100:>8.1f}% "
          f"{int((g('irr') < 0).sum()):>4d}", flush=True)


def main() -> None:
    print("\ncarregando paineis...", flush=True)
    u = hf.full_panels()

    print(f"\n{'=' * 116}")
    print("PARTE 1 — RETORNO. 48 janelas de 5 anos, inicio mensal 2010-01 a 2013-12, lote 1")
    print(f"{'=' * 116}")
    print(f"{'braco':22s} {'n':>3s} {'patrim.med':>12s} {'aportado':>11s} "
          f"{'TIR med':>8s} {'TIR p05':>8s} {'CAGR cota':>9s} {'DD cota':>9s} {'TIR<0':>5s}")

    linhas: dict[str, list[dict]] = {"fechada": [], "aporte": [], "ibov": []}
    for s in hf.HOLDOUT:
        end = s + pd.DateOffset(years=ANOS)
        for chave, ap in (("fechada", 0.0), ("aporte", APORTE)):
            m = robo(u, s, end, ap)
            if m:
                linhas[chave].append(m)
        ib = ibov_com_aporte(s, end, APORTE)
        if ib:
            linhas["ibov"].append(ib)

    resumo("robo, conta fechada", linhas["fechada"])
    resumo(f"robo, aporte {APORTE:.0f}/mes", linhas["aporte"])
    resumo(f"IBOV, aporte {APORTE:.0f}/mes", linhas["ibov"])

    # pareamento janela a janela
    n = min(len(linhas["aporte"]), len(linhas["ibov"]))
    bate = sum(1 for i in range(n) if linhas["aporte"][i]["irr"] > linhas["ibov"][i]["irr"])
    med_r = float(np.median([r["irr"] for r in linhas["aporte"]]))
    med_i = float(np.median([r["irr"] for r in linhas["ibov"]]))
    print(f"\ncriterio declarado antes de rodar:")
    print(f"  TIR mediana do robo acima do IBOV com os mesmos fluxos: "
          f"{med_r*100:.2f}% vs {med_i*100:.2f}% -> {'SIM' if med_r > med_i else 'NAO'}")
    print(f"  bate o IBOV-com-aporte na maioria das janelas: {bate}/{n} -> "
          f"{'SIM' if bate > n / 2 else 'NAO'}")

    cf = float(np.median([r["cagr_cota"] for r in linhas["fechada"]]))
    ca = float(np.median([r["cagr_cota"] for r in linhas["aporte"]]))
    print(f"  cota quase identica a da conta fechada (esperado por construcao): "
          f"{cf*100:.2f}% vs {ca*100:.2f}%  (delta {abs(ca-cf)*100:.2f} p.p.)")

    print(f"\n{'=' * 116}")
    print(f"PARTE 2 — VIABILIDADE. FULL 2010-{FIM_FULL[:4]}, lote 100 (o lote real da corretora)")
    print(f"{'=' * 116}")
    print(f"{'braco':22s} {'patrimonio':>13s} {'aportado':>11s} {'TIR':>8s} "
          f"{'trades':>7s} {'1o mes >=25k':>13s}")
    inicio = pd.Timestamp("2010-01-01")
    for ap in (0.0, 100.0, 500.0):
        r = run_bt(u, LiquidChampion(), cfg(ap, lote=100),
                   start=str(inicio.date()), end=FIM_FULL)
        eq = r.equity_curve
        acima = eq[eq >= 25_000]
        quando = str(acima.index[0].date()) if len(acima) else "nunca"
        print(f"{'aporte ' + format(ap, '.0f') + '/mes':22s} "
              f"R$ {float(eq.iloc[-1]):>10,.0f} "
              f"R$ {r.metrics.get('contributed_total', 0.0):>8,.0f} "
              f"{r.metrics.get('irr', r.metrics['cagr']) * 100:>7.2f}% "
              f"{len(r.trades):>7d} {quando:>13s}", flush=True)
    print("\nlote 100 e o real: com pouco dinheiro os cinco sleeves nao cabem e o robo")
    print("opera distorcido — a coluna de trades mostra o tamanho da distorcao.")


if __name__ == "__main__":
    main()
