# -*- coding: utf-8 -*-
"""O lado COMPRADO e o lado VENDIDO da estrategia ORIGINAL ja disparam em
momentos de mercado diferentes (close<meio vs close>meio sao dias/retangulos
diferentes, nao o mesmo caminho visto de dois angulos). Este script separa
os trades reais por lado pra mostrar isso com numero, respondendo a duvida
de que "e' a mesma ordem, so trocando o rotulo"."""
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

    def roda(dias):
        alvo_dias = set(dias)
        bars = df[[d in alvo_dias for d in df.index.date]]
        strat = WdoRetangulo(janela_barras=20, largura_minima_pontos=piso_w20)
        profile = profile_for(SYMBOL)
        cfg = config_for(
            profile, trade_tick_value=0.01, trade_tick_size=0.001,
            initial_capital=CAPITAL_REAL_BRL,
            target_fills_as_maker=strat.target_fills_as_maker,
            anchor_exits_at_fill=strat.anchor_exits_at_fill,
            limit_fill_capped_by_volume=True,
        )
        return run_intraday_backtest(bars, strat, cfg)

    def resume(trades):
        n = len(trades)
        if n == 0:
            return dict(n=0, win=float("nan"), liquido=0.0, alvo=0, stop=0)
        g = sum(1 for t in trades if t.pnl_brl > 0)
        alvo = sum(1 for t in trades if t.exit_reason == IntradayExitReason.TARGET)
        stop = sum(1 for t in trades if t.exit_reason == IntradayExitReason.STOP)
        return dict(n=n, win=g / n, liquido=sum(t.pnl_brl for t in trades),
                    alvo=alvo, stop=stop)

    print(f"piso_w20 = {br(piso_w20,2)} pts\n")
    for jn, dias in (("IS", dias_is), ("OOS", dias_oos)):
        res = roda(dias)
        trades = list(res.trades)
        vendidos = [t for t in trades if t.side == "short"]
        comprados = [t for t in trades if t.side == "long"]
        print(f"=== {jn} ===")
        for nome, ts in (("VENDIDO (close<meio)", vendidos), ("COMPRADO (close>meio)", comprados)):
            r = resume(ts)
            pct = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
            print(f"  {nome:<24} n={r['n']:>4}  win={pct(r['win']):>7}  "
                  f"alvo={r['alvo']:>3}  stop={r['stop']:>3}  liquido={br(r['liquido']):>10}")
        print()


if __name__ == "__main__":
    main()
