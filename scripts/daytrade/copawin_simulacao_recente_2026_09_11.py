# -*- coding: utf-8 -*-
"""Simulacao do `copa_win` nas janelas RECENTES -- pedido do dono, 2026-09-11.

Duas janelas:
  * "desde segunda 07/09" -- 2026-09-07 foi FERIADO (Independencia), entao a
    semana comecou na TERCA 08/09. Sobram 3 pregoes completos (08, 09, 10);
    hoje (11/09) ainda esta ABERTO e fica de fora (342 barras contra ~562 de
    um pregao inteiro -- incluir faria o robo "achatar" no meio da tarde e
    contaminaria o numero com um fechamento que nao aconteceu);
  * os ultimos 30 pregoes completos.

Compara a config que ESTAVA no ar ate hoje (alvo_vol=19,0, alvo por `tp`
NATIVO) com a que entrou em producao hoje (alvo_vol=9,5, alvo por
ORDEM-LIMITE REAL fatiada), nos dois capitais que importam: R$250 (o que o
slot sombra tem agora) e R$600 (o piso declarado hoje em
`CopaWin.capital_minimo_recomendado_brl`).

AVISO QUE VALE MAIS QUE QUALQUER NUMERO DAQUI: 3 pregoes nao decidem nada.
Com ~2 trades/pregao isso da' algo entre 5 e 10 operacoes -- amostra em que
o intervalo de confianca do win% cobre praticamente todo o eixo. O criterio
do projeto (IC95% do win% contra o breakeven empirico, itens 6.22/6.23) sai
"indefinido" por construcao nesse tamanho. Isto e' OBSERVACAO do que teria
acontecido, nao validacao -- quem valida sao as janelas IS/OOS congeladas.
A janela de 30 pregoes tambem nao e' cega: ela esta DENTRO do OOS que ja'
foi usado (>=2026-06-13) e ainda por cima e' o pedaco mais recente dele.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_simulacao_recente_2026_09_11.py`
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
INICIO_SEMANA = pd.Timestamp("2026-09-07").date()
CAPITAIS = [250.0, 600.0]
EXTRAS = ("config", "acerto alvo", "flat%", "BE emp", "IC95 win", "s/trade",
          "caixa min", "pior op")


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95_proporcao(k: int, n: int):
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
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    parciais = sorted(d for d, n in contagem.items() if n < MIN_BARRAS_POR_PREGAO)

    print("base WIN@ M1 atualizada ate " + str(df.index.max()))
    print(str(len(completos)) + " pregoes completos, ultimo: " + str(completos[-1]))
    if parciais and parciais[-1] > completos[-1]:
        print("pregao EM ABERTO excluido: " + str(parciais[-1]) + " ("
              + str(contagem[parciais[-1]]) + " barras, incompleto)")

    semana = [d for d in completos if d >= INICIO_SEMANA]
    ultimos30 = completos[-30:]
    janelas = {
        "desde 07/09": semana,
        "ultimos 30 pregoes": ultimos30,
    }
    print("\ndesde 07/09  -> " + str(len(semana)) + " pregoes: "
          + ", ".join(str(d) for d in semana))
    print("           (07/09 foi FERIADO -- Independencia; a semana comecou na terca)")
    print("ultimos 30   -> " + str(ultimos30[0]) + " a " + str(ultimos30[-1]))

    configs = {
        "ANTIGA (alvo 19,0 tp nativo)": dict(alvo_vol=19.0, fatiar=False),
        "ATUAL (alvo 9,5 limite real)": dict(alvo_vol=9.5, fatiar=True),
    }

    for nome_janela, dias in janelas.items():
        alvo_dias = set(dias)
        bars = df[[d in alvo_dias for d in df.index.date]]
        for capital in CAPITAIS:
            linhas = []
            print("\n\n===== " + nome_janela + " (" + str(len(dias))
                  + " pregoes) - capital R$ " + br(capital, 0) + " =====", flush=True)
            for nome_cfg, c in configs.items():
                strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
                strat.alvo_vol = c["alvo_vol"]
                strat.fatiar_saida_alvo = c["fatiar"]
                cfg = config_for(
                    profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
                    initial_capital=capital,
                    target_fills_as_maker=strat.target_fills_as_maker,
                    limit_fill_capped_by_volume=True,
                    queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
                )
                res = run_intraday_backtest(bars, strat, cfg)
                ts = list(res.trades)
                n = len(ts)
                ganhos = [t.pnl_brl for t in ts if t.pnl_brl > 0]
                perdas = [t.pnl_brl for t in ts if t.pnl_brl <= 0]
                lo, hi = ic95_proporcao(len(ganhos), n)
                g = sum(ganhos) / len(ganhos) if ganhos else 0.0
                pm = abs(sum(perdas) / len(perdas)) if perdas else 0.0
                be = pm / (g + pm) if (g + pm) > 0 else float("nan")
                alvo = sum(1 for t in ts if t.exit_reason.value == "target")
                flat = sum(1 for t in ts if t.exit_reason.value == "forced_flatten")
                com = len({t.entry_ts.date() for t in ts})
                eq = res.equity_curve
                cmin = float(eq.min()) if eq is not None and not eq.empty else capital
                linhas.append(linha_de_resultado(
                    nome_cfg, res, capital,
                    extras={
                        "config": "antiga" if not c["fatiar"] else "ATUAL",
                        "acerto alvo": br(100 * alvo / n, 1) + "%" if n else "--",
                        "flat%": br(100 * flat / n, 1) + "%" if n else "--",
                        "BE emp": br(100 * be, 2) + "%" if be == be else "--",
                        "IC95 win": "[" + br(100 * lo, 1) + ";" + br(100 * hi, 1) + "]",
                        "s/trade": str(len(dias) - com) + "/" + str(len(dias)),
                        "caixa min": br(cmin),
                        "pior op": br(min((t.pnl_brl for t in ts), default=0.0)),
                    },
                ))
            print(tabela(linhas, extras=EXTRAS), flush=True)

    # ---- o detalhe operacao a operacao da semana ------------------------
    print("\n\n===== OPERACAO A OPERACAO, desde 07/09, config ATUAL, R$600 =====")
    alvo_dias = set(semana)
    bars = df[[d in alvo_dias for d in df.index.date]]
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=600.0, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    print("entrada".ljust(18) + "saida".ljust(18) + "lado".ljust(7) + "qtd".rjust(4)
          + "motivo".rjust(16) + "R$".rjust(11) + "acumulado".rjust(12))
    acum = 0.0
    for t in res.trades:
        acum += t.pnl_brl
        print(str(t.entry_ts.tz_convert("America/Sao_Paulo"))[:16].ljust(18)
              + str(t.exit_ts.tz_convert("America/Sao_Paulo"))[:16].ljust(18)
              + t.side.ljust(7) + str(t.quantity).rjust(4)
              + t.exit_reason.value.rjust(16) + br(t.pnl_brl).rjust(11)
              + br(acum).rjust(12))
    if not res.trades:
        print("  (nenhuma operacao)")


if __name__ == "__main__":
    main()
