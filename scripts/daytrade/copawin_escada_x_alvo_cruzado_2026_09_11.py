# -*- coding: utf-8 -*-
"""ESCADA DE PERDA x ALVO MENOR, juntas -- a medicao que faltava.

Ordem do dono, 2026-09-11: fechar a decisao. As duas mudancas foram medidas
SEPARADAS nesta mesma data e cada uma resolve metade do problema, estragando
a outra metade:

  * a ESCADA (`teto_perda_abs_brl`, `copawin_escada_perda_sweep_2026_09_11`)
    acaba com o zeramento -- a pior operacao cai de -R$446,50 para -R$159,50
    e o caixa nunca fica negativo -- mas o robo fica parado em 85 de 129
    pregoes e, no capital de folga, PIORA o MaxDD (-51,0% -> -85,8%): ela
    limita a perda de UM trade, nao a de uma SEQUENCIA, e com o stop mais
    curto a sequencia fica mais longa;
  * o ALVO A 50% com ordem-limite real (`copawin_alvo_menor_sweep_` +
    `copawin_alvo_fatiado_fila_sensibilidade_`) faz o robo operar todos os
    pregoes partindo de R$250 e tira a dependencia do fechamento do dia (a
    contribuicao do achatamento para o lucro cai de 114,1% para ~5%), mas o
    caixa marcado a mercado desce a R$23,10 no IS (MaxDD -96,3%).

A PERGUNTA DESTA RODADA, e' uma so': a escada devolve a folga de caixa que o
alvo menor consome, SEM desfazer o ganho dele?

COMO A CELULA DE PRODUCAO E' ESCOLHIDA -- isto importa mais que a grade. O
par candidato NAO sai de "qual celula rendeu mais": sai da REGRA do dono
(alvo a 50% do sugerido; perda por trade ate' 50% da carteira, que no capital
real de R$250 da' ABS=R$125). A grade em volta existe para dizer se esse par
mora num PLATO ou num PENHASCO -- e essa e' a unica pergunta que ela responde.
Escolher a melhor celula da grade seria ajustar ao sorteio: ja' foi medido
nesta mesma data que, com o caixa no piso, celulas vizinhas discordam por
ordem de grandeza porque o que decide a janela e' se as PRIMEIRAS operacoes
ganharam (item 6.29).

CRITERIO DE ACEITE, declarado ANTES de ver o resultado:
  1. veredito POSITIVO (IC95% do win% acima do breakeven empirico) nas DUAS
     janelas, no capital REAL de R$250;
  2. 0 pregoes sem trade nas duas janelas -- janela em que o robo parou e'
     censurada e nao serve de prova;
  3. caixa minimo acima da MARGEM CRUA (R$100 no WIN@) nas duas janelas. E'
     o piso de SOBREVIVENCIA, nao o de partida (CLAUDE.md);
  4. o par da REGRA nao pode ser um pico isolado -- os vizinhos imediatos
     tem de andar na mesma direcao.

Se algum falhar, o par nao vai para producao e o relatorio diz qual falhou.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_escada_x_alvo_cruzado_2026_09_11.py`
"""
from __future__ import annotations

import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
OOS_INICIO = pd.Timestamp("2026-06-13").date()
ALVO_VOL_PRODUCAO = 19.0
MARGEM_CRUA_WIN = 100.0

#: fracao do alvo pedido. 1,00 = producao de hoje.
FRACOES_ALVO = [1.00, 0.70, 0.50, 0.30]
#: teto ABSOLUTO da escada. `None` = escada desligada.
TETOS = [None, 200.0, 125.0, 75.0]
#: R$250 e' o capital REAL do WIN@ (CLAUDE.md) e e' onde a decisao vale.
#: R$750 (piso medido do robo) e R$3.000 leem a geometria sem censura.
CAPITAIS = [250.0, 750.0, 3_000.0]
#: o par que sai da REGRA do dono, nao da grade.
PAR_DA_REGRA = (0.50, 125.0)
EXTRAS = ("alvo%", "escada", "acerto alvo", "flat%", "BE emp", "IC95 win",
          "s/trade", "caixa min", "pior op")

_BARS_CACHE: dict = {}


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


def _bars(janela: str):
    if janela not in _BARS_CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        df = df[[d in completos for d in df.index.date]]
        if janela == "IS":
            df = df[[d < OOS_INICIO for d in df.index.date]]
        else:
            df = df[[d >= OOS_INICIO for d in df.index.date]]
        _BARS_CACHE[janela] = df
    return _BARS_CACHE[janela]


