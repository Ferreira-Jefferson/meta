"""Verificacao de seguranca do CopaWin (risco_pct_por_trade=0.05, ja em
producao) em capital ALTO -- ate agora so' foi medido comecando em R$3.000
(cresceu ate R$12.498) ou no piso fino (R$250-R$3.000). Nunca testado
COMECANDO direto em capital alto. Mesma pergunta que motivou a calibracao da
WDO F1: 5% e' seguro em TODO nivel, ou so' onde ja foi medido por acidente?

Uso: python -u scripts/daytrade/copawin_seguranca_capital_alto_2026_08_29.py
"""
from __future__ import annotations
import os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WIN@"
NIVEIS = [5_000.0, 10_000.0, 20_000.0, 30_000.0, 50_000.0, 100_000.0]
MIN_BARRAS = 400
_CACHE = None

def br(v, dec=2):
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def _bars():
    global _CACHE
    if _CACHE is None:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1
        df = load_m1(SYMBOL).sort_index()
        cont = df.groupby(df.index.date).size()
        ok = {d for d, n in cont.items() if n >= MIN_BARRAS}
        _CACHE = df[[d in ok for d in df.index.date]]
    return _CACHE

def _roda(capital):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot
    bars = _bars()
    profile = profile_for(SYMBOL)
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    cfg = config_for(profile, trade_tick_value=0.20, trade_tick_size=1.0,
                      initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
                      limit_fill_capped_by_volume=True)
    t0 = time.perf_counter()
    r = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0
    liquido = sum(t.pnl_brl for t in r.trades)
    qtds = sorted({t.quantity for t in r.trades}) if r.trades else []
    ef = float(r.equity_curve.iloc[-1]) if not r.equity_curve.empty else capital
    em = float(r.equity_curve.min()) if not r.equity_curve.empty else capital
    return dict(capital=capital, dt=dt, trades=len(r.trades), liquido=liquido,
                equity_final=ef, equity_min=em, quantidades=qtds)

def main():
    n = min(len(NIVEIS), os.cpu_count() or 4)
    print(f"[copawin_seguranca] {SYMBOL}, {len(NIVEIS)} niveis, {n} processos\n", flush=True)
    linhas = []
    with ProcessPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(_roda, c): c for c in NIVEIS}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            linhas.append(r)
            alerta = "QUASE ZEROU" if r["equity_min"] < 0.1 * r["capital"] else "ok"
            print(f"  [{i}/{len(NIVEIS)} {r['dt']:5.1f}s] R${br(r['capital'],0):>10s} -> "
                  f"trades={r['trades']:4d} liquido=R${br(r['liquido']):>13s} "
                  f"final=R${br(r['equity_final']):>13s} min=R${br(r['equity_min']):>13s} "
                  f"qtds={r['quantidades']} [{alerta}]", flush=True)
    print("\n=== resumo ===")
    for l in sorted(linhas, key=lambda l: l["capital"]):
        print(f"  R${br(l['capital'],0):>10s}: liquido=R${br(l['liquido'],2)} final=R${br(l['equity_final'],2)} min=R${br(l['equity_min'],2)}")

if __name__ == "__main__":
    main()
