"""Fecha as DUAS escolhas que ainda estavam abertas no desenho do campeao.

RESULTADO (2026-08-20): a reserva de lucro foi REPROVADA e a regra de universo
empatou. O mecanismo esta implementado AQUI, e nao em `strategy/`, exatamente
por isso — nao entrou no robo. Ver `strategy/liquid_champion.py`.

O que estava em aberto
----------------------
1. **Regra de universo.** `liquid_sleeves5` refaz o top-20 a cada 12 meses;
   `liquid_flow5` reavalia todo mes com banda de rank 20/30 e nao tem cadencia.
   Nas 5 janelas de ajuste o flow5 tinha a melhor pior-janela; no holdout de 48
   janelas o sleeves5 teve menos janelas negativas (3 vs 8). Empate sujo.
2. **Reserva de lucro realizado.** Foi medida so no campeao antigo (uma posicao
   concentrada), onde melhorou o pior-12m de -18,8% para -14,0%. Num robo que ja
   diversifica em cinco sleeves ela pode ser so peso morto.

Protocolo (declarado antes de rodar)
------------------------------------
A calibragem acontece nas CINCO JANELAS DE AJUSTE, nao no holdout. Elas ja
julgaram mais de cem configuracoes — ja estao gastas, e gastar de novo nao
piora nada. O holdout de 2010-2013 fica intocado. Usar o holdout para ESCOLHER
entre os oito bracos abaixo o transformaria em mais um conjunto de ajuste.

Criterio de escolha, nesta ordem, tambem declarado antes:
  1. pior janela (o robo e para operar, nao para exibir mediana)
  2. pior retorno de 12 meses
  3. MaxDD
  4. CAGR mediano como desempate

O que a leitura mostrou
-----------------------
A reserva melhora o MaxDD de forma MONOTONA nas duas regras de universo (banda:
-36,7 / -36,4 / -35,8 / -35,1; epoca: -34,4 / -33,8 / -33,4 / -32,9), o que
descarta ruido. Mas cobra caro: o CAGR mediano da banda cai de 10,85% para
~8%, e o Calmar piora de 0,30 para 0,23 (na epoca, de 0,42 para 0,36). A
ordenacao pelo criterio declarado poe "banda + reserva 10%" em primeiro, mas as
reservas de 2% e 5% ficam ABAIXO da reserva zero na mesma coluna — nao-monotono
e portanto ruido. Escolher o 10% por causa disso seria colher o melhor sorteio.

Conclusao: sleeves e reserva de lucro sao SUBSTITUTOS. Os dois tiram risco pelo
mesmo caminho (menos dinheiro exposto por posicao) e nao somam. A reserva ficou
de fora do robo.

Uso: .venv/Scripts/python.exe scripts/run_champion_calibration.py
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
from core.config import BENCHMARK, BacktestConfig
from strategy.base import Enter
from strategy.liquid_flow5 import LiquidFlow5
from strategy.liquid_sleeve import LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"
WINDOWS = [
    ("2014-01-01", "2018-12-31"),
    ("2016-01-01", "2020-12-31"),
    ("2018-01-01", "2022-12-31"),
    ("2020-01-01", "2024-12-31"),
    ("2021-08-19", "2026-08-19"),
]


class ProfitReserveMixin:
    """Guarda `reserve_rate` de cada lucro realizado num bolso que nao volta."""

    def __init__(self, reserve_rate: float = 0.0, **kwargs):
        super().__init__(**kwargs)
        self.reserve_rate = reserve_rate
        self._reserve = 0.0
        # ticker -> (quantidade, preco de entrada) do pregao anterior. E assim
        # que se detecta um fechamento: a estrategia nao executa a venda, o
        # engine executa; ela so percebe que a posicao sumiu de `open_positions`.
        self._held: dict[str, tuple] = {}
        self._closes: dict[str, pd.Series] = {}

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        self._closes = {t: df["close"] for t, df in panels.items()}

    def _mark(self, ticker: str, date) -> float:
        s = self._closes.get(ticker)
        if s is None or date not in s.index:
            return 0.0
        v = s.loc[date]
        return 0.0 if pd.isna(v) else float(v)

    def on_bar(self, date, open_positions, cash_available):
        if self.reserve_rate > 0.0:
            for t, held in list(self._held.items()):
                if t in open_positions:
                    continue
                px = self._mark(t, date)
                if px:
                    lucro = (px - float(held[1])) * float(held[0])
                    if lucro > 0:
                        self._reserve += lucro * self.reserve_rate
                self._held.pop(t)
            self._held = {t: (p.quantity, p.entry_price) for t, p in open_positions.items()}

        acoes = super().on_bar(date, open_positions, cash_available)
        if self._reserve <= 0.0 or cash_available <= 0.0:
            return acoes

        livre = max(0.0, cash_available - self._reserve) / cash_available
        if livre <= 0.0:
            return [a for a in acoes if not isinstance(a, Enter)]

        # `size_hint` e fracao do caixa que AINDA sobra na hora da k-esima compra,
        # e o pai ja gravou 1/(idle-k) para dar fatias iguais com o caixa cheio.
        # Com uma reserva parada as fatias saem so do caixa livre; a forma fechada
        # e livre/(idle - k*livre), e `idle` se recupera do proprio hint do pai
        # (base = 1/(idle-k) => idle = 1/base + k). Multiplicar tudo por `livre`
        # seria mais curto e estaria errado: reservaria de novo a cada compra da
        # fila, e com a reserva crescendo por anos o erro nao e pequeno.
        for k, a in enumerate(a for a in acoes if isinstance(a, Enter)):
            base = a.size_hint if a.size_hint else 1.0
            idle = 1.0 / base + k
            a.size_hint = livre / (idle - k * livre)
        return acoes


class _BandaReserva(ProfitReserveMixin, LiquidFlow5):
    name = "calib_banda"
    candidate = False


class _EpocaReserva(ProfitReserveMixin, LiquidSleeves5):
    name = "calib_epoca"
    candidate = False

    def _make_sleeve(self, **kwargs) -> LiquidSleeve:
        return LiquidSleeve(**kwargs)


ARMS = []
for rate in (0.00, 0.02, 0.05, 0.10):
    ARMS.append((f"banda 20/30  reserva {rate:.0%}",
                 lambda r=rate: _BandaReserva(reserve_rate=r)))
    ARMS.append((f"epoca 12m    reserva {rate:.0%}",
                 lambda r=rate: _EpocaReserva(reserve_rate=r)))


def medir(factory, u, start, end) -> dict:
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC)
    r = run_bt(u, factory(), cfg, start=start, end=end)
    eq = r.equity_curve
    return {"cagr": float(r.metrics["cagr"]), "dd": float(r.metrics["max_drawdown"]),
            "w12": float((eq / eq.shift(252) - 1).min()), "trades": len(r.trades)}


def ibov_janela(start, end) -> dict:
    c = panel(BENCHMARK)["close"].loc[start:end].dropna()
    anos = (c.index[-1] - c.index[0]).days / 365.25
    return {"cagr": float((c.iloc[-1] / c.iloc[0]) ** (1 / anos) - 1),
            "dd": float((c / c.cummax() - 1).min()),
            "w12": float((c / c.shift(252) - 1).min()), "trades": 0}


def main() -> None:
    u = full_panels()
    ib = [ibov_janela(s, e) for s, e in WINDOWS]

    hdr = (f"{'braco':26s} " + "".join(f"{s[2:7]:>8s}" for s, _ in WINDOWS) +
           f" | {'med':>7s} {'pior':>7s} {'DDpior':>7s} {'12m':>7s} {'trd':>4s}")
    print("\nCALIBRAGEM DO CAMPEAO — 5 janelas de ajuste, caixa na Selic")
    print(f"{'=' * len(hdr)}\n{hdr}\n{'-' * len(hdr)}")

    ibg = [m["cagr"] for m in ib]
    print(f"{'IBOV':26s} " + "".join(f"{g * 100:7.1f}%" for g in ibg) +
          f" | {np.median(ibg) * 100:6.1f}% {min(ibg) * 100:6.1f}% "
          f"{min(m['dd'] for m in ib) * 100:6.1f}% {min(m['w12'] for m in ib) * 100:6.1f}% "
          f"{0:4d}")

    resultados = {}
    for nome, factory in ARMS:
        rows = [medir(factory, u, s, e) for s, e in WINDOWS]
        g = [m["cagr"] for m in rows]
        r = {"med": float(np.median(g)), "pior": min(g),
             "dd": min(m["dd"] for m in rows), "w12": min(m["w12"] for m in rows),
             "trd": int(np.median([m["trades"] for m in rows]))}
        resultados[nome] = r
        print(f"{nome:26s} " + "".join(f"{x * 100:7.1f}%" for x in g) +
              f" | {r['med'] * 100:6.1f}% {r['pior'] * 100:6.1f}% "
              f"{r['dd'] * 100:6.1f}% {r['w12'] * 100:6.1f}% {r['trd']:4d}", flush=True)

    ordem = sorted(resultados.items(),
                   key=lambda kv: (-kv[1]["pior"], -kv[1]["w12"], -kv[1]["dd"], -kv[1]["med"]))
    print("\nordenado pelo criterio declarado (pior janela > pior 12m > MaxDD > mediana):")
    for i, (nome, r) in enumerate(ordem, 1):
        calmar = r["med"] / abs(r["dd"]) if r["dd"] else float("nan")
        print(f"  {i}. {nome:26s} pior {r['pior'] * 100:6.2f}%  12m {r['w12'] * 100:6.2f}%  "
              f"DD {r['dd'] * 100:6.2f}%  med {r['med'] * 100:6.2f}%  Calmar {calmar:.2f}")


if __name__ == "__main__":
    main()
