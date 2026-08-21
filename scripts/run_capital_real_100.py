"""O capital REAL do dono -- R$ 100 por mes, comecando do ZERO. Nunca medido.

A pergunta
----------
Todo numero deste diario foi medido com R$ 1.000 de capital inicial entrando de
uma vez. O capital real do dono e outro: R$ 100 por mes, comecando do zero. Isso
nunca foi medido, e e a unica restricao que importa de verdade para quem vai
operar de verdade.

Contexto ja pesquisado (nao re-derivado aqui): o MT5 da Clear NAO opera
mercado fracionario (so lote de 100 acoes), mas o home broker da Clear opera.
Como o robo decide no FIM DO MES (~12 decisoes por ano), a execucao manual no
home broker e viavel. `lot_size=1` (comprar 7 acoes de um papel) nao e ficcao
aqui -- e exatamente o mercado fracionario. O que muda no fracionario e o
CUSTO: o spread e mais largo que no lote padrao, e numa posicao de poucas
dezenas de reais isso pesa muito mais que numa posicao de R$ 1.000.

Protocolo, declarado antes de rodar
-----------------------------------
PARTE 1 -- RETORNO. As mesmas 48 janelas de 5 anos do holdout congelado
(`run_holdout_frozen.HOLDOUT`, inicio mensal 2010-01 a 2013-12). Config real:
`BacktestConfig(initial_capital=100.0, lot_size=1, monthly_contribution=100.0,
cash_yield_path="data/raw/selic.parquet")`, custos default do repo (slippage
0,15%). Tres bracos: campeao (`LiquidChampion`), dual10 (`LiquidDual10`) e IBOV
com os MESMOS fluxos (R$ 100 no dia 1, R$ 100 por mes) -- o benchmark correto
para quem aporta, nao o indice comprado a vista. PAREAMENTO por dict de
janela: so entram na tabela janelas em que os TRES bracos produziram pelo
menos 250 pontos de curva. Janelas descartadas sao impressas com o motivo.
Metricas honestas com aporte sao a COTA (CAGR, MaxDD) e a TIR (o que o dono
efetivamente ganhou sobre o dinheiro que colocou, quando colocou) -- `cagr` e
`max_drawdown` da curva de patrimonio NAO aparecem aqui porque dinheiro novo
empurra a curva para cima sem nada ter rendido.

PARTE 2 -- DEGENERACAO. A pergunta nova: o robo degenera quando a posicao vira
minuscula? Cinco sleeves de 20% cada sobre um capital que comeca em R$ 100
significa ~R$ 20 por posicao no dia 1. Mede-se, na janela FULL
(2010-01-01 a 2026-08-18), mesmo capital e mesmos fluxos, lote 1, para os dois
robos: valor medio de entrada no primeiro, terceiro e ultimo ano com trade;
quantos trades tiveram valor de entrada abaixo de R$ 50 e que fracao do total;
a data em que o patrimonio passou de R$ 1.000, R$ 5.000 e R$ 25.000; e o
numero total de trades. Uma linha por robo descreve o padrao encontrado --
NAO e um criterio de aprovacao, e leitura direta dos numeros impressos ao
lado.

PARTE 3 -- CUSTO DO FRACIONARIO. Mesma janela FULL, mesmos fluxos, para os
dois robos, com `slippage_pct` em (0,15%, 0,35%, 0,60%). 0,15% e o default do
repo (calibrado para lote padrao, onde o spread e mais estreito); 0,35% e
0,60% sao spreads plausiveis do mercado fracionario numa posicao pequena.
Imprime patrimonio final, TIR e CAGR da cota em cada nivel, mais o custo
somado em reais extraido diretamente de `Trade.fees_total + Trade.slippage_total`
de cada trade fechado -- um campo que existe e e facil de somar, entao nao ha
motivo para nao imprimi-lo. Mudar o slippage muda o preco de execucao de CADA
trade, entao tambem pode mudar QUAIS trades acontecem (caixa disponivel
diferente, dependencia de caminho) -- os numeros de cada nivel nao isolam
"so o custo", isso esta declarado ao lado do resultado.

Vies residual declarado
------------------------
Aporte NOMINAL fixo de R$ 100 ao longo de 16 anos de inflacao brasileira NAO e
um aporte real constante -- R$ 100 de 2010 valiam muito mais que R$ 100 de
2026. Este script mede o que o dono FARIA (deposita R$ 100 todo mes, em
reais correntes), nao poder de compra constante. Corrigir por IPCA mudaria a
resposta da Parte 2 (a conta cresceria mais rapido no comeco, o "primeiro ano"
teria um aporte real maior) e pouco na Parte 1, que ja mede tudo em COTA e TIR
nominais.

Vies de sobrevivencia do POOL (ja documentado em `strategy/liquid_champion.py`
e `strategy/liquid_dual10.py`) continua valendo aqui sem mudanca -- este
script nao o mede de novo.

NAO ha veredito de aprovado/reprovado neste script. Isto e medicao
exploratoria: nao existia nenhum numero sobre R$ 100/mes antes desta rodada, e
o objetivo e produzir os numeros, nao julgar um criterio que ninguem declarou
antes de ver o resultado.

Uso: .venv/Scripts/python.exe scripts/run_capital_real_100.py
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
from core.config import BENCHMARK, BacktestConfig, CostModel
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_dual10 import LiquidDual10

INITIAL = 100.0
APORTE = 100.0
SELIC = "data/raw/selic.parquet"
INICIO_FULL = pd.Timestamp("2010-01-01")
FIM_FULL = "2026-08-18"


def cfg(lote: int = 1, slip: float = 0.0015) -> BacktestConfig:
    """Config oficial da Parte 1/2/3 -- so o slippage varia (Parte 3)."""
    return BacktestConfig(initial_capital=INITIAL, lot_size=lote, cash_yield_path=SELIC,
                          monthly_contribution=APORTE, costs=CostModel(slippage_pct=slip))


def robo(factory, u, start: pd.Timestamp, end: pd.Timestamp, slip: float = 0.0015) -> dict | None:
    r = run_bt(u, factory(), cfg(1, slip), start=str(start.date()), end=str(end.date()))
    eq = r.equity_curve
    if len(eq) < 250:
        return None
    return {
        "final": float(eq.iloc[-1]),
        "aportado": float(r.metrics.get("contributed_total", 0.0)),
        "irr": float(r.metrics.get("irr", r.metrics["cagr"])),
        "cagr_cota": float(r.metrics.get("cagr_unit", r.metrics["cagr"])),
        "dd_cota": float(r.metrics.get("max_drawdown_unit", r.metrics["max_drawdown"])),
        "trades": len(r.trades),
    }


def ibov_com_aporte(start: pd.Timestamp, end: pd.Timestamp, aporte: float) -> dict:
    """Compra indice com os MESMOS fluxos: R$ 100 no dia 1 e R$ 100 por mes.

    Sem lote e sem custo, de proposito -- e o benchmark mais GENEROSO possivel
    para o indice. Copiado de `run_hypothesis_contribution.ibov_com_aporte`,
    so com `INITIAL` = 100.0 em vez de 1000.0.
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
    """Mediana E p05 de cada coluna, em duas linhas (pedido explicitamente)."""
    if not rows:
        print(f"{nome:26s} sem janelas validas")
        return
    g = lambda k: np.array([r[k] for r in rows])
    print(f"{nome:26s} n={len(rows):3d}  [mediana] "
          f"final=R$ {np.median(g('final')):>9,.2f}  aportado=R$ {np.median(g('aportado')):>8,.2f}  "
          f"TIR={np.median(g('irr'))*100:>7.2f}%  CAGRcota={np.median(g('cagr_cota'))*100:>7.2f}%  "
          f"DDcota={np.median(g('dd_cota'))*100:>7.2f}%  trades={np.median(g('trades')):>5.1f}")
    print(f"{'':26s}        [p05]     "
          f"final=R$ {np.percentile(g('final'), 5):>9,.2f}  aportado=R$ {np.percentile(g('aportado'), 5):>8,.2f}  "
          f"TIR={np.percentile(g('irr'), 5)*100:>7.2f}%  CAGRcota={np.percentile(g('cagr_cota'), 5)*100:>7.2f}%  "
          f"DDcota={np.percentile(g('dd_cota'), 5)*100:>7.2f}%  trades={np.percentile(g('trades'), 5):>5.1f}")