def _roda(janela: str, capital: float, fracao: float, teto):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars(janela)
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    strat.alvo_vol = ALVO_VOL_PRODUCAO * fracao
    # o alvo por ordem-limite REAL e' premissa desta rodada, nao variavel: o
    # `tp` nativo e' gatilho varrido a mercado e o CLAUDE.md o proibe.
    strat.fatiar_saida_alvo = True
    if teto is not None:
        strat.teto_perda_abs_brl = float(teto)

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        # declarado explicito: WIN@ nao tem fidelidade calibrada, e herdar 0,0
        # em silencio foi o erro que viciou um mes de medicao (item 3.8)
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    n = len(trades)
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    lo, hi = ic95_proporcao(len(ganhos), n)
    g = sum(ganhos) / len(ganhos) if ganhos else 0.0
    pm = abs(sum(perdas) / len(perdas)) if perdas else 0.0
    be = pm / (g + pm) if (g + pm) > 0 else float("nan")
    alvo = sum(1 for t in trades if t.exit_reason.value == "target")
    flat = sum(1 for t in trades if t.exit_reason.value == "forced_flatten")

    pregoes = len(set(pd.DatetimeIndex(bars.index).date))
    com = len({t.entry_ts.date() for t in trades})
    eq = res.equity_curve
    caixa_min = float(eq.min()) if eq is not None and not eq.empty else capital
    pior = min((t.pnl_brl for t in trades), default=0.0)

    esc = "DESLIGADA" if teto is None else "ABS " + br(teto, 0)
    nome = "alvo " + br(100 * fracao, 0) + "% - escada " + esc
    linha = linha_de_resultado(
        janela + " " + br(capital, 0) + " " + nome, res, capital,
        extras={
            "alvo%": br(100 * fracao, 0) + "%",
            "escada": esc,
            "acerto alvo": br(100 * alvo / n, 1) + "%" if n else "--",
            "flat%": br(100 * flat / n, 1) + "%" if n else "--",
            "BE emp": br(100 * be, 2) + "%" if be == be else "--",
            "IC95 win": "[" + br(100 * lo, 1) + ";" + br(100 * hi, 1) + "]",
            "s/trade": str(pregoes - com) + "/" + str(pregoes),
            "caixa min": br(caixa_min),
            "pior op": br(pior),
        },
    )
    return dict(
        janela=janela, capital=capital, fracao=fracao, teto=teto, nome=nome,
        linha=linha, dt=dt, n=n, win=(len(ganhos) / n if n else 0.0),
        be=be, lo=lo, hi=hi, acerto_alvo=(alvo / n if n else 0.0),
        flat=(flat / n if n else 0.0), liquido=sum(t.pnl_brl for t in trades),
        sem_trade=pregoes - com, pregoes=pregoes, caixa_min=caixa_min, pior=pior,
        veredito=("POSITIVO" if (n and lo > be) else
                  "NEGATIVO" if (n and hi < be) else "indefinido"),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import tabela

    tarefas = [(j, c, fr, t) for j in ("IS", "OOS") for c in CAPITAIS
               for fr in FRACOES_ALVO for t in TETOS]
    print(str(len(tarefas)) + " celulas: " + str(len(FRACOES_ALVO)) + " alvos x "
          + str(len(TETOS)) + " escadas x " + str(len(CAPITAIS)) + " capitais x 2 janelas",
          flush=True)
    print("alvo por ordem-limite REAL fatiada em TODAS as celulas (premissa, nao variavel)\n",
          flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            be = br(100 * r["be"], 1) if r["be"] == r["be"] else "--"
            marca = " <<< PAR DA REGRA" if (r["fracao"], r["teto"]) == PAR_DA_REGRA else ""
            print("[" + str(len(resultados)).rjust(2) + "/" + str(len(tarefas)) + "] "
                  + r["janela"].rjust(3) + " cap " + br(r["capital"], 0).rjust(8) + " "
                  + r["nome"].ljust(34)
                  + " liq " + br(r["liquido"]).rjust(12)
                  + " n=" + str(r["n"]).ljust(4)
                  + " s/trade " + (str(r["sem_trade"]) + "/" + str(r["pregoes"])).rjust(7)
                  + " caixa min " + br(r["caixa_min"]).rjust(9)
                  + " pior " + br(r["pior"]).rjust(9)
                  + " win " + (br(100 * r["win"], 1) + "%").rjust(6)
                  + " BE " + (be + "%").rjust(6)
                  + " " + r["veredito"] + marca, flush=True)

    for janela in ("IS", "OOS"):
        for capital in CAPITAIS:
            sel = [r for r in resultados if r["janela"] == janela and r["capital"] == capital]
            sel.sort(key=lambda r: (-r["fracao"], -(r["teto"] or 1e9)))
            print("\n\n===== " + janela + " - capital R$ " + br(capital, 0) + " =====", flush=True)
            print(tabela([r["linha"] for r in sel], extras=EXTRAS), flush=True)

    # ---- o criterio de aceite, aplicado --------------------------------
    print("\n\n===== CRITERIO DE ACEITE NO CAPITAL REAL (R$ 250) =====")
    print("declarado antes de medir: POSITIVO nas duas janelas, 0 pregoes sem trade")
    print("nas duas, caixa minimo acima da margem crua de R$ " + br(MARGEM_CRUA_WIN, 0)
          + " nas duas.\n")
    print("alvo".rjust(6) + "escada".rjust(12) + "  " + "IS".center(34) + "  " + "OOS".center(34)
          + "  aceite")
    print(" " * 18 + "  " + "liq / s-trade / caixa / vered".center(34)
          + "  " + "liq / s-trade / caixa / vered".center(34))
    for fr in FRACOES_ALVO:
        for t in TETOS:
            cel = {}
            for j in ("IS", "OOS"):
                m = [r for r in resultados if r["capital"] == 250.0 and r["fracao"] == fr
                     and r["teto"] == t and r["janela"] == j]
                cel[j] = m[0] if m else None
            if not all(cel.values()):
                continue
            ok = all(
                c["veredito"] == "POSITIVO" and c["sem_trade"] == 0
                and c["caixa_min"] > MARGEM_CRUA_WIN
                for c in cel.values()
            )
            def desc(c):
                return (br(c["liquido"], 0) + " / " + str(c["sem_trade"]) + "/"
                        + str(c["pregoes"]) + " / " + br(c["caixa_min"], 0) + " / "
                        + c["veredito"][:5])
            marca = " <<< REGRA" if (fr, t) == PAR_DA_REGRA else ""
            print((br(100 * fr, 0) + "%").rjust(6)
                  + ("DESLIG." if t is None else "ABS " + br(t, 0)).rjust(12) + "  "
                  + desc(cel["IS"]).center(34) + "  " + desc(cel["OOS"]).center(34)
                  + "  " + ("PASSA" if ok else "falha") + marca)


if __name__ == "__main__":
    main()
