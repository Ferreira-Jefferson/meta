"""Quanto o campeao ANTIGO teria pago de verdade, para quem nao sabia o futuro.

A pergunta pratica
------------------
"O que justifica sair de uma estrategia que paga R$ 240 mil para uma que paga
R$ 4,9 mil?" A resposta so vale se for um numero, nao um argumento. Os R$ 240
mil existem porque a watchlist de sete tickers foi escolhida em 2026 maximizando
o capital de 2010-2026 — quem operasse em 2014 nao tinha essa lista. Este script
mede o que ele teria pago com a lista que era possivel montar NA EPOCA.

Tres versoes do MESMO robo, mesma janela, mesmas regras de sinal:

  contaminada    a watchlist oficial de 2026 (o numero do diario)
  escolhida 1x   a mesma busca greedy, rodada so com dado ate 2013-12-31,
                 e depois operada sem nunca mais mexer — que e como a lista
                 oficial foi construida: uma vez, e congelada
  reescolhida    a mesma busca refeita a cada 4 anos, sempre so com dado
                 passado — controle para o resultado nao depender de um unico
                 momento de escolha infeliz

E as referencias: o campeao NOVO na mesma janela, e o IBOV.

A diferenca entre a primeira linha e as duas seguintes e o tamanho do gabarito.

Vies residual declarado: o pool de candidatos sai de `data/raw/`, que so tem
empresas vivas em 2026. Quem saiu da bolsa entre 2010 e hoje nao esta la, e isso
empurra para CIMA tambem as versoes honestas — o gabarito real e maior que o
medido aqui, nao menor.

Uso: .venv/Scripts/python.exe scripts/run_champion_counterfactual.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import run_walk_forward as wf

from backtest.metrics import negative_years
from backtest.runner import run as run_bt
from core.config import BENCHMARK, WATCHLIST, BacktestConfig
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_sleeve import POOL
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
TARGET_N = 7  # o mesmo tamanho da WATCHLIST oficial
INICIO = "2014-01-01"
FIM = "2026-08-18"
# Corte da primeira escolha: quatro anos de dado (2010-2013) e o minimo para a
# busca greedy ter o que ranquear sem ja estar olhando a janela de operacao.
CORTE_1 = "2013-12-31"
SEGMENTOS = [("2014-01-01", "2017-12-31"), ("2018-01-01", "2021-12-31"),
             ("2022-01-01", FIM)]


def cfg(capital: float) -> BacktestConfig:
    return BacktestConfig(initial_capital=capital, lot_size=1, cash_yield_path=SELIC)


def rodar(tickers, start, end, capital, bot=None) -> dict:
    universe = {t: wf.panel(t) for t in tickers}
    universe[BENCHMARK] = wf.panel(BENCHMARK)
    r = run_bt(universe, bot or DipTop1Portfolio(), cfg(capital), start=start, end=end)
    return {"final": float(r.metrics["final_capital"]),
            "cagr": float(r.metrics["cagr"]),
            "dd": float(r.metrics["max_drawdown"]),
            "neg": negative_years(r.equity_curve),
            "trades": len(r.trades),
            "curva": r.equity_curve}


def encadeado(cortes_e_segmentos) -> dict:
    """Opera segmento a segmento, reescolhendo a watchlist so com dado passado.

    O capital do fim de um segmento e o inicio do proximo — e isso que faz o
    numero ser comparavel com o R$ 240 mil, que tambem e composto. Medir cada
    segmento com R$ 1.000 zerado e depois somar seria outra coisa.
    """
    capital, dds, negs, trades = INITIAL, [], 0, 0
    curvas = []
    for corte, (ini, fim) in cortes_e_segmentos:
        pool = wf.candidate_pool(0.0, corte)
        print(f"  escolhendo com dado ate {corte} ({len(pool)} candidatos)...", flush=True)
        tickers, _ = wf.greedy_select(pool, "2010-01-01", corte, TARGET_N)
        print(f"    -> {[t.replace('.SA','') for t in tickers]}", flush=True)
        m = rodar(tickers, ini, fim, capital)
        print(f"    {ini[:4]}-{fim[:4]}: R$ {capital:,.0f} -> R$ {m['final']:,.0f} "
              f"(CAGR {m['cagr']*100:.2f}%)", flush=True)
        capital = m["final"]
        dds.append(m["dd"]); negs += m["neg"]; trades += m["trades"]
        curvas.append(m["curva"])
    eq = pd.concat(curvas)
    return {"final": capital, "dd": float((eq / eq.cummax() - 1).min()),
            "neg": negs, "trades": trades,
            "cagr": (capital / INITIAL) ** (365.25 / (pd.Timestamp(FIM) - pd.Timestamp(INICIO)).days) - 1}


def linha(nome: str, m: dict) -> str:
    return (f"  {nome:38s} R$ {m['final']:>11,.0f}  CAGR {m['cagr']*100:>6.2f}%  "
            f"MaxDD {m['dd']*100:>6.1f}%  anos neg {m['neg']:>2d}  trades {m['trades']:>4d}")


def main() -> None:
    print(f"\nCONTRAFACTUAL DO CAMPEAO ANTIGO — {INICIO} a {FIM}, R$ {INITIAL:,.0f} iniciais")
    print("caixa remunerado na Selic em todas as linhas\n")

    print("[1/3] watchlist oficial de 2026 (contaminada) — o numero do diario")
    contaminada = rodar(list(WATCHLIST), INICIO, FIM, INITIAL)
    print(linha("contaminada (watchlist de 2026)", contaminada), flush=True)

    print("\n[2/3] escolhida UMA vez com dado ate 2013-12-31, depois congelada")
    uma_vez = encadeado([(CORTE_1, (INICIO, FIM))])

    print("\n[3/3] reescolhida a cada 4 anos, sempre so com dado passado")
    rolante = encadeado([
        (CORTE_1, SEGMENTOS[0]),
        ("2017-12-31", SEGMENTOS[1]),
        ("2021-12-31", SEGMENTOS[2]),
    ])

    print("\nreferencias na mesma janela")
    novo = rodar(list(POOL), INICIO, FIM, INITIAL, bot=LiquidChampion())
    c = wf.panel(BENCHMARK)["close"].loc[INICIO:FIM].dropna()
    anos = (c.index[-1] - c.index[0]).days / 365.25
    ibov = {"final": INITIAL * float(c.iloc[-1] / c.iloc[0]),
            "cagr": float((c.iloc[-1] / c.iloc[0]) ** (1 / anos) - 1),
            "dd": float((c / c.cummax() - 1).min()),
            "neg": negative_years(c), "trades": 0}

    print(f"\n{'=' * 100}\nRESULTADO — {INICIO} a {FIM}\n{'=' * 100}")
    print(linha("campeao antigo, watchlist de 2026", contaminada))
    print(linha("campeao antigo, escolhida 1x em 2013", uma_vez))
    print(linha("campeao antigo, reescolhida a cada 4a", rolante))
    print(linha("liquid_champion (campeao novo)", novo))
    print(linha("IBOV", ibov))
    print("\na primeira linha e a unica que precisou saber o futuro para existir")


if __name__ == "__main__":
    main()
