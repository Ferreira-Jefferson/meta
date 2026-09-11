# -*- coding: utf-8 -*-
"""O teste que DECIDE entre os finalistas do `copa_win` -- toda data de inicio.

Pedido do dono, 2026-09-11: "ganhadora mesmo que pouco, mas constante".

OS DOIS ACHADOS QUE CHEGARAM ATE AQUI, e o que ja foi refutado no caminho.

REFUTADO hoje, com grade completa (`copawin_grade_constancia_2026_09_11.py`,
152 celulas; `copawin_freios_e_corte_2026_09_11.py`, 54 + 51 celulas):

  * `trail_vol` ligado -- win% despenca para 33-38% e cola no breakeven em 40
    de 40 celulas. O stop arrastado corta o vencedor antes de ele pagar o
    perdedor, e este robo vive de poucos trades grandes.
  * `stop_vol` mais curto -- degrada monotonicamente (s4..s10), e s12 e' OMBRO:
    s14/s16/s20 tambem pioram.
  * `corte_persistencia` mais agressivo (0,6..0,9) -- o robo QUEBRA. 123 a 150
    dos 191 pregoes ficam sem trade porque o caixa cai abaixo do portao.
    Desistir cedo, aqui, e' desistir do lucro tambem.
  * `risco_pct_por_trade` como dial de escala (1% / 2% / 5%) -- INERTE. No
    capital de R$3.000 a quantidade fica presa em 1 contrato pelo piso de
    `quantidade_por_entrada`, entao NAO EXISTE botao de "ganhar menos e
    oscilar menos": o unico tamanho disponivel e' 1.
  * `max_entradas_dia` e `perda_max_dia_pontos` SOMADOS ao alvo novo -- nao
    somam. Cortam de R$14.271 para R$8.5-9.0 mil sem melhorar a constancia.
  * mexer na `defesa_ativa` -- as variantes que rendem mais (0,2/0,3 e
    0,6/0,2) compram lucro com CAUDA: o pior pregao piora de -R$1.469 para
    -R$2.166 e o MaxDD quase dobra. Direcao errada para este pedido.

SOBRARAM DOIS, e os dois sao do mesmo tipo -- nao mexem em quanto o robo
arrisca, mexem em QUAIS operacoes ele aceita fazer:

  1. `alvo_vol` 9,5 -> 7,6. A excursao favoravel mediana nao alcanca o alvo de
     producao; aproximar o alvo do que o mercado de fato paga troca "esperar o
     sino" por "receber". Sobe a taxa de acerto do alvo de 20% para 30%.
  2. `entrada_ttl_barras` 15 -> 5. A ordem-limite de reteste espera no maximo
     5 minutos pelo recuo em vez de 15. NAO e' numero achado na grade e
     justificado depois: o CLAUDE.md ja documenta o mecanismo, medido no
     `wdo_orb` -- ordem de entrada sem prazo curto preenche horas depois do
     sinal (269,7 minutos no caso medido) e "os fills atrasados foram
     justamente os piores resultados". A grade so' confirmou aqui o que aquela
     medicao ja dizia: um reteste que demora nao e' o trade que a estrategia
     pediu, e' uma ordem esquecida no livro que pegou o preco passando.

ESTE SCRIPT FAZ O TESTE QUE DECIDE, que nao e' mais uma tabela de janela: para
cada finalista, roda um horizonte FIXO de 40 pregoes a partir de TODA data de
inicio possivel e conta em que fracao delas o robo termina positivo. E' a
unica forma medivel da pergunta do dono ("eu ganho SEMPRE?") que nao depende
de qual foi o sorteio das primeiras operacoes -- a mesma metodologia que
fixou o piso de capital em R$3.000 hoje.

Inclui de proposito `a9,5 + ttl 5` (o prazo novo SEM o alvo novo) para
separar os dois efeitos: se o ganho vier todo do prazo, o alvo nao precisa
mudar, e mexer em menos coisa e' sempre melhor.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_finalistas_robustez_2026_09_11.py`
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
HORIZONTE = 40
PASSO = 2

#: Fila assumida na frente da ordem-limite do ALVO, em FRACAO do volume
#: MEDIANO da barra M1 do WIN@. O simbolo NAO tem fidelidade calibrada --
#: isto e' sensibilidade ("a que nivel o ganho morre?"), nunca previsao.
FILAS_EM_BARRAS = [0.0, 0.5, 1.0, 2.0, 4.0]

FINALISTAS: list[tuple[str, dict]] = [
    ("PRODUCAO a9,5 ttl15", {}),
    ("a7,6 ttl15", dict(alvo_vol=7.6)),
    ("a9,5 ttl5", dict(entrada_ttl_barras=5)),
    ("a7,6 ttl5  <- candidato", dict(alvo_vol=7.6, entrada_ttl_barras=5)),
    ("a8,55 ttl5 (plato alvo)", dict(alvo_vol=8.55, entrada_ttl_barras=5)),
    ("a7,6 ttl8  (plato ttl)", dict(alvo_vol=7.6, entrada_ttl_barras=8)),
    ("a7,6 ttl3  (plato ttl)", dict(alvo_vol=7.6, entrada_ttl_barras=3)),
]

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


def _volume_mediano() -> float:
    if "vol" not in _CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from backtest.intraday.engine import _bar_volume

        df, _ = _base()
        _CACHE["vol"] = float(df.apply(_bar_volume, axis=1).median())
    return _CACHE["vol"]


def _roda(rotulo: str, kwargs: dict, i: int, fila_barras: float = 0.0):
    """`i is None` roda o historico INTEIRO; senao, a janela de `HORIZONTE`
    pregoes que comeca no indice `i`."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _base()
    janela = list(dias) if i is None else dias[i:i + HORIZONTE]
    bars = df[[d in set(janela) for d in df.index.date]]

    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    for k, v in kwargs.items():
        setattr(strat, k, v)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0,
        exit_queue_ahead_qty=fila_barras * _volume_mediano(),
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    com = {t.entry_ts.date() for t in trades}
    eq = res.equity_curve
    dd = float((eq.cummax() - eq).max()) if eq is not None and not eq.empty else 0.0
    por_dia = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    alvos = sum(1 for t in trades if t.exit_reason.value == "target")
    return dict(
        rotulo=rotulo, inicio=janela[0], fila=fila_barras,
        liquido=sum(t.pnl_brl for t in trades), n=len(trades), maxdd=dd,
        morreu=((getattr(res, "wiped_out_at", None) is not None)
                or (len(janela) - len(com)) > 0),
        pior_dia=min(por_dia.values()) if por_dia else 0.0,
        alvo_pct=(alvos / len(trades)) if trades else float("nan"),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def main() -> None:
    df, dias = _base()
    inicios = list(range(0, len(dias) - HORIZONTE + 1, PASSO))
    tarefas = [(rot, kw, i, 0.0) for rot, kw in FINALISTAS for i in inicios]
    tarefas += [(rot, kw, None, f) for rot, kw in FINALISTAS
                for f in FILAS_EM_BARRAS]
    print("finalistas x " + str(len(inicios)) + " datas de inicio (horizonte "
          "FIXO de " + str(HORIZONTE) + " pregoes) + sensibilidade de fila")
    print("capital R$ " + br(CAPITAL, 0) + ", " + str(len(dias)) + " pregoes na base")
    print(str(len(tarefas)) + " simulacoes\n", flush=True)

    res = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            res.append(fut.result())
            if len(res) % 100 == 0:
                print("  " + str(len(res)) + "/" + str(len(tarefas)), flush=True)

    janelas = [r for r in res if r["inicio"] != dias[0] or r["n"] >= 0]
    por_data = [r for r in res if r["fila"] == 0.0 and r["maxdd"] is not None]
    # separa: as rodadas de fila usam o historico inteiro (n muito maior)
    inteiro = {(r["rotulo"], r["fila"]): r for r in res
               if r.get("inicio") == dias[0] and r["n"] > 300}

    print("\n\n===== O TESTE QUE DECIDE: toda data de inicio, horizonte de "
          + str(HORIZONTE) + " pregoes =====")
    hdr = ("finalista".ljust(26) + "POSITIVAS".rjust(11) + "morreram".rjust(10)
           + "liq mediano".rjust(13) + "PIOR inicio".rjust(13)
           + "p25".rjust(12) + "p75".rjust(12) + "MaxDD med".rjust(12)
           + "pior dia med".rjust(14) + "ops med".rjust(9))
    print(hdr)
    print("-" * len(hdr))
    for rot, _ in FINALISTAS:
        sub = [r for r in res if r["rotulo"] == rot and r["fila"] == 0.0
               and r["n"] < 300]
        if not sub:
            continue
        liq = pd.Series([r["liquido"] for r in sub])
        print(rot.ljust(26)
              + (br(100 * float((liq > 0).mean()), 1) + "%").rjust(11)
              + str(sum(1 for r in sub if r["morreu"])).rjust(10)
              + br(float(liq.median())).rjust(13)
              + br(float(liq.min())).rjust(13)
              + br(float(liq.quantile(0.25))).rjust(12)
              + br(float(liq.quantile(0.75))).rjust(12)
              + br(float(pd.Series([r["maxdd"] for r in sub]).median()), 0).rjust(12)
              + br(float(pd.Series([r["pior_dia"] for r in sub]).median()), 0).rjust(14)
              + br(float(pd.Series([r["n"] for r in sub]).median()), 0).rjust(9))

    print("\n\n===== SENSIBILIDADE A FILA (historico inteiro, 191 pregoes) =====")
    vmed = _volume_mediano()
    print("o WIN@ NAO tem fila calibrada -- 'a que nivel o ganho morre?', "
          "nunca 'quanto rende'")
    print("escala: volume MEDIANO da barra M1 = " + br(vmed, 0) + " contratos\n")
    hdr = "finalista".ljust(26) + "".join(
        (br(f, 2) + "x barra").rjust(15) for f in FILAS_EM_BARRAS)
    print(hdr)
    print("-" * len(hdr))
    for rot, _ in FINALISTAS:
        fila = rot.ljust(26)
        for f in FILAS_EM_BARRAS:
            r = next((x for x in res if x["rotulo"] == rot and x["fila"] == f
                      and x["n"] > 300), None)
            fila += (br(r["liquido"]) if r else "--").rjust(15)
        print(fila)

    print("\n(acerto do alvo no historico inteiro, fila zero)")
    for rot, _ in FINALISTAS:
        r = next((x for x in res if x["rotulo"] == rot and x["fila"] == 0.0
                  and x["n"] > 300), None)
        if r:
            print("  " + rot.ljust(26) + (br(100 * r["alvo_pct"], 1) + "%").rjust(8)
                  + "   " + str(r["n"]) + " operacoes")


if __name__ == "__main__":
    main()
