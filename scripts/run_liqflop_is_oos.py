"""liqflop -- split IS/OOS no protocolo do gremah: a vantagem existe fora do
trecho onde os parametros foram escolhidos?

Pergunta do dono do capital (2026-08-22)
----------------------------------------
O ranking oficial mostra liqflop perdendo do IBOV em 1 ano (+21,8% vs +34,5%)
e em 5 anos (CAGR 4,2% vs 7,8%), e ganhando SO' na janela FULL (R$28.341 vs
R$2.493 do indice em pontos). "Ele so' se sai melhor no cenario full e isso
pode revelar que so' funciona bem pq ele foi treinado com os dados do passado."

Este script mede isso. O que ele PODE e NAO PODE provar, dito antes de rodar:

  - NAO existe OOS limpo para este robo, e nenhum numero abaixo vai criar um.
    Toda decisao de desenho (universo por liquidez, 1 posicao, momentum 12-1,
    dip 2%, janela 40, histerese 15%, pausa de 21 pregoes apos 2 perdas) foi
    tomada em 2026 com a serie 2010-2026 inteira na tela. Um corte declarado
    depois disso e' reconstrucao, nao reserva.
  - O que o corte MEDE de verdade sao duas coisas falsificaveis:
      A. a vantagem esta espalhada nas duas metades da base ou concentrada em
         uma? (se so' existe numa metade, "FULL ganha" e' efeito de composicao
         de um trecho, nao de um edge continuo)
      B. escolher parametros olhando so' o passado ajuda no futuro? Varredura
         completa no IS, UMA passada do vencedor no OOS. Se o vencedor do IS
         nao se destaca no OOS, o ajuste nao transfere -- que e' exatamente a
         acusacao a testar. O numero que decide isso e' a correlacao de posto
         (Spearman) entre desempenho no IS e no OOS ao longo de TODA a grade,
         nao o resultado de um vencedor sozinho.

===========================================================================
DESENHO CONGELADO -- declarado ANTES de rodar. Mudar qualquer coisa aqui
depois de ver o resultado invalida o teste.
===========================================================================

  CORTE     : 2018-12-31. Escolhido por ser a virada de ano mais proxima do
              meio da base (2010-01-04..2026-08-21), sem olhar resultado
              nenhum. IS = 2010-01-01..2018-12-31 (9,0 anos). OOS =
              2019-01-01..2026-08-21 (7,6 anos).
  CAPITAL   : R$ 1.000 em CADA metade, comecando do zero nas duas -- e' o que
              torna as metades comparaveis entre si. Mesma config do ranking
              oficial (`scheduler.CHAMPION_*`): lote 1, caixa remunerado na
              Selic diaria, custos padrao do repo.
              (A taxa fixa de R$1,90/ordem do fracionario NAO entra aqui,
              igual ao ranking oficial -- ver `CostModel.fractional_fixed_fee`,
              que e' 0.0 no default. E' um buraco conhecido e vale para as
              DUAS metades, entao nao inclina a comparacao.)
  REFERENCIA: IBOV na janela exata de cada metade, em PONTOS (sem dividendos,
              como o indice que o repo salva). O robo remunera o caixa parado;
              o indice nao tem caixa. As duas assimetrias ficam declaradas.
  GRADE     : 360 configuracoes = dip_pct {0; 1; 2; 3; 5%} x high_window
              {20; 40; 60} x lookback {126; 252} x skip_recent {0; 21} x
              pause_bars {0; 21; 42} x loss_streak_threshold {2; 3}.
              Inclui o default que esta no ar (2%, 40, 252, 21, 21, 2).
  CRITERIO  : capital final, o mesmo do ranking oficial (memoria
              `ranking_criterion`). Sem portao de DD, sem empate desfeito a mao.
  UMA PASSADA: o vencedor do IS roda no OOS uma vez. Nao ha segunda tentativa,
              nao ha ajuste do corte, nao ha escolha de metrica depois.

===========================================================================

Uso: .venv/Scripts/python.exe scripts/run_liqflop_is_oos.py [--rapido]
     (--rapido roda so' o Teste A, sem a grade)
"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from backtest.runner import run as run_bt
from core.config import BacktestConfig
from market_data.loader import load_universe
from strategy.lab.fee_capacity.hip_03_pausa_apos_perdas import (
    LiquidFocusLossStreakPause as Liqflop,
)

CORTE = "2018-12-31"
JANELAS = {
    "IS  2010-2018": ("2010-01-01", CORTE),
    "OOS 2019-2026": ("2019-01-01", "2026-08-21"),
    "FULL 2010-2026": ("2010-01-01", "2026-08-21"),
}
CAPITAL = 1_000.0
SELIC = "data/raw/selic.parquet"

DEFAULT = dict(dip_pct=0.02, high_window=40, lookback=252, skip_recent=21,
               pause_bars=21, loss_streak_threshold=2)
GRADE = dict(
    dip_pct=(0.0, 0.01, 0.02, 0.03, 0.05),
    high_window=(20, 40, 60),
    lookback=(126, 252),
    skip_recent=(0, 21),
    pause_bars=(0, 21, 42),
    loss_streak_threshold=(2, 3),
)


def _cfg() -> BacktestConfig:
    return BacktestConfig(initial_capital=CAPITAL, lot_size=1, cash_yield_path=SELIC)


def medir(universo, params: dict, start: str, end: str) -> dict:
    r = run_bt(universo, Liqflop(**params), _cfg(), start=start, end=end)
    eq = r.equity_curve
    fechados = [t for t in r.trades if t.exit_date is not None]
    retornos = sorted((t.pnl_pct for t in fechados), reverse=True)
    sem_top3 = 1.0
    for x in retornos[3:]:
        sem_top3 *= 1 + x
    bench = r.benchmark_curve.reindex(eq.index).ffill().dropna()
    tem_bench = len(bench) > 1
    return {
        "final": float(eq.iloc[-1]),
        "cagr": float(r.metrics["cagr"]),
        "dd": float(r.metrics["max_drawdown"]),
        "trades": len(fechados),
        "wr": float(r.metrics["win_rate"]),
        "top3_pct": retornos[:3],
        "sem_top3": sem_top3,
        "ibov_final": float(CAPITAL * bench.iloc[-1] / bench.iloc[0]) if tem_bench else float("nan"),
        "ibov_cagr": float(r.metrics["benchmark_cagr"]),
        "ibov_dd": float((bench / bench.cummax() - 1).min()) if tem_bench else float("nan"),
    }


def teste_a(universo) -> dict[str, dict]:
    print("=" * 104)
    print("TESTE A -- a MESMA configuracao (a que esta no ar) em cada metade, R$1.000 do zero nas duas")
    print("=" * 104)
    hdr = (f"{'janela':16s} {'robo final':>12s} {'CAGR':>8s} {'MaxDD':>8s} {'trd':>4s} "
           f"{'acerto':>7s} | {'IBOV final':>11s} {'CAGR':>7s} {'MaxDD':>8s} | {'robo/ibov':>9s}")
    print(hdr)
    print("-" * len(hdr))
    out = {}
    for nome, (start, end) in JANELAS.items():
        m = medir(universo, DEFAULT, start, end)
        out[nome] = m
        print(f"{nome:16s} {m['final']:12,.2f} {m['cagr']*100:7.2f}% {m['dd']*100:7.2f}% "
              f"{m['trades']:4d} {m['wr']*100:6.1f}% | {m['ibov_final']:11,.2f} "
              f"{m['ibov_cagr']*100:6.2f}% {m['ibov_dd']*100:7.2f}% | "
              f"{m['final']/m['ibov_final']:8.2f}x", flush=True)
    print("\nconcentracao: quanto sobra dos R$1.000 se os 3 melhores trades da janela nao tivessem acontecido")
    for nome, m in out.items():
        top = ", ".join(f"{x*100:+.1f}%" for x in m["top3_pct"])
        print(f"  {nome:16s} 3 maiores: {top:30s} -> sem eles: R$ {CAPITAL*m['sem_top3']:>9,.2f} "
              f"(com eles: R$ {m['final']:,.2f})")
    return out


def teste_b(universo) -> None:
    combos = [dict(zip(GRADE, v)) for v in itertools.product(*GRADE.values())]
    is_start, is_end = JANELAS["IS  2010-2018"]
    oos_start, oos_end = JANELAS["OOS 2019-2026"]
    print("\n" + "=" * 104)
    print(f"TESTE B -- varredura de {len(combos)} configuracoes SO' no IS, uma passada de cada uma no OOS")
    print("=" * 104)

    t0 = time.perf_counter()
    linhas = []
    for i, p in enumerate(combos, 1):
        m_is = medir(universo, p, is_start, is_end)
        m_oos = medir(universo, p, oos_start, oos_end)
        linhas.append({"p": p, "is": m_is, "oos": m_oos})
        if i % 30 == 0:
            print(f"  ... {i}/{len(combos)} ({time.perf_counter()-t0:.0f}s)", flush=True)

    df = pd.DataFrame([
        {**l["p"], "is_final": l["is"]["final"], "oos_final": l["oos"]["final"],
         "is_ibov": l["is"]["ibov_final"], "oos_ibov": l["oos"]["ibov_final"],
         "is_dd": l["is"]["dd"], "oos_dd": l["oos"]["dd"],
         "is_trades": l["is"]["trades"], "oos_trades": l["oos"]["trades"]}
        for l in linhas
    ])
    df["is_rank"] = df["is_final"].rank(ascending=False)
    df["oos_rank"] = df["oos_final"].rank(ascending=False)

    saida = Path("scripts/swing_lab/liqflop_is_oos.csv")
    df.to_csv(saida, index=False)  # antes das estatisticas: 40 min de varredura
    print(f"\ngrade completa gravada em {saida}")  # nao se perde num erro de conta

    # Spearman na mao (Pearson sobre os POSTOS) de proposito: o `method=
    # "spearman"` do pandas importa scipy, que nao e' dependencia deste repo
    # (AGENTS.md: "nao adicionar dependencia sem justificativa") -- e foi
    # exatamente esse import que derrubou a primeira rodada desta varredura,
    # depois de 40 minutos de backtest, na ultima linha de conta.
    spearman = df["is_rank"].corr(df["oos_rank"])
    pearson_log = np.log(df["is_final"]).corr(np.log(df["oos_final"]))

    campea = df.loc[df["is_final"].idxmax()]
    padrao = df[(df[list(DEFAULT)] == pd.Series(DEFAULT)).all(axis=1)].iloc[0]
    chaves = list(GRADE)
    oos_ibov = float(df["oos_ibov"].iloc[0])
    is_ibov = float(df["is_ibov"].iloc[0])

    def desc(row) -> str:
        return ", ".join(f"{k}={row[k]}" for k in chaves)

    print(f"\nvarredura terminada em {time.perf_counter()-t0:.0f}s")
    print(f"\ncampea do IS       : {desc(campea)}")
    print(f"  IS  R$ {campea['is_final']:,.2f} (posto 1 de {len(df)})   "
          f"OOS R$ {campea['oos_final']:,.2f} (posto {int(campea['oos_rank'])} de {len(df)})")
    print(f"\ndefault no ar      : {desc(padrao)}")
    print(f"  IS  R$ {padrao['is_final']:,.2f} (posto {int(padrao['is_rank'])} de {len(df)})   "
          f"OOS R$ {padrao['oos_final']:,.2f} (posto {int(padrao['oos_rank'])} de {len(df)})")
    print(f"\nIBOV na janela     : IS R$ {is_ibov:,.2f}   OOS R$ {oos_ibov:,.2f}")

    print("\ntransferencia IS -> OOS ao longo da grade inteira:")
    print(f"  Spearman(posto IS, posto OOS) = {spearman:+.3f}")
    print(f"  Pearson(log IS, log OOS)      = {pearson_log:+.3f}")
    print(f"  configuracoes que batem o IBOV no IS : {(df['is_final'] > is_ibov).sum()} de {len(df)}")
    print(f"  configuracoes que batem o IBOV no OOS: {(df['oos_final'] > oos_ibov).sum()} de {len(df)}")
    print(f"  top-10 do IS que batem o IBOV no OOS : "
          f"{(df.nlargest(10, 'is_final')['oos_final'] > oos_ibov).sum()} de 10")
    print(f"  mediana OOS da grade                 : R$ {df['oos_final'].median():,.2f}")

    print("\ntop-10 do IS, com o que aconteceu com cada uma no OOS:")
    print(f"{'#IS':>4s} {'config':66s} {'IS final':>11s} {'OOS final':>11s} {'#OOS':>5s}")
    for _, row in df.nlargest(10, "is_final").iterrows():
        print(f"{int(row['is_rank']):4d} {desc(row):66s} {row['is_final']:11,.2f} "
              f"{row['oos_final']:11,.2f} {int(row['oos_rank']):5d}")

    print("\ntop-10 do OOS (o que teria sido escolhido com o gabarito na mao):")
    print(f"{'#OOS':>4s} {'config':66s} {'IS final':>11s} {'OOS final':>11s} {'#IS':>5s}")
    for _, row in df.nlargest(10, "oos_final").iterrows():
        print(f"{int(row['oos_rank']):4d} {desc(row):66s} {row['is_final']:11,.2f} "
              f"{row['oos_final']:11,.2f} {int(row['is_rank']):5d}")


def main() -> None:
    print(__doc__.split("=" * 75)[1])
    s = Liqflop()
    universo = load_universe(tickers=s.universe_tickers)
    print(f"universo: {len(universo)} paineis (pool fixo de {len(s.universe_tickers)} + benchmark)\n")
    teste_a(universo)
    if "--rapido" not in sys.argv:
        teste_b(universo)


if __name__ == "__main__":
    main()
