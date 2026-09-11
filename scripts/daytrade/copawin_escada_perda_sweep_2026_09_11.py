# -*- coding: utf-8 -*-
"""Varredura da ESCADA DE PERDA MAXIMA por trade do `CopaWin` (WIN@).

Pedido do dono (2026-09-11): "o stop dela e' desproporcional ao tamanho da
carteira, acho que deveria ser com ate 50% da carteira e ir diminuindo
conforme a carteira aumenta para representar no maximo 5% ... para nao ser
uma estrategia que ganha muito, mas quando perde, perde tudo".

A escada (`CopaWin.teto_perda_brl`) e' `min(50% x caixa, max(ABS, 5% x
caixa))` -- um parametro para varrer (`ABS`), tres regimes. Ela corta a
DISTANCIA DO STOP, nao a quantidade: no caixa real do WIN@ cabe 1 contrato e
o piso de `quantidade_por_entrada` e' 1, entao cortar quantidade nao corta
nada (5% de R$250 = R$12,50 contra stop MEDIANO de R$293,00 medido em
`copawin_teto_perda_diagnostico_2026_09_11.py`).

O QUE ESTA VARREDURA TEM DE RESPONDER, e a razao de ela existir em vez de a
escada ja entrar ligada: cortar o stop MUDA a estrategia medida. O precedente
que manda duvidar e' o `wdo_orb.alvo_multiplo` -- la' a geometria fixa foi
REFUTADA de forma monotonica, e o mecanismo ("com stop largo o perdedor sai
pelo relogio com perda PEQUENA; com stop apertado o mesmo trade sai no stop
CHEIO") e' exatamente o que pode acontecer aqui, onde 56,1% das saidas sao
por achatamento de fim de pregao.

METODO, emprestado do que a rodada do `wdo_orb` estabeleceu:
  * capital REAL do instrumento, nunca nocional (CLAUDE.md);
  * passada CRONOLOGICA continua -- o caixa de um pregao e' o que sobrou do
    anterior. E' o unico regime em que "travar por capital" pode aparecer;
  * veredito por IC95% do win% contra o BREAKEVEN EMPIRICO, nunca por
    liquido sozinho (itens 6.22/6.23);
  * pregoes SEM TRADE reportados junto -- janela onde o robo parou e'
    censurada e mede a restricao, nao o edge.

RESSALVAS que viajam com qualquer numero daqui:
  * WIN@ NAO tem fidelidade de execucao calibrada (so' WDO@ esta em
    `backtest.intraday.fidelidade.FIDELIDADE`), entao entrada E saida enchem
    no primeiro toque. Duas pernas otimistas, tamanho desconhecido;
  * a janela OOS do WIN@ (>=2026-06-13) ja' foi gasta duas vezes.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_escada_perda_sweep_2026_09_11.py`
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

#: `None` = escada DESLIGADA (a producao de hoje, linha de base).
TETOS_ABS = [None, 400.0, 300.0, 250.0, 200.0, 150.0, 125.0, 100.0, 75.0, 50.0]
CAPITAIS = [250.0, 750.0, 3_000.0]
#: colunas extras desta rodada -- SEMPRE depois das 12 da base (CLAUDE.md).
EXTRAS = ("BE emp", "IC95 win", "s/trade", "caixa min", "pior op")

_BARS_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95_proporcao(k: int, n: int):
    """IC95% de Wilson para uma proporcao -- serve em n pequeno, ao contrario
    do intervalo normal ingenuo."""
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
        elif janela == "OOS":
            df = df[[d >= OOS_INICIO for d in df.index.date]]
        _BARS_CACHE[janela] = df
    return _BARS_CACHE[janela]


def _roda(janela: str, capital: float, teto_abs):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars(janela)
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    if teto_abs is not None:
        # a escada SUBSTITUI o percentual plano (ver `quantidade_por_entrada`)
        strat.teto_perda_abs_brl = float(teto_abs)
    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    n = len(trades)
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    win = len(ganhos) / n if n else 0.0
    lo, hi = ic95_proporcao(len(ganhos), n)
    g_med = sum(ganhos) / len(ganhos) if ganhos else 0.0
    p_med = abs(sum(perdas) / len(perdas)) if perdas else 0.0
    be = p_med / (g_med + p_med) if (g_med + p_med) > 0 else float("nan")

    pregoes_total = len(set(pd.DatetimeIndex(bars.index).date))
    pregoes_com_trade = len({t.entry_ts.date() for t in trades})
    equity = res.equity_curve
    caixa_min = float(equity.min()) if equity is not None and not equity.empty else capital

    nome = "BASE (sem escada)" if teto_abs is None else "ABS R$ " + br(teto_abs, 0)
    be_txt = br(100 * be, 2) + "%" if be == be else "--"
    linha = linha_de_resultado(
        janela + " " + br(capital, 0) + " " + nome, res, capital,
        extras={
            "BE emp": be_txt,
            "IC95 win": "[" + br(100 * lo, 1) + ";" + br(100 * hi, 1) + "]",
            "s/trade": str(pregoes_total - pregoes_com_trade) + "/" + str(pregoes_total),
            "caixa min": br(caixa_min),
            "pior op": br(min((t.pnl_brl for t in trades), default=0.0)),
        },
    )
    return dict(
        janela=janela, capital=capital, teto_abs=teto_abs, nome=nome, linha=linha,
        n=n, win=win, be=be, lo=lo, hi=hi, dt=dt,
        liquido=sum(t.pnl_brl for t in trades),
        sem_trade=pregoes_total - pregoes_com_trade, pregoes=pregoes_total,
        caixa_min=caixa_min,
        pior=min((t.pnl_brl for t in trades), default=0.0),
        veredito=("POSITIVO" if (n and lo > be) else
                  "NEGATIVO" if (n and hi < be) else "indefinido"),
    )


def _unidade(args):
    janela, capital, teto_abs = args
    buf = StringIO()
    with redirect_stdout(buf):
        r = _roda(janela, capital, teto_abs)
    r["stdout"] = buf.getvalue()
    return r


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import tabela

    tarefas = [(j, c, t) for j in ("IS", "OOS") for c in CAPITAIS for t in TETOS_ABS]
    print(str(len(tarefas)) + " celulas: " + str(len(TETOS_ABS)) + " tetos x "
          + str(len(CAPITAIS)) + " capitais x 2 janelas", flush=True)
    print("cada uma imprime assim que termina; a tabela ordenada vem no fim\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            be_txt = br(100 * r["be"], 1) if r["be"] == r["be"] else "--"
            print("[" + str(len(resultados)).rjust(2) + "/" + str(len(tarefas)) + "] "
                  + r["janela"].rjust(3) + " cap " + br(r["capital"], 0).rjust(8) + " "
                  + r["nome"].ljust(18)
                  + " liq " + br(r["liquido"]).rjust(12)
                  + "  n=" + str(r["n"]).ljust(4)
                  + " win " + br(100 * r["win"], 1).rjust(5) + "%"
                  + "  BE " + be_txt.rjust(5) + "%"
                  + "  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"])
                  + "  caixa min " + br(r["caixa_min"]).rjust(9)
                  + "  pior " + br(r["pior"]).rjust(9)
                  + "  " + r["veredito"]
                  + "  (" + str(round(r["dt"])) + "s)", flush=True)

    for janela in ("IS", "OOS"):
        for capital in CAPITAIS:
            sel = [r for r in resultados if r["janela"] == janela and r["capital"] == capital]
            sel.sort(key=lambda r: (r["teto_abs"] is not None, -(r["teto_abs"] or 0)))
            print("\n\n===== " + janela + " - capital R$ " + br(capital, 0) + " =====", flush=True)
            print(tabela([r["linha"] for r in sel], extras=EXTRAS), flush=True)

    print("\n\n===== VEREDITO POR CELULA (IC95% do win% contra o breakeven empirico) =====")
    print("janela".rjust(6) + "capital".rjust(10) + "teto".rjust(19) + "n".rjust(6)
          + "win%".rjust(8) + "BE%".rjust(8) + "IC95".rjust(17) + "veredito".rjust(13))
    for r in sorted(resultados, key=lambda r: (r["janela"], r["capital"],
                                               -(r["teto_abs"] or 1e9))):
        be = br(100 * r["be"], 2) if r["be"] == r["be"] else "--"
        print(r["janela"].rjust(6) + br(r["capital"], 0).rjust(10) + r["nome"].rjust(19)
              + str(r["n"]).rjust(6) + br(100 * r["win"], 2).rjust(8) + be.rjust(8)
              + ("[" + br(100 * r["lo"], 1) + ";" + br(100 * r["hi"], 1) + "]").rjust(17)
              + r["veredito"].rjust(13))


if __name__ == "__main__":
    main()
