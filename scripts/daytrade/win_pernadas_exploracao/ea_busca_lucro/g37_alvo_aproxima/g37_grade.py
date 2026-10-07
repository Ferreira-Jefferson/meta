# -*- coding: utf-8 -*-
"""G37 (curiosidade do dono) -- alvo que se APROXIMA com o tempo. Stop fixo 0,45;
0,90x largura. Celulas:
  fixo: stop in {0.45 (padrao), 0.55, 0.65, 0.75, 0.85}
  que se afasta (checado no fechamento, nativo no teto 0,85): passo 5 e 15 velas
  CONTROLE: passo infinito = stop 0,45 checado no FECHAMENTO (separa o efeito
  "checar no fechamento" do efeito "afastar").
"""
from __future__ import annotations

import io
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "g29_ema34"))
import g29_base as b  # noqa: E402

ALVO = 0.90
CELULAS = [("alvo parado 0,90 (padrao)", 0.45, None),
           ("encolhe a cada 40 velas", 0.45, 40), ("encolhe a cada 20 velas", 0.45, 20),
           ("encolhe a cada 10 velas", 0.45, 10), ("encolhe a cada 5 velas", 0.45, 5)]
JANELAS = {
    "jan-jun": (b.CORTE_IS_INICIO, b.CORTE_IS_FIM),
    "jul-ago": (b.CORTE_IS_FIM, b.CORTE_OOS1_FIM),
    "set": (b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM),
}


def unidade(janela, rotulo, stop, passo):
    buf = io.StringIO()
    with redirect_stdout(buf):
        from backtest.intraday.engine import run_intraday_backtest
        from strategy.daytrade.lab.win_busca_lucro_g37_retangulo_ema34_alvo_aproxima import (
            WinBuscaLucroG37RetanguloEma34AlvoAproxima as E,
        )
        win = b.carrega_win()
        dias = b.dias_da_janela(win, *JANELAS[janela])
        st = E(passo_barras=passo, periodo=34, stop_fracao_largura=stop, alvo_fracao_largura=ALVO)
        res = run_intraday_backtest(b.bars_dos_dias(win, dias), st, b.monta_config(b.CAPITAL))
        trades = sorted(res.trades, key=lambda t: t.exit_ts)
        c = b.consistencia(trades, dias)
        eq = pico = dd = 0.0
        for t in trades:
            eq += t.pnl_brl; pico = max(pico, eq); dd = max(dd, pico - eq)
        g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
        p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    return dict(janela=janela, celula=rotulo, n=c["n"], liquido=c["liquido"],
                win=100 * c["win"] if c["n"] else float("nan"),
                ganho=sum(g) / len(g) if g else 0.0, perda=sum(p) / len(p) if p else 0.0,
                maxdd=dd, caixa_min=b.CAPITAL - dd)


def main():
    import pandas as pd
    linhas = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(unidade, j, *c) for j in JANELAS for c in CELULAS]
        for f in as_completed(futs):
            r = f.result(); linhas.append(r)
            print(f"{r['janela']:8s} {r['celula']:30s} n={r['n']:4d} liq={b.br(r['liquido']):>10s} "
                  f"win={r['win']:5.1f}% ganho={b.br(r['ganho']):>7s} perda={b.br(r['perda']):>8s} "
                  f"maxDD={b.br(r['maxdd']):>9s}", flush=True)
    df = pd.DataFrame(linhas)
    df.to_csv(AQUI / "g37_grade.csv", index=False, sep=";", decimal=",")
    piv = df.pivot_table(index="celula", columns="janela", values="liquido")[["jan-jun", "jul-ago", "set"]]
    piv["total"] = piv.sum(axis=1)
    print("\n" + piv.loc[[c[0] for c in CELULAS]].round(2).to_string())


if __name__ == "__main__":
    main()
