# -*- coding: utf-8 -*-
"""Piso de capital do `copa_win` que NAO depende do dia em que voce comeca.

O QUE ESTE SCRIPT RESOLVE. Duas medicoes do mesmo robo, na mesma config de
producao e no mesmo capital de R$600, deram respostas opostas:

  * comecando em 2025-12-01 e rodando os 191 pregoes: sobrevive inteiro, 0
    pregoes sem trade, +R$12.709,10, caixa minimo R$373,10;
  * comecando em 2026-09-08 (tres pregoes): ZEROU em 2026-09-09.

As duas estao certas. Quem comeca cedo acumula caixa antes de encontrar a
sequencia ruim; quem comeca na vespera dela nao tem com o que paga-la. Um
piso derivado de UMA data de inicio mede o sorteio daquela data -- e' o
mesmo defeito que o CLAUDE.md descreve em "comparar IS com OOS partindo do
piso nao e' validacao, e' comparar dois sorteios sobre quais foram as
primeiras operacoes".

A PERGUNTA CERTA, entao, nao e' "R$X sobrevive?" e sim **"com R$X, que
FRACAO das datas de inicio possiveis sobrevive?"**. E' isso que se mede aqui:
para cada nivel de capital, comeca em muitas datas diferentes, roda um
horizonte fixo a frente, e conta quantas comecadas morrem.

MORRER, aqui, e' qualquer um dos dois (os dois sao absorventes na pratica):
  * ZERAR (`wiped_out_at`);
  * CALAR -- ficar sem trade em algum pregao por falta de capital. O robo que
    trava no portao costuma nunca mais voltar (itens 1.14/3.10/3.11), entao
    contar isso como morte nao e' rigor excessivo, e' o comportamento medido.

O horizonte e' FIXO para todas as datas de inicio: comparar uma comecada que
teve 150 pregoes para se provar com outra que teve 10 favoreceria a primeira
por construcao.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_piso_por_data_de_inicio_2026_09_11.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
HORIZONTE = 40          # pregoes a frente, igual para toda data de inicio
PASSO = 2               # testa 1 a cada N pregoes como data de inicio
NIVEIS = [250.0, 500.0, 750.0, 1_000.0, 1_500.0, 2_000.0, 2_500.0, 3_000.0, 4_000.0, 5_000.0]

_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _df():
    if "df" not in _CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
        _CACHE["df"] = df[[d in set(completos) for d in df.index.date]]
        _CACHE["dias"] = completos
    return _CACHE["df"], _CACHE["dias"]


def _roda(capital: float, i_inicio: int):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _df()
    janela = set(dias[i_inicio:i_inicio + HORIZONTE])
    bars = df[[d in janela for d in df.index.date]]
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    com = len({t.entry_ts.date() for t in trades})
    zerou = getattr(res, "wiped_out_at", None) is not None
    calou = (len(janela) - com) > 0
    eq = res.equity_curve
    return dict(
        capital=capital, inicio=dias[i_inicio], zerou=zerou, calou=calou,
        morreu=(zerou or calou),
        liquido=sum(t.pnl_brl for t in trades),
        caixa_min=(float(eq.min()) if eq is not None and not eq.empty else capital),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def main() -> None:
    df, dias = _df()
    inicios = list(range(0, len(dias) - HORIZONTE + 1, PASSO))
    print("config de PRODUCAO, horizonte FIXO de " + str(HORIZONTE) + " pregoes")
    print(str(len(dias)) + " pregoes na base (" + str(dias[0]) + " a " + str(dias[-1]) + ")")
    print(str(len(inicios)) + " datas de inicio x " + str(len(NIVEIS)) + " capitais = "
          + str(len(inicios) * len(NIVEIS)) + " simulacoes\n", flush=True)

    tarefas = [(c, i) for c in NIVEIS for i in inicios]
    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            resultados.append(fut.result())
            if len(resultados) % 50 == 0:
                print("  " + str(len(resultados)) + "/" + str(len(tarefas)), flush=True)

    print("\nSOBREVIVENCIA POR DATA DE INICIO")
    hdr = ("capital".rjust(9) + "inicios".rjust(9) + "morreram".rjust(10)
           + "  (zerou / calou)".ljust(20) + "SOBREVIVEM".rjust(12)
           + "liquido mediano".rjust(17) + "pior liquido".rjust(14))
    print(hdr); print("-" * len(hdr))
    for cap in NIVEIS:
        sub = [r for r in resultados if r["capital"] == cap]
        mortes = [r for r in sub if r["morreu"]]
        zerou = sum(1 for r in sub if r["zerou"])
        calou = sum(1 for r in sub if r["calou"] and not r["zerou"])
        liq = pd.Series([r["liquido"] for r in sub])
        print(br(cap, 0).rjust(9) + str(len(sub)).rjust(9) + str(len(mortes)).rjust(10)
              + ("  (" + str(zerou) + " / " + str(calou) + ")").ljust(20)
              + (br(100 * (1 - len(mortes) / len(sub)), 1) + "%").rjust(12)
              + br(liq.median()).rjust(17) + br(liq.min()).rjust(14))

    print("\nAS DATAS DE INICIO QUE MATAM, por capital (as 6 primeiras):")
    for cap in NIVEIS:
        mortes = sorted((r["inicio"] for r in resultados
                         if r["capital"] == cap and r["morreu"]))
        if not mortes:
            print("  R$ " + br(cap, 0).rjust(8) + "  nenhuma")
            continue
        print("  R$ " + br(cap, 0).rjust(8) + "  " + str(len(mortes)) + " datas: "
              + ", ".join(str(d) for d in mortes[:6])
              + (" ..." if len(mortes) > 6 else ""))


if __name__ == "__main__":
    main()
