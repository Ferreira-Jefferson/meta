"""Smoke test de `WdoGridFadeOffT3` (AGENTS.md: regra de estrategia em
`strategy/` -> teste com cenario sintetico) -- so' confere que os defaults de
producao da variante `combo_T3` (2026-09-11, ver a docstring do modulo)
instanciam corretamente e que o filtro de regime `fade_off`/20min remove o
lado certo dos candidatos quando o retorno acumulado ultrapassa o limiar.
Nao recria o experimento inteiro (19 pregoes de tick real) -- isso mora em
`scripts/daytrade/wdof1_regime_alvo_combinado_2026_09_11.py`."""
from __future__ import annotations

import pandas as pd
import pytest

from core.instruments import economics_for
from strategy.daytrade.base import Bar
from strategy.daytrade.lab.wdo_grid_fade_off_t3 import (
    JANELA_REGIME_MINUTOS,
    LIMIAR_REGIME_TICKS,
    WdoGridFadeOffT3,
)
from strategy.daytrade.lab.wdo_grid_reload_maker import EXIT_TTL_BARS_SEM_PRAZO


def test_defaults_replicam_a_geometria_combo_t3():
    strat = WdoGridFadeOffT3()

    assert strat.name == "wdo_grid_fade_off_t3"
    assert strat.symbol == "WDO@"
    assert strat.profit_ticks == 3          # T3
    assert strat.stop_ticks == 16           # S16, intacto
    assert strat.fatiar_saida_alvo is True
    assert strat.exit_ttl_bars == EXIT_TTL_BARS_SEM_PRAZO
    assert strat.hard_cap_contratos == 5
    assert strat.risco_pct_por_trade == pytest.approx(0.01)
    assert strat.margin_per_contract_brl == pytest.approx(
        economics_for("WDO@").margin_per_contract_brl
    )
    assert strat.point_value_brl == pytest.approx(
        economics_for("WDO@").point_value_brl
    )
    # Propriedades herdadas de `WdoGridReloadMaker` que a variante nao muda.
    assert strat.target_fills_as_maker is True
    assert strat.anchor_exits_at_fill is True
    assert strat.feed_kind == "tick"
    assert strat.is_futuro is True


def test_primeira_ordem_sem_regime_reproduz_alternancia_normal():
    """Janela de regime ainda vazia (primeiro tick do pregao) -> `None`,
    tratado como neutro -- comportamento IDENTICO ao da classe base."""
    strat = WdoGridFadeOffT3(tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    bar = Bar(ts=ts, open=5000.0, high=5000.0, low=5000.0, close=5000.0, volume=1)

    actions = strat.on_bar(ts, bar, positions=[], session_pnl_brl=0.0)

    assert len(actions) == 1
    assert actions[0].side == "long"  # alternancia normal: long primeiro
    assert actions[0].limit_price == pytest.approx(4999.5)              # 1 tick abaixo da abertura
    assert actions[0].initial_target == pytest.approx(4999.5 + 3 * 0.5)  # T3
    assert actions[0].initial_stop == pytest.approx(4999.5 - 16 * 0.5)   # S16


def test_regime_up_forte_remove_o_lado_short_dos_candidatos():
    """Alta sustentada de mais de `LIMIAR_REGIME_TICKS` ticks nos ultimos
    `JANELA_REGIME_MINUTOS` minutos -> `_next_side_to_arm` nunca devolve
    'short' (o lado que fadaria a alta), mesmo comecando de um estado em que
    a alternancia normal escolheria short."""
    strat = WdoGridFadeOffT3(tick_size=0.5)
    strat.on_session_start(None)
    inicio = pd.Timestamp("2026-01-05 13:00", tz="UTC")

    # Alimenta a janela com um preco antigo (ha' quase 20min) BEM abaixo do
    # atual -- retorno positivo grande o bastante para passar do limiar.
    subida_ticks = LIMIAR_REGIME_TICKS + 5
    preco_antigo = 5000.0
    preco_atual = preco_antigo + subida_ticks * 0.5
    strat._registrar_regime(inicio, preco_antigo)
    ts_agora = inicio + pd.Timedelta(minutes=JANELA_REGIME_MINUTOS - 1)
    strat._registrar_regime(ts_agora, preco_atual)

    assert strat._regime_atual() == "up"
    # Forca o estado a preferir 'short' primeiro (mesmo criterio de
    # alternancia da classe base: comeca pelo lado que NAO fechou por
    # ultimo) -- ainda assim o filtro tem que vetar 'short'.
    strat._state.last_closed_side = "long"
    lado = strat._next_side_to_arm()
    assert lado == "long"
    assert strat.regime_contagem["up"] >= 1


def test_regime_neutro_preserva_alternancia_normal():
    strat = WdoGridFadeOffT3(tick_size=0.5)
    strat.on_session_start(None)
    ts = pd.Timestamp("2026-01-05 13:00", tz="UTC")
    strat._registrar_regime(ts, 5000.0)  # sem variacao -> retorno 0, neutro

    assert strat._regime_atual() == "neutral"
    strat._state.last_closed_side = "long"
    assert strat._next_side_to_arm() == "short"  # alternancia normal, sem veto
