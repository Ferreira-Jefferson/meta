"""Entrada A MERCADO vs ordem-limite parada, `GremahTick` PMAM3 (2026-08-28,
pedido do dono).

## O problema real (esta semana, nao teoria)

`EnterLimit` (a entrada de hoje) fica parada num nivel de preco esperando o
mercado tocar -- e mesmo quando toca, muitas vezes NAO enche, porque tem fila
de gente na frente no mesmo preco (ver `gremah_modelo_fila_ponto_de_morte_
2026_08_27`: fila real da PMAM3 medida em ~7.300x o volume mediano). Essa
semana isso significou ZERO entradas ao vivo.

Teste manual em conta real (2026-08-27, ver `pmam3_mercado_vs_limite_
deslize_2026_08_27`) ja mostrou que ordem a MERCADO resolve o preenchimento
mas desliza ~1 tick -- e o alvo da familia gremah em PMAM3 e' exatamente 1
tick (`alvo_1_tick_confirmado_2026_08_26`), entao o deslize pode comer o
edge inteiro. Aquele teste foi UMA operacao manual (n=1). Este script mede
em ESCALA (todos os sinais dos ultimos 3 meses), com o MESMO modelo de custo
que ja aplica slippage realista por padrao (`IntradayCostModel.
slippage_ticks=1.0`, `backtest/intraday/costs.py`, usado sempre que
`config_for` monta a config -- nao e' um numero novo inventado pra este
teste).

## A mudanca

`GremahTickEntradaMercado` reusa `GremahTick._build_entry` (MESMO nivel,
MESMO alvo, MESMO stop, MESMA quantidade -- nao recalcula nada) e so troca
o tipo de acao devolvida: `Enter` (mercado, preenche na abertura da PROXIMA
barra/negocio com slippage) em vez de `EnterLimit` (parada, preenche so' se
o mercado tocar o nivel, sem slippage, mas sem garantia nenhuma de fila).
`dividir_entrada` (fatiar em varios filhos) nao se aplica a `Enter` -- uma
entrada a mercado enche inteira de uma vez, nao tem fila pra fatiar.

Saida (alvo) continua PASSIVA (`target_fills_as_maker=True`, igual a
producao) -- o problema relatado esta semana e' so' na ENTRADA.

Uso: `python -u scripts/daytrade/gremah_tick_entrada_mercado_2026_08_28.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.base import Enter, capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah_tick import GremahTick  # noqa: E402

SYMBOL = "PMAM3"
JANELA_INICIO = pd.Timestamp("2026-05-28", tz="UTC")
ECONOMICS_CACHE = ROOT / "data" / "_economics_cache.json"


class GremahTickEntradaMercado(GremahTick):
    """Ver docstring do modulo."""

    name = "gremah_tick_entrada_mercado"

    def _build_entry(self, side, anchor, spacing_ticks, profit_ticks, stop_ticks, ts):
        entrada_limite = super()._build_entry(side, anchor, spacing_ticks, profit_ticks, stop_ticks, ts)
        return Enter(
            side=entrada_limite.side,
            initial_stop=entrada_limite.initial_stop,
            initial_target=entrada_limite.initial_target,
            quantity=entrada_limite.quantity,
            reason="gremah_tick_mercado_" + side,
        )


def main() -> None:
    ticks = load_ticks(SYMBOL)
    ticks = ticks.loc[ticks.index >= JANELA_INICIO]
    if ticks.empty:
        raise RuntimeError(f"sem tick local para {SYMBOL!r} na janela")
    bars = ticks_to_degenerate_bars(ticks)

    preco_inicio = float(bars.iloc[0]["close"])
    capital_minimo = capital_minimo_brl(preco_inicio)
    capital_inicial = capital_minimo + 100.0

    economics = json.loads(ECONOMICS_CACHE.read_text(encoding="utf-8"))[SYMBOL]
    cfg = config_for(
        PROFILES[SYMBOL],
        trade_tick_value=economics["trade_tick_value"],
        trade_tick_size=economics["trade_tick_size"],
        target_fills_as_maker=GremahTick.target_fills_as_maker,
        initial_capital=capital_inicial,
    )
    print(f"slippage_ticks aplicado (mesmo default do motor): {cfg.costs.slippage_ticks}")

    pregoes = len(set(bars.index.date))
    print(f"{SYMBOL} tick: {bars.index[0]} .. {bars.index[-1]}  ({pregoes} pregoes, {len(bars)} negocios)")
    print(f"preco inicio = R$ {preco_inicio:.2f}  capital minimo = R$ {capital_minimo:.2f}  "
          f"capital inicial usado = R$ {capital_inicial:.2f}")
    print()

    linhas = []
    for rotulo, estrategia in [
        ("HOJE (EnterLimit, pode nao encher)", GremahTick(symbol=SYMBOL)),
        ("ENTRADA A MERCADO (sempre enche)", GremahTickEntradaMercado(symbol=SYMBOL)),
    ]:
        resultado = run_intraday_backtest(bars, estrategia, cfg)
        linhas.append(linha_de_resultado(rotulo, resultado, capital_inicial))

    print(tabela(linhas))


if __name__ == "__main__":
    main()
