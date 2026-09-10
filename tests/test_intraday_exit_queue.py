"""Fila do lado da SAIDA (`exit_queue_ahead_qty`), arme no FILL
(`exit_arms_at_fill`) e o custo da fatia que estoura o prazo -- os tres
nasceram em 2026-09-09, no primeiro dia do T2/S6 com dinheiro real.

O numero que forcou tudo: 7 saidas por alvo num pregao, UMA preencheu como
ordem-limite e seis estouraram `exit_ttl_bars` e sairam a mercado. O backtest
da mesma geometria previa +R$36,00 no dia; o dia deu -R$14,00. O motor nao
tinha nenhum modelo de fila do lado da saida -- bastava o preco TOCAR o nivel
e haver volume na barra para a fatia preencher -- e a fatia que estourava o
prazo ainda por cima saia a preco de MAKER, sem pagar o tick que uma saida a
mercado paga.

Os tres defaults preservam o motor antigo (`exit_queue_ahead_qty=0.0`,
`exit_arms_at_fill=False`, `timed_out=False`), e o primeiro teste daqui e'
exatamente esse invariante: sem ligar nada, nada muda.
"""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from backtest.intraday.costs import IntradayCostModel
from backtest.intraday.machine import (
    IntradayBacktestConfig,
    IntradaySessionMachine,
    PositionClosed,
)
from core.models import IntradayExitReason
from strategy.daytrade.base import Bar, EnterLimit, IntradayStrategy

#: Alvo e stop das entradas destes testes. Grade de 0,01 para a aritmetica
#: caber na cabeca; o que se mede aqui e' mecanica de fila, nao geometria.
LIMITE, ALVO, STOP = 10.00, 10.02, 9.94


def _bar(minute: int, o, h, low, c, volume: float = 0.0) -> Bar:
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC") + pd.Timedelta(minutes=minute)
    return Bar(ts=ts, open=float(o), high=float(h), low=float(low),
               close=float(c), volume=float(volume))


def _config(**over) -> IntradayBacktestConfig:
    base = dict(
        costs=IntradayCostModel(point_value_brl=1.0, tick_size=0.01,
                                fee_round_trip_brl=0.0, slippage_ticks=1.0),
        initial_capital=1_000.0,  # mecanica de fila; valor sem significado economico
        session_end_time=time(23, 59),
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
        default_quantity=1,
    )
    base.update(over)
    return IntradayBacktestConfig(**base)


class _UmaEntradaFatiada(IntradayStrategy):
    """Manda UMA `EnterLimit` com saida fatiada na barra 0 e cala a boca.

    Fatia de 1 contrato com prazo declarado -- e' o unico caminho que chega em
    `_resolve_simulated_split_exit`, que e' o que estes testes exercitam."""

    name = "uma_entrada_fatiada"
    version = "1"
    symbol = "TEST"

    def __init__(self, ttl: int = 3):
        self.ttl = ttl
        self._i = -1

    def on_session_start(self, session_date) -> None:
        self._i = -1

    def on_bar(self, ts, bar, position, session_pnl_brl):
        self._i += 1
        if self._i == 0:
            return [EnterLimit(side="long", limit_price=LIMITE,
                               initial_target=ALVO, initial_stop=STOP,
                               exit_split_unit=1, exit_ttl_bars=self.ttl)]
        return []


def _abre_posicao(m: IntradaySessionMachine, strat: _UmaEntradaFatiada) -> None:
    """Barra 0 posiciona a ordem; barra 1 preenche ela (toca o limite com
    volume de sobra). Depois disso ha' exatamente 1 posicao aberta."""
    m.begin_session(pd.Timestamp("2026-01-05").date())
    m.on_closed_bar(_bar(0, 10.10, 10.10, 10.05, 10.08, volume=50))
    m.on_closed_bar(_bar(1, 10.05, 10.05, 9.99, 10.01, volume=50))
    assert len(m.positions) == 1, "a entrada tinha de ter preenchido na barra 1"