def parte1(u) -> None:
    print(f"\n{'=' * 118}")
    print("PARTE 1 -- RETORNO. 48 janelas de 5 anos, inicio mensal 2010-01 a 2013-12, "
          f"capital R$ {INITIAL:.0f} + R$ {APORTE:.0f}/mes, lote 1")
    print(f"{'=' * 118}")

    campeao_rows: dict[pd.Timestamp, dict] = {}
    dual10_rows: dict[pd.Timestamp, dict] = {}
    ibov_rows: dict[pd.Timestamp, dict] = {}
    total = len(hf.HOLDOUT)
    descartadas: list[tuple[pd.Timestamp, list[str]]] = []

    for i, start in enumerate(hf.HOLDOUT, 1):
        end = start + pd.DateOffset(years=hf.ANOS)
        c = robo(LiquidChampion, u, start, end)
        d = robo(LiquidDual10, u, start, end)
        ib = ibov_com_aporte(start, end, APORTE)
        faltas = []
        if c is None:
            faltas.append("campeao")
        if d is None:
            faltas.append("dual10")
        if not ib:
            faltas.append("ibov")
        if faltas:
            descartadas.append((start, faltas))
            print(f"janela {i}/{total} inicio {start.date()} descartada "
                  f"(faltou: {', '.join(faltas)})", flush=True)
            continue
        campeao_rows[start] = c
        dual10_rows[start] = d
        ibov_rows[start] = ib
        print(f"janela {i}/{total} inicio {start.date()} ok", flush=True)

    comuns = sorted(campeao_rows)  # so janelas em que os TRES bracos rodaram
    print(f"\n{len(descartadas)} janela(s) descartada(s) de {total}: "
          f"{[(str(s.date()), fs) for s, fs in descartadas] if descartadas else 'nenhuma'}")
    print(f"{len(comuns)} janelas pareadas para a comparacao\n")

    resumo("campeao (liquid_champion)", [campeao_rows[s] for s in comuns])
    resumo("dual10 (liquid_dual10)", [dual10_rows[s] for s in comuns])
    resumo("IBOV com aporte", [ibov_rows[s] for s in comuns])

    print()
    for nome, rows_dict in (("campeao", campeao_rows), ("dual10", dual10_rows)):
        neg = sum(1 for s in comuns if rows_dict[s]["irr"] < 0)
        bate = sum(1 for s in comuns if rows_dict[s]["irr"] > ibov_rows[s]["irr"])
        print(f"{nome}: TIR < 0 em {neg}/{len(comuns)} janelas; "
              f"TIR > IBOV-com-aporte (pareado, janela a janela) em {bate}/{len(comuns)} janelas")


