# -*- coding: utf-8 -*-
"""Os tres freios que atacam a CAUDA ESQUERDA do `copa_win`, um eixo por vez.

Pedido do dono, 2026-09-11: "ganhadora mesmo que pouco, mas constante".

O diagnostico (`copawin_consistencia_diagnostico_2026_09_11.py`) isolou o
problema: o robo acerta mais do que erra (win 54,7% contra breakeven 48,4%) e
mesmo assim o dia ruim e' maior que o dia bom, porque a saida por STOP custa
-R$437,77 contra +R$267,74 da saida por alvo. A grade de geometria mostrou
que os dois ajustes obvios PIORAM: apertar o stop e ligar o trailing.

Sobram os freios que nao mexem na geometria da operacao -- eles nao mudam
onde ficam alvo e stop, mudam QUANDO o robo desiste. Nenhum dos tres foi
medido neste robo:

  1. `perda_max_dia_pontos` -- teto de perda do PREGAO. Existe na classe
     desde sempre, default `None` (desligado). Ataca o dia catastrofico
     direto: o pior pregao do historico foi -R$1.986,50, e o segundo
     -R$1.469,50, os dois em setembro. ATENCAO A UNIDADE: o teto em reais e'
     `pontos x point_value x teto_contratos` = `pontos x 0,2 x 15` = `3 x
     pontos`, e e' FIXO em reais -- nao escala com o caixa. Entao ele aperta
     progressivamente conforme a conta cresce, e isso faz parte do que se
     mede aqui, nao e' efeito colateral a ignorar.
  2. `max_entradas_dia` -- teto de entradas por pregao (producao: 10, na
     pratica nunca amarra: a mediana e' ~2,5). Limita quantas vezes o robo
     paga o pedagio num dia sem sinal bom, e e' a versao "pare de insistir"
     do mesmo freio.
  3. `corte_persistencia_frac_adverso` -- em producao esta' em **1,0**, que
     e' o valor NEUTRO declarado na propria classe ("quase nunca dispara
     sozinho"): exige que 100% das barras ja vividas tenham fechado do lado
     adverso. Baixar para 0,8 faz o mecanismo de fato operar. Este e' o
     candidato mais direto de todos, porque e' o unico que ataca o stop
     ANTES de ele acontecer -- o achado retrospectivo que o gerou media que
     estar do lado adverso cedo ja indicava 84,4% de chance de terminar em
     stop.

UM EIXO POR VEZ, tudo o mais na producao. E' deliberado: cruzar os tres
produziria 60 celulas em que nenhum efeito e' atribuivel: a primeira coisa
que se quer saber e' se cada freio sozinho move alguma coisa (item 6.25 --
grade com eixo morto e' veredito lido no lugar errado).

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_freios_e_corte_2026_09_11.py`
"""
from __future__ import annotations

import math
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
OOS_INICIO = pd.Timestamp("2026-06-13").date()
BLOCO = 20

#: (rotulo, kwargs a sobrescrever na instancia de producao). O primeiro de
#: cada bloco E' a producao -- fica na tabela para a comparacao ser contra o
#: robo que existe, nunca contra um numero lembrado.
VARIANTES: list[tuple[str, dict]] = [
    ("PRODUCAO", {}),
    # --- 1. teto de perda do pregao (R$ = 3 x pontos) -------------------
    ("perda/dia R$150", dict(perda_max_dia_pontos=50.0)),
    ("perda/dia R$300", dict(perda_max_dia_pontos=100.0)),
    ("perda/dia R$600", dict(perda_max_dia_pontos=200.0)),
    ("perda/dia R$900", dict(perda_max_dia_pontos=300.0)),
    ("perda/dia R$1.500", dict(perda_max_dia_pontos=500.0)),
    # --- 2. teto de entradas por pregao ---------------------------------
    ("max 1 entrada/dia", dict(max_entradas_dia=1)),
    ("max 2 entradas/dia", dict(max_entradas_dia=2)),
    ("max 3 entradas/dia", dict(max_entradas_dia=3)),
    ("max 5 entradas/dia", dict(max_entradas_dia=5)),
    # --- 3. corte por persistencia no lado adverso ----------------------
    ("corte 0,9 / 5 barras", dict(corte_persistencia_frac_adverso=0.9,
                                  corte_persistencia_min_barras=5)),
    ("corte 0,9 / 10 barras", dict(corte_persistencia_frac_adverso=0.9,
                                   corte_persistencia_min_barras=10)),
    ("corte 0,9 / 20 barras", dict(corte_persistencia_frac_adverso=0.9,
                                   corte_persistencia_min_barras=20)),
    ("corte 0,8 / 5 barras", dict(corte_persistencia_frac_adverso=0.8,
                                  corte_persistencia_min_barras=5)),
    ("corte 0,8 / 10 barras", dict(corte_persistencia_frac_adverso=0.8,
                                   corte_persistencia_min_barras=10)),
    ("corte 0,8 / 20 barras", dict(corte_persistencia_frac_adverso=0.8,
                                   corte_persistencia_min_barras=20)),
    ("corte 0,7 / 10 barras", dict(corte_persistencia_frac_adverso=0.7,
                                   corte_persistencia_min_barras=10)),
    ("corte 0,6 / 10 barras", dict(corte_persistencia_frac_adverso=0.6,
                                   corte_persistencia_min_barras=10)),
]

