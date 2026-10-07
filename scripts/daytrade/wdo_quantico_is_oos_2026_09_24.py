# -*- coding: utf-8 -*-
"""WDO@: `wdo_quantico` (niveis do oscilador harmonico quantico) -- IS/OOS nas
janelas congeladas, capital real R$375, fila REAL de `fidelidade.py`, desenho
de execucao FECHADO. Base M1 (teste rapido: M1 e' OTIMISTA na fila; um
negativo aqui ja' decide, um positivo pede confirmacao em tick).

Linhas:
  1-3  QUANTICO W30/W60/W120 -- multiplicadores da equacao (1,414 / 2,449 sigma)
  4-5  PLACEBO W60 -- multiplicadores arbitrarios (1,0/2,0 e 2,0/3,0). Se o
       quantico nao se destaca deles, os niveis da equacao nao sao especiais.
  6    QUANTICO W60 SEM FILA -- so' contexto (tamanho do custo da fila).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/wdo_quantico_is_oos_2026_09_24.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))
sys.stdout.reconfigure(encoding="utf-8")

from wdo_retangulo_calibracao_is_oos_2026_09_16 import (  # noqa: E402
    CAPITAL_REAL_BRL, IS_FIM, IS_INICIO, OOS_FIM, OOS_INICIO, SYMBOL,
    _bars_e_dias, _dias_da_janela, br, consistencia,
)

VARIANTES = [
    ("1 QUANTICO W30", dict(janela_barras=30), False),
    ("2 QUANTICO W60", dict(janela_barras=60), False),
    ("3 QUANTICO W120", dict(janela_barras=120), False),
    ("4 PLACEBO W60 1,0/2,0", dict(janela_barras=60, k_entrada=1.0, k_stop=2.0), False),
    ("5 PLACEBO W60 2,0/3,0", dict(janela_barras=60, k_entrada=2.0, k_stop=3.0), False),
    ("6 QUANTICO W60 SEM FILA", dict(janela_barras=60), True),
]


def _roda(dias, kwargs, sem_fila):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_quantico import WdoQuantico

    df, _ = _bars_e_dias()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    strat = WdoQuantico(**kwargs)
    extra = dict(queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
                 target_slippage_ticks=0.0) if sem_fila else {}
    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
        **extra,
    )
    return run_intraday_backtest(bars, strat, cfg)


def _unidade(args):
    janela, dias, rotulo, kwargs, sem_fila = args
    with redirect_stdout(StringIO()):
        res = _roda(dias, kwargs, sem_fila)
    return dict(janela=janela, rotulo=rotulo, res=res, c=consistencia(list(res.trades), dias))


def main() -> None:
    _, dias_is = _dias_da_janela(IS_INICIO, IS_FIM)
    _, dias_oos = _dias_da_janela(OOS_INICIO, OOS_FIM)
    janelas = {"IS": dias_is, "OOS": dias_oos}
    print(f"WDO@ wdo_quantico -- IS {len(dias_is)} pregoes, OOS {len(dias_oos)} pregoes, "
          f"capital R$ {br(CAPITAL_REAL_BRL, 0)}, fila real, M1\n", flush=True)

    tarefas = [(jn, dj, rot, kw, sf) for jn, dj in janelas.items() for rot, kw, sf in VARIANTES]
    out: dict = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out.setdefault(r["janela"], {})[r["rotulo"]] = r
            c = r["c"]
            win = (br(100 * c["win"], 1) + "%") if c["n"] else "--"
            be = (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--"
            print(f"  ok {r['janela']:<4}{r['rotulo']:<26} liq={br(c['liquido']):>11} "
                  f"trades={c['n']:>5} win={win:>7} BEemp={be:>7} {c['veredito']:<10} "
                  f"sem_trade={c['sem_trade']}/{c['pregoes']}", flush=True)

    from backtest.intraday.report import linha_de_resultado, tabela

    EXTRAS = ("BEemp%", "IC95 win%", "veredito", "sem_tr")
    for jn, dj in janelas.items():
        print(f"\n{'=' * 120}\nWDO@ wdo_quantico -- {jn} ({len(dj)} pregoes)\n{'=' * 120}")
        linhas = []
        for rot, _kw, _sf in VARIANTES:
            r = out[jn][rot]
            c = r["c"]
            linhas.append(linha_de_resultado(rot, r["res"], CAPITAL_REAL_BRL, extras={
                "BEemp%": (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
                "IC95 win%": f"[{br(100 * c['lo'], 1)};{br(100 * c['hi'], 1)}]" if c["n"] else "--",
                "veredito": c["veredito"],
                "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
            }))
        print(tabela(linhas, extras=EXTRAS, largura_extra=14))
    print("\nveredito = IC95 do win% contra o breakeven EMPIRICO.")

    # Janela continua sai censurada (o caixa bate no piso em 1-2 pregoes).
    # Cada pregao vira uma PARTIDA independente de R$375 -- mesmo capital
    # real, amostra de operacoes muito maior.
    print(f"\n{'=' * 120}\nPARTIDA DIARIA -- cada pregao comeca em R$ {br(CAPITAL_REAL_BRL, 0)}\n{'=' * 120}")
    print(f"  {'janela':<5}{'variante':<26}{'trades':>7}{'win%':>8}{'BEemp%':>8}{'IC95 win%':>16}"
          f"{'veredito':>12}{'R$/op':>9}{'dias +':>8}{'dias -':>8}{'dias 0':>8}", flush=True)
    tarefas = [(jn, dj, rot, kw, sf) for jn, dj in janelas.items() for rot, kw, sf in VARIANTES]
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade_diaria, t) for t in tarefas]
        for fut in as_completed(futs):
            jn, rot, c, pos, neg, zero = fut.result()
            pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
            rop = br(c["liquido"] / c["n"], 2) if c["n"] else "--"
            print(f"  {jn:<5}{rot:<26}{c['n']:>7}{pc(c['win']):>8}{pc(c['be']):>8}"
                  f"{('[' + br(100*c['lo'],1) + ';' + br(100*c['hi'],1) + ']'):>16}"
                  f"{c['veredito']:>12}{rop:>9}{pos:>8}{neg:>8}{zero:>8}", flush=True)
    print("\nFIM.")


def _unidade_diaria(args):
    janela, dias, rotulo, kwargs, sem_fila = args
    trades = []
    pos = neg = zero = 0
    for d in dias:
        with redirect_stdout(StringIO()):
            res = _roda([d], kwargs, sem_fila)
        t = list(res.trades)
        trades.extend(t)
        s = sum(x.pnl_brl for x in t)
        pos += s > 0
        neg += s < 0
        zero += s == 0
    return janela, rotulo, consistencia(trades, dias), pos, neg, zero


if __name__ == "__main__":
    main()
