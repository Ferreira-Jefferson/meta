# -*- coding: utf-8 -*-
"""`copa_win` de PRODUCAO nas ultimas duas semanas, incluindo hoje (11/09).

Pedido do dono, 2026-09-11. Roda a config que esta em producao desde hoje
(`alvo_vol=9,5` + alvo por ORDEM-LIMITE REAL fatiada) nos pregoes de
2026-09-01 a 2026-09-11.

DUAS RESSALVAS que mudam como o numero deve ser lido, e nenhuma e' detalhe:

  1. **HOJE (11/09) AINDA ESTA ABERTO** -- 367 barras contra ~562 de um
     pregao inteiro, ultima as 15:09 BRT, faltam ~3 horas. Foi incluido
     porque o dono pediu, mas o motor ACHATA qualquer posicao aberta na
     ultima barra DISPONIVEL, que nao e' o fechamento real. O numero de hoje
     e' provisorio nos dois sentidos: uma posicao que seria fechada pelo alvo
     as 16h aparece aqui como achatamento, e operacoes que ainda vao
     acontecer nao existem. A tabela separa "ate 10/09" de "com hoje"
     exatamente para o dono ver quanto do total depende de um pregao
     incompleto.

  2. **8 pregoes nao validam nada.** Com ~2,5 operacoes por pregao isso da'
     algo perto de 20 operacoes -- amostra em que o IC95% do win% cobre quase
     todo o eixo, e o criterio do projeto (IC contra breakeven empirico) sai
     "indefinido" por construcao. Isto e' OBSERVACAO do que teria acontecido,
     nao evidencia sobre a estrategia. Quem valida sao as janelas IS/OOS
     congeladas, e elas ja' foram medidas.

CAPITAIS. R$3.000 e' o piso declarado do robo
(`CopaWin.capital_minimo_recomendado_brl`, primeiro nivel em que 100% das
datas de inicio testadas sobrevivem). R$250 e' o que o slot sombra tem hoje
-- roda junto para o dono ver a diferenca que o caixa faz na MESMA janela,
que e' a coisa que este robo mais castiga.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_duas_semanas_2026_09_11.py`
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
INICIO = pd.Timestamp("2026-09-01").date()
HOJE = pd.Timestamp("2026-09-11").date()
CAPITAIS = [250.0, 3_000.0]
EXTRAS = ("acerto alvo", "flat%", "BE emp", "IC95 win", "s/trade", "caixa min", "pior op")


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int):
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def main() -> None:
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado, tabela
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.registry import get_daytrade_robot

    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    dias = sorted(d for d in contagem.index if d >= INICIO)

    print("config de PRODUCAO: alvo_vol=9,5 + alvo por ordem-limite real fatiada")
    print("base M1 do WIN@ atualizada ate " + str(df.index.max().tz_convert(
        "America/Sao_Paulo")) + " BRT\n")
    print("pregao        barras   estado")
    for d in dias:
        n = int(contagem[d])
        print("  " + str(d) + " " + d.strftime("%a") + "  " + str(n).rjust(5) + "   "
              + ("completo" if n >= 400 else "EM ABERTO (~"
                 + br(100 * n / 562, 0) + "% do pregao)"))

    def roda(dias_alvo, capital):
        alvo = set(dias_alvo)
        bars = df[[d in alvo for d in df.index.date]]
        strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
        cfg = config_for(
            profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
            initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
            limit_fill_capped_by_volume=True,
            queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
        )
        return run_intraday_backtest(bars, strat, cfg), len(alvo)

    def linha(rot, res, pregoes, capital):
        ts = list(res.trades)
        n = len(ts)
        ganhos = [t.pnl_brl for t in ts if t.pnl_brl > 0]
        perdas = [t.pnl_brl for t in ts if t.pnl_brl <= 0]
        lo, hi = ic95(len(ganhos), n)
        g = sum(ganhos) / len(ganhos) if ganhos else 0.0
        pm = abs(sum(perdas) / len(perdas)) if perdas else 0.0
        be = pm / (g + pm) if (g + pm) > 0 else float("nan")
        alvo = sum(1 for t in ts if t.exit_reason.value == "target")
        flat = sum(1 for t in ts if t.exit_reason.value == "forced_flatten")
        com = len({t.entry_ts.date() for t in ts})
        eq = res.equity_curve
        cmin = float(eq.min()) if eq is not None and not eq.empty else capital
        return linha_de_resultado(rot, res, capital, extras={
            "acerto alvo": br(100 * alvo / n, 1) + "%" if n else "--",
            "flat%": br(100 * flat / n, 1) + "%" if n else "--",
            "BE emp": br(100 * be, 2) + "%" if be == be else "--",
            "IC95 win": "[" + br(100 * lo, 1) + ";" + br(100 * hi, 1) + "]",
            "s/trade": str(pregoes - com) + "/" + str(pregoes),
            "caixa min": br(cmin),
            "pior op": br(min((t.pnl_brl for t in ts), default=0.0)),
        })

    ate_ontem = [d for d in dias if d < HOJE]
    for capital in CAPITAIS:
        print("\n\n===== capital R$ " + br(capital, 0) + " =====")
        linhas = []
        for rot, ds in (("ate 10/09 (7 pregoes completos)", ate_ontem),
                        ("COM hoje 11/09 (8, o ultimo em aberto)", dias)):
            res, p = roda(ds, capital)
            linhas.append(linha(rot, res, p, capital))
        print(tabela(linhas, extras=EXTRAS))

    # ---- pregao a pregao e operacao a operacao, no capital de producao ----
    print("\n\n===== PREGAO A PREGAO, capital R$ 3.000 (o piso declarado) =====")
    res, _ = roda(dias, 3_000.0)
    por_dia = {}
    for t in res.trades:
        por_dia.setdefault(t.entry_ts.date(), []).append(t)
    print("pregao        ops        R$ do dia     acumulado")
    acum = 0.0
    for d in dias:
        ts = por_dia.get(d, [])
        dia = sum(t.pnl_brl for t in ts)
        acum += dia
        marca = "   <- EM ABERTO" if d == HOJE else ""
        print("  " + str(d) + " " + d.strftime("%a") + str(len(ts)).rjust(6)
              + br(dia).rjust(16) + br(acum).rjust(14) + marca)

    print("\n===== OPERACAO A OPERACAO =====")
    print("entrada           saida             lado   qtd          motivo"
          + "          R$   acumulado")
    acum = 0.0
    for t in res.trades:
        acum += t.pnl_brl
        print(str(t.entry_ts.tz_convert("America/Sao_Paulo"))[:16].ljust(18)
              + str(t.exit_ts.tz_convert("America/Sao_Paulo"))[:16].ljust(18)
              + t.side.ljust(7) + str(t.quantity).rjust(4)
              + t.exit_reason.value.rjust(16) + br(t.pnl_brl).rjust(12)
              + br(acum).rjust(12))
    if not res.trades:
        print("  (nenhuma operacao)")


if __name__ == "__main__":
    main()
