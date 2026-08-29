"""Varredura fina do piso de sobrevivencia do `CopaWin` (WIN@), mesma
metodologia de `wdof1_sobrevivencia_capital_baixo_2026_08_29.py` -- motivada
pela proposta do dono de "operar so com 1 contrato ate acumular": medido
(`copawin_e_gremah_piso_capital_2026_08_29`) que R$250 (piso de tabela COM
reserva) trava em 2 trades/182 pregoes, e R$3.000 funciona muito bem
(+R$9.498,00) -- intervalo largo, sem saber onde fica a fronteira real.

CopaWin (diferente da WDO F1) NAO tem uma familia de stop_ticks pra varrer --
os parametros de sinal (`alvo_vol`/`stop_vol`/etc) sao a calibracao OOS
confirmada de `_KWARGS_PADRAO["copa_win"]` e nao entram em disputa aqui. Isto
varre SO' capital, com os defaults de producao (`get_daytrade_robot`,
`risco_pct_por_trade=0.05` ja incluso).

Mesmo caminho de producao (`config_for` com `enforce_capital_cap` automatico
pra perfil de futuro), historico M1 salvo INTEIRO (182 pregoes, WIN@,
2025-12-01 -> 2026-08-27), passada continua.

Uso: `python -u scripts/daytrade/copawin_piso_sobrevivencia_2026_08_29.py`
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WIN@"
NIVEIS_CAPITAL = [250.0, 375.0, 500.0, 750.0, 1_000.0, 1_500.0, 2_000.0, 2_500.0, 3_000.0]
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
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    liquido = sum(t.pnl_brl for t in resultado.trades)
    equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else capital
    equity_min = float(resultado.equity_curve.min()) if not resultado.equity_curve.empty else capital

    return dict(capital=capital, dt=dt, trades=len(resultado.trades), liquido=liquido,
                equity_final=equity_final, equity_min=equity_min,
                recusadas_capital=resultado.ordens_recusadas_por_capital,
                zerou=resultado.wiped_out_at is not None)


def main() -> None:
    n_workers = min(len(NIVEIS_CAPITAL), os.cpu_count() or 4)
    print(f"[copawin_piso] {SYMBOL}, {len(NIVEIS_CAPITAL)} niveis de capital, "
          f"{n_workers} processos em paralelo\n", flush=True)
    t0 = time.perf_counter()
    linhas = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, cap): cap for cap in NIVEIS_CAPITAL}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            linhas.append(r)
            feitos += 1
            trava = "TRAVOU/QUASE" if r["trades"] < 50 else "ok"
            print(f"  [{feitos}/{len(NIVEIS_CAPITAL)} {r['dt']:5.1f}s] R${br(r['capital'],0):>8s} -> "
                  f"trades={r['trades']:5d} liquido=R${br(r['liquido']):>12s} "
                  f"final=R${br(r['equity_final']):>10s} min=R${br(r['equity_min']):>10s} "
                  f"recusadas={r['recusadas_capital']:5d} [{trava}]", flush=True)
    print(f"\ntotal: {time.perf_counter()-t0:.1f}s\n")
    print("=== CopaWin (WIN@) -- capital x resultado, historico inteiro (182 pregoes) ===")
    for l in sorted(linhas, key=lambda l: l["capital"]):
        print(f"  R${br(l['capital'],0):>8s}: trades={l['trades']:5d} liquido=R${br(l['liquido']):>12s} "
              f"final=R${br(l['equity_final']):>10s}")


if __name__ == "__main__":
    main()
