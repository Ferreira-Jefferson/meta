"""Peca comum da rodada CRIPTO (2026-08-27): a familia `gremah` testada nos
veiculos de BITCOIN e ETHEREUM listados na B3.

Por que ETF/BDR e nao "BTC/ETH" direto: a gremah e' um maker de grid que
ganha 1 TICK por trade, em reais, com o tarifario e o horario da B3. O que o
dono consegue operar hoje, com a infra que ja existe (MT5 na Rico/Clear), sao
os veiculos listados aqui -- nao a cripto na exchange. O futuro de bitcoin da
B3 (`BIT@`) existe e tem M1 (630 barras/pregao), mas e' outro instrumento
(margem por contrato, ~R$412 mil de nocional por contrato cheio) e fica fora
desta rodada de proposito.

LOTE 1: ETF e BDR da B3 negociam em lote de 1 unidade -- o proprio terminal
declara (`symbol_info.volume_min`: 100 na PMAM3, 1 em BOVA11/BITH11/QETH11).
Por isso `Gremah(shares_per_lot=1)` e `default_quantity=1` no perfil: o caixa
minimo de um ETF de R$93 e' R$186, nao R$18.600.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from backtest.intraday.costs import B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import OOS_CUTOFF, SymbolProfile  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

#: Veiculo -> (o que ele segue). Escolhidos por MERCADO, nao por nome: todo
#: simbolo aqui tem >= 96 barras M1 por pregao e giro mediano acima de
#: R$1 milhao/dia (medido 2026-08-27 nos ultimos 120 pregoes). Ficaram de fora
#: NBIT11 (1.178 unidades/dia), BITO39 (23 barras/pregao), ETHA39 (19),
#: BITB39/CBTC39/XBIT11/GBIT11/EBIT11/BITC11/XETH11/EETH11 (todos abaixo de 35
#: barras/pregao) -- mesma regra que reprovou a CLSC4 na familia de acoes.
CRIPTO = {
    "BITH11": "BTC",
    "QBTC11": "BTC",
    "BTCI11": "BTC (com renda -- volatilidade ~1/3 dos outros)",
    "IBIT39": "BTC (BDR do iShares)",
    "ETHE11": "ETH",
    "QETH11": "ETH",
    "ETHY11": "ETH (com renda)",
    "HASH11": "indice cripto (BTC+ETH+outras)",
}

#: Mesma definicao da familia de acoes (`_geometria_comum.REGIME_START`): a
#: data mais antiga a partir da qual o fechamento diario nunca mais saiu de
#: [0,5x; 2x] do preco de hoje. Calculada 2026-08-27 sobre o M1 salvo.
REGIME_START = {
    "BITH11": "2025-08-27", "QBTC11": "2025-05-28", "BTCI11": "2025-09-23",
    "IBIT39": "2024-03-01", "ETHE11": "2025-08-23", "QETH11": "2025-08-23",
    "ETHY11": "2025-12-16", "HASH11": "2025-09-11",
}

#: Lote em UNIDADES. 1 para todo ETF/BDR da B3 (ver docstring do modulo).
SHARES_PER_LOT = 1

_FEE_NOTE_ETF = (
    "ETF/BDR em lote de 1 unidade: corretagem zero na Rico (mesma regra da "
    "acao a vista em lote padrao -- NAO e' mercado fracionario, logo nao paga "
    "os R$1,90 fixos por ordem), taxa de bolsa em exchange_fee_pct_per_leg "
    "(2x a taxa real, mesma margem de seguranca permanente da familia de "
    "acoes)."
)


def perfil_cripto(symbol: str) -> SymbolProfile:
    """Perfil economico de um veiculo cripto da B3.

    Copia deliberada de `profiles._equity_profile` com UMA diferenca --
    `default_quantity=1` (o lote real do instrumento, ver o modulo). Nao
    reusa a fabrica de la' porque `_equity_profile` fixa 100 e mexer nela
    mudaria os 10 simbolos de producao.

    `frozen_cutoff` = `profiles.OOS_CUTOFF` (2026-06-13), CONGELADO em
    2026-08-22 -- antes de existir qualquer trabalho com cripto neste repo,
    logo nao pode ter sido escolhido para favorecer esta rodada.
    """
    return SymbolProfile(
        frozen_cutoff=OOS_CUTOFF,
        frozen_note=(
            f"{symbol}: regime de preco desde {REGIME_START[symbol]}; IS "
            f"{REGIME_START[symbol]}..{OOS_CUTOFF}, OOS {OOS_CUTOFF}..2026-08-27 "
            f"(54 pregoes) rodado UMA vez, ja com a celula escolhida no IS."
        ),
        fee_round_trip_brl=0.0,
        fee_note=_FEE_NOTE_ETF,
        exchange_fee_pct_per_leg=B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG,
        session_end_time=time(19, 54),      # ignorado por `b3_equities`
        session_end_policy="b3_equities",
        default_quantity=SHARES_PER_LOT,
    )


@dataclass(frozen=True)
class Janela:
    bars: pd.DataFrame
    preco_ref: float
    profile: SymbolProfile


def _regime(symbol: str) -> pd.DataFrame:
    bars = load_m1(symbol)
    if bars.empty:
        return bars
    return bars.loc[bars.index >= pd.Timestamp(REGIME_START[symbol], tz="UTC")]


def carregar_is(symbol: str) -> Janela:
    """Barras IN-SAMPLE (regime de preco + split congelado). NUNCA chama
    `unlock()` -- o OOS nao passa por aqui."""
    profile = perfil_cripto(symbol)
    bars = _regime(symbol)
    if bars.empty:
        return Janela(bars, 0.0, profile)
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    run_bars = LockedBars(bars, split).in_sample()
    if run_bars.empty:
        return Janela(run_bars, 0.0, profile)
    # Mesma convencao de `_geometria_comum.carregar_is`: preco de referencia
    # (= o que dimensiona o capital) e' o FECHAMENTO da primeira barra da
    # janela, nao o preco de hoje.
    return Janela(run_bars, float(run_bars["close"].iloc[0]), profile)


def carregar_oos(symbol: str, motivo: str) -> Janela:
    """Barras OUT-OF-SAMPLE. `motivo` e' obrigatorio: o holdout so' se abre
    para CONFIRMAR uma celula ja escolhida no IS (ver `copa_oos_gasto_
    2026_08_26` -- rodar busca no OOS gasta o holdout)."""
    profile = perfil_cripto(symbol)
    bars = _regime(symbol)
    if bars.empty:
        return Janela(bars, 0.0, profile)
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(bars, split)
    locked.unlock(motivo)
    run_bars = locked.out_of_sample()
    if run_bars.empty:
        return Janela(run_bars, 0.0, profile)
    return Janela(run_bars, float(run_bars["close"].iloc[0]), profile)
