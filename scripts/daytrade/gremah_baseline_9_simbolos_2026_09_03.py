"""Tabela BASELINE limpa da `Gremah` (M1) nos 9 simbolos calibrados hoje --
`defesa_ativa`/`corte_persistencia_ativo` DESLIGADOS (default, nao tocados),
so' a config de PRODUCAO atual de cada simbolo (`_CALIBRATION_BY_SYMBOL`/
`_GEOMETRIA_TICKS_BY_SYMBOL`/`_CAPACIDADE_BY_SYMBOL`, tudo resolvido pelo
proprio `Gremah.__init__` a partir so' de `symbol=`).

Existe para comparar contra a MESMA tabela que outro agente produz para o
motor `GremahTick` na mesma rodada (2026-09-03) -- nao compara os dois
motores aqui, so' entrega o numero limpo deste.

## Escopo: 9 dos 10 simbolos calibrados

`_CALIBRATION_BY_SYMBOL` tem 10 entradas; CLSC4 fica de FORA por pedido
explicito desta rodada (so' 14 trades no OOS historico, `capital_minimo_
brl` de R$30.390 -- fora do capital real do dono, ver a docstring do modulo
`gremah.py`).

## Janela: historico completo, sem split IS/OOS

Nao mexe em regra de saida nem recalibra nada -- so' REPRODUZ o numero ja'
validado de cada simbolo (a mesma config que ja roda em producao hoje), por
isso nao precisa da disciplina de `LockedBars`. Cada simbolo roda a partir
do proprio REGIME_START (a data em que o preco de HOJE comecou a valer --
`_geometria_comum.py::REGIME_START`, duplicado aqui pelo MESMO motivo de
`gremah_defesa_corte_sweep_2026_09_03.py`: nao abrir conexao MT5) ate' o fim
do parquet local salvo.

## Capital (CLAUDE.md, "capital inicial nunca arbitrario")

`capital_minimo_brl(preco_de_referencia)` -- preco de referencia = OPEN da
PRIMEIRA barra da janela de cada simbolo (o preco no inicio do REGIME_START
dele, nao um numero herdado de outro papel nem um valor redondo).

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed`, `redirect_stdout` por
tarefa, `flush=True`, streaming.

Uso: `python -u scripts/daytrade/gremah_baseline_9_simbolos_2026_09_03.py`
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

#: Os 9 simbolos desta rodada (CLSC4 fica de fora -- ver a docstring do
#: modulo), na MESMA ordem que o dono listou na missao.
SYMBOLS = ("PMAM3", "KLBN4", "CSAN3", "DASA3", "PCAR3", "KLBN3", "GRND3", "LPSB3", "BMGB4")

#: MESMOS valores de `scripts/daytrade/_geometria_comum.py::REGIME_START`
#: (duplicados, nao importados -- aquele modulo abre conexao MT5 via
#: `symbol_economics`, que este script nao precisa e nao deve chamar).
REGIME_START = {
    "PMAM3": "2025-12-16", "KLBN4": "2025-09-02", "CSAN3": "2025-09-22",
    "DASA3": "2025-09-11", "PCAR3": "2025-08-21", "KLBN3": "2025-03-10",
    "GRND3": "2025-09-05", "LPSB3": "2022-12-20", "BMGB4": "2025-06-04",
}

MIN_BARRAS_M1_ACAO = 20
TRADE_TICK_VALUE = 0.01
TRADE_TICK_SIZE = 0.01


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _roda_um_simbolo(symbol: str) -> tuple[str, dict]:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.lab.gremah import Gremah

    df = load_m1(symbol).sort_index()
    if df.empty:
        raise SystemExit(f"[{symbol}] sem dado M1 local -- nada a rodar")
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_M1_ACAO}
    df = df[[d in completos for d in df.index.date]]
    regime_start = pd.Timestamp(REGIME_START[symbol], tz=df.index.tz)
    bars = df.loc[df.index >= regime_start]
    if bars.empty:
        raise SystemExit(f"[{symbol}] janela vazia apos filtrar regime_start={REGIME_START[symbol]}")

    preco_ref = float(bars.iloc[0]["open"])
    capital = capital_minimo_brl(preco_ref)

    profile = profile_for(symbol)
    strat = Gremah(symbol=symbol)  # config de PRODUCAO -- so' o simbolo, nada mais
    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    item = linha_de_resultado(symbol, resultado, capital, capital_nocional=False)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item), flush=True)

    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        retorno_pct=item.retorno_pct, maxdd_pct=item.maxdd_pct, capital_final=item.capital_final,
        extras=item.extras, aviso=item.aviso,
        symbol=symbol, capital=capital, preco_ref=preco_ref,
        regime_start=REGIME_START[symbol],
    )
    return buf.getvalue(), campos


def main() -> None:
    from backtest.intraday.report import LinhaResultado, cabecalho, tabela

    t0 = time.perf_counter()
    n_workers = max(1, min(len(SYMBOLS), 6, os.cpu_count() or 4))
    print(f"[gremah_baseline_9_simbolos] {len(SYMBOLS)} simbolos, {n_workers} processos "
          "(mecanismos novos DESLIGADOS -- so' a config de producao atual)", flush=True)
    print(cabecalho(), flush=True)

    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_um_simbolo, s): s for s in SYMBOLS}
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados[futures[future]] = campos
            print(f"[gremah_baseline_9_simbolos] {concluidos}/{len(SYMBOLS)} concluido(s) "
                  f"({futures[future]})", flush=True)

    print(f"\n[gremah_baseline_9_simbolos] motor: {time.perf_counter() - t0:.1f}s\n")

    print("=" * 90)
    print("TABELA BASELINE -- Gremah (M1), mecanismos defesa_recuo/corte_persistencia "
          "DESLIGADOS, config de producao atual por simbolo. Historico completo desde o "
          "REGIME_START de cada um (sem split IS/OOS -- nao mexe em regra de saida).")
    print("=" * 90)
    linhas = [
        LinhaResultado(
            variante=resultados[s]["variante"], liquido_brl=resultados[s]["liquido_brl"],
            maxdd_brl=resultados[s]["maxdd_brl"], win_rate_pct=resultados[s]["win_rate_pct"],
            trades=resultados[s]["trades"], pregoes=resultados[s]["pregoes"],
            retorno_pct=resultados[s]["retorno_pct"], maxdd_pct=resultados[s]["maxdd_pct"],
            capital_final=resultados[s]["capital_final"], extras=resultados[s]["extras"],
            aviso=resultados[s]["aviso"],
        )
        for s in SYMBOLS
    ]
    print(tabela(linhas))

    print("\ncapital inicial usado por simbolo (capital_minimo_brl no preco de referencia "
          "do inicio do regime -- ver REGIME_START):")
    for s in SYMBOLS:
        c = resultados[s]
        print(f"  {s:<6} regime_start={c['regime_start']}  preco_ref=R${br(c['preco_ref'], 4)}  "
              f"capital=R${br(c['capital'])}")

    print(f"\n[gremah_baseline_9_simbolos] total: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