def _valor_entrada(t) -> float:
    return float(t.entry_price) * float(t.quantity)


def _primeira_vez_acima(eq: pd.Series, thr: float) -> str:
    acima = eq[eq >= thr]
    return str(acima.index[0].date()) if len(acima) else "nunca"


def parte2(u) -> None:
    print(f"\n{'=' * 118}")
    print(f"PARTE 2 -- DEGENERACAO. FULL {INICIO_FULL.date()} .. {FIM_FULL}, "
          f"capital R$ {INITIAL:.0f} + R$ {APORTE:.0f}/mes, lote 1")
    print(f"{'=' * 118}")

    for nome, factory in (("campeao (LiquidChampion)", LiquidChampion),
                          ("dual10 (LiquidDual10)", LiquidDual10)):
        print(f"\nrodando {nome}...", flush=True)
        r = run_bt(u, factory(), cfg(1, 0.0015), start=str(INICIO_FULL.date()), end=FIM_FULL)
        trades = r.trades
        eq = r.equity_curve
        print(f"--- {nome} ---")
        print(f"numero total de trades (fechados, inclui os forcados no ultimo dia): {len(trades)}")
        if not trades:
            print("nenhum trade em toda a janela -- o capital nunca coube em nenhuma posicao "
                  "com lote 1 nestes precos")
            continue

        anos = sorted({t.entry_date.year for t in trades})
        ano1 = anos[0]
        ano3 = anos[2] if len(anos) >= 3 else anos[-1]
        anoU = anos[-1]
        for label, ano in (("1o ano com trade", ano1), ("3o ano com trade", ano3),
                          ("ultimo ano com trade", anoU)):
            vals = [_valor_entrada(t) for t in trades if t.entry_date.year == ano]
            if vals:
                print(f"  {label} ({ano}): valor medio de entrada R$ {np.mean(vals):>9,.2f}  "
                      f"(n={len(vals)} trades)")
            else:
                print(f"  {label} ({ano}): sem trades")

        vals_all = [_valor_entrada(t) for t in trades]
        abaixo50 = sum(1 for v in vals_all if v < 50.0)
        frac = abaixo50 / len(vals_all)
        print(f"  trades com valor de entrada < R$ 50: {abaixo50}/{len(vals_all)} ({frac*100:.1f}%)")

        for thr in (1000.0, 5000.0, 25000.0):
            print(f"  patrimonio passou de R$ {thr:>9,.0f} em: {_primeira_vez_acima(eq, thr)}")

        # Leitura descritiva, NAO e criterio de aprovacao -- so descreve os
        # numeros impressos acima (pedido explicitamente para esta parte).
        if frac >= 0.3:
            leitura = (f"sinal de degeneracao ({abaixo50}/{len(vals_all)} = {frac*100:.1f}% dos "
                       "trades abaixo de R$ 50, custo fixo pesando proporcionalmente muito)")
        else:
            leitura = (f"sem sinal forte de degeneracao ({abaixo50}/{len(vals_all)} = "
                       f"{frac*100:.1f}% dos trades abaixo de R$ 50)")
        print(f"  leitura ({nome}): {leitura}")


