"""liqflop -- os trades que carregam o resultado, comparados com o IBOV NOS
MESMOS DIAS.

Por que este arquivo existe
---------------------------
A primeira medicao de concentracao (em `run_liqflop_is_oos.py`) respondia "o
que sobra se os 3 maiores trades nao tivessem acontecido" multiplicando os
retornos dos trades restantes. O dono do capital apontou o furo (2026-08-22):
esse numero nao tem periodo. Ele tira 3 trades do robo e deixa o IBOV com a
janela inteira -- comparacao desigual, do tipo que a memoria
`feedback_honest_period_comparison` proibe.

Aqui a comparacao e' dia a dia:
  1. cada trade grande e' medido contra o IBOV entre a MESMA data de entrada e
     a MESMA data de saida. Se o indice subiu o mesmo tanto, o trade foi
     mercado; se nao, foi escolha.
  2. o contrafactual honesto nao APAGA o trade -- ele SUBSTITUI a acao
     escolhida pelo indice no mesmo intervalo ("e se, nesses 3 periodos, ele
     tivesse comprado IBOV em vez do papel?"). Assim o robo contrafactual
     continua investido nos mesmos dias e a comparacao com o indice na janela
     inteira volta a ser legitima.

Limite declarado deste contrafactual: ele troca o RETORNO de 3 trades e mantem
todos os outros iguais. Nao simula o efeito de caminho (uma saida diferente
mudaria o caixa, a histerese e a proxima escolha do robo) -- para isso seria
preciso um robo diferente, nao uma conta. O numero abaixo mede o peso dos 3
trades, nao "o que o robo teria feito".

O elo entre trade e patrimonio tambem e' verificado, nao presumido: o script
imprime o produto de (1+retorno) de TODOS os trades ao lado do capital final
de verdade. Se os dois nao baterem de perto, e' porque caixa remunerado,
custos e dimensionamento entram no meio -- e o produto passa a ser leitura
aproximada, nao identidade.

Uso: .venv/Scripts/python.exe scripts/run_liqflop_top_trades.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from backtest.runner import run as run_bt
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.lab.fee_capacity.hip_03_pausa_apos_perdas import (
    LiquidFocusLossStreakPause as Liqflop,
)

CAPITAL = 1_000.0
SELIC = "data/raw/selic.parquet"
JANELAS = {
    "IS  2010-2018": ("2010-01-01", "2018-12-31"),
    "OOS 2019-2026": ("2019-01-01", "2026-08-21"),
    "FULL 2010-2026": ("2010-01-01", "2026-08-21"),
}
QUANTOS = 3


def ibov_no_intervalo(bench: pd.Series, ini, fim) -> float | None:
    """Retorno do indice entre duas datas, usando o ultimo fechamento <= data."""
    s = bench.dropna()
    i = s.index.asof(pd.Timestamp(ini))
    f = s.index.asof(pd.Timestamp(fim))
    if pd.isna(i) or pd.isna(f) or i == f:
        return None
    return float(s.loc[f] / s.loc[i] - 1)


def analisa(universo, nome: str, start: str, end: str) -> None:
    cfg = BacktestConfig(initial_capital=CAPITAL, lot_size=1, cash_yield_path=SELIC)
    r = run_bt(universo, Liqflop(), cfg, start=start, end=end)
    bench = r.benchmark_curve.dropna()
    fechados = [t for t in r.trades if t.exit_date is not None]
    linhas = []
    for t in fechados:
        ib = ibov_no_intervalo(bench, t.entry_date, t.exit_date)
        linhas.append({
            "ticker": t.ticker, "entrada": t.entry_date, "saida": t.exit_date,
            "dias": (t.exit_date - t.entry_date).days,
            "robo": t.pnl_pct, "ibov": ib, "motivo": t.exit_reason.value,
        })
    df = pd.DataFrame(linhas).sort_values("robo", ascending=False)

    produto_todos = float((1 + df["robo"]).prod())
    ibov_janela = ibov_no_intervalo(bench, r.equity_curve.index[0], r.equity_curve.index[-1])

    produto_ibov = float((1 + df["ibov"].dropna()).prod())
    real = float(r.equity_curve.iloc[-1])

    print("=" * 108)
    print(f"{nome}   ({start} a {end})")
    print("=" * 108)
    print(f"capital final real                       R$ {real:>12,.2f}")
    print(f"produto de (1+r) dos {len(df):2d} trades              {produto_todos:>12.2f}x  "
          f"(= R$ {CAPITAL*produto_todos:,.2f})")
    print(f"  ^ a diferenca para o capital real e' {real/(CAPITAL*produto_todos):.2f}x: caixa "
          f"remunerado na Selic entre trades, custos e dimensionamento.")
    print(f"  ^ por isso as linhas de trade abaixo se comparam ENTRE SI, na mesma conta, "
          f"nunca com o capital final.")
    print(f"IBOV comprado nos MESMOS {len(df):2d} intervalos     {produto_ibov:>12.2f}x  "
          f"(mesma conta: so' os dias em que o robo esteve posicionado)")
    print(f"IBOV comprado e segurado na janela toda  R$ {CAPITAL*(1+ibov_janela):>12,.2f}   "
          f"({ibov_janela*100:+.1f}%)")

    print(f"\nos {QUANTOS} maiores trades, contra o IBOV NOS MESMOS DIAS:")
    hdr = (f"  {'ticker':10s} {'entrada':>11s} {'saida':>11s} {'dias':>5s} "
           f"{'robo':>8s} {'IBOV igual periodo':>19s} {'excesso':>9s} {'saida por':>12s}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    top = df.head(QUANTOS)
    for _, x in top.iterrows():
        ib = "n/d" if x["ibov"] is None else f"{x['ibov']*100:+.1f}%"
        ex = "n/d" if x["ibov"] is None else f"{(x['robo']-x['ibov'])*100:+.1f} p.p."
        print(f"  {x['ticker']:10s} {str(x['entrada']):>11s} {str(x['saida']):>11s} "
              f"{x['dias']:5d} {x['robo']*100:+7.1f}% {ib:>19s} {ex:>9s} {x['motivo']:>12s}")

    resto = df.iloc[QUANTOS:]
    print(f"\n  os outros {len(resto)} trades juntos: robo {(1+resto['robo']).prod():.2f}x   "
          f"IBOV nos mesmos {len(resto)} intervalos: "
          f"{(1+resto['ibov'].dropna()).prod():.2f}x")

    print("\ncontrafactual de MESMO PERIODO -- nesses 3 intervalos ele compra o INDICE,")
    print("em vez do papel escolhido; todo o resto fica igual:")
    subs = float((1 + top["ibov"].fillna(0)).prod() * (1 + resto["robo"]).prod())
    print(f"  robo real, os {len(df)} picks dele            {produto_todos:8.2f}x")
    print(f"  so' os 3 maiores virando IBOV          {subs:8.2f}x")
    print(f"  TODOS os picks virando IBOV            {produto_ibov:8.2f}x")
    print(f"  peso dos 3 trades (real / contrafact.) {produto_todos/subs:8.2f}x\n")


def main() -> None:
    s = Liqflop()
    universo = load_universe(tickers=s.universe_tickers)
    print(f"universo: {len(universo)} paineis\n")
    for nome, (start, end) in JANELAS.items():
        analisa(universo, nome, start, end)


if __name__ == "__main__":
    main()
