"""Passo 3 da calibracao da `gremah_tick` (ver o aviso no topo de
`strategy/daytrade/lab/gremah_tick.py`): varredura fina em TICK, contra a
calibracao ATUAL de producao (`GremahTick(symbol=)` sem parametro nenhum --
hoje isso e' o par percentual herdado do M1 para 9 dos 10 simbolos, e o
proprio par confirmado em tick para a PMAM3).

Varre DOIS espacos, mesmo espirito de `sweep_gremah_vol.py` (a versao M1
deste script): a grade PERCENTUAL de sempre (`profit_pct` x
`stop_multiplier`) e a grade por VOLATILIDADE (Variante A: so' `k`, stop
continua no `stop_multiplier` do simbolo; Variante B: `k` e `s` globais) --
"recalibrar tudo" (pedido do dono 2026-08-23) significa nao presumir que o
percentual herdado do M1 e' o melhor ponto de partida em tick.

CAIXA REAL por simbolo (`capital_minimo_brl` no preco do inicio da janela),
nao R$100 fixo -- mesmo motivo documentado em `sweep_gremah_vol.py`: R$100
mascara o piso de 1 lote em papeis caros e pode fazer um par parecer melhor
ou pior do que e' de verdade.

So' IN-SAMPLE aqui -- a confirmacao OOS e' UMA passada so', depois, com o
par escolhido. CRITERIO DE ADOCAO (mesmo de sempre): so' vale mudar a
calibracao se o par novo empatar ou melhorar no OOS -- este script so'
informa o IS, nao decide.

Uso:
    python scripts/daytrade/sweep_gremah_tick.py
    python scripts/daytrade/sweep_gremah_tick.py --symbol PMAM3
    python scripts/daytrade/sweep_gremah_tick.py --symbol PMAM3 --top 15
    python scripts/daytrade/sweep_gremah_tick.py --symbol CSAN3 --symbol PCAR3
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah_tick import _CALIBRATION_BY_SYMBOL_TICK, GremahTick  # noqa: E402

# Mesmo regime de preco declarado para o M1 do simbolo (propriedade do
# ATIVO, nao da fonte de dado -- ver `sweep_gremah_vol.py`).
REGIME_START = {
    "PMAM3": "2025-12-16", "KLBN4": "2025-09-02", "CSAN3": "2025-09-22",
    "DASA3": "2025-09-11", "PCAR3": "2025-08-21", "CLSC4": "2025-05-12",
    "KLBN3": "2025-03-10", "GRND3": "2025-09-05", "LPSB3": "2022-12-20",
    "BMGB4": "2025-06-04",
}

PROFIT_PCT_GRID = [0.0015, 0.0020, 0.0025, 0.0032, 0.0040, 0.0050, 0.0060]
STOP_MULTIPLIER_GRID = [5.0, 8.0, 10.0, 15.0, 20.0, 30.0]
K_GRID = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
S_GRID = [5.0, 8.0, 10.0, 15.0, 20.0, 30.0]  # so' Variante B
VOL_JANELA_DIAS_PADRAO = 10
MIN_TRADES_CONFIAVEL = 30


def _rodar(profile, run_bars: pd.DataFrame, econ, strat: GremahTick, preco_atual: float) -> dict:
    capital_inicial = capital_minimo_brl(preco_atual)
    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value, trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_atual,
    )
    result = run_intraday_backtest(run_bars, strat, config)
    m = result.metrics
    final = capital_inicial + sum(t.pnl_brl for t in result.trades)
    n = len(result.trades)
    return {
        "retorno_%": m["cagr"] * 100, "maxdd_%": m["max_drawdown"] * 100,
        "calmar": m["calmar"], "win_rate_%": m.get("win_rate", 0.0) * 100,
        "trades": n, "capital_final": final, "capital_inicial": capital_inicial,
        "confiavel": n >= MIN_TRADES_CONFIAVEL, "wiped_out": result.wiped_out_at is not None,
        "dias_pulados": len(result.sessoes_puladas_por_capital),
    }


def _linha(label: str, r: dict) -> str:
    confiavel = "sim" if r["confiavel"] else f"NAO (<{MIN_TRADES_CONFIAVEL})"
    aviso = " ZERADO" if r["wiped_out"] else (f" pulou{r['dias_pulados']}d" if r["dias_pulados"] else "")
    return (f"{label:<24}{r['retorno_%']:>9.1f}%{r['maxdd_%']:>9.1f}%{r['calmar']:>9.2f}"
            f"{r['win_rate_%']:>10.1f}%{r['trades']:>8d}  R${r['capital_final']:>10.2f}"
            f"  {confiavel:>13}{aviso}")


def _sweep_symbol(symbol: str, top: int, tail_ticks: int | None = None) -> None:
    profile = PROFILES[symbol]
    ticks = load_ticks(symbol)
    if ticks.empty:
        print(f"[sweep_tick] sem dado local para {symbol!r} — rode backfill_ticks.py primeiro")
        return
    regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
    ticks = ticks.loc[ticks.index >= regime_start]
    bars = ticks_to_degenerate_bars(ticks)

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    run_bars = LockedBars(bars, split).in_sample()
    if tail_ticks is not None and len(run_bars) > tail_ticks:
        # Corte de tempo, nao de escopo: symbolos com volume de tick alto
        # demais pra rodar a grade inteira em tempo razoavel (CSAN3,
        # 2026-08-23) usam so' os ultimos N negocios ANTES do corte OOS --
        # ainda dentro do IS declarado, sem tocar no OOS.
        run_bars = run_bars.tail(tail_ticks)
        print(f"[sweep_tick] {symbol}: cortado para os ultimos {tail_ticks} negocios do IS "
              f"(tinha {len(LockedBars(bars, split).in_sample())})", flush=True)
    if run_bars.empty:
        print(f"[sweep_tick] {symbol}: janela IS vazia em tick (regime comeca depois do corte?)")
        return

    econ = symbol_economics(symbol)
    if econ is None:
        print("[sweep_tick] nao consegui ler symbol_economics — terminal MT5 aberto?")
        return

    preco_atual = float(run_bars.iloc[0]["close"])
    calib = _CALIBRATION_BY_SYMBOL_TICK[symbol]
    print(f"\n=== {symbol} — IN-SAMPLE (tick): {len(run_bars)} negocios, "
          f"{run_bars.index.min()} -> {run_bars.index.max()}, "
          f"caixa minimo R${capital_minimo_brl(preco_atual):.2f} ===")

    linhas: list[tuple[str, dict]] = []
    baseline = GremahTick(symbol=symbol)
    rotulo_atual = (
        f"atual (k={baseline.alvo_vol_mult:.2f}/s={baseline.stop_vol_mult:.0f})"
        if baseline.alvo_por_volatilidade
        else f"atual ({calib.profit_pct*100:.2f}%/{calib.stop_multiplier:.0f}x)"
    )
    linhas.append((rotulo_atual, _rodar(profile, run_bars, econ, baseline, preco_atual)))

    for profit_pct in PROFIT_PCT_GRID:
        for stop_multiplier in STOP_MULTIPLIER_GRID:
            strat_p = GremahTick(symbol=symbol, profit_pct=profit_pct, stop_multiplier=stop_multiplier)
            label = f"% {profit_pct*100:.2f}%/{stop_multiplier:.0f}x"
            linhas.append((label, _rodar(profile, run_bars, econ, strat_p, preco_atual)))

    for k in K_GRID:
        strat_a = GremahTick(symbol=symbol, alvo_por_volatilidade=True,
                              alvo_vol_mult=k, vol_janela_dias=VOL_JANELA_DIAS_PADRAO)
        linhas.append((f"A k={k:.2f}", _rodar(profile, run_bars, econ, strat_a, preco_atual)))

    for k in K_GRID:
        for s in S_GRID:
            strat_b = GremahTick(symbol=symbol, alvo_por_volatilidade=True,
                                  alvo_vol_mult=k, vol_janela_dias=VOL_JANELA_DIAS_PADRAO,
                                  stop_vol_mult=s)
            linhas.append((f"B k={k:.2f} s={s:.0f}", _rodar(profile, run_bars, econ, strat_b, preco_atual)))

    atual = linhas[0]
    resto = sorted(linhas[1:], key=lambda item: item[1]["capital_final"], reverse=True)

    print(f"{'variante':<24}{'retorno':>10}{'maxdd':>10}{'calmar':>9}"
          f"{'win rate':>11}{'trades':>8}{'capital final':>15}  {'confiavel':>13}")
    print(_linha(*atual))
    for label, r in resto[:top]:
        print(_linha(label, r))
    if len(resto) > top:
        print(f"  ... {len(resto) - top} combinacao(oes) a mais, fora do top-{top}")


def _sweep_symbol_capturado(symbol: str, top: int, tail_ticks: int | None) -> str:
    """Mesmo motivo de `sweep_gremah_vol.py::_sweep_symbol_capturado` --
    paraleliza por SIMBOLO (`ProcessPoolExecutor` em `main`) e devolve texto
    em vez de imprimir direto, pra saida de dois simbolos nao se intercalar."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _sweep_symbol(symbol, top, tail_ticks)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", choices=sorted(_CALIBRATION_BY_SYMBOL_TICK),
                        default=None, help="repetivel; default: todos os 10 simbolos calibrados")
    parser.add_argument("--top", type=int, default=10,
                        help="quantas combinacoes mostrar por simbolo, alem da linha 'atual' (default 10)")
    parser.add_argument("--jobs", type=int, default=None,
                        help="processos em paralelo (default: min(simbolos, nucleos disponiveis))")
    parser.add_argument("--tail-ticks", type=int, default=None,
                        help="usa so' os ultimos N negocios do IS (antes do corte OOS) -- "
                             "para simbolos com volume de tick alto demais pra grade inteira "
                             "em tempo razoavel (ex.: CSAN3)")
    args = parser.parse_args()
    symbols = args.symbol if args.symbol else sorted(_CALIBRATION_BY_SYMBOL_TICK)

    if len(symbols) == 1:
        _sweep_symbol(symbols[0], args.top, args.tail_ticks)
        return

    max_workers = args.jobs or min(len(symbols), os.cpu_count() or 4)
    print(f"[sweep_tick] {len(symbols)} simbolo(s) em ate {max_workers} processo(s) paralelo(s)...",
          flush=True)
    # `as_completed` (nao `pool.map`) -- `map` so' entrega resultado na ORDEM
    # de submissao, entao um simbolo rapido (poucos negocios) fica preso
    # atras de um lento (CSAN3, milhoes de negocios) mesmo ja tendo
    # terminado ha muito tempo. `flush=True` em cada print, porque stdout
    # redirecionado a arquivo e' bufferizado em bloco (nao por linha) -- sem
    # isso nada aparece no arquivo ate' o processo inteiro terminar, e' como
    # se nao houvesse progresso nenhum ate' o fim (aconteceu 2026-08-23,
    # rodada de 10 simbolos em tick cancelada depois de mais de 1h sem
    # nenhuma saida visivel, mesmo com 2 simbolos ja prontos).
    concluidos = 0
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_sweep_symbol_capturado, s, args.top, args.tail_ticks): s
                   for s in symbols}
        for future in as_completed(futures):
            concluidos += 1
            symbol = futures[future]
            print(future.result(), end="", flush=True)
            print(f"[sweep_tick] {concluidos}/{len(symbols)} concluido(s) ({symbol})", flush=True)


if __name__ == "__main__":
    main()
