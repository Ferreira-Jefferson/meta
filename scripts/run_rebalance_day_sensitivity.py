"""Hipotese 3 — o resultado depende do DIA em que o robo rebalanceia?

A pergunta
----------
Toda a familia decide no ULTIMO pregao do mes. Essa data nao veio de teoria
nenhuma — veio de ser a escolha obvia quando alguem escreveu `is_month_end`. Se
mover o gatilho em alguns pregoes para tras ou para a frente mudar muito o
resultado, entao o que os backtests medem nao e vantagem: e sorte de calendario.
O robo estaria colhendo um punhado de datas felizes e chamando isso de sinal.

E a checagem de fragilidade mais barata que faltava, e a mais dificil de
racionalizar depois: nao existe historia economica que explique por que o
penultimo pregao do mes funcionaria e o antepenultimo nao.

Como ler o resultado
--------------------
O que importa nao e qual deslocamento ganha — e a DISPERSAO. Um robo saudavel
tem os onze deslocamentos agrupados; um robo sorteado tem alguns otimos e
alguns pessimos, e o dia zero por acaso e um dos otimos.

Duas leituras somadas:
  - o coeficiente de variacao do CAGR entre os deslocamentos;
  - o POSTO do dia zero entre os onze. Se o dia oficial for sistematicamente o
    melhor, o backtest esta se auto-selecionando; se ficar no meio, nao esta.

O deslocamento e aplicado no gatilho `_month_end` DEPOIS do `initialize`, sem
tocar em indicador nenhum: o momentum, o dip e o gate de Selic continuam
identicos. So muda o dia em que o robo olha para eles.

Uso: .venv/Scripts/python.exe scripts/run_rebalance_day_sensitivity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from run_sleeve_validation import full_panels
from safety_lab import panel

from backtest.runner import run as run_bt
from core.config import BENCHMARK, WATCHLIST, BacktestConfig
from strategy.liquid_flow5 import LiquidFlow5
from strategy.liquid_sleeves5 import LiquidSleeves5
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
OFFSETS = list(range(-5, 6))
WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]


def shift_trigger(bot, offset: int):
    """Desloca o gatilho de rebalanceamento em `offset` pregoes, recursivamente.

    Recursivo porque `LiquidSleeves5` nao decide nada sozinho — quem tem
    `_month_end` sao os cinco sleeves internos. Deslocar so o objeto de fora
    nao mudaria uma unica ordem, e o teste passaria dando 'zero sensibilidade'
    pelo motivo errado.
    """
    if hasattr(bot, "_month_end") and len(getattr(bot, "_month_end")) and offset:
        me = bot._month_end
        bot._month_end = pd.Series(
            np.roll(me.to_numpy(), offset), index=me.index
        )
        # `np.roll` e circular: as `|offset|` posicoes que deram a volta viriam
        # do outro extremo da serie. Zerar as pontas evita um rebalanceamento
        # fantasma no primeiro/ultimo mes.
        if offset > 0:
            bot._month_end.iloc[:offset] = False
        else:
            bot._month_end.iloc[offset:] = False
    for sub in getattr(bot, "_sleeves", []):
        shift_trigger(sub, offset)


class _Shifted:
    """Embrulha uma fabrica de robo aplicando o deslocamento apos o initialize."""

    def __init__(self, factory, offset: int):
        self._factory, self._offset = factory, offset

    def __call__(self):
        bot = self._factory()
        original = bot.initialize

        def initialize(panels, ibov):
            original(panels, ibov)
            shift_trigger(bot, self._offset)

        bot.initialize = initialize
        return bot


def medir(factory, u, start, end) -> dict:
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC)
    r = run_bt(u, factory(), cfg, start=start, end=end)
    eq = r.equity_curve
    return {"cagr": float(r.metrics["cagr"]), "dd": float(r.metrics["max_drawdown"]),
            "final": float(r.metrics["final_capital"]),
            "w12": float((eq / eq.shift(252) - 1).min()), "trades": len(r.trades)}


def avaliar(nome: str, factory, u) -> None:
    print(f"\n{'=' * 104}\n{nome}\n{'=' * 104}")
    print(f"{'desloc':>7s} " + "".join(f"| {s[2:7]:>7s} " for s, _ in WINDOWS) +
          f"| {'CAGRmed':>8s} {'pior':>7s} {'DDpior':>7s} {'12m':>7s} {'trd':>5s}")
    linhas = {}
    for off in OFFSETS:
        rows = [medir(_Shifted(factory, off), u, s, e) for s, e in WINDOWS]
        g = [m["cagr"] for m in rows]
        linhas[off] = {"med": float(np.median(g)), "pior": min(g),
                       "dd": min(m["dd"] for m in rows),
                       "w12": min(m["w12"] for m in rows),
                       "trd": int(np.median([m["trades"] for m in rows]))}
        marca = " <-- oficial" if off == 0 else ""
        print(f"{off:+7d} " + "".join(f"| {m['cagr'] * 100:6.1f}% " for m in rows) +
              f"| {linhas[off]['med'] * 100:7.2f}% {linhas[off]['pior'] * 100:6.2f}% "
              f"{linhas[off]['dd'] * 100:6.1f}% {linhas[off]['w12'] * 100:6.1f}% "
              f"{linhas[off]['trd']:5d}{marca}", flush=True)

    meds = np.array([linhas[o]["med"] for o in OFFSETS])
    piores = np.array([linhas[o]["pior"] for o in OFFSETS])
    cv = float(np.std(meds) / abs(np.mean(meds))) if np.mean(meds) else float("nan")
    posto = int((meds > linhas[0]["med"]).sum()) + 1
    print(f"\n  CAGR mediano entre deslocamentos: {meds.min() * 100:.2f}% a {meds.max() * 100:.2f}% "
          f"(amplitude {(meds.max() - meds.min()) * 100:.2f} p.p.)")
    print(f"  coeficiente de variacao: {cv * 100:.1f}%")
    print(f"  o dia OFICIAL ficou em {posto}o de {len(OFFSETS)}")
    print(f"  deslocamentos com pior janela negativa: {(piores < 0).sum()} de {len(OFFSETS)}")


def main() -> None:
    # Um robo por invocacao (`--only`): a primeira versao rodava os tres em
    # sequencia e o processo morreu no meio do segundo, levando junto o terceiro
    # que ja estava pago. Isolar custa alguns segundos de carga repetida e
    # garante que uma queda perca no maximo um robo.
    alvo = None
    if "--only" in sys.argv:
        alvo = sys.argv[sys.argv.index("--only") + 1]

    print("\nHIPOTESE 3 — SENSIBILIDADE AO DIA DO REBALANCEAMENTO")
    print("caixa remunerado na Selic nas duas pontas | 5 janelas fechadas de 5 anos")
    print("deslocamento em PREGOES em torno do fim de mes oficial")

    robos = {
        "campeao": ("portfolio_dip2_hw40 (campeao, watchlist oficial)", DipTop1Portfolio, "wl"),
        "sleeves5": ("liquid_sleeves5", LiquidSleeves5, "pool"),
        "flow5": ("liquid_flow5", LiquidFlow5, "pool"),
    }
    escolhidos = [alvo] if alvo else list(robos)

    for chave in escolhidos:
        nome, factory, fonte = robos[chave]
        if fonte == "wl":
            u = {t: panel(t) for t in WATCHLIST}
            u[BENCHMARK] = panel(BENCHMARK)
        else:
            u = full_panels()
        avaliar(nome, factory, u)


if __name__ == "__main__":
    main()