def _fechamentos(eventos) -> list[PositionClosed]:
    return [e for e in eventos if isinstance(e, PositionClosed)]


# ---------- o default nao muda nada ----------------------------------------

def test_sem_fila_declarada_a_fatia_preenche_no_toque_seguinte_como_antes():
    """`exit_queue_ahead_qty=0.0` e `exit_arms_at_fill=False` sao os defaults,
    e com eles o motor tem de se comportar exatamente como antes de 2026-09-09:
    arma no primeiro toque do alvo, preenche no PROXIMO toque com volume.

    E' o teste que protege todas as medicoes ja feitas: se este quebrar, os
    numeros historicos deixaram de ser comparaveis com os novos."""
    strat = _UmaEntradaFatiada()
    m = IntradaySessionMachine(strat, _config())
    _abre_posicao(m, strat)

    # toque 1: ARMA a fatia, nao preenche (atraso estrutural de 1 barra)
    evs = m.on_closed_bar(_bar(2, 10.01, ALVO, 10.00, 10.01, volume=50))
    assert _fechamentos(evs) == []
    assert m.positions[0].exit_resting_qty == 1

    # toque 2: preenche no NIVEL do alvo
    evs = m.on_closed_bar(_bar(3, 10.01, ALVO, 10.00, 10.01, volume=50))
    fechados = _fechamentos(evs)
    assert len(fechados) == 1
    assert fechados[0].trade.exit_reason == IntradayExitReason.TARGET
    assert fechados[0].trade.exit_price == ALVO
    assert m.positions == []


# ---------- a fila do nivel ------------------------------------------------

def test_fila_a_frente_segura_a_fatia_ate_o_volume_no_nivel_consumir_ela():
    """Com Q=100 na frente, os 40 contratos negociados no primeiro toque e os
    50 do segundo NAO alcancam a fatia; o terceiro toque, que zera a fila e
    ainda sobra volume, preenche.

    E' a diferenca entre "o preco tocou o meu nivel" e "negociaram COMIGO" --
    a mesma que `queue_ahead_qty` corrigiu do lado da entrada em 2026-08-26."""
    strat = _UmaEntradaFatiada(ttl=99)  # prazo longo: aqui quem decide e' a fila
    m = IntradaySessionMachine(strat, _config(exit_queue_ahead_qty=100.0))
    _abre_posicao(m, strat)

    m.on_closed_bar(_bar(2, 10.01, ALVO, 10.00, 10.01, volume=40))  # arma
    pos = m.positions[0]
    assert pos.exit_resting_qty == 1
    assert pos.exit_queue_ahead_remaining == 100.0, "a fila comeca cheia no arme"

    evs = m.on_closed_bar(_bar(3, 10.01, ALVO, 10.00, 10.01, volume=40))
    assert _fechamentos(evs) == []
    assert m.positions[0].exit_queue_ahead_remaining == 60.0

    evs = m.on_closed_bar(_bar(4, 10.01, ALVO, 10.00, 10.01, volume=50))
    assert _fechamentos(evs) == [], "ainda ha 10 na frente"
    assert m.positions[0].exit_queue_ahead_remaining == 10.0

    # 10 zeram a fila, sobra 30 -- mais que suficiente para a fatia de 1
    evs = m.on_closed_bar(_bar(5, 10.01, ALVO, 10.00, 10.01, volume=40))
    fechados = _fechamentos(evs)
    assert len(fechados) == 1 and fechados[0].trade.exit_price == ALVO


