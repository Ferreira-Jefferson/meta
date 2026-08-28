"""Varredura da TREGUA (2026-08-28, pedido do dono): `GremahReavaliaAposTregua`
(ver `gremah_reavalia_cada_barra_2026_08_28.py`) com `tregua_bars` de 1 a 30
minutos (M1, PMAM3) -- 0 min (reavalia toda barra) ja mediu -R$13,16; 5 min
mediu +R$297,51 (empate com a baseline +R$293,29). Esta varredura preenche o
espaco entre os dois pra ver ONDE a trégua para de atrapalhar.

Mesma janela (ultimos 3 meses corridos, sem trava IS/OOS -- ja liberado:
medir efeito de mecanismo sobre calibracao fixada), mesmo capital (minimo
real da PMAM3 no preco do inicio da janela + R$100).

Paralelo por `tregua_bars` (`ProcessPoolExecutor`, `submit`/`as_completed`,
nunca `pool.map`) -- cada rodada imprime a linha DELA assim que termina;
resumo ordenado (1..30) vem no fim, ver AGENTS.md/CLAUDE.md.

Uso: `python -u scripts/daytrade/sweep_tregua_gremah_2026_08_28.py`
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
from backtest.intraday.report import linha, linha_de_resultado  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import Exit, capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402

SYMBOL = "PMAM3"
JANELA_INICIO = pd.Timestamp("2026-05-28", tz="UTC")
ECONOMICS_CACHE = ROOT / "data" / "_economics_cache.json"
TREGUA_MIN, TREGUA_MAX = 30, 60


class GremahReavaliaAposTregua(Gremah):
    """Copia de `gremah_reavalia_cada_barra_2026_08_28.py` -- duplicado de
    proposito (nao importado): cada worker do `ProcessPoolExecutor` roda em
    processo separado, e a classe precisa existir top-level no MODULO que o
    worker importa para ser picklable."""

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


def _carregar_bars_e_config():
    bars_full = load_m1(SYMBOL)
    bars = bars_full.loc[bars_full.index >= JANELA_INICIO]
    preco_inicio = float(bars.iloc[0]["close"])
    capital_inicial = capital_minimo_brl(preco_inicio) + 100.0
    economics = json.loads(ECONOMICS_CACHE.read_text(encoding="utf-8"))[SYMBOL]
    cfg = config_for(
        PROFILES[SYMBOL],
        trade_tick_value=economics["trade_tick_value"],
        trade_tick_size=economics["trade_tick_size"],
        target_fills_as_maker=Gremah.target_fills_as_maker,
        initial_capital=capital_inicial,
    )
    return bars, cfg, capital_inicial


def _roda_tregua(tregua_bars: int) -> tuple[int, str]:
    bars, cfg, capital_inicial = _carregar_bars_e_config()
    estrategia = GremahReavaliaAposTregua(symbol=SYMBOL, tregua_bars=tregua_bars)
    resultado = run_intraday_backtest(bars, estrategia, cfg)
    item = linha_de_resultado(f"tregua {tregua_bars:02d}min", resultado, capital_inicial)
    return tregua_bars, linha(item)


def main() -> None:
    bars, cfg, capital_inicial = _carregar_bars_e_config()
    baseline = run_intraday_backtest(bars, Gremah(symbol=SYMBOL), cfg)
    linha_base = linha_de_resultado("HOJE (sem tregua)", baseline, capital_inicial)

    from backtest.intraday.report import cabecalho
    print(f"{SYMBOL}: janela >= {JANELA_INICIO.date()}, capital inicial = R$ {capital_inicial:.2f}")
    print()
    print(cabecalho())
    print(linha(linha_base), flush=True)

    resultados: dict[int, str] = {}
    with ProcessPoolExecutor() as pool:
        futures = {pool.submit(_roda_tregua, n): n for n in range(TREGUA_MIN, TREGUA_MAX + 1)}
        concluidos = 0
        for future in as_completed(futures):
            n, texto = future.result()
            resultados[n] = texto
            concluidos += 1
            print(texto, flush=True)
            print(f"[sweep_tregua] {concluidos}/{len(futures)} concluido(s) (tregua={n}min)", flush=True)

    print()
    print("--- resumo ordenado (1..30 min) ---")
    print(cabecalho())
    print(linha(linha_base))
    for n in range(TREGUA_MIN, TREGUA_MAX + 1):
        print(resultados[n])


if __name__ == "__main__":
    main()
