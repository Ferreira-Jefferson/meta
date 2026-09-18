# -*- coding: utf-8 -*-
"""Quebra de exit_reason (stop/alvo/flatten) do wdo_retangulo, IS e OOS,
para as 4 variantes ja calibradas em
scripts/daytrade/wdo_retangulo_calibracao_is_oos_2026_09_16.py -- reusa a
mesma calibracao de piso de largura, mesma janela congelada, mesmo capital
real e fila real. Nao e novo experimento, e leitura mais fina do mesmo run."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
MIN_BARRAS_POR_PREGAO = 500

IS_INICIO = pd.Timestamp("2026-02-27", tz="UTC")
IS_FIM = pd.Timestamp("2026-06-13", tz="UTC")
OOS_INICIO = pd.Timestamp("2026-06-15", tz="UTC")
OOS_FIM = pd.Timestamp("2026-08-26", tz="UTC")


def br(v, dec=1):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    from market_data_intraday.storage import load_m1
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_retangulo import WdoRetangulo, detecta_retangulo
    import numpy as np
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

    # recalibra o piso empirico (mesmo metodo/numero do script oficial)
    def larguras_do_dia(bars_dia, W):
        high = bars_dia["high"].to_numpy(float)
        low = bars_dia["low"].to_numpy(float)
        close = bars_dia["close"].to_numpy(float)
        n = len(close)
        minimo_barras = 3 * W
        if n < minimo_barras:
            return []
        larguras = []
        ret = None
        fora = 0
        t = minimo_barras - 1
        while t < n:
            if ret is None:
                ini = t - W + 1
                ant_ini = t - 3 * W + 1
                amp_ant = (float(high[ant_ini:ini].max() - low[ant_ini:ini].min())
                           if ant_ini >= 0 else None)
                r = detecta_retangulo(high[ini:t+1], low[ini:t+1], close[ini:t+1], amp_ant)
                if r is not None:
                    larguras.append(r["largura"])
                    ret = r
                    fora = 0
                t += 1
            else:
                margem = 0.25 * ret["largura"]
                c = close[t]
                if c > ret["topo"] + margem or c < ret["piso"] - margem:
                    fora += 1
                    if fora >= 3:
                        ret = None
                        fora = 0
                else:
                    fora = 0
                t += 1
        return larguras

    todas_w20, todas_w30 = [], []
    for d in dias_is:
        bd = bars_is[bars_is.index.date == d]
        todas_w20.extend(larguras_do_dia(bd, 20))
        todas_w30.extend(larguras_do_dia(bd, 30))
    piso_w20 = float(np.quantile(todas_w20, 2/3))
    piso_w30 = float(np.quantile(todas_w30, 2/3))

    VARIANTES = [
        ("1 CANDIDATO W20 (piso tercil)", dict(janela_barras=20, largura_minima_pontos=piso_w20)),
        ("2 W20 sem piso empirico", dict(janela_barras=20, largura_minima_pontos=0.0)),
        ("3 W30 (ref, piso tercil)", dict(janela_barras=30, largura_minima_pontos=piso_w30)),
    ]

    def roda(dias, kwargs_estrategia):
        alvo = set(dias)
        bars = df[[d in alvo for d in df.index.date]]
        strat = WdoRetangulo(**kwargs_estrategia)
        profile = profile_for(SYMBOL)
        cfg = config_for(
            profile,
            trade_tick_value=0.01, trade_tick_size=0.001,
            initial_capital=CAPITAL_REAL_BRL,
            target_fills_as_maker=strat.target_fills_as_maker,
            anchor_exits_at_fill=strat.anchor_exits_at_fill,
            limit_fill_capped_by_volume=True,
        )
        return run_intraday_backtest(bars, strat, cfg)

    janelas = {"IS": dias_is, "OOS": dias_oos}
    print(f"piso_w20={br(piso_w20,2)} pts | piso_w30={br(piso_w30,2)} pts\n")

    for jn, dj in janelas.items():
        print(f"=== {jn} ({len(dj)} pregoes) ===")
        for rot, kw in VARIANTES:
            res = roda(dj, kw)
            trades = list(res.trades)
            n = len(trades)
            cont = {}
            for t in trades:
                cont[t.exit_reason] = cont.get(t.exit_reason, 0) + 1
            stop = cont.get(IntradayExitReason.STOP, 0)
            target = cont.get(IntradayExitReason.TARGET, 0)
            flatten = cont.get(IntradayExitReason.FORCED_FLATTEN, 0)
            outros = n - stop - target - flatten
            pct = lambda x: (br(100 * x / n, 1) + "%") if n else "--"
            print(f"  {rot:<32} n={n:>4}  alvo={target:>3} ({pct(target)})  "
                  f"stop={stop:>3} ({pct(stop)})  flatten={flatten:>3} ({pct(flatten)})  "
                  f"outros={outros:>3} ({pct(outros)})")
        print()


if __name__ == "__main__":
    main()
