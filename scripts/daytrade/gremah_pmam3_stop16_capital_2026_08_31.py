"""Pedido do dono (2026-08-31): "teste pmam com stop de 16 pra ver com quantos
comeca a lucrar" -- logo depois de eu mostrar a ficha da Gremah (PMAM3 usa
geometria em ticks confirmada no OOS 2026-08-26: alvo=1/espacamento=1/stop=4,
ver `_GEOMETRIA_TICKS_BY_SYMBOL` em `strategy/daytrade/lab/gremah.py`).

Este script troca SO' o stop, de 4 para 16 ticks -- alvo e espacamento
continuam em 1 tick, a geometria de producao -- e varre capital inicial de
R$30 (piso real de hoje, preco colapsado da PMAM3) ate' R$10.000, historico M1
salvo INTEIRO, passada UNICA continua (nunca reinicia caixa por pregao, mesmo
motivo de sempre: uma sequencia de perda so' atravessa dias assim).

Por que stop=16 e' uma pergunta diferente de "qual o stop ja confirmado": o
par (1,1,4) foi o vencedor da varredura independente de 48 celulas + 1
confirmacao OOS (ver a docstring de `_GEOMETRIA_TICKS_BY_SYMBOL`) -- este
script NAO repete aquela varredura, so' testa o ponto especifico que o dono
pediu (S16) contra capital, do jeito que ja foi feito para a WDO F1 em
`wdof1_sobrevivencia_capital_baixo_2026_08_29.py`.

Uso: `python -u scripts/daytrade/gremah_pmam3_stop16_capital_2026_08_31.py`
"""
from __future__ import annotations

import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SYMBOL = "PMAM3"
PROFIT_TICKS = 1
SPACING_TICKS = 1
STOP_TICKS_TESTE = 16
NIVEIS_CAPITAL = [30.0, 50.0, 100.0, 200.0, 375.0, 500.0, 750.0,
                  1_000.0, 1_500.0, 2_000.0, 3_000.0, 5_000.0, 10_000.0]
MIN_EVENTOS_POR_PREGAO_ACAO = 20  # PMAM3 tem giro bem mais baixo que WIN@/WDO@

OUT_CSV = ROOT / "scripts" / "daytrade" / "gremah_pmam3_stop16_capital_2026_08_31.csv"

_BARS_CACHE = None  # por processo -- o pool reusa processos entre tarefas


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
        completos = {d for d, n in contagem.items() if n >= MIN_EVENTOS_POR_PREGAO_ACAO}
        _BARS_CACHE = df[[d in completos for d in df.index.date]]
    return _BARS_CACHE


def _roda(capital: float) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.gremah import Gremah

    bars = _bars_do_processo()
    profile = profile_for(SYMBOL)
    strat = Gremah(
        symbol=SYMBOL,
        profit_ticks=PROFIT_TICKS, spacing_ticks=SPACING_TICKS, stop_ticks=STOP_TICKS_TESTE,
    )
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.01,
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
    dias_cobertos = (
        len(set(pd.DatetimeIndex(resultado.equity_curve.index).date))
        if not resultado.equity_curve.empty else 0
    )
    pulou = len(resultado.sessoes_puladas_por_capital)

    return dict(
        capital=capital, dt=dt,
        trades=len(resultado.trades), liquido=liquido, equity_final=equity_final,
        equity_min=equity_min, dias_cobertos=dias_cobertos, pulou=pulou,
        zerou=resultado.wiped_out_at is not None,
    )


def main() -> None:
    n_workers = min(len(NIVEIS_CAPITAL), os.cpu_count() or 4)
    print(f"[gremah_stop16] PMAM3, T{PROFIT_TICKS}/E{SPACING_TICKS}/S{STOP_TICKS_TESTE} "
          f"(producao usa S4 -- so' o stop muda aqui), {len(NIVEIS_CAPITAL)} niveis de capital, "
          f"{n_workers} processos\n", flush=True)

    t0 = time.perf_counter()
    linhas: list[dict] = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, cap): cap for cap in NIVEIS_CAPITAL}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            linhas.append(r)
            feitos += 1
            status = "ZEROU" if r["zerou"] else ("lucra" if r["liquido"] > 0 else "perde")
            print(f"  [{feitos:2d}/{len(NIVEIS_CAPITAL)} {r['dt']:5.1f}s] "
                  f"R${br(r['capital'], 0):>9s} -> trades={r['trades']:5d} "
                  f"liquido=R${br(r['liquido']):>12s} final=R${br(r['equity_final']):>12s} "
                  f"min=R${br(r['equity_min']):>12s} pregoes_pulados={r['pulou']:4d} "
                  f"dias_cobertos={r['dias_cobertos']:4d} [{status}]", flush=True)

    print(f"\ntotal: {time.perf_counter() - t0:.1f}s\n", flush=True)

    linhas.sort(key=lambda l: l["capital"])
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["capital", "trades", "liquido", "equity_final",
                                           "equity_min", "dias_cobertos", "pulou", "zerou"])
        w.writeheader()
        for l in linhas:
            w.writerow({k: l[k] for k in w.fieldnames})
    print(f"[gremah_stop16] CSV salvo em {OUT_CSV}\n")

    print(f"=== PMAM3, T{PROFIT_TICKS}/E{SPACING_TICKS}/S{STOP_TICKS_TESTE} -- capital x resultado, historico inteiro ===")
    for l in linhas:
        print(f"  R${br(l['capital'], 0):>9s}: trades={l['trades']:5d} liquido=R${br(l['liquido']):>12s} "
              f"final=R${br(l['equity_final']):>12s} min=R${br(l['equity_min']):>12s} "
              f"pregoes_pulados={l['pulou']:4d}")

    lucrativos = [l for l in linhas if l["liquido"] > 0 and not l["zerou"]]
    if lucrativos:
        piso = min(lucrativos, key=lambda l: l["capital"])
        print(f"\n*** menor capital testado que fecha positivo: R${br(piso['capital'], 0)} "
              f"(liquido=R${br(piso['liquido'])}, {piso['trades']} trades) ***")
    else:
        print("\n*** NENHUM nivel testado fecha positivo com stop_ticks=16. ***")


if __name__ == "__main__":
    main()
