"""NOTA (2026-09-11, apos rodar): neste modo TICK o motor mediu ~1.800
ticks/s nesta maquina (varios `run_live.py` reais + outras sessoes de
pesquisa concorrentes disputando CPU -- ver `repo_no_git_concurrent_
session` na memoria do projeto), o que tornou ESTE script (3 semanas x 4
variantes, ~16M ticks) impraticavel dentro do tempo disponivel -- foi
interrompido sem terminar. O veredito real desta hipotese saiu de
`ondas_wolfe_wdo_m1_is_completo_2026_09_11.py` (mesmo desenho de execucao,
medido em barra M1 em vez de tick -- ~500x menos eventos, ~60s para a grade
inteira), com a fidelidade calibrada de `fidelidade.py` aplicada de forma
DECLARADAMENTE otimista (ver a docstring daquele arquivo). Este script fica
como a implementacao FIEL (tick a tick) para quem tiver uma janela de
maquina maior -- nao foi excluido, so' nao foi o que decidiu.

TESTE PEQUENO PRIMEIRO (convencao do projeto): 3 semanas de WDO@ real
(2026-02-27..2026-03-20, o INICIO do IS congelado do robo WDO F1/wdo_orb --
nao toca OOS), antes de gastar tempo de maquina na janela inteira.

Roda uma GRADE pequena de `zigzag_reversal_ticks` (o unico eixo que decide
quantos pivos por pregao existem) via `ProcessPoolExecutor`, desenho de
execucao FECHADO (`config_for`, fila calibrada de `fidelidade.py`, capital
real R$375), e imprime, por variante: pivos/dia, ondas detectadas,
trades, win%, breakeven empirico, liquido, MaxDD, pregoes sem trade.

Uso: python -u scripts/daytrade/ondas_wolfe_wdo_teste_pequeno_2026_09_11.py
"""
from __future__ import annotations

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

INICIO = pd.Timestamp("2026-02-27", tz="UTC")
FIM = pd.Timestamp("2026-03-20", tz="UTC")  # ~3 semanas, dentro do IS congelado

GRADE_ZIGZAG_TICKS = (16.0, 24.0, 32.0, 40.0)

EXTRAS = ("ondas_dia", "pivos_dia", "pregoes_sem_trade", "atraso_p50_min", "caixa_min")


def _roda_uma(zigzag_ticks: float):
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars
    from ondas_wolfe_wdo_lab import OndasWolfeWdo

    df = pd.read_parquet(CACHE)
    df = df[(df.index >= INICIO) & (df.index < FIM)]
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
    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}

    # atraso realizado da ordem de ENTRADA, em minutos (CLAUDE.md: nunca
    # traduza ttl em barras pra tempo sem calibrar -- aqui calibramos com o
    # proprio resultado: fill_ts - o instante em que a ordem foi armada nao
    # e' gravado no IntradayTrade, entao aproximamos pelo delta entre
    # entry_ts e o INICIO do minuto em que o trade fechou nao serve --
    # deixamos NaN e reportamos a contagem de trades como evidencia direta.
    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "ondas_dia": f"{strat.ondas_detectadas_no_dia if not dias_janela else '-'}",
        "pivos_dia": "-",
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "atraso_p50_min": "n/d",
        "caixa_min": f"{caixa_min:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."),
    }
    rotulo = f"zigzag={zigzag_ticks:.0f}t"
    item = linha_de_resultado(rotulo, resultado, CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{dt:5.1f}s] {linha(item, EXTRAS)}", flush=True)
    n_dias = len(dias_janela)
    return rotulo, item, buf.getvalue(), n_dias, len(trades)


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(f"cache ausente: {CACHE}")
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt

    print(f"[teste_pequeno] janela {INICIO.date()}..{FIM.date()}, "
          f"capital real R${CAPITAL_REAL_BRL:.2f}, {len(GRADE_ZIGZAG_TICKS)} variantes\n",
          flush=True)

    resultados: dict = {}
    n_workers = max(1, min(len(GRADE_ZIGZAG_TICKS), os.cpu_count() or 4))
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, z): z for z in GRADE_ZIGZAG_TICKS}
        for fut in as_completed(futures):
            rotulo, item, texto_pronto, n_dias, n_trades = fut.result()
            resultados[rotulo] = item
            print(f"{texto_pronto}", end="", flush=True)
            print(f"    -> {n_dias} pregoes na janela, {n_trades} trades\n", flush=True)
    dt_total = time.perf_counter() - t0
    print(f"[teste_pequeno] motor: {dt_total:.1f}s em {n_workers} processos\n")

    print("=== tabela ===")
    print(cabecalho(EXTRAS))
    for z in GRADE_ZIGZAG_TICKS:
        rotulo = f"zigzag={z:.0f}t"
        print(linha_fmt(resultados[rotulo], EXTRAS))


if __name__ == "__main__":
    main()