def test_volume_de_barra_que_nao_toca_o_alvo_nao_anda_na_fila():
    """Por identidade: se o preco nao chegou no nivel, ninguem negociou NO
    nivel, e a fila la' nao andou um contrato sequer.

    E' o erro que a medicao de 2026-09-09 quase cometeu -- supor que chegar
    cedo faz a fila ANDAR. Chegar cedo compra tempo DEPOIS que o preco
    chega; nao adianta a fila antes disso."""
    strat = _UmaEntradaFatiada(ttl=99)
    m = IntradaySessionMachine(strat, _config(exit_queue_ahead_qty=50.0))
    _abre_posicao(m, strat)

    m.on_closed_bar(_bar(2, 10.01, ALVO, 10.00, 10.01, volume=10))  # arma
    assert m.positions[0].exit_queue_ahead_remaining == 50.0

    # barras com MUITO volume, longe do alvo
    for minuto in (3, 4, 5):
        evs = m.on_closed_bar(_bar(minuto, 10.00, 10.00, 9.98, 9.99, volume=10_000))
        assert _fechamentos(evs) == []
    assert m.positions[0].exit_queue_ahead_remaining == 50.0


# ---------- arme no fill ---------------------------------------------------

def test_arme_no_fill_preenche_no_PRIMEIRO_toque_que_o_arme_no_toque_perde():
    """A mecanica que esta rodada existe para avaliar: com a fatia ja parada
    no book desde o fill da entrada, a PROPRIA barra que toca o alvo pode
    preencher. Armando no toque, essa barra e' gasta so' para armar.

    As duas maquinas veem exatamente as mesmas barras."""
    barras = [_bar(2, 10.01, ALVO, 10.00, 10.01, volume=50)]

    no_toque = IntradaySessionMachine(_UmaEntradaFatiada(), _config())
    _abre_posicao(no_toque, no_toque.strategy)
    no_fill = IntradaySessionMachine(_UmaEntradaFatiada(),
                                     _config(exit_arms_at_fill=True))
    _abre_posicao(no_fill, no_fill.strategy)

    for bar in barras:
        evs_toque = no_toque.on_closed_bar(bar)
        evs_fill = no_fill.on_closed_bar(bar)

    assert _fechamentos(evs_toque) == []
    assert len(no_toque.positions) == 1
    fechados = _fechamentos(evs_fill)
    assert len(fechados) == 1 and fechados[0].trade.exit_price == ALVO
    assert no_fill.positions == []


def test_arme_no_fill_nao_deixa_o_prazo_correr_antes_do_preco_chegar():
    """`exit_ttl_bars` foi calibrado como "quanto espero NO NIVEL". Se o
    relogio comecasse no fill da entrada, o alvo viraria um time-stop: a
    posicao fecharia a mercado sem o preco nunca ter chegado perto, e a
    rodada estaria medindo DUAS mudancas de uma vez.

    Aqui o prazo e' 3 barras e passam 5 sem tocar o alvo -- nada fecha."""
    strat = _UmaEntradaFatiada(ttl=3)
    m = IntradaySessionMachine(strat, _config(exit_arms_at_fill=True))
    _abre_posicao(m, strat)

    for minuto in range(2, 7):
        evs = m.on_closed_bar(_bar(minuto, 10.00, 10.01, 9.99, 10.00, volume=50))
        assert _fechamentos(evs) == [], f"fechou na barra {minuto} sem tocar o alvo"
    pos = m.positions[0]
    assert pos.exit_resting_qty == 1, "a fatia continua parada no book"
    assert pos.resting_exit_bars_waited == 0, "o prazo nem comecou"
    assert pos.exit_touched_once is False


# ---------- a fatia que estoura o prazo E' uma saida a mercado -------------

