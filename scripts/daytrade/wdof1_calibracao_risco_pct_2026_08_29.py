"""Calibracao do `risco_pct_por_trade` da WDO F1 -- o valor 0.05 (copiado
direto do `CopaWin`, sem medir se cabia AQUI) fez o capital R$5.000 -- antes
o piso LIMPO com dimensionamento estatico -- quase zerar (liquido
-R$4.753,12, equity minima R$246,88) quando o dinamico foi ligado em
producao. Motivo: o stop desta estrategia e' FIXO em R$ (`stop_ticks x
tick_size x point_value_brl` = 16 x 0,5 x 10 = R$80/contrato, CONSTANTE,
diferente do stop por volatilidade do CopaWin) -- 5% de caixa em torno de
R$5.000 ja libera 2-3 contratos ENQUANTO o caixa ainda esta' perto do piso,
amplificando a sequencia de perdas normal bem antes de existir folga de
verdade.

Varre `risco_pct_por_trade` em {0.01, 0.02, 0.03, 0.05} x os niveis de
capital que mais importam (onde o comportamento muda: 3.000/5.000/10.000/
20.000/30.000/50.000), mesmo caminho de producao
(`WdoGridReloadMaker(margin_per_contract_brl=150, hard_cap_contratos=5,
risco_pct_por_trade=X, point_value_brl=10.0)`), historico M1 salvo INTEIRO,
passada continua.

Uso: `python -u scripts/daytrade/wdof1_calibracao_risco_pct_2026_08_29.py`
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
RISCO_PCT_VALUES = [0.01, 0.02, 0.03, 0.05]
NIVEIS_CAPITAL = [3_000.0, 5_000.0, 10_000.0, 20_000.0, 30_000.0, 50_000.0]
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


def _roda(args):
    risco_pct, capital = args
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker

    bars = _bars_do_processo()
    profile = profile_for(SYMBOL)
    strat = WdoGridReloadMaker(
        margin_per_contract_brl=150.0, hard_cap_contratos=5,
        risco_pct_por_trade=risco_pct, point_value_brl=10.0,
    )
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

    return dict(risco_pct=risco_pct, capital=capital, dt=dt, trades=len(resultado.trades),
                liquido=liquido, equity_final=equity_final, equity_min=equity_min, quantidades=qtds)


def main() -> None:
    combos = [(rp, cap) for rp in RISCO_PCT_VALUES for cap in NIVEIS_CAPITAL]
    n_workers = min(12, os.cpu_count() or 4)
    print(f"[wdof1_calib_risco] {len(combos)} combinacoes, {n_workers} processos\n", flush=True)
    t0 = time.perf_counter()
    linhas = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, c): c for c in combos}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            linhas.append(r)
            feitos += 1
            alerta = "QUASE ZEROU" if r["equity_min"] < 0.1 * r["capital"] else "ok"
            print(f"  [{feitos:2d}/{len(combos)} {r['dt']:5.1f}s] risco={r['risco_pct']*100:4.1f}% "
                  f"R${br(r['capital'],0):>9s} -> trades={r['trades']:5d} "
                  f"liquido=R${br(r['liquido']):>13s} final=R${br(r['equity_final']):>12s} "
                  f"min=R${br(r['equity_min']):>11s} qtds={r['quantidades']} [{alerta}]", flush=True)
    print(f"\ntotal: {time.perf_counter()-t0:.1f}s\n")

    print("=== resumo: liquido por risco_pct x capital ===")
    print(f"{'risco_pct':>10}" + "".join(f"{('R$'+br(c,0)):>15}" for c in NIVEIS_CAPITAL))
    for rp in RISCO_PCT_VALUES:
        linha = f"{rp*100:>9.1f}%"
        for cap in NIVEIS_CAPITAL:
            l = next(x for x in linhas if x["risco_pct"] == rp and x["capital"] == cap)
            marca = "!" if l["equity_min"] < 0.1 * cap else " "
            linha += f"{('R$'+br(l['liquido'],0)+marca):>15}"
        print(linha)


if __name__ == "__main__":
    main()