#: SEGUNDA RODADA (`sys.argv[1] == "entrada"`): os eixos do FILTRO DE ENTRADA,
#: os unicos que nunca foram tocados neste robo, medidos ja sobre a geometria
#: candidata (`alvo_vol=7,6`). A pergunta e' se o robo pode simplesmente
#: OPERAR MENOS e melhor -- recusar o rompimento de faixa achatada, olhar uma
#: faixa mais longa, esperar mais tempo depois da abertura. E a defesa de
#: recuo, que hoje esta ligada com numeros que ninguem varreu (0,2 / 0,1).
_A76 = dict(alvo_vol=7.6)
VARIANTES_ENTRADA: list[tuple[str, dict]] = [
    ("PRODUCAO (alvo 9,5)", {}),
    ("a7,6 (base da rodada)", dict(_A76)),
    # faixa rolante do rompimento (producao: 10 barras)
    ("a7,6 faixa 5", dict(_A76, janela_rompimento=5)),
    ("a7,6 faixa 20", dict(_A76, janela_rompimento=20)),
    ("a7,6 faixa 30", dict(_A76, janela_rompimento=30)),
    # piso de volatilidade para operar (producao: 8 ticks)
    ("a7,6 vol_min 4", dict(_A76, vol_min_ticks=4.0)),
    ("a7,6 vol_min 12", dict(_A76, vol_min_ticks=12.0)),
    ("a7,6 vol_min 16", dict(_A76, vol_min_ticks=16.0)),
    # barras da abertura sem operar (producao: 45)
    ("a7,6 aquecimento 30", dict(_A76, aquecimento_barras=30)),
    ("a7,6 aquecimento 60", dict(_A76, aquecimento_barras=60)),
    ("a7,6 aquecimento 90", dict(_A76, aquecimento_barras=90)),
    # prazo da ordem-limite de entrada (producao: 15 barras)
    ("a7,6 ttl entrada 5", dict(_A76, entrada_ttl_barras=5)),
    ("a7,6 ttl entrada 30", dict(_A76, entrada_ttl_barras=30)),
    # defesa de recuo (producao: gatilho 0,2 / proximidade 0,1)
    ("a7,6 defesa OFF", dict(_A76, defesa_ativa=False)),
    ("a7,6 defesa 0,4/0,1", dict(_A76, defesa_gatilho_stop_pct=0.4)),
    ("a7,6 defesa 0,2/0,3", dict(_A76, defesa_alvo_proximidade_pct=0.3)),
    ("a7,6 defesa 0,6/0,2", dict(_A76, defesa_gatilho_stop_pct=0.6,
                                 defesa_alvo_proximidade_pct=0.2)),
]

if len(sys.argv) > 1 and sys.argv[1] == "entrada":
    VARIANTES = VARIANTES_ENTRADA


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


