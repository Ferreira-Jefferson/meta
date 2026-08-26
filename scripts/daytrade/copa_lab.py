"""Montagem COMPARTILHADA das rodadas da familia `copa` — o unico lugar onde
dado, perfil economico, teto de contratos e robo se encontram.

Mora em `scripts/` (orquestracao) e nao em `backtest/` por causa da regra de
fronteira do `AGENTS.md`: uma feature so' importa `core/`, e aqui e' preciso
importar `backtest` E `strategy` ao mesmo tempo. `sweep_copa.py` e
`run_copa_score.py` importam daqui em vez de cada um montar a sua versao --
duas montagens sao duas chances de o teto passado ao ROBO divergir do teto
passado ao MOTOR, e essa divergencia produziria um numero que nao descreve
nada (o robo dimensionando para 12 enquanto o motor recusa acima de 4).

Capital NOCIONAL, nao real: o simulador da Copa declara margem infinita e nao
tem saldo ficticio. `CAPITAL_NOCIONAL` existe so' para a curva de patrimonio
ter uma base e o motor conseguir detectar quebra -- todo relatorio da familia
reporta R$ liquido, nunca percentual sobre ele (ver `backtest/intraday/
report.py`).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.copa_score import (  # noqa: E402
    blocos_de_fase,
    resultados_diarios,
    resumir_blocos,
)
from backtest.intraday.costs import IntradayCostModel  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import LinhaResultado, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.copa import Copa  # noqa: E402

#: Linha de base declarada da curva de patrimonio. NAO e' um saldo: e' grande
#: o bastante para o motor nunca declarar a conta quebrada por acidente num
#: teste de teto alto, e todo numero reportado e' em R$ absolutos.
CAPITAL_NOCIONAL = 1_000_000.0

#: Teto usado nos testes, com FOLGA deliberada sobre o oficial de 2025 (WIN
#: 15 / WDO 5). Decisao do dono: "o maximo e' bonus -- se for bom com 4 vai
#: ser melhor com 5". Calibrar no teto exato faria o desenho depender de um
#: numero que pode mudar antes de 14/09/2026.
TETO_DE_TESTE = {"WIN@": 12, "WDO@": 4}

#: Minimo de barras para uma sessao contar. Medido: 1 pregao do WIN tem 325
#: barras (meia sessao) e 1 do WDO tem 142, contra ~565 tipicas -- meio pregao
#: nao e' um pregao, e deixa-lo dentro distorce qualquer media por dia.
MIN_BARRAS_POR_PREGAO = 400


@dataclass(frozen=True)
class Rodada:
    """Uma rodada medida: o resultado cru + o que so' a familia `copa`
    reporta."""

    rotulo: str
    resultado: object
    teto: int
    pedagio_ticks: float

    @property
    def liquido_brl(self) -> float:
        return sum(t.pnl_brl for t in self.resultado.trades)

    @property
    def recusas_pct(self) -> float:
        r = self.resultado
        total = r.ordens_aceitas + r.ordens_recusadas_por_teto
        return 100.0 * r.ordens_recusadas_por_teto / total if total else 0.0

    @property
    def diarios(self):
        return resultados_diarios(self.resultado.trades)

    @property
    def resumo(self):
        diarios = self.diarios
        return resumir_blocos(blocos_de_fase(diarios), diarios)

    def linha(self) -> LinhaResultado:
        """Linha da tabela PADRAO (12 colunas da base) + os `EXTRAS` desta
        familia. `bloco med` e `blocos+` aparecem ja no in-sample de
        proposito: e' a linguagem do portao de aceitacao (bloco de 4 pregoes,
        a fase real da competicao), e uma varredura que so' mostrasse o
        acumulado esconderia que o total veio de dois dias bons."""
        r = self.resumo
        return linha_de_resultado(
            self.rotulo, self.resultado, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={
                "teto": str(self.teto),
                "recusas%": num_br(self.recusas_pct, 1),
                "pedagio": num_br(self.pedagio_ticks, 1),
                "bloco med": num_br(r.liquido_mediano_brl, 0),
                "blocos+": f"{r.positivos}/{r.n_blocos}",
            },
        )


#: Colunas EXTRAS desta familia, na ordem -- entram depois das 12 da base.
#: `bloco med` = liquido MEDIANO de um bloco de 4 pregoes (a fase real da
#: competicao); `blocos+` = quantos desses blocos foram positivos.
EXTRAS = ("teto", "recusas%", "pedagio", "bloco med", "blocos+")


def _sessoes_completas(bars: pd.DataFrame) -> pd.DataFrame:
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return bars[[d in completos for d in bars.index.date]]


def barras(symbol: str) -> LockedBars:
    """Barras M1 do simbolo ja envolvidas no split CONGELADO do perfil.

    `.in_sample()` sempre disponivel; `.out_of_sample()` levanta ate alguem
    chamar `.unlock(motivo)` -- e' a trava estrutural do teste cego, nao uma
    convencao de nome de variavel."""
    df = load_m1(symbol)
    if df.empty:
        raise SystemExit(
            f"[copa] sem dado M1 salvo para {symbol!r} -- rode "
            f"`scripts/daytrade/backfill_m1.py --symbol {symbol}` primeiro."
        )
    profile = profile_for(symbol)
    df = _sessoes_completas(df.sort_index())
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    return LockedBars(df, split)


def config(symbol: str, teto: int, pedagio_ticks: float = 0.0,
           com_custo: bool = True, pernas_maker: int = 1) -> IntradayBacktestConfig:
    """Config do motor para o simbolo, com o TETO desta rodada.

    `com_custo=False` zera tarifa E slippage -- nao se sabe se o simulador da
    Copa cobra alguma coisa, entao todo relatorio mostra o par com/sem em vez
    de escolher uma das duas hipoteses e apresenta-la como a verdade.

    `pedagio_ticks` (portao G7): pedagio artificial de N ticks por perna
    MAKER, somado a tarifa. Um backtest em barra M1 nao enxerga posicao na
    fila -- ele assume que a ordem parada preencheu sempre que o preco tocou
    o nivel. Se o edge morre com 1 tick de pedagio, ele era ficcao de fila.
    `pernas_maker` vem da INSTANCIA do robo, nao da classe: `CopaWin` tem 1
    perna maker com entrada a mercado e 2 com `entrada_maker=True`, e cobrar o
    pedagio errado tornaria o portao G7 mais frouxo justamente na variante
    mais exposta a fila."""
    profile = profile_for(symbol)
    economia = _economia(symbol)
    cfg = config_for(
        profile,
        trade_tick_value=economia[0], trade_tick_size=economia[1],
        initial_capital=CAPITAL_NOCIONAL,
        target_fills_as_maker=True,
        max_open_contracts=teto,
    )
    custos = cfg.costs
    if not com_custo:
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=0.0, slippage_ticks=0.0,
            exchange_fee_pct_per_leg=0.0,
        )
    if pedagio_ticks:
        extra = pedagio_ticks * custos.tick_size * custos.point_value_brl * pernas_maker
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=custos.fee_round_trip_brl + extra,
            slippage_ticks=custos.slippage_ticks,
            exchange_fee_pct_per_leg=custos.exchange_fee_pct_per_leg,
        )
    return IntradayBacktestConfig(
        costs=custos,
        initial_capital=cfg.initial_capital,
        default_quantity=cfg.default_quantity,
        session_end_time=cfg.session_end_time,
        session_end_policy=cfg.session_end_policy,
        target_fills_as_maker=cfg.target_fills_as_maker,
        limit_fill_capped_by_volume=cfg.limit_fill_capped_by_volume,
        enforce_capital_minimo=cfg.enforce_capital_minimo,
        max_open_contracts=cfg.max_open_contracts,
    )


#: Economia lida do terminal UMA vez por processo. A serie continua reporta o
#: tick errado de proposito corrigido por `SymbolProfile.price_tick_size` (ver
#: `profiles.py`); o que vem daqui e' so' o valor do PONTO. Fallback declarado
#: para o script rodar sem o MT5 aberto (varredura em maquina sem terminal) --
#: os dois numeros sao propriedade do CONTRATO, nao cotacao, e estao medidos.
_ECONOMIA_CONHECIDA = {"WIN@": (0.2, 1.0), "WDO@": (0.01, 0.001)}
_economia_cache: dict[str, tuple[float, float]] = {}


def _economia(symbol: str) -> tuple[float, float]:
    if symbol in _economia_cache:
        return _economia_cache[symbol]
    valor = _ECONOMIA_CONHECIDA.get(symbol)
    try:
        from market_data_intraday.mt5_source import symbol_economics
        econ = symbol_economics(symbol)
        if econ is not None:
            valor = (econ.trade_tick_value, econ.trade_tick_size)
    except Exception:
        pass
    if valor is None:
        raise SystemExit(f"[copa] sem economia conhecida para {symbol!r} e terminal MT5 indisponivel.")
    _economia_cache[symbol] = valor
    return valor


def robo(symbol: str, teto: int, **params):
    """Instancia o robo do simbolo com o MESMO teto que vai para o motor.

    A economia (tick e valor do ponto) entra aqui vinda do perfil, nao de um
    default da classe: um robo com o tick errado arredonda o nivel para um
    preco que nao existe no book."""
    cfg = config(symbol, teto)
    return Copa(symbol=symbol, teto_contratos=teto,
                tick_size=cfg.costs.tick_size,
                point_value_brl=cfg.costs.point_value_brl,
                **params)


def rodar(symbol: str, bars: pd.DataFrame, teto: int, rotulo: str,
          pedagio_ticks: float = 0.0, com_custo: bool = True, **params) -> Rodada:
    """Uma rodada completa: monta robo + config com o MESMO teto, roda o
    motor, devolve `Rodada` (o resultado cru mais o que a familia reporta)."""
    instancia = robo(symbol, teto, **params)
    cfg = config(symbol, teto, pedagio_ticks=pedagio_ticks, com_custo=com_custo,
                 pernas_maker=int(getattr(instancia, "pernas_maker", 1)))
    resultado = run_intraday_backtest(bars, instancia, cfg)
    return Rodada(rotulo=rotulo, resultado=resultado, teto=teto,
                  pedagio_ticks=pedagio_ticks)


def descreve_janela(bars: pd.DataFrame) -> str:
    pregoes = len(set(bars.index.date))
    return (f"{len(bars)} barras M1, {pregoes} pregoes, "
            f"{bars.index.min():%Y-%m-%d} -> {bars.index.max():%Y-%m-%d}")
