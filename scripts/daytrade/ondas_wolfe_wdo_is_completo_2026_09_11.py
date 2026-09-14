"""NOTA (2026-09-11): mesmo motivo do `ondas_wolfe_wdo_teste_pequeno_2026_
09_11.py` -- modo TICK mede ~1.800 ticks/s nesta maquina (carga concorrente
de outras sessoes/robos reais), e o IS completo (~14,5M ticks) e' proibitivo
em tempo de parede disponivel. O veredito usado foi o de
`ondas_wolfe_wdo_m1_is_completo_2026_09_11.py` (mesmo desenho de execucao,
barra M1, fidelidade aplicada de forma declaradamente otimista). Este
arquivo fica como a versao FIEL para confirmacao tick-a-tick futura.

Ondas de Wolfe no WDO@, desenho de execucao FECHADO, IS COMPLETO (o mesmo
IS congelado usado para o `wdo_orb`/WDO F1 -- 2026-02-27..2026-06-12, ~72
pregoes) -- so' roda se o teste pequeno
(`ondas_wolfe_wdo_teste_pequeno_2026_09_11.py`) tiver sobrevivido.

NAO toca o OOS (2026-06-15 em diante) -- ver a convencao do projeto ("OOS so'
ao criar/melhorar"; aqui e' so' validacao de hipotese, ainda sem candidato
promovido).

Reporta, por variante de `zigzag_reversal_ticks`: liquido, MaxDD, win% com
IC95% de Wilson CONTRA O BREAKEVEN EMPIRICO (perda_media/(ganho_media+
perda_media), nao o nominal -- ver item 6.23 de LICOES_DE_PRODUCAO.md),
trades, stops, pregoes sem trade, capital minimo tocado.

Uso: python -u scripts/daytrade/ondas_wolfe_wdo_is_completo_2026_09_11.py
"""
from __future__ import annotations

import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0

#: MESMO split congelado do WDO F1 / wdo_orb -- nao mexido aqui.
IS_INICIO = pd.Timestamp("2026-02-27", tz="UTC")
IS_FIM = pd.Timestamp("2026-06-13", tz="UTC")  # exclusivo -> ultimo dia 06-12

#: grade decidida a partir do teste pequeno -- ver o script correspondente.
GRADE_ZIGZAG_TICKS = (16.0, 24.0, 32.0, 40.0)


def _wilson_ic95(k: int, n: int) -> tuple[float, float]:
    """IC95% de Wilson para uma proporcao — sem depender de scipy/statsmodels
    (`z=1.959963985` para 95%)."""
    if n == 0:
        return (float("nan"), float("nan"))
    z = 1.959963985
    p = k / n
    denom = 1 + z * z / n
    centro = p + z * z / (2 * n)
    margem = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centro - margem) / denom, (centro + margem) / denom)


def _roda_uma(zigzag_ticks: float):
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado
    from core.models import IntradayExitReason
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars
    from ondas_wolfe_wdo_lab import OndasWolfeWdo

    df = pd.read_parquet(CACHE)
    df = df[(df.index >= IS_INICIO) & (df.index < IS_FIM)]
    bars = ticks_to_degenerate_bars(df)

    strat = OndasWolfeWdo(zigzag_reversal_ticks=zigzag_ticks)
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [-t.pnl_brl for t in trades if t.pnl_brl <= 0]
    n = len(trades)
    k = len(ganhos)
    win_pct = 100.0 * k / n if n else float("nan")
    ganho_medio = sum(ganhos) / len(ganhos) if ganhos else float("nan")
    perda_media = sum(perdas) / len(perdas) if perdas else float("nan")
    if ganhos and perdas:
        be_empirico = 100.0 * perda_media / (ganho_medio + perda_media)
    else:
        be_empirico = float("nan")
    ic_lo, ic_hi = _wilson_ic95(k, n) if n else (float("nan"), float("nan"))

    n_stops = sum(1 for t in trades if t.exit_reason == IntradayExitReason.STOP)
    n_alvo = sum(1 for t in trades if t.exit_reason == IntradayExitReason.TARGET)
    n_flat = sum(1 for t in trades if t.exit_reason == IntradayExitReason.FORCED_FLATTEN)

    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    dias_positivos = set()
    if trades:
        por_dia = {}
        for t in trades:
            d = pd.Timestamp(t.entry_ts).date()
            por_dia[d] = por_dia.get(d, 0.0) + t.pnl_brl
        dias_positivos = {d for d, v in por_dia.items() if v > 0}

    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "n_stops": str(n_stops),
        "n_alvo": str(n_alvo),
        "n_flat": str(n_flat),
        "be_emp%": f"{be_empirico:.2f}".replace(".", ",") if not math.isnan(be_empirico) else "n/d",
        "win_ic95": (f"[{ic_lo*100:.1f};{ic_hi*100:.1f}]".replace(".", ",")
                     if n else "n/d"),
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "dias_pos_%": (f"{100.0*len(dias_positivos)/len(dias_com_trade):.1f}".replace(".", ",")
                       if dias_com_trade else "n/d"),
        "caixa_min": f"{caixa_min:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."),
    }
    rotulo = f"zigzag={zigzag_ticks:.0f}t"
    item = linha_de_resultado(rotulo, resultado, CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{dt:5.1f}s] {linha(item, tuple(extras.keys()))}", flush=True)
    return rotulo, item, buf.getvalue(), extras


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(f"cache ausente: {CACHE}")
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt

    print(f"[IS completo] janela {IS_INICIO.date()}..2026-06-12 (~72 pregoes), "
          f"capital real R${CAPITAL_REAL_BRL:.2f}, {len(GRADE_ZIGZAG_TICKS)} variantes\n",
          flush=True)

    resultados: dict = {}
    extras_por_variante: dict = {}
    n_workers = max(1, min(len(GRADE_ZIGZAG_TICKS), os.cpu_count() or 4))
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, z): z for z in GRADE_ZIGZAG_TICKS}
        for fut in as_completed(futures):
            rotulo, item, texto_pronto, extras = fut.result()
            resultados[rotulo] = item
            extras_por_variante[rotulo] = extras
            print(texto_pronto, end="", flush=True)
    dt_total = time.perf_counter() - t0
    print(f"\n[IS completo] motor: {dt_total:.1f}s em {n_workers} processos\n")

    extras_keys = tuple(next(iter(extras_por_variante.values())).keys()) if extras_por_variante else ()
    print("=== tabela IS completo ===")
    print(cabecalho(extras_keys))
    for z in GRADE_ZIGZAG_TICKS:
        rotulo = f"zigzag={z:.0f}t"
        print(linha_fmt(resultados[rotulo], extras_keys))


if __name__ == "__main__":
    main()
