# -*- coding: utf-8 -*-
"""Teste correto do eixo que sobra: direcao (compra/venda) e' FORCADA pela
mecanica (a ordem descansa no meio -- so' um lado e' limite de verdade dado
onde o preco esta). O grau de liberdade real e' qual FRACAO faz o papel de
alvo e qual faz o papel de stop.

Original (D1 centro, herdado do WIN): alvo=0,80xL (alem da borda proxima,
continuacao), stop=0,50xL (na borda oposta).

Este teste: TROCA as duas -- alvo=0,50xL (so' ate' a borda proxima, mais
facil de bater), stop=0,80xL (alem da borda oposta, mais largo). Mesma
direcao (forcada), payoff invertido: alvo menor, stop maior -- precisa de
win% MAIOR pra empatar, mas o alvo mais perto pode compensar."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
MIN_BARRAS_POR_PREGAO = 500

IS_INICIO = pd.Timestamp("2026-02-27", tz="UTC")
IS_FIM = pd.Timestamp("2026-06-13", tz="UTC")
OOS_INICIO = pd.Timestamp("2026-06-15", tz="UTC")
OOS_FIM = pd.Timestamp("2026-08-26", tz="UTC")


def br(v, dec=1):
    if v != v:
        return "--"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    from market_data_intraday.storage import load_m1
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_retangulo import WdoRetangulo, detecta_retangulo
    from core.models import IntradayExitReason

    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    df = df[[d in completos for d in df.index.date]]

    def dias_da_janela(inicio, fim):
        bars = df[(df.index >= inicio) & (df.index < fim)]
        dias = sorted({d for d in bars.index.date if d in completos})
        bars = bars[[d in set(dias) for d in bars.index.date]]
        return bars, dias

    bars_is, dias_is = dias_da_janela(IS_INICIO, IS_FIM)
    bars_oos, dias_oos = dias_da_janela(OOS_INICIO, OOS_FIM)

    def larguras_do_dia(bars_dia, W):
        high = bars_dia["high"].to_numpy(float)
        low = bars_dia["low"].to_numpy(float)
        close = bars_dia["close"].to_numpy(float)
        n = len(close)
        minimo_barras = 3 * W
        if n < minimo_barras:
            return []
        larguras, ret, fora = [], None, 0
        t = minimo_barras - 1
        while t < n:
            if ret is None:
                ini = t - W + 1
                ant_ini = t - 3 * W + 1
                amp_ant = (float(high[ant_ini:ini].max() - low[ant_ini:ini].min())
                           if ant_ini >= 0 else None)
                r = detecta_retangulo(high[ini:t+1], low[ini:t+1], close[ini:t+1], amp_ant)
                if r is not None:
                    larguras.append(r["largura"]); ret = r; fora = 0
                t += 1
            else:
                margem = 0.25 * ret["largura"]
                c = close[t]
                if c > ret["topo"] + margem or c < ret["piso"] - margem:
                    fora += 1
                    if fora >= 3:
                        ret = None; fora = 0
                else:
                    fora = 0
                t += 1
        return larguras

    todas_w20 = []
    for d in dias_is:
        bd = bars_is[bars_is.index.date == d]
        todas_w20.extend(larguras_do_dia(bd, 20))
    piso_w20 = float(np.quantile(todas_w20, 2 / 3))
    print(f"piso_w20 (mesmo da calibracao oficial) = {br(piso_w20, 2)} pts\n")

    def roda(dias, alvo_frac, stop_frac):
        alvo_dias = set(dias)
        bars = df[[d in alvo_dias for d in df.index.date]]
        strat = WdoRetangulo(
            janela_barras=20, largura_minima_pontos=piso_w20,
            alvo_fracao_largura=alvo_frac, stop_fracao_largura=stop_frac,
        )
        profile = profile_for(SYMBOL)
        cfg = config_for(
            profile, trade_tick_value=0.01, trade_tick_size=0.001,
            initial_capital=CAPITAL_REAL_BRL,
            target_fills_as_maker=strat.target_fills_as_maker,
            anchor_exits_at_fill=strat.anchor_exits_at_fill,
            limit_fill_capped_by_volume=True,
        )
        return run_intraday_backtest(bars, strat, cfg)

    def resume(trades, n_dias):
        n = len(trades)
        liquido = sum(t.pnl_brl for t in trades)
        g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
        p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
        gm = (sum(g) / len(g)) if g else 0.0
        pm = (abs(sum(p) / len(p))) if p else 0.0
        be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
        win = len(g) / n if n else float("nan")
        dias_com_trade = len({pd.Timestamp(t.exit_ts).date() for t in trades})
        alvo_n = sum(1 for t in trades if t.exit_reason == IntradayExitReason.TARGET)
        stop_n = sum(1 for t in trades if t.exit_reason == IntradayExitReason.STOP)
        return dict(n=n, liquido=liquido, win=win, be=be, alvo=alvo_n, stop=stop_n,
                    sem_trade=n_dias - dias_com_trade)

    VARIANTES = [
        ("ORIGINAL: alvo=0.80L / stop=0.50L", 0.80, 0.50),
        ("TROCADO:  alvo=0.50L / stop=0.80L", 0.50, 0.80),
    ]

    for nome, af, sf in VARIANTES:
        print(f"=== {nome} ===")
        for jn, dias in (("IS", dias_is), ("OOS", dias_oos)):
            res = roda(dias, af, sf)
            r = resume(list(res.trades), len(dias))
            pct = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
            print(f"  {jn:<4} n={r['n']:>4}  liquido={br(r['liquido']):>10}  "
                  f"win={pct(r['win']):>7}  BEemp={pct(r['be']):>7}  "
                  f"alvo={r['alvo']:>3}  stop={r['stop']:>3}  sem_trade={r['sem_trade']}/{len(dias)}")
        print()


if __name__ == "__main__":
    main()
