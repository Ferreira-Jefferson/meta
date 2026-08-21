"""Perfil economico por SIMBOLO intradiario — split congelado, custo real,
horario de flatten, tamanho de posicao.

Morava em `scripts/daytrade/run_backtest.py` ate 2026-08-21. Subiu para
`backtest/` quando a operacao ao vivo passou a precisar dos MESMOS numeros:
um `session_end_time` diferente entre backtest e producao faria o robô ao
vivo achatar em outro minuto do que o validado, e um custo diferente faria
o P&L em modo sombra nao bater com o backtest — que e' exatamente a
verificacao que o modo sombra existe para fazer. Um numero declarado em dois
lugares e' um numero que vai divergir.

Cada simbolo tem seu proprio perfil porque a economia de um instrumento nao
se transfere para outro: mesmo ponto de preco significa coisas diferentes,
mesmo lote significa coisas diferentes, e o horario de fechamento pode nem
seguir o mesmo calendario.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Literal

from backtest.intraday.costs import (
    PMAM3_EXCHANGE_FEE_PCT_PER_LEG,
    IntradayCostModel,
)
from backtest.intraday.machine import IntradayBacktestConfig


@dataclass(frozen=True)
class SymbolProfile:
    frozen_cutoff: str
    frozen_note: str
    fee_round_trip_brl: float
    fee_note: str
    session_end_time: time
    default_quantity: int
    exchange_fee_pct_per_leg: float = 0.0
    # "b3_equities" tira o corte de flatten do calendario e IGNORA
    # `session_end_time`; "fixed" usa o campo tal qual. Todo perfil real hoje
    # e' acao, logo "b3_equities" — "fixed" existe para um instrumento com
    # horario proprio (futuro, por exemplo, cujo fechamento medido NAO desloca
    # com o horario de verao dos EUA) e para relogio sintetico de teste.
    session_end_policy: Literal["fixed", "b3_equities"] = "b3_equities"


PROFILES: dict[str, SymbolProfile] = {
    "PMAM3": SymbolProfile(
        frozen_cutoff="2025-12-01",
        frozen_note=(
            "corte declarado 2026-08-21 antes de testar qualquer hipotese nesta acao; "
            "profundidade real 2023-04-11..2026-08-20 (~3,4 anos); "
            "~2,6 anos IS (2023-04-11..2025-11-30), ~8,7 meses OOS travado"
        ),
        # Lote PADRAO (100 acoes, nao fracionario): corretagem confirmada
        # R$0 em multiplas fontes pesquisadas 2026-08-21 (Rico zera
        # corretagem de acoes tanto lote padrao quanto fracionario — a
        # tarifa de R$1,90 encontrada antes era de uma leitura mais antiga/
        # especifica, superada). A taxa de BOLSA (B3, emolumentos+
        # liquidacao day trade) NAO e' zero: ~0,025% do notional por perna,
        # pesquisada 2026-08-21. Por pedido explicito do usuario, toda
        # compra/venda desta acao assume 2x essa taxa real como margem de
        # seguranca, de forma PERMANENTE (nao um ajuste de sensibilidade
        # pontual) -- ver `PMAM3_EXCHANGE_FEE_PCT_PER_LEG` em
        # `backtest/intraday/costs.py`.
        fee_round_trip_brl=0.0,
        fee_note="lote padrao (100 acoes): corretagem zero; taxa de bolsa em exchange_fee_pct_per_leg (2x a taxa real)",
        exchange_fee_pct_per_leg=PMAM3_EXCHANGE_FEE_PCT_PER_LEG,
        # `session_end_policy="b3_equities"` abaixo ignora este campo — quem
        # decide o corte e' o calendario (`core.b3_session`), nao um horario
        # fixo. Preenchido so porque o dataclass exige um valor: e' o antigo
        # corte fixo (19:54 UTC), que na verdade era so a moda de UM dos dois
        # regimes de horario de verao americano nas barras salvas — o outro
        # regime (20:54 UTC) foi tratado por anos como "cluster minoritario",
        # quando era o proprio calendario aparecendo no dado.
        session_end_time=time(19, 54),
        session_end_policy="b3_equities",
        default_quantity=100,  # 1 lote padrao
    ),
}


def config_for(
    profile: SymbolProfile,
    trade_tick_value: float,
    trade_tick_size: float,
    default_quantity: int | None = None,
    target_fills_as_maker: bool = False,
) -> IntradayBacktestConfig:
    """Monta o `IntradayBacktestConfig` de um perfil + a economia do simbolo
    lida do terminal (`market_data_intraday.mt5_source.symbol_economics`).

    Existe para o backtest e a operacao ao vivo montarem a config pelo MESMO
    caminho — `default_quantity` so e' sobrescrevivel porque ao vivo a
    quantidade sai do caixa destinado ao robo, nao do lote de referencia do
    perfil (ver `live/intraday_runtime.py`)."""
    costs = IntradayCostModel.from_symbol_info(
        trade_tick_value=trade_tick_value,
        trade_tick_size=trade_tick_size,
        fee_round_trip_brl=profile.fee_round_trip_brl,
        exchange_fee_pct_per_leg=profile.exchange_fee_pct_per_leg,
    )
    return IntradayBacktestConfig(
        costs=costs,
        session_end_time=profile.session_end_time,
        session_end_policy=profile.session_end_policy,
        default_quantity=(profile.default_quantity if default_quantity is None else default_quantity),
        target_fills_as_maker=target_fills_as_maker,
    )
