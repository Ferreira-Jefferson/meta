"""Diagnostico que precede o TETO DE PERDA POR TRADE do `CopaWin` (WIN@).

Pedido do dono (2026-09-11): "o stop dela e' desproporcional ao tamanho da
carteira, acho que deveria ser com ate 50% da carteira e ir diminuindo
conforme a carteira aumenta para representar no maximo 5%".

Antes de construir a escada, tres perguntas que decidem o DESENHO dela, e
que nenhuma medicao anterior do repo responde:

  1. QUANTO custa o stop hoje, por contrato, em R$ -- distribuicao, nao
     media (item 6.x: numero sem dispersao nao e' medida). E' esse numero
     que a escada precisa cortar.
  2. Por onde os trades SAEM. O dono suspeita que a estrategia "se baseia
     muito no fechamento do dia" -- se a maioria sai por FORCED_FLATTEN
     (achatamento de fim de pregao), a suspeita esta' certa e o resultado
     depende de onde o dia fechou, nao da geometria.
  3. Quantos trades teriam sido RECUSADOS por um teto de perda em R$, em
     cada nivel de capital -- ou seja, quanto da estrategia a escada apaga
     antes mesmo de medir o que ela faz com o resultado.

Roda no capital NAO censurado (R$3.000 -- o piso real do robo e' R$750, ver
`copawin-e-gremah-piso-capital-2026-08-29`) de proposito: aqui a pergunta e'
"como e' a populacao de trades desta geometria", e no piso real a populacao
nao existe (R$250 da' 2 trades em 182 pregoes).

RESSALVAS que viajam com qualquer numero daqui:
  * WIN@ NAO tem fidelidade de execucao calibrada (`backtest.intraday.
    fidelidade.FIDELIDADE` so' tem WDO@), entao entrada E saida enchem no
    primeiro toque -- o motor otimista de ate 2026-09-08. A linha sai
    carimbada `fila NAO CALIBRADA`.
  * a janela OOS do WIN@ (>=2026-06-13) ja' foi gasta duas vezes (memoria
    `copa-oos-gasto-2026-08-26` e a ressalva em `_KWARGS_PADRAO`).

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_teto_perda_diagnostico_2026_09_11.py`
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
CAPITAL_DIAGNOSTICO = 3_000.0
MIN_BARRAS_POR_PREGAO = 400
OOS_INICIO = pd.Timestamp("2026-06-13").date()
NIVEIS_CARTEIRA = [250.0, 375.0, 500.0, 750.0, 1_000.0, 2_500.0, 5_000.0, 10_000.0]


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float) -> str:
    return f"{br(100 * v, 1)}%"


def quantis(vals: list[float]) -> dict[str, float]:
    s = pd.Series(vals)
    return {
        "n": len(s), "media": s.mean(), "p05": s.quantile(0.05),
        "p25": s.quantile(0.25), "p50": s.median(), "p75": s.quantile(0.75),
        "p95": s.quantile(0.95), "max": s.max(), "desvio": s.std(),
    }


def main() -> None:
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.registry import get_daytrade_robot

    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    bars = df[[d in completos for d in df.index.date]]
    pregoes = sorted(completos)
    print(f"WIN@ M1: {len(pregoes)} pregoes completos, {pregoes[0]} -> {pregoes[-1]}", flush=True)

    profile = profile_for(SYMBOL)
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL_DIAGNOSTICO,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    print(f"fila calibrada? {cfg.costs.fidelidade_calibrada} | "
          f"queue_ent={cfg.queue_ahead_qty} queue_sai={cfg.exit_queue_ahead_qty} | "
          f"deslize alvo nativo={cfg.costs.target_slippage_ticks}t", flush=True)

    res = run_intraday_backtest(bars, strat, cfg)
    trades = res.trades
    print(f"\ncapital do diagnostico R$ {br(CAPITAL_DIAGNOSTICO)} -> {len(trades)} trades\n", flush=True)

    # ---------- 2. por onde saem -----------------------------------------
    def mix(ts) -> None:
        c = Counter(t.exit_reason.value for t in ts)
        tot = max(1, len(ts))
        print(f"    {'motivo':<18} {'n':>5} {'%':>7} {'R$/op':>10} {'liquido':>12}")
        for motivo, n in c.most_common():
            sub = [t for t in ts if t.exit_reason.value == motivo]
            liq = sum(t.pnl_brl for t in sub)
            print(f"    {motivo:<18} {n:>5} {pct(n/tot):>7} {br(liq/n):>10} {br(liq):>12}")
        liq = sum(t.pnl_brl for t in ts)
        print(f"    {'TOTAL':<18} {len(ts):>5} {'':>7} {br(liq/tot):>10} {br(liq):>12}")

    is_t = [t for t in trades if t.exit_ts.date() < OOS_INICIO]
    oos_t = [t for t in trades if t.exit_ts.date() >= OOS_INICIO]
    print("POR ONDE OS TRADES SAEM -- historico completo")
    mix(trades)
    print(f"\n  IS (< {OOS_INICIO})")
    mix(is_t)
    print(f"\n  OOS (>= {OOS_INICIO})")
    mix(oos_t)

    # ---------- 1. quanto custa a perda, por CONTRATO ---------------------
    perdas_por_contrato = [abs(t.pnl_brl) / t.quantity for t in trades if t.pnl_brl < 0]
    perdas_stop = [abs(t.pnl_brl) / t.quantity for t in trades
                   if t.pnl_brl < 0 and t.exit_reason.value == "stop"]
    ganhos_por_contrato = [t.pnl_brl / t.quantity for t in trades if t.pnl_brl > 0]

    print("\n\nQUANTO CUSTA UMA PERDA, POR CONTRATO (R$)")
    print(f"    {'populacao':<22} {'n':>5} {'media':>9} {'p05':>9} {'p25':>9} "
          f"{'p50':>9} {'p75':>9} {'p95':>9} {'max':>9} {'desvio':>9}")
    for nome, vals in (("toda perda", perdas_por_contrato),
                       ("so' saida por STOP", perdas_stop),
                       ("todo ganho", ganhos_por_contrato)):
        q = quantis(vals)
        print(f"    {nome:<22} {q['n']:>5} " + " ".join(
            f"{br(q[k]):>9}" for k in ("media", "p05", "p25", "p50", "p75", "p95", "max", "desvio")))

    # ---------- 3. o que um teto de perda apagaria ------------------------
    print("\n\nO QUE A ESCADA APAGA -- fracao das PERDAS acima do teto, por carteira")
    print("    escada: teto_R$ = min(50% x caixa, max(TETO_ABS, 5% x caixa)), TETO_ABS = R$125")
    print(f"    {'carteira':>10} {'teto R$':>10} {'%da carteira':>13} "
          f"{'perdas acima':>13} {'% das perdas':>13} {'% de TODOS':>12}")
    TETO_ABS = 125.0
    n_perdas = max(1, len(perdas_por_contrato))
    for cash in NIVEIS_CARTEIRA:
        teto = min(0.50 * cash, max(TETO_ABS, 0.05 * cash))
        acima = sum(1 for p in perdas_por_contrato if p > teto)
        print(f"    {br(cash):>10} {br(teto):>10} {pct(teto/cash):>13} "
              f"{acima:>13} {pct(acima/n_perdas):>13} {pct(acima/max(1,len(trades))):>12}")

    # ---------- contexto: quantos contratos cabem -------------------------
    qtds = Counter(t.quantity for t in trades)
    print(f"\n\nCONTRATOS POR ENTRADA no diagnostico (R$ {br(CAPITAL_DIAGNOSTICO)}): "
          + ", ".join(f"{q}x:{n}" for q, n in sorted(qtds.items())))


if __name__ == "__main__":
    main()
