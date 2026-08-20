"""HOLDOUT — desenho CONGELADO, medido em janelas que nunca escolheram nada.

Por que este arquivo existe
---------------------------
Auditoria da sessao de 2026-08-20: as mesmas CINCO janelas de cinco anos
(inicios em 2014, 2016, 2018, 2020 e 2021) foram usadas para julgar mais de cem
configuracoes — 11 variantes de seguranca, 8 valores de k, 10 combinacoes de
cadencia x despejo, 22 variantes na recontagem do caixa, 16 de drawdown e 33
deslocamentos de calendario. Com cem tentativas, "a melhor passou os quatro
portoes" e o resultado esperado por acaso, nao evidencia.

Tres escolhas especificas foram feitas OLHANDO essas cinco janelas:
  - k = 5 contas
  - `evict_on_refresh = False` (grandfathering)
  - carregar so os sobreviventes da rodada 1 para a rodada 2

Este script mede o desenho resultante em janelas cujo INICIO cai em territorio
que nunca participou de escolha nenhuma: 2010 a 2013.

Honestidade sobre o que este holdout NAO e
------------------------------------------
Ele nao e limpo. Uma janela de cinco anos comecando em 2013 termina em 2018, e
2014-2018 foi usado nas decisoes. Nao existe janela de cinco anos inteiramente
contida em 2010-2013 — a serie comeca em 2010-01-04. O que e genuinamente
intocado e o INICIO de cada janela, que e o que determina o universo escolhido,
a primeira posicao e toda a dependencia de caminho que vem depois.

Alem disso, inicios antes de 2012 sofrem handicap de aquecimento: o robo exige
`min_history_days=504` para ranquear liquidez, entao uma janela iniciada em
2010-01 passa os dois primeiros anos sem universo. Isso NAO foi ajustado para
favorecer o resultado — esta declarado aqui e as colunas mostram o inicio de
cada janela para o efeito ser visivel.

===========================================================================
DESENHO CONGELADO — declarado ANTES de rodar, nao se altera apos ver o
resultado. Qualquer mudanca abaixo invalida este teste e exige holdout novo.
===========================================================================

  candidato primario : liquid_flow5
  referencias        : liquid_sleeves5, portfolio_dip2_hw40, IBOV

  universo   : top-20 por giro financeiro mediano de 252 pregoes, na data,
               banda de rank 20/30, min_history_days=504
  contas     : 5 sleeves disjuntos, 20% do capital cada, caixa compartilhado
  despejo    : desligado (grandfathering)
  sinal      : momentum 12-1 (lookback 252, skip 21), dip 2%, high_window 40,
               histerese 15%, confirmacao 2 meses, gate de Selic 63d/0,005
  execucao   : stop 15%, lote 1, R$ 1.000, custos padrao do repo
  caixa      : remunerado na Selic diaria (data/raw/selic.parquet)

  PORTOES (os mesmos de `run_safety_walkforward.py`, sem recalibragem):
    G1  pior janela com CAGR > 0
    G2  pior MaxDD melhor que -45%
    G3  CAGR mediano >= CAGR mediano do IBOV nas mesmas janelas
    G5  pior retorno de 12 meses melhor que -35%

===========================================================================

Uso: .venv/Scripts/python.exe scripts/run_holdout_frozen.py [--only flow5]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from run_sleeve_validation import full_panels
from safety_lab import panel

from backtest.runner import run as run_bt
from core.config import BENCHMARK, WATCHLIST, BacktestConfig
from strategy.liquid_flow5 import LiquidFlow5
from strategy.liquid_sleeves5 import LiquidSleeves5
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
ANOS = 5

# Inicios MENSAIS de 2010-01 a 2013-12 — 48 janelas de 5 anos. O periodo de
# inicio nunca participou de nenhuma escolha desta sessao.
HOLDOUT = [pd.Timestamp(f"{y}-{m:02d}-01") for y in range(2010, 2014) for m in range(1, 13)]

# As cinco janelas em que TUDO foi decidido — so para comparacao lado a lado.
USADAS = [pd.Timestamp(s) for s in
          ("2014-01-01", "2016-01-01", "2018-01-01", "2020-01-01", "2021-08-19")]

GATES = {"G2_dd": -0.45, "G5_w12": -0.35}


def medir(factory, u, start: pd.Timestamp) -> dict | None:
    end = start + pd.DateOffset(years=ANOS)
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC)
    r = run_bt(u, factory(), cfg, start=str(start.date()), end=str(end.date()))
    eq = r.equity_curve
    if len(eq) < 250:
        return None
    return {"cagr": float(r.metrics["cagr"]), "dd": float(r.metrics["max_drawdown"]),
            "w12": float((eq / eq.shift(252) - 1).min()), "trades": len(r.trades)}


def ibov_janela(start: pd.Timestamp) -> dict:
    end = start + pd.DateOffset(years=ANOS)
    c = panel(BENCHMARK)["close"].loc[str(start.date()):str(end.date())].dropna()
    anos = (c.index[-1] - c.index[0]).days / 365.25
    return {"cagr": float((c.iloc[-1] / c.iloc[0]) ** (1 / anos) - 1),
            "dd": float((c / c.cummax() - 1).min()),
            "w12": float((c / c.shift(252) - 1).min()), "trades": 0}


def resumo(nome: str, rows: list[dict], ib: list[dict]) -> dict:
    g = np.array([m["cagr"] for m in rows])
    ibg = np.array([m["cagr"] for m in ib])
    r = {
        "nome": nome, "n": len(rows),
        "p05": float(np.percentile(g, 5)), "med": float(np.median(g)),
        "p95": float(np.percentile(g, 95)), "pior": float(g.min()),
        "dd": min(m["dd"] for m in rows), "w12": min(m["w12"] for m in rows),
        "neg": int((g < 0).sum()),
        "bate_ibov": int((g > ibg).sum()),
        "trades": int(np.median([m["trades"] for m in rows])),
    }
    r["G1"] = r["pior"] > 0
    r["G2"] = r["dd"] > GATES["G2_dd"]
    r["G3"] = r["med"] >= float(np.median(ibg))
    r["G5"] = r["w12"] > GATES["G5_w12"]
    return r


def linha(r: dict) -> str:
    portoes = "".join(k if r[k] else k.lower() for k in ("G1", "G2", "G3", "G5"))
    veredito = "PASSA" if all(r[k] for k in ("G1", "G2", "G3", "G5")) else "falha"
    return (f"{r['nome']:24s} {r['n']:4d} {r['p05']*100:7.1f}% {r['med']*100:7.1f}% "
            f"{r['p95']*100:7.1f}% {r['pior']*100:7.1f}% {r['dd']*100:7.1f}% "
            f"{r['w12']*100:7.1f}% {r['neg']:4d} {r['bate_ibov']:4d} "
            f"{r['trades']:5d}  {portoes:10s} {veredito}")


def main() -> None:
    alvo = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None

    print(__doc__.split("=" * 75)[1])
    print(f"\nHOLDOUT: {len(HOLDOUT)} janelas de {ANOS} anos, inicio mensal "
          f"{HOLDOUT[0].date()} .. {HOLDOUT[-1].date()}")
    print(f"COMPARACAO: as {len(USADAS)} janelas em que o desenho foi escolhido\n")

    wl = {t: panel(t) for t in WATCHLIST}
    wl[BENCHMARK] = panel(BENCHMARK)
    pool = full_panels()
    robos = {
        "flow5": ("liquid_flow5", LiquidFlow5, pool),
        "sleeves5": ("liquid_sleeves5", LiquidSleeves5, pool),
        "campeao": ("portfolio_dip2_hw40", DipTop1Portfolio, wl),
    }
    if alvo:
        robos = {alvo: robos[alvo]}

    hdr = (f"{'robo / conjunto':24s} {'n':>4s} {'p05':>8s} {'mediana':>8s} {'p95':>8s} "
           f"{'pior':>8s} {'DDpior':>8s} {'12m':>8s} {'neg':>4s} {'>ibov':>5s} {'trd':>5s}  "
           f"{'portoes':10s} veredito")

    for conjunto, starts in (("HOLDOUT 2010-2013", HOLDOUT), ("USADAS 2014-2021", USADAS)):
        ib = [ibov_janela(s) for s in starts]
        print(f"\n{'=' * len(hdr)}\n{conjunto}\n{'=' * len(hdr)}")
        print(hdr)
        print("-" * len(hdr))
        ibr = resumo("IBOV", ib, ib)
        print(linha(ibr))
        for chave, (nome, factory, u) in robos.items():
            rows = [m for s in starts if (m := medir(factory, u, s)) is not None]
            if not rows:
                continue
            print(linha(resumo(nome, rows, ib[: len(rows)])), flush=True)

    print("\nportoes em MAIUSCULA passaram, minuscula falharam (G1 pior>0, G2 DD>-45%, "
          "G3 mediana>=IBOV, G5 12m>-35%)")
    print("inicios antes de 2012 tem handicap de aquecimento declarado — ver docstring")


if __name__ == "__main__":
    main()