def _roda(janela: str, rotulo: str, kwargs: dict):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _base()
    if janela == "IS":
        ds = [d for d in dias if d < OOS_INICIO]
    elif janela == "OOS":
        ds = [d for d in dias if d >= OOS_INICIO]
    else:
        ds = list(dias)
    bars = df[[d in set(ds) for d in df.index.date]]

    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    for k, v in kwargs.items():
        setattr(strat, k, v)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)

    por_dia = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    serie = pd.Series([por_dia.get(d, 0.0) for d in ds], index=pd.to_datetime(ds))
    com = list(por_dia.values())
    blocos = [float(serie.iloc[i:i + BLOCO].sum())
              for i in range(0, max(1, len(serie) - BLOCO + 1))]
    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    eq = res.equity_curve
    dd = float((eq.cummax() - eq).max()) if eq is not None and not eq.empty else 0.0
    stops = [t for t in trades if t.exit_reason.value == "stop"]

    return dict(
        janela=janela, rotulo=rotulo, liquido=sum(t.pnl_brl for t in trades), n=n,
        frac_preg=(sum(1 for v in com if v > 0) / len(com)) if com else float("nan"),
        frac_bl=(sum(1 for b in blocos if b > 0) / len(blocos)) if blocos else float("nan"),
        pior_dia=float(serie.min()) if len(serie) else float("nan"),
        maxdd=dd, win=(len(g) / n) if n else float("nan"), be=be,
        veredito=(("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido")
                  if be == be and n else "--"),
        stop_rs=(sum(t.pnl_brl for t in stops) / len(stops)) if stops else float("nan"),
        stop_pct=(len(stops) / n) if n else float("nan"),
        sem_trade=len(ds) - len(com), pregoes=len(ds),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


_HDR = ("variante".ljust(24) + "liquido".rjust(12) + "ops".rjust(6)
        + "preg+".rjust(7) + "bl20+".rjust(7) + "pior dia".rjust(11)
        + "MaxDD".rjust(10) + "R$/stop".rjust(9) + "stop%".rjust(7)
        + "win%".rjust(7) + "BE%".rjust(7) + "veredito".rjust(12))


def _linha(r) -> str:
    return (r["rotulo"].ljust(24) + br(r["liquido"]).rjust(12) + str(r["n"]).rjust(6)
            + (br(100 * r["frac_preg"], 0) + "%").rjust(7)
            + (br(100 * r["frac_bl"], 0) + "%").rjust(7)
            + br(r["pior_dia"]).rjust(11) + br(r["maxdd"], 0).rjust(10)
            + br(r["stop_rs"], 0).rjust(9)
            + (br(100 * r["stop_pct"], 0) + "%").rjust(7)
            + (br(100 * r["win"], 1) + "%").rjust(7)
            + (br(100 * r["be"], 1) + "%").rjust(7)
            + r["veredito"].rjust(12)
            + (("  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"]))
               if r["sem_trade"] else ""))


def main() -> None:
    tarefas = [(j, rot, kw) for j in ("IS", "OOS", "TUDO")
               for rot, kw in VARIANTES]
    print("freios de CAUDA ESQUERDA, um eixo por vez -- capital R$ "
          + br(CAPITAL, 0) + ", geometria de PRODUCAO (alvo 9,5 / stop 12,0)")
    print(str(len(VARIANTES)) + " variantes x 3 janelas = " + str(len(tarefas))
          + " celulas\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print("[" + str(len(resultados)).rjust(2) + "/" + str(len(tarefas))
                  + "] " + r["janela"].ljust(5) + r["rotulo"].ljust(24)
                  + " liq " + br(r["liquido"]).rjust(11)
                  + "  bl20+ " + (br(100 * r["frac_bl"], 0) + "%").rjust(5)
                  + "  " + r["veredito"], flush=True)

    ordem = [rot for rot, _ in VARIANTES]
    for janela in ("TUDO", "IS", "OOS"):
        sub = {r["rotulo"]: r for r in resultados if r["janela"] == janela}
        print("\n\n===== " + janela + " =====")
        print(_HDR)
        print("-" * len(_HDR))
        for rot in ordem:
            if rot in sub:
                print(_linha(sub[rot]) + ("   <== PRODUCAO" if rot == "PRODUCAO" else ""))


if __name__ == "__main__":
    main()