def test_fatia_que_estoura_o_prazo_paga_slippage_e_fica_marcada():
    """Ela carimba `TARGET` (o gatilho foi o alvo), mas nao preencheu no
    nivel: o motor cancela a limite e fecha a MERCADO. Ate 2026-09-09 caia no
    ramo maker e saia exatamente no fechamento da barra, de graca.

    Custo de esconder isso: ao vivo, 6 das 7 saidas por alvo do dia foram por
    esse caminho -- ou seja, o backtest precificava como maker justamente a
    saida que quase sempre acontece."""
    strat = _UmaEntradaFatiada(ttl=2)
    m = IntradaySessionMachine(strat, _config(exit_queue_ahead_qty=10_000.0))
    _abre_posicao(m, strat)

    m.on_closed_bar(_bar(2, 10.01, ALVO, 10.00, 10.01, volume=1))  # arma, toca
    m.on_closed_bar(_bar(3, 10.01, ALVO, 10.00, 10.01, volume=1))  # espera 1
    evs = m.on_closed_bar(_bar(4, 10.01, ALVO, 10.00, 10.005, volume=1))  # estoura

    fechados = _fechamentos(evs)
    assert len(fechados) == 1
    assert fechados[0].trade.exit_reason == IntradayExitReason.TARGET
    # Saida de um LONG e' venda: o slippage de 1 tick sai ABAIXO do fechamento
    # da barra (10,005 - 0,01), nao no proprio fechamento.
    assert fechados[0].trade.exit_price == pytest.approx(9.995)

    trade = _fechamentos(evs)[0].trade
    assert trade.exit_detail == "target_timeout"
    assert trade.slippage_total > 0.0


def test_saida_por_alvo_que_preencheu_de_verdade_nao_e_marcada_como_prazo():
    """O contrapositivo do teste acima -- sem ele `exit_detail` poderia estar
    sempre preenchido e o teste anterior passaria por acidente."""
    strat = _UmaEntradaFatiada()
    m = IntradaySessionMachine(strat, _config())
    _abre_posicao(m, strat)
    m.on_closed_bar(_bar(2, 10.01, ALVO, 10.00, 10.01, volume=50))
    evs = m.on_closed_bar(_bar(3, 10.01, ALVO, 10.00, 10.01, volume=50))

    trade = _fechamentos(evs)[0].trade
    assert trade.exit_reason == IntradayExitReason.TARGET
    assert trade.exit_detail is None
    assert trade.exit_price == ALVO
    assert trade.slippage_total == 0.0


# ---------- reinicio -------------------------------------------------------

def test_fila_e_o_ja_tocou_sobrevivem_a_um_state_restore():
    """Sem persistir os dois, um restart devolveria a fatia ao book com a fila
    ZERADA (preenchimento instantaneo no proximo toque) e com o prazo correndo
    desde ja -- as duas coisas favoraveis, que e' o sinal de erro perigoso."""
    strat = _UmaEntradaFatiada(ttl=99)
    m = IntradaySessionMachine(strat, _config(exit_queue_ahead_qty=100.0))
    _abre_posicao(m, strat)
    m.on_closed_bar(_bar(2, 10.01, ALVO, 10.00, 10.01, volume=30))  # arma
    m.on_closed_bar(_bar(3, 10.01, ALVO, 10.00, 10.01, volume=30))  # come 30

    estado = m.state()
    outra = IntradaySessionMachine(_UmaEntradaFatiada(ttl=99),
                                   _config(exit_queue_ahead_qty=100.0))
    outra.restore(estado)

    pos = outra.positions[0]
    assert pos.exit_resting_qty == 1
    assert pos.exit_queue_ahead_remaining == 70.0
    assert pos.exit_touched_once is True


def test_stop_desarma_a_fatia_inteira_inclusive_a_fila():
    """Deixar `exit_queue_ahead_remaining` para tras faria a PROXIMA fatia
    herdar uma fila ja cortada que ela nunca esperou -- otimismo silencioso,
    o pior tipo."""
    strat = _UmaEntradaFatiada(ttl=99)
    m = IntradaySessionMachine(strat, _config(exit_queue_ahead_qty=100.0))
    _abre_posicao(m, strat)
    m.on_closed_bar(_bar(2, 10.01, ALVO, 10.00, 10.01, volume=30))  # arma
    m.on_closed_bar(_bar(3, 10.01, ALVO, 10.00, 10.01, volume=30))  # come 30
    assert m.positions[0].exit_queue_ahead_remaining == 70.0

    evs = m.on_closed_bar(_bar(4, 10.00, 10.00, STOP, STOP, volume=30))
    fechados = _fechamentos(evs)
    assert len(fechados) == 1 and fechados[0].trade.exit_reason == IntradayExitReason.STOP
    assert m.positions == []