def parte3(u) -> None:
    print(f"\n{'=' * 118}")
    print(f"PARTE 3 -- CUSTO DO FRACIONARIO. FULL {INICIO_FULL.date()} .. {FIM_FULL}, "
          f"mesmos fluxos, lote 1, slippage variando")
    print(f"{'=' * 118}")

    niveis = (0.0015, 0.0035, 0.0060)
    resultados: dict[str, list[dict]] = {}

    for nome, factory in (("campeao", LiquidChampion), ("dual10", LiquidDual10)):
        resultados[nome] = []
        for slip in niveis:
            r = run_bt(u, factory(), cfg(1, slip), start=str(INICIO_FULL.date()), end=FIM_FULL)
            # Custo somado em reais: extraido direto de Trade.fees_total +
            # Trade.slippage_total de cada trade fechado -- campo que existe
            # e e facil de somar, sem inventar nada.
            custo = float(sum(t.fees_total + t.slippage_total for t in r.trades))
            resultados[nome].append({
                "slip": slip,
                "final": float(r.equity_curve.iloc[-1]),
                "irr": float(r.metrics.get("irr", r.metrics["cagr"])),
                "cagr_cota": float(r.metrics.get("cagr_unit", r.metrics["cagr"])),
                "custo": custo,
                "trades": len(r.trades),
            })
            print(f"  {nome} slippage {slip*100:.2f}% ok", flush=True)

    print(f"\n{'robo':10s} {'slippage':>9s} {'final':>13s} {'TIR':>8s} "
          f"{'CAGRcota':>9s} {'custo (R$)':>12s} {'trades':>7s}")
    for nome in resultados:
        for row in resultados[nome]:
            print(f"{nome:10s} {row['slip']*100:>8.2f}% R$ {row['final']:>10,.2f} "
                  f"{row['irr']*100:>7.2f}% {row['cagr_cota']*100:>8.2f}% "
                  f"R$ {row['custo']:>9,.2f} {row['trades']:>7d}")

    print("\nressalva: mudar o slippage muda o preco de execucao de CADA trade e portanto pode "
          "mudar QUAIS trades acontecem (caixa disponivel diferente, dependencia de caminho) -- "
          "os tres niveis nao isolam 'so o custo', sao tres backtests distintos.")

    print("\nconclusao:")
    for nome in resultados:
        base = resultados[nome][0]
        pior = resultados[nome][-1]
        delta_final = (pior["final"] / base["final"] - 1.0) * 100.0 if base["final"] else float("nan")
        delta_tir = (pior["irr"] - base["irr"]) * 100.0
        print(f"  {nome}: capital final vai de R$ {base['final']:,.2f} (spread 0,15%) a "
              f"R$ {pior['final']:,.2f} (spread 0,60%), delta {delta_final:+.1f}%; "
              f"TIR vai de {base['irr']*100:.2f}% a {pior['irr']*100:.2f}% "
              f"(delta {delta_tir:+.2f} p.p.); custo medido em trades sobe de "
              f"R$ {base['custo']:,.2f} para R$ {pior['custo']:,.2f}.")


def main() -> None:
    print(__doc__.split("Uso:")[0])
    print("carregando paineis...", flush=True)
    u = hf.full_panels()

    parte1(u)
    parte2(u)
    parte3(u)


if __name__ == "__main__":
    main()
