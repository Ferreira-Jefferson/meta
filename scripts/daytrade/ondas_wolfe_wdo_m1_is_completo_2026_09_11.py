"""Ondas de Wolfe no WDO@, desenho de execucao FECHADO, medido em BARRA M1
(nao tick) -- desvio DECLARADO da convencao do projeto (`wdo_orb`/WDO F1 sao
medidos em tick), adotado por uma razao CONCRETA de tempo de maquina: o motor
tick-a-tick processa ~1.800 ticks/s nesta maquina (medido, ver
`_wolfe_diag_1dia.py`), e o IS congelado (72 pregoes) tem ~12M ticks -- mais
de 1,5h so' de motor, por variante, numa maquina ja' ocupada por outros
processos (varios `run_live.py` reais rodando ao lado). Em M1 o mesmo IS tem
~41 mil barras -- ordens de magnitude mais rapido, o que permite terminar
esta VALIDACAO dentro do tempo disponivel.

## O CUSTO desta escolha, declarado (nao escondido)

`fidelidade.py` (329/494, Kaplan-Meier) foi calibrado TICK A TICK: "quanto
volume negociou no nosso nivel entre a ordem entrar no livro e preencher/
cancelar". Aplicar o MESMO numero contra o volume agregado de 1 minuto
inteiro (`limit_fill_capped_by_volume`, motor `machine.py`) e' OTIMISTA --
uma barra M1 contem o volume do minuto TODO, nao so' o que aconteceu ate' o
toque, entao a fila "e' vencida" mais facil do que na realidade tick a tick.

CONSEQUENCIA PRATICA: um resultado POSITIVO aqui NAO e' validacao final --
e' o teste pequeno (na verdade, o teste RAPIDO) que decide se vale a pena
gastar a hora e meia de motor tick-a-tick para confirmar. Um resultado
NEGATIVO ou INDEFINIDO aqui, ao contrario, e' informativo por si -- rodar em
tick so' pode fazer a fidelidade PIORAR (mais fila, menos fill), nunca
melhorar o veredito.

Split IS congelado do WDO F1/wdo_orb, intocado: IS 2026-02-27..2026-06-12
(~72 pregoes). OOS NAO e' tocado aqui.

Uso: python -u scripts/daytrade/ondas_wolfe_wdo_m1_is_completo_2026_09_11.py
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

IS_INICIO = pd.Timestamp("2026-02-27", tz="UTC")
IS_FIM = pd.Timestamp("2026-06-13", tz="UTC")  # exclusivo

GRADE_ZIGZAG_TICKS = (16.0, 20.0, 24.0, 32.0, 40.0)
#: prazo da ordem de ENTRADA em MINUTOS/barras (feed_kind="m1" -- aqui 1
#: barra = 1 minuto, ao contrario do modo tick).
ENTRADA_TTL_MINUTOS = 20


def _wilson_ic95(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    z = 1.959963985
    p = k / n
    denom = 1 + z * z / n
    centro = p + z * z / (2 * n)
    margem = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centro - margem) / denom, (centro + margem) / denom)


def _m1_bars(df_ticks: pd.DataFrame) -> pd.DataFrame:
    price = df_ticks["last"]
    vol = df_ticks["volume_real"].where(df_ticks["volume_real"] > 0, df_ticks["volume"])
    o = price.resample("1min").first()
    h = price.resample("1min").max()
    l = price.resample("1min").min()
    c = price.resample("1min").last()
    v = vol.resample("1min").sum()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v})
    return out.dropna(subset=["close"])


def _roda_uma(zigzag_ticks: float):
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado
    from core.models import IntradayExitReason
    from ondas_wolfe_wdo_lab import OndasWolfeWdo

    df = pd.read_parquet(CACHE)
    df = df[(df.index >= IS_INICIO) & (df.index < IS_FIM)]
    bars = _m1_bars(df)

    strat = OndasWolfeWdo(zigzag_reversal_ticks=zigzag_ticks, feed_kind="m1",
                          entrada_ttl_bars=ENTRADA_TTL_MINUTOS)
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
    be_empirico = (100.0 * perda_media / (ganho_medio + perda_media)
                  if (ganhos and perdas) else float("nan"))
    ic_lo, ic_hi = _wilson_ic95(k, n) if n else (float("nan"), float("nan"))

    n_stops = sum(1 for t in trades if t.exit_reason == IntradayExitReason.STOP)
    n_alvo = sum(1 for t in trades if t.exit_reason == IntradayExitReason.TARGET)
    n_flat = sum(1 for t in trades if t.exit_reason == IntradayExitReason.FORCED_FLATTEN)

    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    por_dia: dict = {}
    for t in trades:
        d = pd.Timestamp(t.entry_ts).date()
        por_dia[d] = por_dia.get(d, 0.0) + t.pnl_brl
    dias_positivos = {d for d, v in por_dia.items() if v > 0}

    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "win_ic95": (f"[{ic_lo*100:.1f};{ic_hi*100:.1f}]".replace(".", ",") if n else "n/d"),
        "be_emp%": (f"{be_empirico:.2f}".replace(".", ",") if not math.isnan(be_empirico) else "n/d"),
        "n_stops": str(n_stops),
        "n_alvo": str(n_alvo),
        "n_flat": str(n_flat),
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

    print(f"[wolfe M1] IS {IS_INICIO.date()}..2026-06-12, capital real "
          f"R${CAPITAL_REAL_BRL:.2f}, {len(GRADE_ZIGZAG_TICKS)} variantes, "
          f"AVISO: fidelidade calibrada em TICK aplicada a barra M1 (otimista -- ver docstring)\n",
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
    print(f"\n[wolfe M1] motor: {dt_total:.1f}s em {n_workers} processos\n", flush=True)

    extras_keys = tuple(next(iter(extras_por_variante.values())).keys()) if extras_por_variante else ()
    print("=== tabela IS completo (M1) ===")
    print(cabecalho(extras_keys))
    for z in GRADE_ZIGZAG_TICKS:
        rotulo = f"zigzag={z:.0f}t"
        print(linha_fmt(resultados[rotulo], extras_keys))


if __name__ == "__main__":
    main()
