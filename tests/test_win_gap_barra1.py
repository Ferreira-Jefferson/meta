"""WinGapBarra1: gap a partir de barras, sinal so' com a barra 1 contra o gap, sem look-ahead, vencimento, flatten.

Paralelo-seguro: sem arquivo fixo (so' `tmp_path`), sem ordem entre testes, sem estado global.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from strategy.daytrade.base import AdjustStop, Bar, EnterLimit, Exit, IntradayOpenPosition
from strategy.daytrade.lab.win_gap_barra1 import (
    EXIT_TTL_BARS_SEM_PRAZO, WinGapBarra1, rolagem_entre, vencimento_do_mes,
)


def b(ts, o, h, l, c, v=1000.0):
    return Bar(ts=pd.Timestamp(ts), open=o, high=h, low=l, close=c, volume=v)


def dia_anterior(strat, dia="2026-05-04", call=100_000.0):
    """Alimenta o dia D-1 inteiro (so' a ultima barra importa: seu close e' o call)."""
    strat.on_session_start(pd.Timestamp(dia).date())
    strat.on_bar(pd.Timestamp(f"{dia} 09:00"), b(f"{dia} 09:00", 99_900, 100_100, 99_800, 99_950), [], 0.0)
    strat.on_bar(pd.Timestamp(f"{dia} 18:20"), b(f"{dia} 18:20", 99_950, 100_050, 99_900, call), [], 0.0)


def barra1(strat, dia, o, c, h=None, l=None):
    strat.on_session_start(pd.Timestamp(dia).date())
    h = max(o, c) + 50 if h is None else h
    l = min(o, c) - 50 if l is None else l
    return strat.on_bar(pd.Timestamp(f"{dia} 09:00"), b(f"{dia} 09:00", o, h, l, c), [], 0.0)


def test_gap_sai_so_de_barras_e_tem_o_sinal_certo():
    # gap = open da 1a barra de D (leilao) - close da ultima barra de D-1 (call)
    s = WinGapBarra1(stop_pts=700)
    dia_anterior(s, call=100_000.0)
    acoes = barra1(s, "2026-05-05", o=99_500, c=99_800)          # gap -500, barra de ALTA (contra o gap)
    assert len(acoes) == 1 and isinstance(acoes[0], EnterLimit) and acoes[0].side == "long"
    assert s._d.gap == pytest.approx(-500.0)
    s2 = WinGapBarra1(stop_pts=700)
    dia_anterior(s2, call=100_000.0)
    acoes = barra1(s2, "2026-05-05", o=100_400, c=100_100)       # gap +400, barra de BAIXA (contra o gap)
    assert acoes[0].side == "short" and s2._d.gap == pytest.approx(400.0)


@pytest.mark.parametrize("gap,o,c,espera", [
    (-500, 99_500, 99_800, "long"),    # gap baixa, barra alta  -> compra
    (-500, 99_500, 99_300, None),      # gap baixa, barra baixa -> a favor do gap: sem trade
    (500, 100_500, 100_200, "short"),  # gap alta, barra baixa  -> venda
    (500, 100_500, 100_800, None),     # gap alta, barra alta   -> sem trade
    (500, 100_500, 100_500, None),     # barra sem corpo        -> sem trade
])
def test_so_opera_se_a_barra_1_fecha_contra_o_gap(gap, o, c, espera):
    s = WinGapBarra1()
    dia_anterior(s, call=100_000.0)
    assert o - 100_000.0 == gap
    acoes = barra1(s, "2026-05-05", o=o, c=c)
    assert (acoes[0].side if acoes else None) == espera


def test_entrada_limite_no_close_com_prazo_stop_e_alvo_fatiado():
    s = WinGapBarra1(stop_pts=700, alvo_pts=1000)
    dia_anterior(s)
    o = barra1(s, "2026-05-05", o=99_500, c=99_800)[0]
    assert o.limit_price == 99_800 and o.initial_stop == 99_100 and o.initial_target == 100_800
    assert o.ttl_bars == 6 and o.exit_split_unit == 1 and o.exit_ttl_bars == EXIT_TTL_BARS_SEM_PRAZO
    assert WinGapBarra1.anchor_exits_at_fill and WinGapBarra1.target_fills_as_maker and WinGapBarra1.quantity_e_unidade
    s2 = WinGapBarra1(stop_pts=700)                                  # sem alvo: nada de fatia de saida
    dia_anterior(s2)
    o2 = barra1(s2, "2026-05-05", o=99_500, c=99_800)[0]
    assert o2.initial_target is None and o2.exit_split_unit is None
    with pytest.raises(ValueError):
        WinGapBarra1(ttl_barras=0)


def test_sem_look_ahead_a_decisao_so_depende_da_barra_1_e_do_passado():
    def decide(extra):
        s = WinGapBarra1()
        dia_anterior(s)
        acoes = barra1(s, "2026-05-05", o=99_500, c=99_800)
        # barras seguintes (futuro) so' chegam depois da decisao
        for k, (o, c) in enumerate(extra, start=1):
            ts = pd.Timestamp("2026-05-05 09:00") + pd.Timedelta(minutes=5 * k)
            s.on_bar(ts, b(ts, o, max(o, c) + 10, min(o, c) - 10, c), [], 0.0)
        return acoes
    a1 = decide([(99_800, 99_900)])
    a2 = decide([(99_800, 50_000), (50_000, 150_000)])
    assert (a1[0].side, a1[0].limit_price, a1[0].initial_stop) == (a2[0].side, a2[0].limit_price, a2[0].initial_stop)
    # e o call de D-1 e' o close da ULTIMA barra vista, nao uma barra de D
    s = WinGapBarra1()
    dia_anterior(s, call=100_000.0)
    s.on_session_start(dt.date(2026, 5, 5))
    s.on_bar(pd.Timestamp("2026-05-05 09:00"), b("2026-05-05 09:00", 99_500, 99_900, 99_450, 99_800), [], 0.0)
    assert s._d.gap == pytest.approx(-500.0)


def test_nao_opera_sem_dia_anterior_nem_com_abertura_atrasada():
    s = WinGapBarra1()
    assert barra1(s, "2026-05-05", o=99_500, c=99_800) == []        # sem call de D-1 visto
    s = WinGapBarra1()
    dia_anterior(s)
    s.on_session_start(dt.date(2026, 5, 5))
    ts = pd.Timestamp("2026-05-05 12:30")                            # 2026-07-31: abre as 12:34
    assert s.on_bar(ts, b(ts, 99_500, 99_900, 99_450, 99_800), [], 0.0) == []
    s = WinGapBarra1()
    dia_anterior(s, dia="2026-04-20")
    assert barra1(s, "2026-05-05", o=99_500, c=99_800) == []        # D-1 a mais de 5 dias


def test_vencimento_e_filtro_de_rolagem():
    assert vencimento_do_mes(2026, 4) == dt.date(2026, 4, 15)
    assert vencimento_do_mes(2026, 6) == dt.date(2026, 6, 17)
    assert vencimento_do_mes(2026, 8) == dt.date(2026, 8, 12)
    assert vencimento_do_mes(2025, 12) == dt.date(2025, 12, 17)
    assert rolagem_entre(dt.date(2026, 8, 11), dt.date(2026, 8, 12))       # o proprio dia do vencimento
    assert not rolagem_entre(dt.date(2026, 8, 12), dt.date(2026, 8, 13))   # o dia seguinte e' normal
    assert rolagem_entre(dt.date(2026, 8, 11), dt.date(2026, 8, 13))       # vencimento em feriado: 1a sessao depois
    s = WinGapBarra1()
    dia_anterior(s, dia="2026-08-11")
    assert barra1(s, "2026-08-12", o=99_500, c=99_800) == []               # gap de rolagem: sem sinal
    s = WinGapBarra1(evitar_vencimento=False)
    dia_anterior(s, dia="2026-08-11")
    assert len(barra1(s, "2026-08-12", o=99_500, c=99_800)) == 1


def _posicao(lado="long", entrada=99_800.0, stop=99_100.0):
    return IntradayOpenPosition(side=lado, entry_ts=pd.Timestamp("2026-05-05 09:10"), entry_price=entrada, quantity=2,
                                current_stop=stop, current_target=None, bars_held=1)


def test_flatten_na_barra_anterior_a_ultima_do_continuo_nunca_no_call():
    s = WinGapBarra1()
    dia_anterior(s)
    barra1(s, "2026-05-05", o=99_500, c=99_800)
    pos = [_posicao()]
    saidas = []
    ts = pd.Timestamp("2026-05-05 09:05")
    while ts <= pd.Timestamp("2026-05-05 18:20"):
        acoes = s.on_bar(ts, b(ts, 99_900, 99_950, 99_850, 99_900), pos, 0.0)
        if any(isinstance(a, Exit) for a in acoes):
            saidas.append(ts.strftime("%H:%M"))
        ts += pd.Timedelta(minutes=5)
    assert saidas == ["18:10"]                    # Exit no fecho da barra das 18:10 -> executa na abertura das 18:15, antes do call; uma vez so'
    # regime antigo (17:55): a barra de saida e' 17:45
    s = WinGapBarra1(fim_continuo_min=535)
    dia_anterior(s)
    barra1(s, "2026-05-05", o=99_500, c=99_800)
    saidas = []
    ts = pd.Timestamp("2026-05-05 09:05")
    while ts <= pd.Timestamp("2026-05-05 17:50"):
        if any(isinstance(a, Exit) for a in s.on_bar(ts, b(ts, 99_900, 99_950, 99_850, 99_900), pos, 0.0)):
            saidas.append(ts.strftime("%H:%M"))
        ts += pd.Timedelta(minutes=5)
    assert saidas == ["17:40"]


def test_independe_do_fuso_do_feed():
    s = WinGapBarra1(abertura_h=12)               # feed em UTC: pregao abre 12:00
    s.on_session_start(dt.date(2026, 5, 4))
    s.on_bar(pd.Timestamp("2026-05-04 12:00"), b("2026-05-04 12:00", 99_900, 100_100, 99_800, 99_950), [], 0.0)
    s.on_bar(pd.Timestamp("2026-05-04 21:20"), b("2026-05-04 21:20", 99_950, 100_050, 99_900, 100_000), [], 0.0)
    s.on_session_start(dt.date(2026, 5, 5))
    acoes = s.on_bar(pd.Timestamp("2026-05-05 12:00"), b("2026-05-05 12:00", 99_500, 99_900, 99_450, 99_800), [], 0.0)
    assert len(acoes) == 1 and acoes[0].side == "long"


def test_breakeven_move_o_stop_depois_de_be_r_do_stop():
    s = WinGapBarra1(stop_pts=700, be_r=1.0)
    dia_anterior(s)
    barra1(s, "2026-05-05", o=99_500, c=99_800)
    pos = [_posicao()]
    ts = pd.Timestamp("2026-05-05 09:10")
    a = s.on_bar(ts, b(ts, 99_800, 100_300, 99_700, 100_200), pos, 0.0)       # +500: ainda nao
    assert not any(isinstance(x, AdjustStop) for x in a)
    ts += pd.Timedelta(minutes=5)
    a = s.on_bar(ts, b(ts, 100_200, 100_600, 100_100, 100_500), pos, 0.0)     # +800 >= 700
    ajuste = [x for x in a if isinstance(x, AdjustStop)]
    assert ajuste and ajuste[0].new_stop == 99_805.0


def test_nao_esta_no_registry():
    from strategy.daytrade import registry
    assert "win_gap_barra1" not in registry._ROBOTS


def test_sem_flatten_proprio_quando_desligado():
    s = WinGapBarra1(zerar_no_fim=False)
    dia_anterior(s)
    barra1(s, "2026-05-05", o=99_500, c=99_800)
    ts = pd.Timestamp("2026-05-05 18:10")
    assert not any(isinstance(a, Exit) for a in s.on_bar(ts, b(ts, 99_900, 99_950, 99_850, 99_900), [_posicao()], 0.0))


def test_dias_sem_operar_bloqueia_o_sinal():
    s = WinGapBarra1(dias_sem_operar=frozenset({dt.date(2026, 5, 5)}))
    dia_anterior(s)
    assert barra1(s, "2026-05-05", o=99_500, c=99_800) == []


def test_call_de_d_menos_1_vem_de_initialize_quando_o_motor_nao_entrega_a_ultima_barra():
    idx = pd.to_datetime(["2026-05-04 09:00", "2026-05-04 18:15", "2026-05-04 18:20", "2026-05-05 09:00", "2026-05-05 18:20"])
    hist = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": [99_950.0, 99_990.0, 100_000.0, 99_800.0, 7.0]}, index=idx)
    s = WinGapBarra1()
    s.initialize(hist)
    # so' a barra das 18:15 de D-1 chegou a on_bar (a das 18:20, com o call, nao): o call vem da tabela
    s.on_session_start(dt.date(2026, 5, 4))
    s.on_bar(pd.Timestamp("2026-05-04 18:15"), b("2026-05-04 18:15", 99_980, 99_995, 99_970, 99_990), [], 0.0)
    acoes = barra1(s, "2026-05-05", o=99_500, c=99_800)
    assert s._d.gap == pytest.approx(-500.0) and acoes[0].side == "long"      # 99.500 - 100.000, nao 99.500 - 99.990
    # o close de HOJE (7.0 na tabela) nunca entra: so' datas anteriores
    s2 = WinGapBarra1()
    s2.initialize(hist)
    barra1(s2, "2026-05-05", o=99_500, c=99_800)
    assert s2._d.gap == pytest.approx(-500.0)
