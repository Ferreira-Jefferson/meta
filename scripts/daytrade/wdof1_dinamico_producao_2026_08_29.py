"""Verificacao do dimensionamento dinamico da `WdoGridReloadMaker` recem-
LIGADO em producao (`registry._KWARGS_PADRAO`, 2026-08-29) -- pedido do
dono: "wdo tambem tem que ser dinamico... implemente pra rodar em producao,
em ambos [WDO e WIN]".

Ate agora a WDO F1 sempre pediu exatamente 1 contrato (`default_quantity=1`
do perfil de futuro, sem dimensionamento dinamico proprio ligado). Este
script confirma DUAS coisas pelo caminho de producao real
(`get_daytrade_robot`, SEM parametro manual):

1. O piso de capital baixo (R$375 a R$3.000, ja medido em
   `wdof1_sobrevivencia_capital_baixo_2026_08_29.py`) NAO piora -- o teto por
   risco (5%) arredonda pra 0 contrato nesses niveis e o piso `max(1, teto)`
   da propria estrategia mantem exatamente 1 contrato, igual antes.
2. Capital ALTO (R$5.000 a R$50.000) agora escala de verdade (o teto por
   risco permite mais de 1 contrato), e ISSO NAO reintroduz o risco de
   quase-zerar que motivou o item 3.9 (CopaWin) -- a equity MINIMA de cada
   nivel nunca deve chegar perto de zero.

Mesma metodologia de sempre: historico M1 salvo INTEIRO (177 pregoes,
2025-12-09 -> 2026-08-28), passada CONTINUA, caminho de producao
(`config_for` sem `max_open_contracts`/`enforce_capital_cap` explicitos).

Uso: `python -u scripts/daytrade/wdof1_dinamico_producao_2026_08_29.py`
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WDO@"
NIVEIS_CAPITAL = [375.0, 500.0, 750.0, 1_000.0, 1_500.0, 2_000.0, 3_000.0,
                  5_000.0, 10_000.0, 20_000.0, 30_000.0, 50_000.0]
MIN_BARRAS_POR_PREGAO = 400

_BARS_CACHE = None


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _bars_do_processo() -> pd.DataFrame:
    global _BARS_CACHE
    if _BARS_CACHE is None:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        _BARS_CACHE = df[[d in completos for d in df.index.date]]
    return _BARS_CACHE


def _roda(capital):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars_do_processo()
    profile = profile_for(SYMBOL)
    strat = get_daytrade_robot("wdo_grid_reload_maker")
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=capital,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
    )
    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    liquido = sum(t.pnl_brl for t in resultado.trades)
    qtds = sorted({t.quantity for t in resultado.trades}) if resultado.trades else []
    equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else capital
    equity_min = float(resultado.equity_curve.min()) if not resultado.equity_curve.empty else capital

    return dict(capital=capital, dt=dt, trades=len(resultado.trades), liquido=liquido,
                equity_final=equity_final, equity_min=equity_min, quantidades=qtds,
                recusadas_capital=resultado.ordens_recusadas_por_capital,
                zerou=resultado.wiped_out_at is not None)


def main() -> None:
    n_workers = min(len(NIVEIS_CAPITAL), os.cpu_count() or 4)
    print(f"[wdof1_dinamico] {SYMBOL}, {len(NIVEIS_CAPITAL)} niveis de capital "
          f"(defaults de PRODUCAO, dinamico agora LIGADO), {n_workers} processos\n", flush=True)
    t0 = time.perf_counter()
    linhas = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, cap): cap for cap in NIVEIS_CAPITAL}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            linhas.append(r)
            feitos += 1
            alerta = "*** ZEROU ***" if r["zerou"] else (
                "*** QUASE ZEROU ***" if r["equity_min"] < 0.1 * r["capital"] else "ok")
            print(f"  [{feitos}/{len(NIVEIS_CAPITAL)} {r['dt']:5.1f}s] R${br(r['capital'],0):>9s} -> "
                  f"trades={r['trades']:5d} liquido=R${br(r['liquido']):>13s} "
                  f"final=R${br(r['equity_final']):>12s} min=R${br(r['equity_min']):>11s} "
                  f"qtds={r['quantidades']} [{alerta}]", flush=True)
    print(f"\ntotal: {time.perf_counter()-t0:.1f}s\n")
    print("=== WDO F1 dinamico (producao) -- capital x resultado, historico inteiro ===")
    for l in sorted(linhas, key=lambda l: l["capital"]):
        print(f"  R${br(l['capital'],0):>9s}: trades={l['trades']:5d} liquido=R${br(l['liquido']):>13s} "
              f"final=R${br(l['equity_final']):>12s} min=R${br(l['equity_min']):>11s} qtds={l['quantidades']}")


if __name__ == "__main__":
    main()
