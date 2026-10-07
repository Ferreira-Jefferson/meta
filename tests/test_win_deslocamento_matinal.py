"""`strategy.daytrade.lab.win_deslocamento_matinal.WinDeslocamentoMatinal`.

Estrategia pura: os testes chamam `seed_daily_volatility`/`on_bar` direto, sem motor.
Protegem (1) o desenho de execucao fechado, (2) a regra do achado (deslocamento >= X ATR
as 10:30 sem ter cruzado a abertura), (3) ausencia de look-ahead (nada decide antes dos
90 min) e (4) o teto de stop por capital.
"""
from __future__ import annotations

import pandas as pd

from strategy.daytrade.base import Bar, Enter, EnterLimit
from strategy.daytrade.lab.win_deslocamento_matinal import (
    EXIT_TTL_BARS_SEM_PRAZO, WinDeslocamentoMatinal,
)

ABERTURA = pd.Timestamp("2026-03-02 12:00", tz="UTC")  # 09:00 BRT
ATR = 1_000.0
ABRE = 100_000.0


def _diarias(n: int = 16, vol: float = 1_000.0) -> list[Bar]:
    """n sessoes com range 1.000 e fechamento fixo: true range = 1.000 -> ATR14 = 1.000."""
    return [Bar(ts=ABERTURA - pd.Timedelta(days=n - i), open=ABRE, high=ABRE + 500,
                low=ABRE - 500, close=ABRE, volume=vol) for i in range(n)]


def _robo(**kw) -> WinDeslocamentoMatinal:
    r = WinDeslocamentoMatinal(**kw)
    r.on_session_start(ABERTURA.date())
    r.seed_daily_volatility(_diarias())
    return r


def _bar(minuto: int, close: float, o: float | None = None) -> Bar:
    return Bar(ts=ABERTURA + pd.Timedelta(minutes=minuto), open=ABRE if o is None else o,
               high=max(close, ABRE if o is None else o), low=min(close, ABRE if o is None else o),
               close=close, volume=100.0)


def _manha(robo, fechamentos: dict[int, float], ate: int = 89):
    """Alimenta minutos 0..ate; `fechamentos` sobrescreve o close de minutos especificos."""
    acao = []
    for m in range(ate + 1):
        b = _bar(m, fechamentos.get(m, ABRE + 100.0), o=ABRE if m == 0 else None)
        acao = robo.on_bar(b.ts, b, [], 0.0)
        if m < ate:
            assert acao == [], "nada decide antes dos 90 minutos"
    return acao


def test_desenho_de_execucao_entrada_limite_com_prazo_nunca_a_mercado():
    robo = _robo()
    (acao,) = _manha(robo, {89: ABRE + 400.0})
    assert isinstance(acao, EnterLimit) and not isinstance(acao, Enter)
    assert acao.side == "long"
    assert acao.ttl_bars == robo.entrada_ttl_bars == 15
    assert acao.limit_price == ABRE + 400.0
    assert acao.initial_target is None and acao.exit_split_unit is None
    assert robo.target_fills_as_maker and robo.anchor_exits_at_fill


def test_alvo_e_limite_fatiada_sem_prazo():
    robo = _robo(alvo_atr=0.30)
    (acao,) = _manha(robo, {89: ABRE + 400.0})
    assert acao.initial_target == ABRE + 400.0 + 0.30 * ATR
    assert acao.exit_split_unit == 1
    assert acao.exit_ttl_bars == EXIT_TTL_BARS_SEM_PRAZO


def test_stop_na_linha_da_abertura_com_banda():
    robo = _robo()
    (acao,) = _manha(robo, {89: ABRE + 400.0})
    # linha = abertura - 0,05 ATR
    assert acao.initial_stop == ABRE - 0.05 * ATR


def test_teto_do_stop_por_capital():
    robo = _robo(stop_atr=0.15)
    (acao,) = _manha(robo, {89: ABRE + 400.0})
    assert acao.limit_price - acao.initial_stop == 0.15 * ATR


def test_short_simetrico():
    robo = _robo()
    (acao,) = _manha(robo, {m: ABRE - 100.0 for m in range(0, 89)} | {89: ABRE - 400.0})
    assert acao.side == "short"
    assert acao.initial_stop == ABRE + 0.05 * ATR


def test_sem_sinal_abaixo_do_deslocamento_minimo():
    assert _manha(_robo(), {89: ABRE + 299.0}) == []


def test_sem_sinal_se_ja_fechou_do_outro_lado_da_abertura_alem_da_banda():
    # um fechamento 60 pts abaixo da abertura (> banda 0,05 ATR = 50) invalida o dia "limpo"
    assert _manha(_robo(), {30: ABRE - 60.0, 89: ABRE + 400.0}) == []
    # dentro da banda nao invalida
    assert len(_manha(_robo(), {30: ABRE - 40.0, 89: ABRE + 400.0})) == 1


def test_uma_decisao_por_pregao():
    robo = _robo()
    _manha(robo, {89: ABRE + 400.0})
    b = _bar(90, ABRE + 500.0)
    assert robo.on_bar(b.ts, b, [], 0.0) == []


def test_sem_atr_sem_historico_nao_opera():
    robo = WinDeslocamentoMatinal()
    robo.on_session_start(ABERTURA.date())
    robo.seed_daily_volatility(_diarias(14))   # 14 barras = 13 true ranges: insuficiente
    assert _manha(robo, {89: ABRE + 400.0}) == []


def test_atr_e_media_de_14_true_ranges_com_gap():
    robo = WinDeslocamentoMatinal()
    barras = _diarias(16)
    # o ultimo dia abriu em gap: true range usa o fechamento anterior
    ult = barras[-1]
    barras[-1] = Bar(ts=ult.ts, open=ABRE + 800, high=ABRE + 1_000, low=ABRE + 700, close=ABRE + 900, volume=1.0)
    robo.seed_daily_volatility(barras)
    # 13 TRs de 1.000 e um de max(300, 1.000, 700) = 1.000 -> ATR 1.000
    assert abs(robo._atr - 1_000.0) < 1e-9


def test_escala_volume_so_na_ablacao():
    base = _robo(stop_atr=0.25)
    assert base._escala == 1.0
    abl = WinDeslocamentoMatinal(stop_atr=0.25, escala_volume=True)
    abl.on_session_start(ABERTURA.date())
    d = _diarias(20)
    d[-1] = Bar(ts=d[-1].ts, open=ABRE, high=ABRE + 500, low=ABRE - 500, close=ABRE, volume=2_000.0)
    abl.seed_daily_volatility(d)
    assert 1.0 < abl._escala <= 1.25
