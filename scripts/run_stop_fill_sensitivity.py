"""Quanto custa a unica divergencia estrutural entre backtest e operacao real.

A pergunta
----------
No backtest o stop dispara quando `low[D] <= stop` e preenche em
`min(open[D], stop)` — o engine ve a barra FECHADA, de tras para frente. Ao
vivo nao existe "a barra inteira": existe o preco que o feed entregou no
momento em que entregou. Se o feed atrasar, ou se a amostragem for esparsa, a
saida acontece DEPOIS do movimento, num preco pior. Nada disso e defeito da
estrategia — o nivel do stop continua sendo o mesmo — e nao tem conserto em
codigo. Tem medicao.

Isto NAO e academico para o campeao: 47 dos 174 trades da janela FULL saem por
stop (27%). Se cada um sai um pouco pior do que o diario diz, o diario esta
otimista de forma sistematica.

Protocolo, declarado antes de rodar
-----------------------------------
Tres hipoteses de EXECUCAO sobre exatamente a mesma estrategia, mesmo
universo, mesma janela, mesmo capital. Nenhuma delas muda uma regra de
decisao; `config.stop_fill` (ver `core/config.py`) so troca como se sai.

  stop_or_open  o que o diario sempre assumiu: dispara se `low <= stop`,
                preenche em `min(open, stop)`. Hipotese OTIMISTA — assume que
                se conseguiu sair no nivel pedido.
  low           dispara igual, preenche na MINIMA do dia. Limite inferior de
                qualquer feed intradiario com atraso: ninguem sai pior que a
                minima. Nao e o cenario esperado, e o piso.
  close         dispara SO se `close <= stop`, preenche no `close`. E o que o
                `ParquetCloseFeed` de `scripts/run_live_sim.py` faz de
                verdade hoje. Um feed que so ve o fechamento nao enxerga a
                perfuracao intradiaria: as vezes sai pior, as vezes NAO SAI —
                e ficar dentro pode ser melhor ou pior, o que torna este arm
                o unico que pode aparecer ACIMA do REF sem ser boa noticia.

O que o resultado significa (dito antes de existir): se `low` estiver perto do
REF, a divergencia e ruido e a operacao pode confiar no diario. Se estiver
longe, o numero do diario nao e alcancavel com o feed que existe, e a diferenca
e o preco de operar com dado diario — nao um erro a corrigir, um custo a
declarar.

RESULTADO MEDIDO (2026-08-20, `liquid_champion`, caixa na Selic)
----------------------------------------------------------------
             FULL (16,6a)                          5Y
  arm        capital   CAGR    MaxDD  stops    capital  CAGR   MaxDD  stops
  REF        R$ 4.915  10,05%  -34,2%   47     R$ 1.032  0,62%  -25,6%  13
  low        R$ 4.090   8,84%  -36,4%   47     R$ 1.007  0,14%  -26,3%  13
  close      R$ 5.044  10,23%  -33,4%   35     R$ 1.188  3,51%  -20,7%   8

Distancia do preco assumido ate a minima do dia, nos 47 stops da FULL:
mediana -0,90%, media -1,72%, pior -11,58%; 8 dos 47 com a minima mais de 3%
abaixo. Na 5Y: mediana -0,74%, pior -2,41%, nenhum acima de 3%.

Leitura, com o cuidado de nao virar mais do que e:

  - O PISO custa 16,8% do capital na FULL (1,2 p.p. de CAGR) e 2,4% na 5Y. E
    piso, nao expectativa: um feed que amostra a cada minuto pega o stop perto
    do nivel, nao na minima do dia. O numero do diario e otimista, e o tamanho
    do otimismo esta entre zero e isso.
  - A cauda concentra o dano: metade dos stops perde menos de 1%, mas 8 de 47
    perdem mais de 3% e o pior perde 11,6%. Nao e um custo diluido por trade,
    e um punhado de dias ruins.
  - O arm `close` fica ACIMA do REF nas duas janelas — porque 12 stops (FULL)
    e 5 (5Y) simplesmente nao disparam. Nao e boa noticia, e fragilidade: o
    resultado passa a depender de o dia recuperar.

Controle rodado a parte, porque o `close` sugeria "menos stop e melhor":
`stop_loss_pct=0.0` (sem stop nenhum) da R$ 4.178 / 8,98% / MaxDD -41,8% na
FULL e R$ 1.173 / 3,23% / -21,2% na 5Y. As duas janelas discordam, entao o
stop nao esta simplesmente sobrando — a vantagem do arm `close` nao se explica
por "stop e ruim".

Uso: .venv/Scripts/python.exe scripts/run_stop_fill_sensitivity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from backtest.metrics import negative_years
from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from core.models import ExitReason
from market_data.loader import load_one
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_sleeve import POOL

INITIAL = 1_000.0
SELIC = "data/raw/selic.parquet"
FIM = "2026-08-18"
JANELAS = [("FULL", "2010-01-01"), ("5Y", "2021-08-18")]
ARMS = ["stop_or_open", "low", "close"]


def cfg(fill: str) -> BacktestConfig:
    return BacktestConfig(initial_capital=INITIAL, lot_size=1,
                          cash_yield_path=SELIC, stop_fill=fill)


def rodar(universe, start: str, fill: str) -> dict:
    r = run_bt(universe, LiquidChampion(), cfg(fill), start=start, end=FIM)
    stops = [t for t in r.trades if t.exit_reason == ExitReason.STOP]
    return {
        "final": float(r.metrics["final_capital"]),
        "cagr": float(r.metrics["cagr"]),
        "dd": float(r.metrics["max_drawdown"]),
        "neg": negative_years(r.equity_curve),
        "trades": len(r.trades),
        "stops": len(stops),
    }


def gap_por_trade(universe, start: str) -> pd.Series:
    """Quanto PIOR que o preco assumido e a minima do dia, em %, trade a trade.

    Medido no arm REF (o unico em que os 47 stops existem por definicao):
    para cada saida por stop, compara o preco que o engine booked com a minima
    daquele pregao. E a distancia maxima que um feed atrasado pode custar
    naquele trade — o teto do dano por evento, nao a media esperada.
    """
    r = run_bt(universe, LiquidChampion(), cfg("stop_or_open"), start=start, end=FIM)
    gaps = []
    for t in r.trades:
        if t.exit_reason != ExitReason.STOP:
            continue
        df = universe.get(t.ticker)
        ts = pd.Timestamp(t.exit_date)
        if df is None or ts not in df.index:
            continue
        low = float(df.loc[ts, "low"])
        if t.exit_price <= 0:
            continue
        gaps.append((low / t.exit_price - 1.0) * 100.0)
    return pd.Series(gaps, dtype=float)


def main() -> None:
    print("\ncarregando universo...", flush=True)
    universe = {t: load_one(t) for t in POOL}
    universe[BENCHMARK] = load_one(BENCHMARK)

    for nome, start in JANELAS:
        print(f"\n{'=' * 92}\n{nome} — {start} a {FIM}, R$ {INITIAL:,.0f} iniciais, "
              f"caixa na Selic\n{'=' * 92}")
        print(f"{'arm':14s} {'capital':>12s} {'CAGR':>8s} {'MaxDD':>8s} "
              f"{'anos neg':>9s} {'trades':>7s} {'stops':>6s} {'vs REF':>9s}")
        ref = None
        for fill in ARMS:
            m = rodar(universe, start, fill)
            if ref is None:
                ref = m["final"]
                delta = "     —"
            else:
                delta = f"{(m['final'] / ref - 1) * 100:+8.1f}%"
            print(f"{fill:14s} R$ {m['final']:>9,.0f} {m['cagr'] * 100:>7.2f}% "
                  f"{m['dd'] * 100:>7.1f}% {m['neg']:>9d} {m['trades']:>7d} "
                  f"{m['stops']:>6d} {delta}", flush=True)

        g = gap_por_trade(universe, start)
        if len(g):
            print(f"\n  distancia do preco assumido ate a minima do dia, nos {len(g)} stops:")
            print(f"    mediana {g.median():.2f}%   media {g.mean():.2f}%   "
                  f"pior {g.min():.2f}%   melhor {g.max():.2f}%")
            print(f"    trades em que a minima ficou mais de 3% abaixo: "
                  f"{int((g < -3).sum())} de {len(g)}")

    print("\nnenhuma linha acima muda regra de decisao — so a hipotese de execucao.")
    print("o arm `close` pode aparecer ACIMA do REF: nao sair tambem e um desfecho.")


if __name__ == "__main__":
    main()
