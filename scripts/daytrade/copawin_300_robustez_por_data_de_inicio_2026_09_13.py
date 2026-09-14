# -*- coding: utf-8 -*-
"""Com R$300, em quantas datas de inicio o robo SOBREVIVE 40 pregoes?

Terceira e ultima etapa da pergunta do dono de 2026-09-13 ("versao com no
maximo R$300 e acerto de no minimo 90%"). As duas primeiras:

  1. `copawin_300_reais_acerto_90_2026_09_13.py` -- a grade. Achou o TETO de
     acerto: 88,2% (IS) / 88,6% (OOS) com `alvo_vol=0,08`, ja' encostado no
     piso de 2 ticks reais. 90% nao existe em geometria executavel. E achou
     um SIGN-FLIP: a familia de alvo fino e' NEGATIVA no IS (11 de 15 celulas
     negativas a R$3.000, 129 pregoes) e POSITIVA no OOS (62 pregoes).
  2. `copawin_300_alvo_fino_sensibilidade_fila_2026_09_13.py` -- a fila. NAO
     e' ela que derruba: a 1x o volume mediano da barra o alvo fino retem
     92-95% do liquido e o acerto fica em ~88%.

ENTAO O QUE DECIDE E' ESTE TESTE, e ele existe porque as duas janelas
discordam. Com capital no piso, comparar IS com OOS nao e' validacao -- e'
comparar dois sorteios sobre quais foram as PRIMEIRAS operacoes (corolario do
CLAUDE.md). O caso e' literal aqui: `a0,15 s20` a R$300 morre no IS (11
operacoes, 127 dos 129 pregoes em silencio, ZEROU) e prospera no OOS
(+R$2.833,20, 482 operacoes, caixa minimo R$270). Mesma geometria, mesmo
capital, destinos opostos.

A forma medivel de "eu ganho sempre?" que NAO depende desse sorteio e' a
mesma ja usada para escolher a geometria de producao e para fixar o piso de
capital: **comecando em qualquer dia do historico, e rodando um horizonte
FIXO a frente, em que fracao das datas de inicio eu termino positivo -- e em
quantas o robo simplesmente MORRE?**

"MORREU" aqui e' `zerou` OU `calou`: cair abaixo do portao de capital
(margem crua de R$100 no WIN@) cala o robo para SEMPRE, e uma janela em que
ele emudeceu no terceiro pregao nao virou "resultado pequeno", virou fim. E'
a distincao que o item 1.14/3.9 de LICOES_DE_PRODUCAO.md existe para manter
visivel.

A REFERENCIA de comparacao e' a producao (a7,6 s12) rodada no MESMO capital de
R$300 -- nunca o numero lembrado de R$3.000. E a coluna `R$3.000` da producao
entra so' no rodape, como lembrete do que o robo faz quando tem o caixa que
ele pede.

Uso:
    .venv/Scripts/python.exe -u scripts/daytrade/copawin_300_robustez_por_data_de_inicio_2026_09_13.py
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
CAPITAL = 300.0
HORIZONTE = 40      # pregoes a frente, igual para toda data de inicio
PASSO = 2           # testa 1 a cada N pregoes como data de inicio

#: `(alvo_vol, stop_vol)`. Os quatro primeiros sao a familia de alvo fino que
#: a grade premiou por ACERTO; o ultimo e' a producao, no mesmo capital.
GEOMETRIAS = [(0.08, 20.0), (0.15, 20.0), (0.25, 20.0), (0.60, 20.0),
              (7.60, 12.0)]
PRODUCAO = (7.60, 12.0)

#: A producao tambem roda no caixa que ela PEDE, como rodape -- nao para
#: comparar (capitais diferentes nao se comparam), e sim para o leitor ver o
#: que esta' sendo trocado ao descer para R$300.
CAPITAL_REFERENCIA = 3_000.0

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


def _roda(alvo: float, stop: float, capital: float, i: int):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _base()
    janela = dias[i:i + HORIZONTE]
    bars = df[[d in set(janela) for d in df.index.date]]

    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    strat.alvo_vol = alvo
    strat.stop_vol = stop
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
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
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]

    return dict(alvo=alvo, stop=stop, capital=capital, inicio=janela[0],
                liquido=liquido, n=len(trades), maxdd=dd,
                zerou=zerou, calou=calou, morreu=(zerou or calou),
                win=(len(g) / len(trades)) if trades else float("nan"))


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def main() -> None:
    df, dias = _base()
    inicios = list(range(0, len(dias) - HORIZONTE + 1, PASSO))
    tarefas = [(a, s, CAPITAL, i) for a, s in GEOMETRIAS for i in inicios]
    tarefas += [(PRODUCAO[0], PRODUCAO[1], CAPITAL_REFERENCIA, i)
                for i in inicios]

    print("robustez por DATA DE INICIO -- horizonte FIXO de "
          + str(HORIZONTE) + " pregoes")
    print("capital R$ " + br(CAPITAL, 0) + " (ordem do dono), "
          + str(len(inicios)) + " datas de inicio, "
          + str(len(dias)) + " pregoes no historico")
    print(str(len(tarefas)) + " simulacoes")
    print("MORREU = zerou OU calou (caixa abaixo do portao de R$100 = fim "
          "permanente)\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            resultados.append(fut.result())
            if len(resultados) % 25 == 0:
                print("  ... " + str(len(resultados)) + "/" + str(len(tarefas)),
                      flush=True)

    hdr = ("geometria".ljust(14) + "caixa".rjust(9) + "positivas".rjust(11)
           + "MORREU".rjust(9) + "pior R$".rjust(12) + "mediana R$".rjust(12)
           + "melhor R$".rjust(12) + "ops med".rjust(9) + "win% med".rjust(10))
    print("\n\n===== " + str(len(inicios)) + " datas de inicio, "
          + str(HORIZONTE) + " pregoes cada =====")
    print(hdr)
    print("-" * len(hdr))

    linhas = [(a, s, CAPITAL) for a, s in GEOMETRIAS]
    linhas.append((PRODUCAO[0], PRODUCAO[1], CAPITAL_REFERENCIA))
    for a, s, cap in linhas:
        sub = [r for r in resultados if r["alvo"] == a and r["stop"] == s
               and r["capital"] == cap]
        if not sub:
            continue
        liq = pd.Series([r["liquido"] for r in sub])
        pos = sum(1 for r in sub if r["liquido"] > 0)
        mortes = sum(1 for r in sub if r["morreu"])
        wins = pd.Series([r["win"] for r in sub if r["win"] == r["win"]])
        rot = "a" + br(a, 2) + " s" + br(s, 0)
        print(rot.ljust(14) + ("R$" + br(cap, 0)).rjust(9)
              + (br(100 * pos / len(sub), 1) + "%").rjust(11)
              + (str(mortes) + "/" + str(len(sub))).rjust(9)
              + br(liq.min()).rjust(12) + br(liq.median()).rjust(12)
              + br(liq.max()).rjust(12)
              + br(pd.Series([r["n"] for r in sub]).median(), 0).rjust(9)
              + ((br(100 * wins.median(), 1) + "%") if len(wins) else "--").rjust(10)
              + ("   <== PRODUCAO" if (a, s) == PRODUCAO else ""))

    print("\nleitura: `positivas` conta a janela que terminou no azul, "
          "INCLUSIVE as que")
    print("terminaram no azul porque o robo morreu cedo com lucro pequeno e "
          "ficou mudo.")
    print("Por isso `MORREU` esta' ao lado: as duas colunas so' fazem sentido "
          "juntas.")


if __name__ == "__main__":
    main()
