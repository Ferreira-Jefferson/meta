# -*- coding: utf-8 -*-
"""Existe uma versao do `copa_win` que roda com R$300 E acerta >= 90%?

Pedido do dono, 2026-09-13: "consegue criar uma versao dela para rodar com
capital inicial de no max 300 e que tenha uma taxa de acerto de no min 90%".

A ARITMETICA QUE DEFINE A GRADE, e que precisa estar escrita antes de
qualquer numero aparecer. Taxa de acerto nao e' um eixo livre: num robo de
alvo-e-stop ela e' consequencia direta da GEOMETRIA. O nulo nominal e'
`stop/(alvo+stop)` -- que e' exatamente o breakeven a custo zero. Entao pedir
90% de acerto e' pedir `stop ~= 9x alvo`, e nessa geometria o robo so' e'
lucrativo se acertar MAIS de 90%. A taxa alta nao compra seguranca nenhuma;
ela apenas move para onde o risco mora (poucos eventos, cada um caro).

Este e' o modo de falha ja pago duas vezes neste repo, e por isso a grade
existe para TESTAR a hipotese, nao para confirma-la:
  * WDO F1 T2/S16 -- win 94,5% (n=9.635) contra breakeven 95,00%: NEGATIVO;
  * `wdo_grid_reload_maker` -- win 82-84% contra breakeven 88-90%, gap
    estrutural, familia ENCERRADA em 2026-09-10.

O SEGUNDO EIXO E' O CAIXA, e ele morde mais forte do que parece. A R$300 o
dimensionamento fica preso em 1 contrato, e o portao de capital do motor
(`contracts_from_capital_operacional`, margem CRUA de R$100 no WIN@) cala o
robo para sempre assim que o caixa cruza R$100 para baixo. Ou seja: a conta
tolera ~R$200 de prejuizo acumulado, no total, antes de travar. Um stop de
`stop_vol=12` sobre volatilidade de referencia tipica ja e' dezenas de reais
POR OPERACAO -- e a geometria de 90% pede stop AINDA MAIOR. As duas
restricoes do pedido puxam em sentidos opostos, e e' isso que a grade mede.

POR ISSO A TABELA TRAZ `caixa_min` E `s/trade` COLADOS NO `win%`: numa janela
censurada (robo travou no portao de capital) o win% descreve as poucas
operacoes que couberam antes da morte, nao a estrategia. Uma celula com
"win 100%, 2 trades, 189 pregoes sem trade" nao e' um robo de 100% de acerto
-- e' um robo morto. Ver o corolario de leitura de backtest no CLAUDE.md.

PISO DE EXECUTABILIDADE. O alvo sai por ordem-limite real fatiada, e alvo de
1 tick e' inexequivel neste projeto (proibicao geral do CLAUDE.md, valida
para qualquer robo com `target_fills_as_maker`; e o piso
`PROFIT_TICKS_MINIMO=2` que a familia gremah ja pagou). O tick REAL do WIN@ e'
de 5 pontos (`core.instruments.FUTUROS["WIN@"].price_tick_size`), entao a
coluna `alvo pts` sai junto com `alvo tk` = alvo em ticks reais, e celula com
mediana abaixo de 2 ticks e' marcada `INEXEQ` -- ela nao conta como resposta
mesmo que os numeros saiam bonitos.

Uso:
    .venv/Scripts/python.exe -u scripts/daytrade/copawin_300_reais_acerto_90_2026_09_13.py
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
#: ORDEM DO DONO: teto de R$300. Nao e' o piso do instrumento (R$250 com
#: reserva) nem o piso medido do robo (R$2.500) -- e' o valor que ele tem.
#:
#: A rodada `fino` acrescenta R$3.000 como SEGUNDO caixa, e isto precisa de
#: justificativa porque o CLAUDE.md proibe bateria "com folga": R$3.000 nao e'
#: um capital inventado para deixar a celula bonita, e' o caixa DECLARADO da
#: producao deste mesmo robo. Sem ele nao da' para distinguir as duas causas
#: possiveis de um "nao" -- a geometria nao ACERTA 90%, ou acerta e o caixa de
#: R$300 mata antes -- e essas duas respostas levam a acoes opostas.
CAPITAL = 300.0
OOS_INICIO = pd.Timestamp("2026-06-13").date()
TICK_REAL_PONTOS = 5.0
ACERTO_PEDIDO = 0.90

#: Producao (a7,6 s12) entra como celula de referencia: a comparacao tem de
#: ser contra um numero MEDIDO no mesmo capital, nunca contra o numero
#: lembrado de R$3.000.
PRODUCAO = (7.6, 12.0)

#: DUAS RODADAS, e a segunda existe por causa do resultado da primeira.
#:
#: `base` -- alvos pequenos x stops largos, a familia em que 90% de acerto e'
#: aritmeticamente possivel. `stop/alvo` de 3,75 (be nominal 79%) a 37,5 (97%).
#: RESULTADO: nenhuma celula bate 90%; o teto ficou em 81,4% (`a0,8`), e 24
#: das 26 geometrias sairam CENSURADAS a R$300 (124-127 dos 129 pregoes sem
#: trade no IS), quase todas com `ZEROU`.
#:
#: `fino` -- existe porque a rodada base parou LONGE do limite que importa. O
#: menor alvo dela (`a0,8`) ainda da' **25,4 ticks reais** de alvo; o piso de
#: executabilidade e' 2 ticks. Ou seja, a base varreu so' o topo do eixo e
#: concluir "nao existe 90%" ali seria concluir da parede que ninguem tentou
#: atravessar -- o mesmo erro que a rodada `extensao` do
#: `copawin_grade_constancia_2026_09_11.py` teve de corrigir. Aqui o alvo
#: desce ate `0,08` (~2,5 ticks reais na volatilidade mediana medida de ~159
#: pontos), e cada geometria roda nos DOIS caixas.
RODADAS = {
    "base": dict(alvos=[0.8, 1.2, 1.6, 2.4, 3.2],
                 stops=[12.0, 16.0, 20.0, 24.0, 30.0],
                 capitais=[300.0]),
    "fino": dict(alvos=[0.08, 0.15, 0.25, 0.4, 0.6],
                 stops=[12.0, 20.0, 30.0],
                 capitais=[300.0, 3_000.0]),
}
RODADA = sys.argv[1] if len(sys.argv) > 1 else "base"
ALVOS = RODADAS[RODADA]["alvos"]
STOPS = RODADAS[RODADA]["stops"]
CAPITAIS = RODADAS[RODADA]["capitais"]

_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    if v != v:
        return "--"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int):
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


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


def _roda(janela: str, alvo: float, stop: float, capital: float = CAPITAL):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _base()
    ds = [d for d in dias if (d < OOS_INICIO if janela == "IS" else d >= OOS_INICIO)]
    bars = df[[d in set(ds) for d in df.index.date]]

    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    strat.alvo_vol = alvo
    strat.stop_vol = stop

    # Espiao em `_entrada` -- so' ele sabe a volatilidade de REFERENCIA que
    # valia no instante da entrada, que e' o que traduz `alvo_vol` (adimen-
    # sional) em pontos e em ticks reais. Mesmo mecanismo do script de
    # anatomia; nao altera decisao nenhuma, so' registra.
    vols: list[float] = []
    orig = strat._entrada

    def espiao(lado, preco, nivel, vol):
        vols.append(float(vol))
        return orig(lado, preco, nivel, vol)

    strat._entrada = espiao

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    por_dia: dict = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl

    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    eq = res.equity_curve
    dd = float((eq.cummax() - eq).max()) if eq is not None and not eq.empty else 0.0
    cmin = float(eq.min()) if eq is not None and not eq.empty else capital
    vol_med = float(pd.Series(vols).median()) if vols else float("nan")
    alvo_pts = alvo * vol_med
    stop_pts = stop * vol_med

    return dict(
        janela=janela, alvo=alvo, stop=stop, capital=capital, dt=dt,
        liquido=sum(t.pnl_brl for t in trades), n=n,
        pregoes=len(ds), sem_trade=len(ds) - len(por_dia),
        win=(len(g) / n) if n else float("nan"), be=be, lo=lo, hi=hi,
        veredito=(("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido")
                  if be == be and n else "--"),
        maxdd=dd, caixa_min=cmin,
        zerou=(getattr(res, "wiped_out_at", None) is not None),
        be_nominal=stop / (alvo + stop),
        alvo_pts=alvo_pts, stop_pts=stop_pts,
        alvo_tk=alvo_pts / TICK_REAL_PONTOS,
        alvo_rs=alvo_pts * 0.20, stop_rs=stop_pts * 0.20,
        ganho_med=gm, perda_med=pm,
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def _rotulo(r) -> str:
    return ("a" + br(r["alvo"], 2) + " s" + br(r["stop"], 0)
            + " R$" + br(r["capital"], 0))


def _flags(r) -> str:
    f = []
    if r["alvo_tk"] == r["alvo_tk"] and r["alvo_tk"] < 2.0:
        f.append("INEXEQ")
    if r["sem_trade"]:
        f.append("s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"]))
    if r["zerou"]:
        f.append("ZEROU")
    return ("  " + "  ".join(f)) if f else ""


def _linha(r) -> str:
    return (_rotulo(r).ljust(21)
            + (br(100 * r["win"], 1) + "%").rjust(8)
            + ("[" + br(100 * r["lo"], 0) + ";" + br(100 * r["hi"], 0) + "]").rjust(12)
            + (br(100 * r["be"], 1) + "%").rjust(8)
            + (br(100 * r["be_nominal"], 0) + "%").rjust(7)
            + br(r["liquido"]).rjust(12)
            + str(r["n"]).rjust(6)
            + br(r["caixa_min"], 0).rjust(9)
            + br(r["alvo_tk"], 1).rjust(8)
            + br(r["alvo_rs"], 1).rjust(9)
            + br(r["stop_rs"], 1).rjust(9)
            + r["veredito"].rjust(12)
            + _flags(r))


_HDR = ("alvo/stop/caixa".ljust(21) + "win%".rjust(8) + "IC95%".rjust(12)
        + "BE emp".rjust(8) + "BEnom".rjust(7) + "liquido".rjust(12)
        + "ops".rjust(6) + "caixa min".rjust(9) + "alvo tk".rjust(8)
        + "alvo R$".rjust(9) + "stop R$".rjust(9) + "veredito".rjust(12))


def main() -> None:
    combos = [(a, s) for a in ALVOS for s in STOPS]
    if PRODUCAO not in combos:
        combos.append(PRODUCAO)
    tarefas = [(j, a, s, c) for j in ("IS", "OOS")
               for a, s in combos for c in CAPITAIS]

    print("existe versao do copa_win com CAPITAL R$ " + br(CAPITAL, 0)
          + " e ACERTO >= " + br(100 * ACERTO_PEDIDO, 0) + "%?   rodada "
          + RODADA.upper())
    print(str(len(combos)) + " geometrias x 2 janelas x "
          + str(len(CAPITAIS)) + " caixa(s) = " + str(len(tarefas))
          + " celulas   (producao a7,6 s12 incluida como referencia)")
    print("caixa(s): " + ", ".join("R$" + br(c, 0) for c in CAPITAIS))
    print("lembrete aritmetico: acerto >= 90% exige stop ~9x alvo, e nessa "
          "geometria")
    print("o breakeven tambem fica em ~90% -- as duas colunas tem de ser "
          "lidas juntas.\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print("[" + str(len(resultados)).rjust(3) + "/" + str(len(tarefas))
                  + "] " + r["janela"].ljust(4) + _rotulo(r).ljust(21)
                  + " win " + (br(100 * r["win"], 1) + "%").rjust(6)
                  + "  liq " + br(r["liquido"]).rjust(11)
                  + "  " + r["veredito"].ljust(11)
                  + _flags(r) + "  (" + str(round(r["dt"])) + "s)", flush=True)

    for janela in ("IS", "OOS"):
        sub = sorted((r for r in resultados if r["janela"] == janela),
                     key=lambda r: -r["win"] if r["win"] == r["win"] else 1)
        print("\n\n===== " + janela + " -- ordenado por taxa de ACERTO "
              "(o que o dono pediu) =====")
        print(_HDR)
        print("-" * len(_HDR))
        for r in sub:
            marca = "   <== PRODUCAO" if (r["alvo"], r["stop"]) == PRODUCAO else ""
            print(_linha(r) + marca)

    print("\n\n===== RESPOSTA: celulas que cumprem AS DUAS condicoes =====")
    print("criterio: caixa R$" + br(CAPITAL, 0) + ", win% >= "
          + br(100 * ACERTO_PEDIDO, 0) + "%, liquido > 0, alvo >= 2 ticks "
          "reais, janela NAO censurada (0 pregoes sem trade)")
    achou = False
    for janela in ("IS", "OOS"):
        for r in sorted((x for x in resultados
                         if x["janela"] == janela and x["capital"] == CAPITAL),
                        key=lambda x: -x["liquido"]):
            if (r["win"] >= ACERTO_PEDIDO and r["liquido"] > 0
                    and r["alvo_tk"] >= 2.0 and not r["sem_trade"]):
                achou = True
                print("  " + janela + "  " + _linha(r))
    if not achou:
        print("  NENHUMA. Ver as tabelas acima -- a coluna que explica por que")
        print("  esta no `s/trade` (censura pelo caixa) ou no `BE emp` "
              "(acerto alto que")
        print("  nao paga, porque o breakeven subiu junto).")


if __name__ == "__main__":
    main()
