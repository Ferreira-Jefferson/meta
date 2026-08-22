"""liqflop com APORTE MENSAL de R$ 100, contra o IBOV recebendo os MESMOS aportes.

Por que este arquivo existe
---------------------------
O ranking oficial mede um depósito único (R$ 100 em 2010 e nada mais) — útil
para comparar robôs entre si, mas não é o que o dono do capital faz: ele aporta
R$ 100 por mês. Com aporte, "capital final" deixa de ser desempenho e passa a
misturar dinheiro que entrou; o que responde "ganhei quanto?" é
patrimônio final MENOS o total aportado, em reais.

A comparação com o índice só é honesta se o índice receber o MESMO fluxo. Aqui
o IBOV é comprado com os mesmos R$ 100, NAS MESMAS DATAS que o motor credita
(lidas de `result.contributions`, não recalculadas de memória) — ou seja, DCA
contra DCA. Sem isso a comparação viraria "quem aporta contra quem não aporta".

Assimetrias declaradas, as duas a FAVOR do índice:
  - o IBOV aqui é o índice em PONTOS: sem dividendos, mas também sem
    corretagem, sem spread e sem lote. Quem replicasse via ETF no fracionário
    pagaria os mesmos R$ 1,90 por ordem que o robô paga.
  - o robô paga a corretagem real do fracionário em cada perna que não fecha
    lote de 100 (regime oficial desde 2026-08-22, ver `scheduler.champion_costs`).

Uso: .venv/Scripts/python.exe scripts/run_liqflop_aporte.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from market_data.loader import load_universe
from scheduler import CHAMPION_CASH_YIELD, champion_costs
from strategy.lab.fee_capacity.hip_03_pausa_apos_perdas import (
    LiquidFocusLossStreakPause as Liqflop,
)

INICIAL = 100.0
APORTE = 100.0
JANELAS = {
    "FULL 2010-2026": ("2010-01-01", "2026-08-20"),
    # As duas metades do split congelado de `run_liqflop_is_oos.py` (corte
    # 2018-12-31), agora no regime de aporte: cada metade recomeça com R$ 100 e
    # recebe R$ 100/mês do zero, para o OOS não herdar o patrimônio que a
    # primeira metade acumulou — herdar tornaria a segunda metade incomparável
    # com a primeira (a taxa fixa pesa conforme o tamanho da posição).
    "IS  2010-2018": ("2010-01-01", "2018-12-31"),
    "OOS 2019-2026": ("2019-01-01", "2026-08-20"),
    "5 anos 2021-2026": ("2021-08-20", "2026-08-20"),
    "1 ano 2025": ("2025-01-01", "2025-12-31"),
}


def ibov_dca(ibov: pd.Series, datas: list[pd.Timestamp], valores: list[float],
             fim: pd.Timestamp) -> float:
    """Patrimônio final de quem comprou o índice com o mesmo fluxo de caixa."""
    s = ibov.dropna()
    cotas = 0.0
    for d, v in zip(datas, valores):
        i = s.index.asof(pd.Timestamp(d))
        if pd.isna(i):
            continue
        cotas += v / float(s.loc[i])
    f = s.index.asof(pd.Timestamp(fim))
    return cotas * float(s.loc[f])


def main() -> None:
    s = Liqflop()
    universo = load_universe(tickers=s.universe_tickers)
    ibov = universo[BENCHMARK]["close"]

    hdr = (f"{'janela':18s} {'aportado':>10s} | {'ROBO final':>11s} {'lucro R$':>11s} "
           f"{'TIR a.a.':>9s} {'DD cota':>8s} | {'IBOV final':>11s} {'lucro R$':>10s} | "
           f"{'robo - ibov':>12s}")
    print(hdr)
    print("-" * len(hdr))
    for nome, (ini, fim) in JANELAS.items():
        cfg = BacktestConfig(initial_capital=INICIAL, lot_size=1,
                             cash_yield_path=CHAMPION_CASH_YIELD,
                             costs=champion_costs(), monthly_contribution=APORTE)
        r = run_bt(universo, Liqflop(), cfg, start=ini, end=fim)
        eq = r.equity_curve
        datas = [eq.index[0]] + [pd.Timestamp(d) for d, _ in r.contributions]
        valores = [INICIAL] + [v for _, v in r.contributions]
        aportado = sum(valores)
        robo = float(eq.iloc[-1])
        idx = ibov_dca(ibov, datas, valores, eq.index[-1])
        print(f"{nome:18s} {aportado:10,.2f} | {robo:11,.2f} {robo-aportado:11,.2f} "
              f"{r.metrics.get('irr', float('nan'))*100:8.2f}% "
              f"{r.metrics.get('max_drawdown_unit', float('nan'))*100:7.1f}% | "
              f"{idx:11,.2f} {idx-aportado:10,.2f} | {robo-idx:12,.2f}", flush=True)

    print(f"\naportes: R$ {INICIAL:,.0f} no primeiro pregão + R$ {APORTE:,.0f} no primeiro "
          f"pregão de cada mês seguinte, nas MESMAS datas para os dois.")
    print("lucro R$ = patrimônio final - total aportado. TIR = retorno anual do fluxo de "
          "caixa real (o que 'CAGR' não sabe medir quando entra dinheiro no meio).")
    print("DD cota = pior queda da COTA, que neutraliza o aporte; a queda do patrimônio "
          "seria menor só porque dinheiro novo entra todo mês.")


if __name__ == "__main__":
    main()
