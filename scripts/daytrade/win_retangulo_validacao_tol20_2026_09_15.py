# -*- coding: utf-8 -*-
"""`win_retangulo` -- VALIDACAO INDEPENDENTE do achado do subagente (tol 20% +
teto de risco R$80), rodando o ROBO DE PRODUCAO e nao o laboratorio dele.

O subagente reportou +33% no IS e +46% no OOS mexendo em dois numeros. Antes
de adotar, tres coisas precisam ser verificadas por fora, porque cada uma
delas e' capaz de derrubar o achado:

  1. **O robo de producao reproduz os numeros do laboratorio dele?** Se nao
     reproduzir, o ganho e' do script, nao do robo -- e e' o robo que opera.

  2. **O REBAIXAMENTO piorou, e quanto?** O relatorio traz MaxDD subindo de
     ~686 para ~1.042 no IS. Isso importa MUITO aqui, porque o piso de caixa
     de R$650 foi derivado justamente de MaxDD + margem. Se o rebaixamento
     quase dobra, o piso deixa de ser R$650 e o dono precisa saber ANTES de
     ligar o robo, nao depois.

     O script mede o MaxDD pelos DOIS metodos que convivem no repo, porque
     eles divergem e a diferenca ja confundiu esta linha:
       * por SERIE DIARIA (soma o pregao, depois acumula) -- foi o que deu
         R$525,60 e originou o piso de R$650;
       * por OPERACAO (acumula trade a trade) -- e' o que o PORTAO DE CAPITAL
         de fato enxerga, porque o caixa e' creditado/debitado por operacao.
     O segundo e' o certo para decidir caixa. O primeiro suaviza o que
     acontece dentro do dia e por isso e' otimista.

  3. **O piso de caixa ainda e' R$650?** Escada de capital na variante nova,
     procurando o penhasco do jeito que ele foi achado da primeira vez (a
     R$275 o desenho antigo calava para sempre).

Nada aqui re-otimiza nada: as tres variantes sao as que o subagente ja
decidiu, e o OOS entra so' para conferir o numero que ele reportou.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_validacao_tol20_2026_09_15.py`
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
    "estr_val", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_val"] = _estr
_spec.loader.exec_module(_estr)

_base = _estr._base
SYMBOL = _base.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()
MARGEM_WIN = 100.0

VARIANTES = {
    "1 BASELINE tol 8%, sem teto": dict(tolerancia_borda=0.08,
                                        risco_maximo_brl=float("inf")),
    "2 tol 20%, sem teto": dict(tolerancia_borda=0.20,
                                risco_maximo_brl=float("inf")),
    "3 tol 20% + teto R$80": dict(tolerancia_borda=0.20, risco_maximo_brl=80.0),
}
#: escada so' da variante 3 (a recomendada), para achar o piso NOVO
CAPITAIS = (250.0, 400.0, 650.0, 800.0, 1000.0, 1150.0, 1300.0, 1600.0, 3000.0)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _maxdd(valores: np.ndarray) -> float:
    if len(valores) == 0:
        return float("nan")
    eq = np.cumsum(valores)
    return float(np.maximum.accumulate(eq).__sub__(eq).max())


def _unidade(args):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.win_retangulo import WinRetangulo

    rotulo, janela, dias, kw, capital = args
    strat = WinRetangulo(**kw)
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(SYMBOL)
    # SEM `dataclasses.replace`: `config_for` ja entrega o corte de achatamento
    # recuado de FOLGA_ACHATAMENTO_MINUTOS (18:20 BRT), que e' exatamente o que
    # a producao usa. Mexer aqui seria inventar um pregao que o robo nao opera.
    cfg = config_for(
        profile, trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True, queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    c = _base.consistencia(trades, dias)

    seq = np.array([t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)],
                   dtype=float)
    c["maxdd_dia"] = _maxdd(c["serie"].to_numpy(float))
    c["maxdd_op"] = _maxdd(seq)
    c["caixa_min"] = float(capital + np.cumsum(seq).min()) if len(seq) else capital
    c["pior"] = float(seq.min()) if len(seq) else 0.0
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    c.pop("serie", None)
    return dict(rotulo=rotulo, janela=janela, capital=capital, c=c)


def main():
    df, dias_todos = _base._df()
    JAN = {"IS": [d for d in dias_todos if d < CORTE_OOS],
           "OOS": [d for d in dias_todos if d >= CORTE_OOS]}

    print("=" * 134)
    print("win_retangulo -- VALIDACAO do tol 20% + teto de risco, no ROBO DE PRODUCAO")
    print("=" * 134)
    print(f"  IS {len(JAN['IS'])} pregoes | OOS {len(JAN['OOS'])} pregoes | "
          f"1 contrato | custo 7,5 pontos")
    print("  horario: o mesmo da producao -- achatamento 18:20 BRT, fim 18:25 "
          "(vem de config_for, nao digitado)")
    print("  fila NAO calibrada para WIN@: preenche no TOQUE nas duas pontas\n",
          flush=True)

    tarefas = [(rot, jn, dd, kw, 650.0)
               for jn, dd in JAN.items() for rot, kw in VARIANTES.items()]
    tarefas += [(f"escada {cap:.0f}", jn, dd, VARIANTES["3 tol 20% + teto R$80"], cap)
                for jn, dd in JAN.items() for cap in CAPITAIS]

    out = {}
    feitos = 0
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["rotulo"], r["janela"])] = r["c"]
            feitos += 1
            if feitos % 8 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
    print("\n" + "=" * 134)
    print("AS TRES VARIANTES, capital R$650")
    print("=" * 134)
    hdr = (f"  {'janela':<6}{'variante':<30}{'liquido':>11}{'trades':>8}{'win%':>7}"
           f"{'BEemp%':>9}{'veredito':>12}{'pts/op':>9}{'DD dia':>10}{'DD oper.':>10}"
           f"{'pior op.':>10}{'caixa min':>11}{'sem_tr':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for jn in JAN:
        for rot in VARIANTES:
            c = out[(rot, jn)]
            print(f"  {jn:<6}{rot:<30}{br(c['liquido']):>11}{c['n']:>8}{pc(c['win']):>7}"
                  f"{pc(c['be']):>9}{c['veredito']:>12}{br(c['pts'],1):>9}"
                  f"{br(c['maxdd_dia']):>10}{br(c['maxdd_op']):>10}{br(c['pior']):>10}"
                  f"{br(c['caixa_min']):>11}"
                  f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")
        print()

    print("=" * 134)
    print("ESCADA DE CAPITAL da variante 3 -- o piso de R$650 ainda serve?")
    print("=" * 134)
    hdr2 = (f"  {'capital':>9}{'jan':<5}{'liquido':>11}{'trades':>8}{'% das op.':>11}"
            f"{'caixa min':>11}{'pior op.':>10}{'sem_trade':>12}")
    print(hdr2)
    print("  " + "-" * (len(hdr2) - 2))
    for jn in JAN:
        ref = out[(f"escada {3000.0:.0f}", jn)]["n"]
        for cap in CAPITAIS:
            c = out[(f"escada {cap:.0f}", jn)]
            marca = "  <- CENSURADA" if c["caixa_min"] < MARGEM_WIN else ""
            print(f"  {br(cap,0):>9}{jn:<5}{br(c['liquido']):>11}{c['n']:>8}"
                  f"{(br(100*c['n']/ref,0)+'%') if ref else '--':>11}"
                  f"{br(c['caixa_min']):>11}{br(c['pior']):>10}"
                  f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>12}{marca}")
        print()

    print("=" * 134)
    print("O PISO, pelas duas leituras")
    print("=" * 134)
    for rot in VARIANTES:
        dd_op = max(out[(rot, "IS")]["maxdd_op"], out[(rot, "OOS")]["maxdd_op"])
        dd_dia = max(out[(rot, "IS")]["maxdd_dia"], out[(rot, "OOS")]["maxdd_dia"])
        print(f"  {rot:<30} DD por operacao {br(dd_op):>9} -> piso {br(dd_op+MARGEM_WIN):>9}"
              f"   |  DD diario {br(dd_dia):>9} -> piso {br(dd_dia+MARGEM_WIN):>9}")
    print("\n  'piso' = pior rebaixamento observado + margem crua do WIN@ (R$100): o caixa")
    print("  que aguenta COMECAR EM QUALQUER PONTO da serie. A escada acima mostra o outro")
    print("  numero, o que basta para comecar no dia 1 -- e os dois nao sao a mesma coisa.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
