# -*- coding: utf-8 -*-
"""`win_retangulo` -- CONFERENCIA DE ARRANQUE: o robo de producao reproduz o
laboratorio?

Esta e' a unica coisa que separa "o robo que a gente validou" de "um robo
parecido com o que a gente validou". O motor e' o mesmo, a janela e' a mesma,
o custo e' o mesmo -- se o numero nao bater, o robo de producao nao e' o robo
medido, e toda a tabela do relatorio deixa de descrever ele.

Compara `strategy.daytrade.lab.win_retangulo.WinRetangulo` (producao, defaults
da classe) contra `RetanguloLab` (o laboratorio) com os parametros congelados,
nas DUAS janelas, com o capital de PARTIDA medido (R$650).

## A diferenca conhecida, declarada de proposito

O laboratorio faz a conferencia mecanica ("a limite descansa do lado certo?")
com o preco CRU do meio e so' depois arredonda ao tick. A producao arredonda
PRIMEIRO e confere o preco que a ordem de fato vai ter. A producao esta certa
-- e' o preco arredondado que vai para a corretora, e uma limite que cai em
cima do preco e' ordem a mercado disfarcada, que o desenho de execucao deste
projeto proibe.

Entao um punhado de operacoes pode divergir. Este script MEDE essa divergencia
em vez de supor que ela e' pequena: se ela mover o resultado de forma
material, quem manda e' a producao e a tabela do relatorio tem de ser
reescrita com o numero dela.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_conferencia_arranque_2026_09_15.py`
"""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "estr_conf", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_conf"] = _estr
_spec.loader.exec_module(_estr)

_base = _estr._base
SYMBOL = _base.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()
CAPITAL = 650.0
GEO_LAB = dict(modo="centro", W=20, alvo_frac=1.6, stop_frac=0.5,
               max_barras_apos=None, uma_por_retangulo=False,
               barras_extra_apos_morte=0, largura_min_pontos=328.0)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _maxdd(serie: pd.Series) -> float:
    if len(serie) == 0:
        return float("nan")
    eq = serie.cumsum()
    return float((eq.cummax() - eq).max())


def _unidade(args):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import _recua, config_for, profile_for
    from strategy.daytrade.lab.win_retangulo import WinRetangulo

    qual, janela, dias = args
    # tolerancia 0,08 e SEM teto de risco: sao os parametros do laboratorio.
    # Os DEFAULTS da classe hoje sao outros (0,20 e R$80, medidos depois) --
    # esta conferencia existe para provar que a PORTA e' fiel, entao ela tem
    # de comparar a mesma configuracao dos dois lados.
    strat = (WinRetangulo(tolerancia_borda=0.08, risco_maximo_brl=float("inf"))
             if qual == "producao" else _estr.RetanguloLab(**GEO_LAB))

    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True, queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    cfg = dataclasses.replace(cfg, session_end_time=_recua(profile.session_end_time, 5))

    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    c = _base.consistencia(trades, dias)
    c["maxdd"] = _maxdd(c["serie"])
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    c["caixa_min"] = float(CAPITAL + np.cumsum(seq).min()) if seq else CAPITAL
    c.pop("serie", None)
    # assinatura das operacoes, para localizar divergencia
    c["chaves"] = {(t.entry_ts.isoformat(), round(t.entry_price, 2),
                    round(t.exit_price, 2)) for t in trades}
    return dict(qual=qual, janela=janela, c=c)


def main():
    df, dias_todos = _base._df()
    JAN = {"IS": [d for d in dias_todos if d < CORTE_OOS],
           "OOS": [d for d in dias_todos if d >= CORTE_OOS]}

    print("=" * 118)
    print("win_retangulo -- CONFERENCIA DE ARRANQUE (producao x laboratorio)")
    print("=" * 118)
    print(f"  capital R$ {br(CAPITAL,0)} (piso de partida medido) | 1 contrato | "
          f"custo ida-e-volta 7,5 pontos")
    print("  premissa de execucao: WIN@ sem fila calibrada -> limite preenche no TOQUE\n",
          flush=True)

    out = {}
    tarefas = [(q, jn, dd) for jn, dd in JAN.items() for q in ("producao", "laboratorio")]
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["qual"], r["janela"])] = r["c"]
            print(f"  ok {r['janela']:<5}{r['qual']}", flush=True)

    hdr = (f"\n  {'janela':<6}{'origem':<14}{'liquido':>11}{'trades':>8}{'win%':>7}"
           f"{'BEemp%':>9}{'pts/op':>9}{'MaxDD':>10}{'caixa min':>11}{'sem_tr':>10}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 3))
    for jn in JAN:
        for q in ("laboratorio", "producao"):
            c = out[(q, jn)]
            pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
            print(f"  {jn:<6}{q:<14}{br(c['liquido']):>11}{c['n']:>8}{pc(c['win']):>7}"
                  f"{pc(c['be']):>9}{br(c['pts'],2):>9}{br(c['maxdd']):>10}"
                  f"{br(c['caixa_min']):>11}"
                  f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>10}")
        print()

    print("=" * 118)
    print("DIVERGENCIA")
    print("=" * 118)
    ok = True
    for jn in JAN:
        lab, prod = out[("laboratorio", jn)], out[("producao", jn)]
        d_liq = prod["liquido"] - lab["liquido"]
        so_lab = lab["chaves"] - prod["chaves"]
        so_prod = prod["chaves"] - lab["chaves"]
        iguais = len(lab["chaves"] & prod["chaves"])
        print(f"  {jn}: liquido {br(d_liq):>10} "
              f"({br(100*d_liq/lab['liquido'],2) if lab['liquido'] else '—'}%) | "
              f"operacoes {prod['n'] - lab['n']:+d}")
        print(f"        {iguais} operacoes IDENTICAS | {len(so_lab)} so' no laboratorio | "
              f"{len(so_prod)} so' na producao")
        if so_lab or so_prod:
            ok = False
            for k in sorted(so_lab)[:3]:
                print(f"          so' lab : {k[0]}  entrada {br(k[1])}  saida {br(k[2])}")
            for k in sorted(so_prod)[:3]:
                print(f"          so' prod: {k[0]}  entrada {br(k[1])}  saida {br(k[2])}")

    print()
    if ok:
        print("  ARRANQUE CONFERE byte a byte: producao e laboratorio sao o MESMO robo.")
    else:
        print("  Ha divergencia. Ela e' ESPERADA (ver a docstring): a producao confere o")
        print("  lado da limite DEPOIS de arredondar ao tick, o laboratorio ANTES. Quem")
        print("  manda e' a producao -- o numero dela e' o que descreve o robo que opera.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
