"""Cenarios sinteticos para as regras de universo dos robos liquidos.

AGENTS.md: "toda regra de saida/entrada em `strategy/` -> teste com cenario
sintetico". As regras novas aqui sao tres — quem entra no universo (liquidez
point-in-time), quem continua nele (banda de rank) e o que acontece com a
posicao de quem saiu (despejo x grandfathering) — mais a aritmetica de
`size_hint`, que e onde um erro passa despercebido por anos porque nao quebra
nada: so dimensiona errado.

Dado sintetico e nao fixture de mercado de proposito: com liquidez inventada da
para afirmar QUEM deveria ser escolhido e falhar quando nao for. Com dado real,
o teste so consegue dizer que algo foi escolhido.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.config import BENCHMARK
from strategy.base import Enter, Exit, OpenPosition
from strategy.liquid_flow import LiquidFlowSleeve
from strategy.liquid_sleeve import LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5

DAYS = 900
IDX = pd.bdate_range("2015-01-01", periods=DAYS)


def make_panel(price: float, volume: float, start: int = 0) -> pd.DataFrame:
    """Painel plano: preco constante, volume constante, opcionalmente atrasado."""
    close = pd.Series(float(price), index=IDX)
    vol = pd.Series(float(volume), index=IDX)
    if start:
        close.iloc[:start] = np.nan
        vol.iloc[:start] = np.nan
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": vol})
    return df.dropna()


def panels_by_turnover(turnovers: dict[str, float]) -> dict[str, pd.DataFrame]:
    u = {t: make_panel(10.0, tv / 10.0) for t, tv in turnovers.items()}
    u[BENCHMARK] = make_panel(100.0, 1.0)
    return u


def ibov_of(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return panels[BENCHMARK]


def sleeve(**kw) -> LiquidSleeve:
    kw.setdefault("liquidity_window", 60)
    kw.setdefault("min_history_days", 100)
    kw.setdefault("universe_n", 4)
    kw.setdefault("sleeve_count", 2)
    return LiquidSleeve(**kw)


# ------------------------------------------------------------------ universo


def test_universo_pega_os_mais_liquidos_e_ignora_o_resto():
    panels = panels_by_turnover({f"T{i}.SA": 1000.0 * (10 - i) for i in range(8)})
    s = sleeve(sleeve_index=0, sleeve_count=1, universe_n=4)
    s.initialize(panels, ibov_of(panels))
    d = IDX[-1]
    elegiveis = {t for t in panels if t != BENCHMARK and s.is_eligible(t, d)}
    assert elegiveis == {"T0.SA", "T1.SA", "T2.SA", "T3.SA"}


def test_benchmark_nunca_entra_no_universo():
    panels = panels_by_turnover({f"T{i}.SA": 100.0 for i in range(3)})
    s = sleeve(sleeve_index=0, sleeve_count=1, universe_n=10)
    s.initialize(panels, ibov_of(panels))
    assert not s.is_eligible(BENCHMARK, IDX[-1])


def test_sleeves_sao_disjuntos_e_cobrem_o_universo():
    panels = panels_by_turnover({f"T{i}.SA": 1000.0 * (10 - i) for i in range(8)})
    d = IDX[-1]
    vistos: list[set[str]] = []
    for i in range(2):
        s = sleeve(sleeve_index=i, sleeve_count=2, universe_n=4)
        s.initialize(panels, ibov_of(panels))
        vistos.append({t for t in panels if t != BENCHMARK and s.is_eligible(t, d)})
    assert vistos[0] & vistos[1] == set(), "um papel nao pode estar em dois sleeves"
    assert vistos[0] | vistos[1] == {"T0.SA", "T1.SA", "T2.SA", "T3.SA"}


def test_sem_look_ahead_papel_ilikido_no_passado_nao_e_elegivel_no_passado():
    """O papel so vira liquido na metade da serie; antes disso nao pode ser escolhido."""
    tv = pd.Series(1.0, index=IDX)
    tv.iloc[DAYS // 2:] = 10_000_000.0
    novo = pd.DataFrame({"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
                         "volume": tv / 10.0}, index=IDX)
    panels = panels_by_turnover({f"T{i}.SA": 5000.0 for i in range(4)})
    panels["NOVO.SA"] = novo

    s = sleeve(sleeve_index=0, sleeve_count=1, universe_n=2)
    s.initialize(panels, ibov_of(panels))
    antes, depois = IDX[DAYS // 2 - 5], IDX[-1]
    assert not s.is_eligible("NOVO.SA", antes), "usou liquidez que ainda nao existia"
    assert s.is_eligible("NOVO.SA", depois)


def test_historico_minimo_barra_papel_recem_listado():
    panels = panels_by_turnover({f"T{i}.SA": 100.0 for i in range(3)})
    panels["NOVO.SA"] = make_panel(10.0, 1e9, start=DAYS - 30)  # o mais liquido de todos
    s = sleeve(sleeve_index=0, sleeve_count=1, universe_n=4, min_history_days=200)
    s.initialize(panels, ibov_of(panels))
    assert not s.is_eligible("NOVO.SA", IDX[-1]), "entrou sem historico para o momentum 12-1"


# -------------------------------------------------------------- banda de rank


def test_banda_de_rank_segura_papel_que_so_oscilou():
    """Cai da 4a para a 5a posicao com universe_n=4 e exit_rank=6: continua dentro."""
    base = {f"T{i}.SA": 1000.0 * (10 - i) for i in range(8)}
    panels = panels_by_turnover(base)
    # T3 perde liquidez no meio, o suficiente para sair do top-4 mas nao do top-6.
    tv = pd.Series(7000.0, index=IDX)
    tv.iloc[DAYS // 2:] = 5500.0  # fica entre T4 (6000) e T5 (5000)
    panels["T3.SA"] = pd.DataFrame({"open": 10.0, "high": 10.0, "low": 10.0,
                                    "close": 10.0, "volume": tv / 10.0}, index=IDX)

    s = LiquidFlowSleeve(sleeve_index=0, sleeve_count=1, universe_n=4, exit_rank=6,
                         liquidity_window=60, min_history_days=100)
    s.initialize(panels, ibov_of(panels))
    assert s.is_eligible("T3.SA", IDX[-1]), "banda de rank nao segurou o papel"


def test_banda_de_rank_expulsa_quem_afundou():
    base = {f"T{i}.SA": 1000.0 * (10 - i) for i in range(8)}
    panels = panels_by_turnover(base)
    tv = pd.Series(7000.0, index=IDX)
    tv.iloc[DAYS // 2:] = 10.0  # afunda para o ultimo lugar
    panels["T3.SA"] = pd.DataFrame({"open": 10.0, "high": 10.0, "low": 10.0,
                                    "close": 10.0, "volume": tv / 10.0}, index=IDX)

    s = LiquidFlowSleeve(sleeve_index=0, sleeve_count=1, universe_n=4, exit_rank=6,
                         liquidity_window=60, min_history_days=100)
    s.initialize(panels, ibov_of(panels))
    assert not s.is_eligible("T3.SA", IDX[-1])


# ------------------------------------------------------- despejo x grandfather


def held(ticker: str) -> dict[str, OpenPosition]:
    return {ticker: OpenPosition(ticker=ticker, entry_date=IDX[0], entry_price=10.0,
                                 quantity=10, current_stop=None, bars_held=1)}


def _sleeve_com_posicao_fora_do_universo(evict: bool) -> tuple[LiquidSleeve, str]:
    panels = panels_by_turnover({f"T{i}.SA": 1000.0 * (10 - i) for i in range(8)})
    s = sleeve(sleeve_index=0, sleeve_count=1, universe_n=2, evict_on_refresh=evict)
    s.initialize(panels, ibov_of(panels))
    fora = "T7.SA"
    assert not s.is_eligible(fora, IDX[-1])
    return s, fora


def test_despejo_ligado_manda_sair_no_mesmo_dia():
    s, fora = _sleeve_com_posicao_fora_do_universo(True)
    acoes = s.on_bar(IDX[-1], held(fora), 0.0)
    assert [a.ticker for a in acoes if isinstance(a, Exit)] == [fora]


def test_grandfathering_nao_vende_por_calendario():
    """Sem despejo, sair do universo nao e por si so motivo de venda."""
    s, fora = _sleeve_com_posicao_fora_do_universo(False)
    acoes = s.on_bar(IDX[-1], held(fora), 0.0)
    assert not [a for a in acoes if isinstance(a, Exit) and a.ticker == fora]


def test_grandfathering_devolve_o_score_mascarado_depois_de_decidir():
    """O score real e emprestado so durante a decisao — nao pode vazar depois.

    Se vazasse, o papel voltaria a concorrer como se ainda estivesse no universo
    e o filtro de liquidez teria deixado de existir a partir da primeira posicao
    herdada.
    """
    s, fora = _sleeve_com_posicao_fora_do_universo(False)
    antes = s._scores[fora].copy()
    s.on_bar(IDX[-1], held(fora), 0.0)
    pd.testing.assert_series_equal(s._scores[fora], antes)


# ------------------------------------------------------------------- sizing


class _FakeSleeve:
    """Sleeve de mentira: devolve exatamente as acoes que o teste mandar."""

    def __init__(self, acoes):
        self._acoes = acoes
        self._pending_rebalance = False

    def initialize(self, panels, ibov):
        pass

    def is_eligible(self, ticker, date):
        return False

    def on_bar(self, date, open_positions, cash_available):
        return list(self._acoes)


@pytest.mark.parametrize("n_entradas,n_posicoes,esperado", [
    (5, 0, [1 / 5, 1 / 4, 1 / 3, 1 / 2, 1.0]),   # carteira vazia: 20% cada
    (1, 4, [1.0]),                               # 4 sleeves parados, 1 entra
    (2, 0, [1 / 5, 1 / 4]),                      # 3 sleeves sem sinal guardam a fatia
])
def test_size_hint_divide_o_caixa_em_fatias_iguais(n_entradas, n_posicoes, esperado):
    """`size_hint` e fracao do CAIXA, e o caixa encolhe a cada compra.

    O caso (2, 0) e o que importa: dois sleeves entrando com a carteira vazia
    NAO podem levar metade do capital cada — os outros tres nao acharam sinal,
    mas o dinheiro continua sendo deles.
    """
    bot = LiquidSleeves5.__new__(LiquidSleeves5)
    bot.sleeve_count = 5
    bot._owner = {}
    bot._sleeves = [_FakeSleeve([]) for _ in range(5)]
    for i in range(n_entradas):
        bot._sleeves[i] = _FakeSleeve([Enter(ticker=f"E{i}.SA", size_hint=1.0)])

    posicoes = {f"P{i}.SA": OpenPosition(ticker=f"P{i}.SA", entry_date=IDX[0],
                                         entry_price=10.0, quantity=1,
                                         current_stop=None, bars_held=1)
                for i in range(n_posicoes)}
    # As posicoes abertas pertencem aos sleeves que NAO estao entrando.
    bot._owner = {f"P{i}.SA": n_entradas + i for i in range(n_posicoes)}

    acoes = bot.on_bar(IDX[-1], posicoes, 1000.0)
    hints = [a.size_hint for a in acoes if isinstance(a, Enter)]
    assert hints == pytest.approx(esperado)


def test_size_hint_soma_um_capital_inteiro_quando_todos_entram():
    """As cinco fatias tem de consumir exatamente o caixa, sem sobra nem estouro."""
    bot = LiquidSleeves5.__new__(LiquidSleeves5)
    bot.sleeve_count = 5
    bot._owner = {}
    bot._sleeves = [_FakeSleeve([Enter(ticker=f"E{i}.SA")]) for i in range(5)]
    acoes = bot.on_bar(IDX[-1], {}, 1000.0)

    caixa = 1000.0
    gasto = 0.0
    for a in acoes:
        if isinstance(a, Enter):
            fatia = caixa * a.size_hint
            gasto += fatia
            caixa -= fatia
    assert gasto == pytest.approx(1000.0)
    assert caixa == pytest.approx(0.0)


# -------------------------------------------------------------------- estado


def test_posse_sobrevive_a_restart():
    """`_owner` diz de qual sleeve e cada posicao — perde-lo remonta a carteira errado."""
    bot = LiquidSleeves5()
    bot._owner = {"WEGE3.SA": 3, "VALE3.SA": 0}
    bot._sleeves[2]._pending_rebalance = True

    novo = LiquidSleeves5()
    novo.restore(bot.state())

    assert novo._owner == {"WEGE3.SA": 3, "VALE3.SA": 0}
    assert [s._pending_rebalance for s in novo._sleeves] == [False, False, True, False, False]
