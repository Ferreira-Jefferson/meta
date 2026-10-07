# -*- coding: utf-8 -*-
"""G35 -- grade de SAIDA sobre o padrao atual (G21+EMA34 congelado v29).
Entrada intocada. Stop inicial fixo 0,45x largura. Varia:
  alvo_mult in {2 (padrao), 2.5, 3 (pedido), 4}  (alvo = alvo_mult x stop)
  gestao    in {nenhuma, breakeven, trail1R, trail05R, alvo_movel}
Roda as 3 janelas de 2026. Leitura honesta: a escolha e' pelo IS; OOS-1 e
setembro so' conferem (a grade e' pequena e foi definida antes de rodar).
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

ALVOS = (2.0, 2.5, 3.0, 4.0)
GESTOES = ("nenhuma", "breakeven", "trail1R", "trail05R", "alvo_movel")
JANELAS = {
    "jan-jun": (b.CORTE_IS_INICIO, b.CORTE_IS_FIM),
    "jul-ago": (b.CORTE_IS_FIM, b.CORTE_OOS1_FIM),
    "set": (b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM),
}


def unidade(janela: str, alvo_mult: float, gestao: str) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        from backtest.intraday.engine import run_intraday_backtest
        from strategy.daytrade.lab.win_busca_lucro_g35_retangulo_ema34_gestao import (
            WinBuscaLucroG35RetanguloEma34Gestao as E,
        )
        win = b.carrega_win()
        ini, fim = JANELAS[janela]
        dias = b.dias_da_janela(win, ini, fim)
        st = E(gestao=gestao, periodo=34, stop_fracao_largura=b.STOP_FRACAO,
               alvo_fracao_largura=b.STOP_FRACAO * alvo_mult)
        res = run_intraday_backtest(b.bars_dos_dias(win, dias), st, b.monta_config(b.CAPITAL))
        trades = sorted(res.trades, key=lambda t: t.exit_ts)
        c = b.consistencia(trades, dias)
        eq, pico, dd = 0.0, 0.0, 0.0
        for t in trades:
            eq += t.pnl_brl; pico = max(pico, eq); dd = max(dd, pico - eq)
        ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
        perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    return dict(janela=janela, alvo=alvo_mult, gestao=gestao, n=c["n"], liquido=c["liquido"],
                win=100 * c["win"] if c["n"] else float("nan"),
                be=100 * c["be"] if c["be"] == c["be"] else float("nan"),
                ganho_med=sum(ganhos) / len(ganhos) if ganhos else 0.0,
                perda_med=sum(perdas) / len(perdas) if perdas else 0.0,
                maxdd=dd, veredito=c["veredito"])


def main() -> None:
    jobs = [(j, a, g) for j in JANELAS for a in ALVOS for g in GESTOES]
    linhas = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(unidade, *job): job for job in jobs}
        for f in as_completed(futs):
            r = f.result()
            linhas.append(r)
            print(f"{r['janela']:8s} alvo {r['alvo']:.1f}x {r['gestao']:10s} n={r['n']:4d} "
                  f"liq={b.br(r['liquido']):>10s} win={r['win']:5.1f}% be={r['be']:5.1f}% "
                  f"ganho={b.br(r['ganho_med']):>7s} perda={b.br(r['perda_med']):>7s} "
                  f"maxDD={b.br(r['maxdd']):>9s} {r['veredito']}", flush=True)
    import pandas as pd
    df = pd.DataFrame(linhas)
    df.to_csv(AQUI / "g35_grade.csv", index=False, sep=";", decimal=",")
    piv = df.pivot_table(index=["alvo", "gestao"], columns="janela", values="liquido")
    piv = piv[["jan-jun", "jul-ago", "set"]]
    piv["total"] = piv.sum(axis=1)
    print("\nLIQUIDO R$ por celula (linhas) x janela (colunas):")
    print(piv.round(2).to_string())


if __name__ == "__main__":
    main()
