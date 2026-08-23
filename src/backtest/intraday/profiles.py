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

Hoje todos os perfis sao ACAO da B3 em lote padrao, e por isso quase tudo
neles e' identico — o que varia de verdade e' so o SPLIT (ate onde a pesquisa
podia olhar). Dai `_equity_profile()`: a parte comum fica escrita UMA vez, e
cada entrada da tabela declara so o que e' dela. Um instrumento com economia
propria (futuro, BDR, ETF) nao usa a fabrica — monta `SymbolProfile` na mao,
com o motivo escrito junto.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Literal

from strategy.daytrade.base import capital_minimo_brl

from backtest.intraday.costs import (
    B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG,
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


#: Corte IS/OOS de TODA a familia de acoes calibrada em 2026-08-22. Declarado
#: ANTES da varredura de parametros: a varredura fina so enxergou o trecho
#: anterior a esta data, e o trecho posterior foi rodado UMA vez, ja com o par
#: escolhido, so para confirmar. Simbolo que ficou positivo no IS e negativo
#: no OOS foi DESCARTADO (aconteceu com CMIN3, BBDC3, EQTL3 e EUCA4) -- e' o
#: unico motivo de este corte existir.
#:
#: Substitui, para a PMAM3, o corte anterior de 2025-12-01 (declarado
#: 2026-08-21). Nao foi conveniencia: o preco da PMAM3 caiu de ~R$2,55 para
#: R$0,14, e o regime de preco em que ela opera HOJE (ver `regime_start`
#: abaixo) comeca em 2025-12-16 -- inteiramente DEPOIS do corte velho, que
#: portanto nao separava mais nada de util. Custo honesto dessa troca,
#: registrado para nao se perder: a calibracao da PMAM3 (0,32%/10x) foi
#: escolhida com dado que o corte de 2025-12-01 mantinha reservado, entao ela
#: tem menos independencia IS/OOS que as outras nove.
OOS_CUTOFF = "2026-06-13"

_FEE_NOTE = (
    "lote padrao (100 acoes): corretagem zero na Rico; taxa de bolsa em "
    "exchange_fee_pct_per_leg (2x a taxa real, margem de seguranca permanente). "
    "O mercado FRACIONARIO cobra R$1,90 fixos por ordem (confirmado pelo dono "
    "2026-08-22) e por isso day trade nunca opera nele -- ver "
    "`live/broker_mt5.py` e `scripts/run_live.py::build_intraday`, que nem "
    "recebem mapa fracionario no slot intradiario."
)


def _equity_profile(regime_start: str, oos_note: str) -> SymbolProfile:
    """Perfil de uma ACAO da B3 operada em lote padrao pela familia gremah.

    `regime_start`: primeiro dia do REGIME DE PRECO atual do papel — a data
    mais antiga a partir da qual o fechamento diario nunca mais saiu da faixa
    [0,5x, 2x] do preco de hoje. A calibracao so foi medida dai para frente,
    porque `profit_pct` vira TICKS (`Gremah._ticks_from_pct`) e portanto o
    mesmo percentual significa coisas diferentes em precos diferentes: medir
    CSAN3 desde 2021, quando ela valia o dobro, calibraria para um papel que
    nao existe mais.

    `session_end_time` e' preenchido so porque o dataclass exige um valor —
    `session_end_policy="b3_equities"` o IGNORA e tira o corte de flatten do
    calendario (`core.b3_session`), que anda 1h com o horario de verao dos
    EUA. O valor aqui e' o antigo corte fixo (19:54 UTC), que era so a moda de
    UM dos dois regimes de DST nas barras salvas.
    """
    return SymbolProfile(
        frozen_cutoff=OOS_CUTOFF,
        frozen_note=(
            f"regime de preco atual desde {regime_start}; IS {regime_start}..{OOS_CUTOFF} "
            f"(unico trecho que a varredura de parametros enxergou), OOS "
            f"{OOS_CUTOFF}..2026-08-21 confirmado positivo em 2026-08-22 ({oos_note}). "
            f"Capital do teste = `strategy.daytrade.base.capital_minimo_brl` no preco atual."
        ),
        fee_round_trip_brl=0.0,
        fee_note=_FEE_NOTE,
        exchange_fee_pct_per_leg=B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG,
        session_end_time=time(19, 54),
        session_end_policy="b3_equities",
        default_quantity=100,  # 1 lote padrao
    )


#: Ordem = lucro OOS decrescente dentro de cada grupo, PMAM3 primeiro por ser
#: o papel original da familia. Toda entrada aqui tem calibracao propria em
#: `strategy.daytrade.lab.gremah._CALIBRATION_BY_SYMBOL` — as duas tabelas
#: precisam andar juntas, e `tests/test_intraday_profiles.py` falha se
#: divergirem (um simbolo calibrado sem perfil nao consegue operar ao vivo:
#: `scripts/run_live.py::build_intraday` o recusa).
PROFILES: dict[str, SymbolProfile] = {
    "PMAM3": _equity_profile(
        "2025-12-16", "319 trades, wr 83,1%, +R$177,79, pf 2,75, MaxDD -21,59%"),
    "KLBN4": _equity_profile(
        "2025-09-02", "671 trades, wr 98,7%, +R$425,02, pf 12,15, MaxDD -0,81%"),
    "CSAN3": _equity_profile(
        "2025-09-22", "627 trades, wr 98,2%, +R$347,48, pf 4,22, MaxDD -2,16%"),
    "DASA3": _equity_profile(
        "2025-09-11", "857 trades, wr 93,5%, +R$278,94, pf 1,77, MaxDD -4,24%"),
    "PCAR3": _equity_profile(
        "2025-08-21", "894 trades, wr 92,4%, +R$249,89, pf 1,59, MaxDD -4,55%"),
    # AMOSTRA FINA, e a acao mais cara da tabela por MUITO: R$151,95 -> lote de
    # R$15.195 -> minimo de R$30.390 em caixa. So 131 trades no IS e 14 no OOS
    # (as outras fazem centenas a milhares) porque o alvo de 0,42% num papel
    # caro e' muito maior em reais e o preco raramente percorre isso num dia.
    # Passou nos dois trechos, entao esta aqui; mas 14 trades nao provam edge,
    # e o capital exigido esta fora da realidade do dono hoje.
    "CLSC4": _equity_profile(
        "2025-05-12", "14 trades, wr 64,3%, +R$215,21, pf 1,56, MaxDD -0,99%"),
    "KLBN3": _equity_profile(
        "2025-03-10", "395 trades, wr 95,9%, +R$198,43, pf 3,63, MaxDD -1,48%"),
    "GRND3": _equity_profile(
        "2025-09-05", "334 trades, wr 97,3%, +R$189,70, pf 5,59, MaxDD -1,54%"),
    "LPSB3": _equity_profile(
        "2022-12-20", "171 trades, wr 94,2%, +R$139,51, pf 4,83, MaxDD -2,42%"),
    "BMGB4": _equity_profile(
        "2025-06-04", "316 trades, wr 97,5%, +R$137,72, pf 2,86, MaxDD -2,11%"),
}


def config_for(
    profile: SymbolProfile,
    trade_tick_value: float,
    trade_tick_size: float,
    default_quantity: int | None = None,
    target_fills_as_maker: bool = False,
    preco_atual: float | None = None,
    initial_capital: float | None = None,
) -> IntradayBacktestConfig:
    """Monta o `IntradayBacktestConfig` de um perfil + a economia do simbolo
    lida do terminal (`market_data_intraday.mt5_source.symbol_economics`).

    Existe para o backtest e a operacao ao vivo montarem a config pelo MESMO
    caminho — `default_quantity` so e' sobrescrevivel porque ao vivo a
    quantidade sai do caixa destinado ao robo, nao do lote de referencia do
    perfil (ver `live/intraday_runtime.py`).

    `initial_capital`: sem default fixo (ver o motivo em `IntradayBacktestConfig.
    initial_capital`) -- passe-o explicitamente (backtest ao vivo sempre
    sobrescreve depois, via `IntradayLiveRuntime`) OU passe `preco_atual` para
    este montador computar o minimo real do simbolo (`capital_minimo_brl`).
    Passar os dois e' erro do chamador."""
    if initial_capital is None:
        if preco_atual is None:
            raise ValueError(
                "config_for precisa de `initial_capital` explicito OU `preco_atual` "
                "(para computar capital_minimo_brl) -- nao ha mais default implicito."
            )
        initial_capital = capital_minimo_brl(preco_atual)
    elif preco_atual is not None:
        raise ValueError("config_for: passe `initial_capital` OU `preco_atual`, nao os dois.")
    costs = IntradayCostModel.from_symbol_info(
        trade_tick_value=trade_tick_value,
        trade_tick_size=trade_tick_size,
        fee_round_trip_brl=profile.fee_round_trip_brl,
        exchange_fee_pct_per_leg=profile.exchange_fee_pct_per_leg,
    )
    return IntradayBacktestConfig(
        costs=costs,
        initial_capital=initial_capital,
        session_end_time=profile.session_end_time,
        session_end_policy=profile.session_end_policy,
        default_quantity=(profile.default_quantity if default_quantity is None else default_quantity),
        target_fills_as_maker=target_fills_as_maker,
    )
