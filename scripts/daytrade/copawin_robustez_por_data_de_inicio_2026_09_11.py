# -*- coding: utf-8 -*-
"""Quem ganha POUCO MAS SEMPRE, medido a partir de TODA data de inicio.

Pedido do dono, 2026-09-11: "descubra como fazer essa estrategia se tornar
ganhadora mesmo que pouco, mas constante".

POR QUE ESTE TESTE, e nao mais uma tabela de IS/OOS. A grade de geometria
(`copawin_grade_constancia_2026_09_11.py`) deixou tres finalistas separados
por pouco, e separados de forma CONTRADITORIA: `a7,6` lidera o IS (bl20+ 89%
contra 76% da producao) e perde no OOS (+R$2.752 contra +R$4.255). Decidir
isso por um numero de janela inteira e' escolher qual sorteio agradou mais.

A pergunta que o dono fez nao e' "quanto rende a janela inteira" -- e' "eu
ganho SEMPRE?". A forma medivel disso e': **comecando em qualquer dia, e
rodando um horizonte FIXO a frente, em que fracao das datas de inicio eu
termino positivo?** E' a mesma metodologia que fixou o piso de capital em
R$3.000 hoje (`copawin_piso_por_data_de_inicio_2026_09_11.py`), agora usada
para escolher GEOMETRIA em vez de CAPITAL -- e ela e' imune ao defeito que
estraga a leitura de janela unica: comecar em 2025-12-01 e comecar em
2026-09-08 sao dois experimentos diferentes, e a media dos dois nao e'
nenhum deles.

Horizonte FIXO para toda data de inicio, de proposito: comparar uma comecada
que teve 150 pregoes para se provar com outra que teve 10 favoreceria a
primeira por construcao.

OS DOIS EIXOS, e por que estao no MESMO teste:

  * `alvo_vol` (geometria) -- muda a FORMA do resultado: quantas operacoes
    chegam ao alvo, quantas morrem no stop. Finalistas da grade, todos com
    `stop_vol=12,0` e trail DESLIGADO (as duas coisas ja foram medidas e
    fixadas la': apertar stop degrada monotonicamente, trailing derruba o
    win% para 33-38% em 40 de 40 celulas).
  * `risco_pct_por_trade` (escala) -- muda o TAMANHO do resultado, nao a
    forma. `contracts_from_risk` dimensiona a entrada pelo orcamento de
    perda; 5% e' o valor de producao e nunca foi varrido neste robo. E' o
    dial mais direto de "ganhar menos e oscilar menos" -- e por isso
    precisa ser medido JUNTO da geometria, nao depois: os dois interagem
    pelo piso de 1 contrato (abaixo de um certo orcamento a quantidade
    trava em 1 e o dial para de funcionar).

MORTE, aqui, e' o mesmo criterio do teste de capital: ZERAR (`wiped_out_at`)
ou CALAR (ficar sem trade em algum pregao por falta de capital) -- os dois
sao absorventes na pratica (itens 1.14/3.10/3.11).

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_robustez_por_data_de_inicio_2026_09_11.py`
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
CAPITAL = 3_000.0
HORIZONTE = 40      # pregoes a frente, igual para toda data de inicio
PASSO = 2           # testa 1 a cada N pregoes como data de inicio

#: Finalistas da grade de geometria. `stop_vol` e `trail_vol` NAO sao eixo
#: aqui -- ja foram decididos la' e reabrir os tres eixos juntos so' geraria
#: celulas que ninguem consegue ler.
ALVOS = [6.65, 7.6, 8.55, 9.5]      # 9,5 = producao
RISCOS = [0.01, 0.02, 0.05]         # 0,05 = producao

_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    if v != v:
        return "--"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _base():
    if "df" not in _CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        cont = df.groupby(df.index.date).size()
        dias = sorted(d for d, n in cont.items() if n >= MIN_BARRAS_POR_PREGAO)
        _CACHE["df"] = df[[d in set(dias) for d in df.index.date]]
        _CACHE["dias"] = dias
    return _CACHE["df"], _CACHE["dias"]


def _roda(alvo: float, risco: float, i: int):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _base()
    janela = dias[i:i + HORIZONTE]
    bars = df[[d in set(janela) for d in df.index.date]]

    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    strat.alvo_vol = alvo
    strat.risco_pct_por_trade = risco
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    com = {t.entry_ts.date() for t in trades}
    eq = res.equity_curve
    dd = float((eq.cummax() - eq).max()) if eq is not None and not eq.empty else 0.0
    zerou = getattr(res, "wiped_out_at", None) is not None
    calou = (len(janela) - len(com)) > 0
    liquido = sum(t.pnl_brl for t in trades)

    por_dia = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    pos = sum(1 for v in por_dia.values() if v > 0)

    return dict(alvo=alvo, risco=risco, inicio=janela[0], liquido=liquido,
                n=len(trades), maxdd=dd, zerou=zerou, calou=calou,
                morreu=(zerou or calou),
                frac_preg=(pos / len(por_dia)) if por_dia else float("nan"))


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def main() -> None:
    df, dias = _base()
    inicios = list(range(0, len(dias) - HORIZONTE + 1, PASSO))
    tarefas = [(a, r, i) for a in ALVOS for r in RISCOS for i in inicios]
    print("horizonte FIXO de " + str(HORIZONTE) + " pregoes, capital R$ "
          + br(CAPITAL, 0) + ", stop_vol 12,0 e trail DESLIGADO em todas")
    print(str(len(dias)) + " pregoes na base (" + str(dias[0]) + " a "
          + str(dias[-1]) + ")")
    print(str(len(ALVOS)) + " alvos x " + str(len(RISCOS)) + " riscos x "
          + str(len(inicios)) + " datas de inicio = " + str(len(tarefas))
          + " simulacoes")
    print("producao = alvo 9,5 / risco 5%\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            resultados.append(fut.result())
            if len(resultados) % 100 == 0:
                print("  " + str(len(resultados)) + "/" + str(len(tarefas)),
                      flush=True)

    print("\n\n===== CADA CELULA VISTA DE TODAS AS DATAS DE INICIO =====")
    hdr = ("alvo".rjust(6) + "risco".rjust(8) + "inicios".rjust(9)
           + "POSITIVAS".rjust(11) + "morreram".rjust(10)
           + "liq mediano".rjust(13) + "pior liq".rjust(12)
           + "melhor liq".rjust(12) + "p25 liq".rjust(11)
           + "MaxDD mediano".rjust(15) + "preg+ mediano".rjust(15)
           + "ops medianas".rjust(14))
    print(hdr)
    print("-" * len(hdr))
    tabela = []
    for a in ALVOS:
        for r in RISCOS:
            sub = [x for x in resultados if x["alvo"] == a and x["risco"] == r]
            liq = pd.Series([x["liquido"] for x in sub])
            fp = pd.Series([x["frac_preg"] for x in sub]).dropna()
            linha = dict(
                alvo=a, risco=r, n=len(sub),
                frac_pos=float((liq > 0).mean()),
                mortes=sum(1 for x in sub if x["morreu"]),
                med=float(liq.median()), pior=float(liq.min()),
                melhor=float(liq.max()), p25=float(liq.quantile(0.25)),
                dd=float(pd.Series([x["maxdd"] for x in sub]).median()),
                preg=float(fp.median()) if len(fp) else float("nan"),
                ops=float(pd.Series([x["n"] for x in sub]).median()),
            )
            tabela.append(linha)
            marca = "   <== PRODUCAO" if (a == 9.5 and r == 0.05) else ""
            print(br(a, 2).rjust(6) + (br(100 * r, 0) + "%").rjust(8)
                  + str(linha["n"]).rjust(9)
                  + (br(100 * linha["frac_pos"], 1) + "%").rjust(11)
                  + str(linha["mortes"]).rjust(10)
                  + br(linha["med"]).rjust(13) + br(linha["pior"]).rjust(12)
                  + br(linha["melhor"]).rjust(12) + br(linha["p25"]).rjust(11)
                  + br(linha["dd"]).rjust(15)
                  + (br(100 * linha["preg"], 0) + "%").rjust(15)
                  + br(linha["ops"], 0).rjust(14) + marca)

    print("\n\n===== ORDENADO POR 'FRACAO DE DATAS DE INICIO POSITIVAS' "
          "(a pergunta do dono) =====")
    print("  alvo  risco   positivas   liq mediano     pior liq      p25 liq"
          "   MaxDD med")
    for l in sorted(tabela, key=lambda x: (-x["frac_pos"], -x["med"])):
        marca = "   <== PRODUCAO" if (l["alvo"] == 9.5 and l["risco"] == 0.05) else ""
        print("  " + br(l["alvo"], 2).rjust(4) + (br(100 * l["risco"], 0) + "%").rjust(7)
              + (br(100 * l["frac_pos"], 1) + "%").rjust(12)
              + br(l["med"]).rjust(14) + br(l["pior"]).rjust(13)
              + br(l["p25"]).rjust(13) + br(l["dd"]).rjust(12) + marca)

    print("\n\n===== O MAPA: fracao de datas de inicio POSITIVAS =====")
    print("alvo \\ risco".ljust(14) + "".join(
        (br(100 * r, 0) + "%").rjust(10) for r in RISCOS))
    for a in ALVOS:
        fila = br(a, 2).ljust(14)
        for r in RISCOS:
            l = next(x for x in tabela if x["alvo"] == a and x["risco"] == r)
            fila += (br(100 * l["frac_pos"], 1) + "%").rjust(10)
        print(fila)

    print("\n===== O MAPA: liquido MEDIANO por data de inicio (R$) =====")
    print("alvo \\ risco".ljust(14) + "".join(
        (br(100 * r, 0) + "%").rjust(11) for r in RISCOS))
    for a in ALVOS:
        fila = br(a, 2).ljust(14)
        for r in RISCOS:
            l = next(x for x in tabela if x["alvo"] == a and x["risco"] == r)
            fila += br(l["med"], 0).rjust(11)
        print(fila)


if __name__ == "__main__":
    main()
