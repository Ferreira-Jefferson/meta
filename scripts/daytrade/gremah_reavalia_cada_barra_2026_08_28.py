"""Comparativo REAL (2026-08-28, pedido do dono): `Gremah` (PMAM3) como opera
HOJE vs uma variante que reavalia a decisao a CADA barra fechada, sem esperar
o resultado real da ordem (stop/alvo/TTL) -- se a posicao aberta estivesse
PERDENDO agora (nao realizado), sai e deixa a maquina rearmar o lado oposto
na proxima oportunidade, em vez de esperar o trade fechar sozinho.

## A regra de hoje (`Gremah._next_side_to_arm`, gremah.py:1259-1281)

So decide o proximo lado DEPOIS que o trade FECHA: repete o lado se ganhou,
troca se perdeu. Enquanto uma posicao esta aberta, `on_bar` nem avalia nada
-- so contabilidade, `return []` (gremah.py:1481-1496).

## A variante testada (`GremahReavaliaCadaBarra`, abaixo)

Mesma regra (repete se ganhando, troca se perdendo), mas aplicada a CADA
barra fechada usando o resultado NAO REALIZADO da posicao aberta como proxy
-- "sem esperar o resultado da ordem". Reusa `Gremah.on_bar` sem tocar em
gremah.py (subclasse, mesmo padrao de `capital_ladder_gremah_2026_08_27.py::
GremahLoteFixo`): deixa a classe original rodar sua contabilidade normal, e
so intercepta o `[]` do caminho "posicionado, nada a fazer" para decidir se
early-exit ou nao. Zero mudanca de motor -- usa `Exit`, que ja funciona com
posicao aberta.

## M1 x M5

Mesma classe (baseline OU variante), alimentada com as MESMAS barras reais
da PMAM3 -- uma vez nativas (M1), uma vez reamostradas pra 5 minutos
(agregacao OHLCV por sessao, nunca atravessando o fechamento). RESSALVA:
`Gremah` foi calibrada (espacamento/alvo/stop em TICKS) em cima de M1 -- os
numeros de M5 usam a MESMA calibracao, nao uma nova, entao qualquer diferenca
reflete granularidade de barra sobre um ajuste feito pra M1, nao uma
calibracao M5 legitima.

## Dados e capital

Ultimos 3 meses corridos (>=2026-05-28), lidos DIRETO do parquet local
(`market_data_intraday.storage.load_m1`), sem a trava de IS/OOS dos scripts
`capital_ladder_*_2026_08_27.py` -- nao estou calibrando nada novo, so
medindo o efeito de um mecanismo sobre uma calibracao ja fixada (a mesma
liberacao que `frozen_split_scope_2026_08_21` documenta). Capital inicial =
capital minimo real da PMAM3 no preco do INICIO da janela (2 lotes de 100
acoes, `capital_minimo_brl`) + R$100, pedido explicito do dono.

Uso: `python -u scripts/daytrade/gremah_reavalia_cada_barra_2026_08_28.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import Exit, capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402

SYMBOL = "PMAM3"
JANELA_INICIO = pd.Timestamp("2026-05-28", tz="UTC")
ECONOMICS_CACHE = ROOT / "data" / "_economics_cache.json"


class GremahReavaliaCadaBarra(Gremah):
    """Ver docstring do modulo. `Gremah.on_bar` sem alteracao nenhuma --
    so intercepta o `[]` do caminho "posicionado, sem sinal novo" para
    decidir se sai AGORA (perdendo, sem esperar o stop/alvo real)."""

    name = "gremah_reavalia_cada_barra"

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if acoes or not positions:
            return acoes  # halt de sessao (Exit) ou flat: nada a interceptar
        pos = positions[0]
        ganho_nao_realizado = (
            (bar.close - pos.entry_price) if pos.side == "long"
            else (pos.entry_price - bar.close)
        )
        if ganho_nao_realizado > 0.0:
            return []  # ganhando agora -- "repete" (fica), mesma decisao de sempre
        oposto = "short" if pos.side == "long" else "long"
        if self._fills_of(oposto) >= self.max_trades_per_side:
            return []  # sem pra onde reverter -- deixa o trade seguir pro stop/alvo real
        return [Exit(reason="reavaliacao_a_cada_barra_perdendo")]


class GremahReavaliaAposTregua(Gremah):
    """Mesma ideia de `GremahReavaliaCadaBarra`, mas com uma TREGUA (pedido
    do dono, 2026-08-28): so reavalia a cada `tregua_bars` barras apos a
    entrada preencher, nao em toda barra -- da tempo do trade normal
    (stop/alvo) resolver sozinho antes de qualquer interferencia. Em M1,
    `tregua_bars=5` = 5 minutos de folga antes do primeiro cheque; depois
    disso, um cheque novo a cada 5 barras (nao so uma vez).

    `pos.bars_held` conta barras FECHADAS desde o fill, sem contar a propria
    barra do fill (fica em 0 nela) -- por isso o guarda extra de `== 0`
    abaixo: sem ele, `0 % tregua_bars == 0` dispararia um cheque na PRIMEIRA
    barra depois do fill, a mesma pressa que a tregua existe para evitar."""

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
            return []  # ainda na tregua -- deixa o trade normal resolver sozinho
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


def _resample_m5(bars_m1: pd.DataFrame) -> pd.DataFrame:
    """OHLCV de 5 minutos, por SESSAO (nunca agrega atravessando o
    fechamento) -- rotulo = fim da janela, mesma convencao de `run_intraday_
    backtest` ("index = timestamp de fechamento da barra")."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    for col in ("tick_volume", "real_volume", "volume"):
        if col in bars_m1.columns:
            agg[col] = "sum"
    partes = []
    for _, grupo in bars_m1.groupby(bars_m1.index.date):
        m5 = grupo.resample("5min", label="right", closed="right").agg(agg)
        partes.append(m5.dropna(subset=["open"]))
    return pd.concat(partes)


