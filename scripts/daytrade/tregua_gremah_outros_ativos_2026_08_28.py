"""Robustez entre ATIVOS da tregua (2026-08-28, pedido do dono): os 3 melhores
`tregua_bars` do sweep 1-60min em PMAM3 (17, 51, 52 -- todos empatados dentro
do platô de ruído já documentado, ver `sweep_tregua_gremah_2026_08_28.py`)
testados em 3 outros ativos calibrados da `gremah` (KLBN4, CSAN3, DASA3,
próximos na ordem de `Gremah.calibrated_setups()` -- não escolhidos a dedo).

MESMO periodo em todos os 4 ativos (regra `feedback_honest_period_comparison`:
mesmo período pra todos, a partir da base mais curta) -- KLBN4/CSAN3/DASA3
só têm dado local até 2026-08-21 (PMAM3 vai até 2026-08-24), então a janela
usada aqui é [2026-05-28, 2026-08-21], TRUNCANDO a PMAM3 também, para os
4 ativos serem exatamente comparáveis (não é a mesma janela do sweep
anterior, que usava a PMAM3 até 08-24 sozinha).

MESMA lógica de capital inicial: capital mínimo real (2 lotes de 100 ações
no preço do INÍCIO da janela) + R$100, por ativo.

Uso: `python -u scripts/daytrade/tregua_gremah_outros_ativos_2026_08_28.py`
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import Exit, capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402

SYMBOLS = ["PMAM3", "KLBN4", "CSAN3", "DASA3"]
TOP3_TREGUAS = [17, 51, 52]
JANELA_INICIO = pd.Timestamp("2026-05-28", tz="UTC")
JANELA_FIM = pd.Timestamp("2026-08-21 23:59", tz="UTC")  # dado comum mais curto (KLBN4/CSAN3/DASA3)
ECONOMICS_CACHE = ROOT / "data" / "_economics_cache.json"


class GremahReavaliaAposTregua(Gremah):
    """Duplicado de proposito (picklable top-level p/ ProcessPoolExecutor) --
    ver `gremah_reavalia_cada_barra_2026_08_28.py` pro original/motivo."""

    name = "gremah_reavalia_apos_tregua"

    def __init__(self, *args, tregua_bars: int = 5, **kwargs):
        super().__init__(*args, **kwargs)
        self.tregua_bars = tregua_bars

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if acoes or not positions:
            return acoes
        pos = positions[0]
        if pos.bars_held == 0 or pos.bars_held % self.tregua_bars != 0:
            return []
        ganho_nao_realizado = (
            (bar.close - pos.entry_price) if pos.side == "long"
            else (pos.entry_price - bar.close)
        )
        if ganho_nao_realizado > 0.0:
            return []
        oposto = "short" if pos.side == "long" else "long"
        if self._fills_of(oposto) >= self.max_trades_per_side:
            return []
        return [Exit(reason=f"reavaliacao_apos_tregua_{self.tregua_bars}b_perdendo")]


def _preparar(symbol: str):
    bars_full = load_m1(symbol)
    bars = bars_full.loc[(bars_full.index >= JANELA_INICIO) & (bars_full.index <= JANELA_FIM)]
    preco_inicio = float(bars.iloc[0]["close"])
    capital_inicial = capital_minimo_brl(preco_inicio) + 100.0
    economics = json.loads(ECONOMICS_CACHE.read_text(encoding="utf-8"))[symbol]
    cfg = config_for(
        PROFILES[symbol],
        trade_tick_value=economics["trade_tick_value"],
        trade_tick_size=economics["trade_tick_size"],
        target_fills_as_maker=Gremah.target_fills_as_maker,
        initial_capital=capital_inicial,
    )
    return bars, cfg, capital_inicial, preco_inicio


def _roda_uma(symbol: str, tregua_bars: int | None) -> tuple[str, int | None, str]:
    bars, cfg, capital_inicial, _ = _preparar(symbol)
    if tregua_bars is None:
        estrategia = Gremah(symbol=symbol)
        rotulo = f"{symbol} HOJE (sem tregua)"
    else:
        estrategia = GremahReavaliaAposTregua(symbol=symbol, tregua_bars=tregua_bars)
        rotulo = f"{symbol} tregua {tregua_bars}min"
    resultado = run_intraday_backtest(bars, estrategia, cfg)
    item = linha_de_resultado(rotulo, resultado, capital_inicial)
    return symbol, tregua_bars, linha(item)


def main() -> None:
    print(f"Janela comum: {JANELA_INICIO.date()} .. {JANELA_FIM.date()}")
    for symbol in SYMBOLS:
        _, _, capital_inicial, preco_inicio = _preparar(symbol)
        print(f"  {symbol}: preco inicio R$ {preco_inicio:.2f}  capital inicial R$ {capital_inicial:.2f}")
    print()
    print(cabecalho())

    tarefas = [(s, None) for s in SYMBOLS] + [(s, t) for s in SYMBOLS for t in TOP3_TREGUAS]
    resultados: dict[tuple[str, int | None], str] = {}
    with ProcessPoolExecutor() as pool:
        futures = {pool.submit(_roda_uma, s, t): (s, t) for s, t in tarefas}
        concluidos = 0
        for future in as_completed(futures):
            symbol, tregua_bars, texto = future.result()
            resultados[(symbol, tregua_bars)] = texto
            concluidos += 1
            print(texto, flush=True)
            print(f"[tregua_outros_ativos] {concluidos}/{len(tarefas)} concluido(s) "
                  f"({symbol}, tregua={tregua_bars})", flush=True)

    print()
    print("--- resumo por ativo (baseline primeiro, depois os 3 treguas) ---")
    print(cabecalho())
    for symbol in SYMBOLS:
        print(resultados[(symbol, None)])
        for t in TOP3_TREGUAS:
            print(resultados[(symbol, t)])
        print("-" * 40)


if __name__ == "__main__":
    main()
