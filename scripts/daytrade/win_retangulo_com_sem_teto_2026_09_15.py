# -*- coding: utf-8 -*-
"""`win_retangulo` COM e SEM o teto de risco de R$80 -- quanto aquela celula
mudaria os numeros que ja foram mostrados?

Pergunta do dono (2026-09-15): "se nao tivesse com o ajuste da celula, aquele
que iniciou com o 80, o resultado seria diferente?".

Contexto: o teto de R$80 por operacao entrou no robo e foi DESLIGADO no mesmo
dia, depois de tres medicoes mostrarem que ele nao e' alavanca (no IS e' o
PIOR valor da vizinhanca R$70-120; no OOS e' um pico de uma celula so',
decidido por 2 rejeicoes em 133; e a largura preve retorno/risco na direcao
CONTRARIA ao teto). Todas as tabelas mostradas depois disso rodaram SEM ele.

Este script responde a pergunta na forma direta: as MESMAS janelas, com e sem,
pela regua padrao. Se a diferenca for grande, vale saber o tamanho dela mesmo
tendo decidido contra; se for pequena, a decisao custou pouco de qualquer
jeito.

Janelas: as duas semanas (01/09 a 14/09, 9 pregoes), cada pregao recente
separado, e as duas janelas congeladas (IS e OOS) para dar escala.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_com_sem_teto_2026_09_15.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402

CAPITAL = 1_100.0
MIN_BARRAS = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
TETO = 80.0


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _unidade(args):
    rotulo, dias, teto = args
    robo = WinRetangulo(risco_maximo_brl=teto)
    df = load_m1(robo.symbol).sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(robo.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01, initial_capital=CAPITAL,
        target_fills_as_maker=robo.target_fills_as_maker,
        anchor_exits_at_fill=robo.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True)
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, robo, cfg)
    trades = list(res.trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    return dict(rotulo=rotulo, teto=teto,
                liquido=sum(t.pnl_brl for t in trades), n=len(trades),
                win=(len(g) / len(trades)) if trades else float("nan"),
                pior=min(p) if p else 0.0,
                chaves={t.entry_ts.isoformat() for t in trades})


def main():
    df = load_m1("WIN@").sort_index()
    c = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in c.items() if n >= MIN_BARRAS)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]
    duas = [d for d in completos if pd.Timestamp("2026-09-01").date() <= d < HOJE]

    janelas = [("IS  (129 pregoes)", IS),
               ("OOS (64 pregoes)", OOS),
               ("2 semanas (9 pregoes)", duas),
               ("11/09 sex", [pd.Timestamp("2026-09-11").date()]),
               ("14/09 seg", [pd.Timestamp("2026-09-14").date()]),
               ("15/09 ter (parcial)", [HOJE])]

    print("=" * 128)
    print("win_retangulo -- COM e SEM o teto de risco de R$80 por operacao")
    print("=" * 128)
    print(f"  capital R$ {br(CAPITAL,0)} | 1 contrato | corte do perfil | fila NAO CALIBRADA")
    print("  o robo hoje roda SEM teto (`risco_maximo_brl=inf`): e' a coluna 'sem'\n",
          flush=True)

    tarefas = [(rot, dd, t) for rot, dd in janelas for t in (float("inf"), TETO)]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["rotulo"], r["teto"])] = r

    hdr = (f"  {'janela':<24}{'liq SEM':>11}{'liq COM':>11}{'diferenca':>12}"
           f"{'ops SEM':>9}{'ops COM':>9}{'win SEM':>9}{'win COM':>9}"
           f"{'pior SEM':>10}{'pior COM':>10}{'ops trocadas':>14}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for rot, _dd in janelas:
        s = out[(rot, float("inf"))]
        ct = out[(rot, TETO)]
        d = ct["liquido"] - s["liquido"]
        trocadas = len(s["chaves"] ^ ct["chaves"])
        pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
        print(f"  {rot:<24}{br(s['liquido']):>11}{br(ct['liquido']):>11}{br(d):>12}"
              f"{s['n']:>9}{ct['n']:>9}{pc(s['win']):>9}{pc(ct['win']):>9}"
              f"{br(s['pior']):>10}{br(ct['pior']):>10}{trocadas:>14}")

    print("\n  'ops trocadas' = operacoes que existem numa versao e nao na outra")
    print("  (diferenca simetrica dos conjuntos). E' o tamanho REAL do efeito do teto:")
    print("  o resto das operacoes e' identico nas duas.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