def main() -> None:
    bars_m1_full = load_m1(SYMBOL)
    if bars_m1_full.empty:
        raise RuntimeError(f"sem dado M1 local para {SYMBOL!r}")
    bars_m1 = bars_m1_full.loc[bars_m1_full.index >= JANELA_INICIO]
    if bars_m1.empty:
        raise RuntimeError(f"janela >= {JANELA_INICIO} vazia para {SYMBOL!r}")
    bars_m5 = _resample_m5(bars_m1)

    preco_inicio = float(bars_m1.iloc[0]["close"])
    capital_minimo = capital_minimo_brl(preco_inicio)
    capital_inicial = capital_minimo + 100.0

    import json
    economics = json.loads(ECONOMICS_CACHE.read_text(encoding="utf-8"))[SYMBOL]

    cfg = config_for(
        PROFILES[SYMBOL],
        trade_tick_value=economics["trade_tick_value"],
        trade_tick_size=economics["trade_tick_size"],
        target_fills_as_maker=Gremah.target_fills_as_maker,
        initial_capital=capital_inicial,
    )

    rodadas = [
        ("HOJE (M1)", Gremah(symbol=SYMBOL), bars_m1),
        ("REAVALIA A CADA BARRA (M1)", GremahReavaliaCadaBarra(symbol=SYMBOL), bars_m1),
        ("REAVALIA APOS TREGUA 5min (M1)", GremahReavaliaAposTregua(symbol=SYMBOL, tregua_bars=5), bars_m1),
        ("HOJE (M5)", Gremah(symbol=SYMBOL), bars_m5),
        ("REAVALIA A CADA BARRA (M5)", GremahReavaliaCadaBarra(symbol=SYMBOL), bars_m5),
    ]

    linhas = []
    for rotulo, estrategia, bars in rodadas:
        resultado = run_intraday_backtest(bars, estrategia, cfg)
        linhas.append(linha_de_resultado(rotulo, resultado, capital_inicial))

    print(f"{SYMBOL}: {bars_m1.index[0]} .. {bars_m1.index[-1]}  "
          f"({len(set(bars_m1.index.date))} pregoes M1, {len(set(bars_m5.index.date))} pregoes M5)")
    print(f"preco inicio da janela = R$ {preco_inicio:.2f}  "
          f"capital minimo (2 lotes) = R$ {capital_minimo:.2f}  "
          f"capital inicial usado = R$ {capital_inicial:.2f}")
    print()
    print(tabela(linhas))
    print()
    print("Nota: em M5 cada barra JA cobre 5 minutos -- 'REAVALIA A CADA BARRA (M5)'")
    print("acima E' a versao de tregua de 5min nessa granularidade, nao precisa de linha propria.")


if __name__ == "__main__":
    main()
