"""Comparativo ILUSTRATIVO do mecanismo de reversao (2026-08-28) -- `Enter`
de lado oposto com posicao aberta, adicionado em `backtest/intraday/machine.py`
nesta sessao (ver a mudanca na secao 3 de `on_closed_bar` + `_entrar_a_mercado`).

NAO e' backtest de nenhum robo real: nenhuma estrategia em producao (familia
`gremah`) emite `Enter` com posicao aberta -- todas usam `EnterLimit` e nem
avaliam sinal novo enquanto estao posicionadas (`if positions: return []`).
Este script isola so' o MECANISMO, com dados sinteticos, pra responder
"qual o resultado" com numero em vez de so' passa/falha de teste.

## Desenho

6 pregoes sinteticos, MESMA entrada (compra) e MESMO sinal oposto (venda)
chegando na mesma barra em todos -- a UNICA coisa que muda entre pregoes e'
o que o preco faz DEPOIS do sinal oposto:

  - 3 pregoes onde o preco CONTINUA caindo depois do sinal de venda (o sinal
    era informativo) -- "antes" (sinal ignorado, comportamento do motor ATE
    2026-08-27) so' segura a compra perdendo mais; "depois" (reversao)
    fecha a compra e vira vendido, capturando a queda que continuou.
  - 3 pregoes onde o preco INVERTE e volta a subir depois do sinal de venda
    (sinal falso) -- "antes" segura a compra e SE RECUPERA; "depois" vira
    vendido bem na hora errada e perde na alta.

Custo ZERADO de proposito (`slippage_ticks=0`, `fee_round_trip_brl=0`): o
objetivo e' isolar o efeito do MECANISMO, nao estimar um robo operavel.

## Como reproduzir "antes" sem reverter o motor

`_SEM_REVERSAO` nunca manda o `Enter` oposto -- so' a compra. Rodar essa
estrategia no motor ATUAL (com a mudanca) da' o MESMO resultado que rodar no
motor ANTIGO (que so' tratava esse `Enter` oposto de outro jeito quando ele
de fato chegava) -- a diferenca entre os dois motores so' aparece quando o
`Enter` oposto E' enviado, que e' exatamente o que `_COM_REVERSAO` faz.

Uso: `python -u scripts/daytrade/reversal_signal_ilustrativo_2026_08_28.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.costs import IntradayCostModel  # noqa: E402
from backtest.intraday.engine import IntradayBacktestConfig, run_intraday_backtest  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from strategy.daytrade.base import Enter, IntradayStrategy  # noqa: E402

CAPITAL_INICIAL = 10_000.0


class _StubStrategy(IntradayStrategy):
    name = "stub_reversal_demo"
    version = "0.1"
    symbol = "STUB3"

    def __init__(self, actions_by_ts: dict[pd.Timestamp, list]):
        self.actions_by_ts = actions_by_ts

    def on_bar(self, ts, bar, position, session_pnl_brl):
        return self.actions_by_ts.get(ts, [])


def _mk_bars(session_date: str, rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range(f"{session_date} 09:00", periods=len(rows), freq="1min", tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["tick_volume"] = 100
    return df


# cada pregao: b0 decide compra, b1 executa compra (open) e decide venda
# (sinal oposto), b2 e' onde a reversao executaria (open), b3/b4 o preco
# continua o movimento, b5 (ultima barra) flatten forcado.
_PREGOES_QUEDA_CONTINUA = {
    "2026-01-05": [(100, 101, 99, 100), (100, 101, 99, 100), (95, 96, 94, 95),
                   (90, 91, 89, 90), (85, 86, 84, 85), (85, 86, 84, 85)],
    "2026-01-06": [(200, 201, 199, 200), (200, 201, 199, 200), (197, 198, 196, 197),
                   (194, 195, 193, 194), (191, 192, 190, 191), (191, 192, 190, 191)],
    "2026-01-07": [(50, 51, 49, 50), (50, 51, 49, 50), (48, 49, 47, 48),
                   (46, 47, 45, 46), (44, 45, 43, 44), (44, 45, 43, 44)],
}
_PREGOES_SINAL_FALSO = {
    "2026-01-08": [(100, 101, 99, 100), (100, 101, 99, 100), (98, 99, 97, 98),
                   (103, 104, 102, 103), (108, 109, 107, 108), (108, 109, 107, 108)],
    "2026-01-09": [(150, 151, 149, 150), (150, 151, 149, 150), (148, 149, 147, 148),
                   (152, 153, 151, 152), (155, 156, 154, 155), (155, 156, 154, 155)],
    "2026-01-12": [(80, 81, 79, 80), (80, 81, 79, 80), (79, 80, 78, 79),
                   (81, 82, 80, 81), (83, 84, 82, 83), (83, 84, 82, 83)],
}
_TODOS_OS_PREGOES = {**_PREGOES_QUEDA_CONTINUA, **_PREGOES_SINAL_FALSO}


def _monta_bars() -> pd.DataFrame:
    return pd.concat([_mk_bars(dia, rows) for dia, rows in _TODOS_OS_PREGOES.items()])


def _config() -> IntradayBacktestConfig:
    costs = IntradayCostModel(point_value_brl=1.0, tick_size=1.0,
                               fee_round_trip_brl=0.0, slippage_ticks=0.0)
    return IntradayBacktestConfig(costs=costs, initial_capital=CAPITAL_INICIAL,
                                   default_quantity=1, session_end_time=pd.Timestamp("23:59").time())


def _acoes_sem_reversao(bars: pd.DataFrame) -> dict[pd.Timestamp, list]:
    acoes: dict[pd.Timestamp, list] = {}
    for dia in _TODOS_OS_PREGOES:
        b0 = bars[bars.index.date == pd.Timestamp(dia).date()].index[0]
        acoes[b0] = [Enter(side="long")]
    return acoes


def _acoes_com_reversao(bars: pd.DataFrame) -> dict[pd.Timestamp, list]:
    acoes: dict[pd.Timestamp, list] = {}
    for dia in _TODOS_OS_PREGOES:
        idx_dia = bars[bars.index.date == pd.Timestamp(dia).date()].index
        acoes[idx_dia[0]] = [Enter(side="long")]
        acoes[idx_dia[1]] = [Enter(side="short")]  # sinal oposto, posicao ja aberta
    return acoes


def main() -> None:
    bars = _monta_bars()
    cfg = _config()

    sem_reversao = run_intraday_backtest(bars, _StubStrategy(_acoes_sem_reversao(bars)), cfg)
    com_reversao = run_intraday_backtest(bars, _StubStrategy(_acoes_com_reversao(bars)), cfg)

    linhas = [
        linha_de_resultado("ANTES (sinal oposto ignorado)", sem_reversao, CAPITAL_INICIAL),
        linha_de_resultado("DEPOIS (sinal oposto reverte)", com_reversao, CAPITAL_INICIAL),
    ]
    print(__doc__.strip().splitlines()[0])
    print()
    print(tabela(linhas))
    print()
    print("Por pregao (positivo = reversao ganhou vs ignorar o sinal; negativo = reversao perdeu):")
    trades_sem = {t.entry_ts.date(): t.pnl_brl for t in sem_reversao.trades}
    trades_com: dict = {}
    for t in com_reversao.trades:
        trades_com.setdefault(t.entry_ts.date(), 0.0)
        trades_com[t.entry_ts.date()] += t.pnl_brl
    for dia in sorted(trades_sem):
        antes = trades_sem[dia]
        depois = trades_com.get(dia, 0.0)
        tipo = "queda continua" if dia.isoformat() in _PREGOES_QUEDA_CONTINUA else "sinal falso"
        print(f"{dia}  {tipo:<16}  antes={antes:+7.2f}  depois={depois:+7.2f}  swing={depois - antes:+7.2f}")


if __name__ == "__main__":
    main()
