"""Testes do relogio de pregao da B3 (`live.clock`).

Cada data usada aqui e conferivel de forma independente (calculadora de
Pascoa, calendario de feriados da B3 publicado em b3.com.br) — os
comentarios explicam a conta, nao so o resultado, para que uma revisao
futura consiga auditar sem re-derivar tudo do zero.
"""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from core.live_models import SessionPhase
from live.clock import (
    SAO_PAULO,
    b3_holidays,
    easter,
    in_active_window,
    intraday_session,
    is_half_day,
    is_trading_day,
    next_session,
    phase,
    previous_session,
    seconds_until_active_window,
    session_date,
    session_open,
    sessions_between,
)


# ---------- easter -------------------------------------------------------

@pytest.mark.parametrize(
    "year, expected",
    [
        (2024, date(2024, 3, 31)),  # Pascoa 2024, publicamente conhecida
        (2025, date(2025, 4, 20)),  # Pascoa 2025
        (2026, date(2026, 4, 5)),   # Pascoa 2026
    ],
)
def test_easter(year: int, expected: date) -> None:
    assert easter(year) == expected


# ---------- feriados moveis, familia 2026 --------------------------------

def test_sexta_feira_santa_2026_nao_e_pregao() -> None:
    # easter(2026) - 2 dias = 2026-04-05 - 2 = 2026-04-03
    assert not is_trading_day(date(2026, 4, 3))


def test_carnaval_2026_nao_e_pregao() -> None:
    # easter(2026)=2026-04-05; segunda=-48d=02-16; terca=-47d=02-17
    assert not is_trading_day(date(2026, 2, 16))
    assert not is_trading_day(date(2026, 2, 17))


def test_corpus_christi_2026_nao_e_pregao() -> None:
    # easter(2026) + 60 dias = 2026-06-04
    assert not is_trading_day(date(2026, 6, 4))


# ---------- feriados moveis, familia 2025 (mesma logica, ano diferente) --

def test_sexta_feira_santa_2025_nao_e_pregao() -> None:
    assert not is_trading_day(date(2025, 4, 18))


def test_carnaval_2025_nao_e_pregao() -> None:
    assert not is_trading_day(date(2025, 3, 3))
    assert not is_trading_day(date(2025, 3, 4))


def test_corpus_christi_2025_nao_e_pregao() -> None:
    assert not is_trading_day(date(2025, 6, 19))


# ---------- quarta de cinzas: pregao normal, so que meio pregao ---------

def test_quarta_de_cinzas_2026_e_pregao_e_meio_pregao() -> None:
    # easter(2026) - 46 dias = 2026-02-18 (dia seguinte ao carnaval)
    d = date(2026, 2, 18)
    assert is_trading_day(d) is True
    assert is_half_day(d) is True
    assert session_open(d) == time(13, 0)


def test_quarta_de_cinzas_nao_esta_no_conjunto_de_feriados() -> None:
    # is_half_day != feriado: o dia tem que aparecer como pregao normal,
    # so que com abertura deslocada.
    d = date(2026, 2, 18)
    assert d not in b3_holidays(2026)


# ---------- consciencia negra: so a partir de 2024 (Lei 14.759/2023) -----

def test_consciencia_negra_2023_nao_e_feriado() -> None:
    # lei sancionada em dez/2023, so alcanca o 20/11 seguinte (2024)
    assert is_trading_day(date(2023, 11, 20)) is True


def test_consciencia_negra_2024_e_feriado() -> None:
    assert is_trading_day(date(2024, 11, 20)) is False


# ---------- fechamentos de convencao da bolsa (nao sao feriado nacional) -

def test_vespera_de_natal_nao_e_pregao() -> None:
    assert is_trading_day(date(2025, 12, 24)) is False


def test_vespera_de_ano_novo_nao_e_pregao() -> None:
    assert is_trading_day(date(2025, 12, 31)) is False


def test_fim_de_semana_nao_e_pregao() -> None:
    # 2026-08-15 e sabado, 2026-08-16 e domingo
    assert is_trading_day(date(2026, 8, 15)) is False
    assert is_trading_day(date(2026, 8, 16)) is False


# ---------- phase ---------------------------------------------------------

# 2026-08-17 e segunda-feira, dia de pregao normal (sem feriado por perto), e
# cai DENTRO do horario de verao dos EUA (que em 2026 vai de 08/03 a 01/11) —
# regime em que o pregao a vista da B3 fecha 1h mais cedo. Ver
# `core.b3_session` para a medicao em barras M1 reais.
_NORMAL_DAY = date(2026, 8, 17)

# 2026-01-19, segunda-feira comum FORA do horario de verao americano: mesmo
# pregao, fronteiras de fechamento 1h depois. As duas parametrizacoes juntas
# sao o teste de verdade — uma so nao distinguiria "certo" de "1h errado".
_US_STANDARD_DAY = date(2026, 1, 19)


@pytest.mark.parametrize(
    "hhmm, expected",
    [
        ((9, 0), SessionPhase.CLOSED),          # antes do leilao de abertura
        ((9, 44), SessionPhase.CLOSED),         # 1 min antes do limiar
        ((9, 45), SessionPhase.PRE_OPEN),       # leilao comeca a formar
        ((9, 59), SessionPhase.PRE_OPEN),
        ((10, 0), SessionPhase.OPEN),           # abertura do continuo (nao desloca)
        ((13, 30), SessionPhase.OPEN),          # meio do pregao
        ((16, 54), SessionPhase.OPEN),          # ultima barra M1 medida
        ((16, 55), SessionPhase.CLOSING_AUCTION),
        ((16, 59), SessionPhase.CLOSING_AUCTION),
        ((17, 0), SessionPhase.AFTER_HOURS),
        ((17, 29), SessionPhase.AFTER_HOURS),
        ((17, 30), SessionPhase.POST_CLOSE),
        # o horario que era o fechamento no codigo antigo ja e' POST_CLOSE:
        # e' exatamente o erro de 1h que este teste existe para travar.
        ((17, 55), SessionPhase.POST_CLOSE),
        ((23, 0), SessionPhase.POST_CLOSE),
    ],
)
def test_phase_dia_normal_sob_horario_de_verao_dos_eua(
    hhmm: tuple[int, int], expected: SessionPhase
) -> None:
    now = datetime.combine(_NORMAL_DAY, time(*hhmm))
    assert phase(now) == expected


@pytest.mark.parametrize(
    "hhmm, expected",
    [
        ((9, 45), SessionPhase.PRE_OPEN),
        ((10, 0), SessionPhase.OPEN),           # abertura identica nos dois regimes
        ((16, 55), SessionPhase.OPEN),          # aqui ainda negocia
        ((17, 54), SessionPhase.OPEN),
        ((17, 55), SessionPhase.CLOSING_AUCTION),
        ((18, 0), SessionPhase.AFTER_HOURS),
        ((18, 30), SessionPhase.POST_CLOSE),
    ],
)
def test_phase_dia_normal_fora_do_horario_de_verao_dos_eua(
    hhmm: tuple[int, int], expected: SessionPhase
) -> None:
    now = datetime.combine(_US_STANDARD_DAY, time(*hhmm))
    assert phase(now) == expected


def test_fechamento_desloca_exatamente_na_virada_do_dst_americano() -> None:
    """As datas vem da medicao em barras M1 de PETR4 (ver `core.b3_session`):
    sexta 06/03/2026 fechou 17:54 e segunda 09/03 fechou 16:54, com o horario
    de verao dos EUA comecando no domingo 08/03."""
    sexta_antes = datetime.combine(date(2026, 3, 6), time(17, 30))
    segunda_depois = datetime.combine(date(2026, 3, 9), time(17, 30))
    assert phase(sexta_antes) == SessionPhase.OPEN
    assert phase(segunda_depois) == SessionPhase.POST_CLOSE


def test_phase_meio_pregao_antes_das_13_ainda_fechado() -> None:
    # quarta de cinzas 2026: abertura 13:00, leilao comeca 12:45
    d = date(2026, 2, 18)
    assert phase(datetime.combine(d, time(12, 30))) == SessionPhase.CLOSED
    assert phase(datetime.combine(d, time(12, 45))) == SessionPhase.PRE_OPEN
    assert phase(datetime.combine(d, time(13, 0))) == SessionPhase.OPEN


def test_phase_em_feriado_e_sempre_closed() -> None:
    # sexta-feira santa 2026, mesmo em plena "hora de pregao"
    d = date(2026, 4, 3)
    assert phase(datetime.combine(d, time(11, 0))) == SessionPhase.CLOSED


def test_phase_aceita_datetime_naive_e_aware() -> None:
    naive = datetime.combine(_NORMAL_DAY, time(11, 0))
    aware = naive.replace(tzinfo=SAO_PAULO)
    assert phase(naive) == phase(aware) == SessionPhase.OPEN


def test_phase_default_none_nao_quebra() -> None:
    # so garante que "agora" funciona sem lancar excecao
    assert isinstance(phase(), SessionPhase)


# ---------- active window (loops/polling de segundo plano) ----------------

def test_in_active_window_uma_hora_antes_da_abertura() -> None:
    assert in_active_window(datetime.combine(_NORMAL_DAY, time(8, 59))) is False
    assert in_active_window(datetime.combine(_NORMAL_DAY, time(9, 0))) is True


def test_in_active_window_uma_hora_depois_do_leilao_de_fechamento() -> None:
    # sob horario de verao dos EUA o leilao termina 17:00 -> +1h de folga = 18:00
    assert in_active_window(datetime.combine(_NORMAL_DAY, time(18, 0))) is True
    assert in_active_window(datetime.combine(_NORMAL_DAY, time(18, 1))) is False
    # fora dele, a mesma folga cai 1h depois
    assert in_active_window(datetime.combine(_US_STANDARD_DAY, time(19, 0))) is True
    assert in_active_window(datetime.combine(_US_STANDARD_DAY, time(19, 1))) is False


def test_in_active_window_meio_do_pregao_e_true() -> None:
    assert in_active_window(datetime.combine(_NORMAL_DAY, time(13, 30))) is True


def test_in_active_window_fim_de_semana_e_sempre_false() -> None:
    sabado = date(2026, 8, 15)
    assert in_active_window(datetime.combine(sabado, time(11, 0))) is False


def test_in_active_window_feriado_e_sempre_false() -> None:
    sexta_santa = date(2026, 4, 3)
    assert in_active_window(datetime.combine(sexta_santa, time(11, 0))) is False


def test_seconds_until_active_window_zero_quando_ja_dentro() -> None:
    assert seconds_until_active_window(datetime.combine(_NORMAL_DAY, time(13, 30))) == 0.0


def test_seconds_until_active_window_mesmo_dia_antes_da_janela() -> None:
    now = datetime.combine(_NORMAL_DAY, time(7, 0))
    esperado = 2 * 3600  # janela abre as 9h (10h - 1h de folga)
    assert seconds_until_active_window(now) == pytest.approx(esperado)


def test_seconds_until_active_window_atravessa_fim_de_semana() -> None:
    # sexta 2026-08-14, 20h (ja passou da janela de hoje) -> proxima janela e
    # segunda 2026-08-17 as 9h, pulando sabado/domingo por completo.
    sexta_20h = datetime.combine(date(2026, 8, 14), time(20, 0), tzinfo=SAO_PAULO)
    segunda_9h = datetime.combine(date(2026, 8, 17), time(9, 0), tzinfo=SAO_PAULO)
    esperado = (segunda_9h - sexta_20h).total_seconds()
    assert seconds_until_active_window(sexta_20h) == pytest.approx(esperado)


# ---------- session_date ---------------------------------------------------

def test_session_date_durante_pregao_aberto_e_o_pregao_anterior() -> None:
    # segunda 2026-08-17, 11h: mercado aberto, fecho de hoje ainda nao existe
    now = datetime.combine(_NORMAL_DAY, time(11, 0))
    assert session_date(now) == previous_session(_NORMAL_DAY)


def test_session_date_apos_fechamento_e_hoje() -> None:
    now = datetime.combine(_NORMAL_DAY, time(19, 0))
    assert session_date(now) == _NORMAL_DAY


def test_session_date_after_hours_tambem_e_hoje() -> None:
    now = datetime.combine(_NORMAL_DAY, time(18, 5))
    assert session_date(now) == _NORMAL_DAY


def test_session_date_no_sabado_e_a_sexta_anterior() -> None:
    # 2026-08-15 e sabado; 2026-08-14 (sexta) e pregao normal
    sabado = date(2026, 8, 15)
    sexta = date(2026, 8, 14)
    assert is_trading_day(sexta) is True
    now = datetime.combine(sabado, time(12, 0))
    assert session_date(now) == sexta


# ---------- intraday_session: dia trade precisa de HOJE, nunca do pregao
# anterior (ver docstring — `session_date()` durante o continuo aponta pro
# ultimo pregao encerrado, pensado pro swing; achado ao vivo em
# 2026-08-24 jornalizando toda operacao do dia com a data de sexta-feira).

def test_intraday_session_durante_pregao_aberto_e_hoje() -> None:
    now = datetime.combine(_NORMAL_DAY, time(11, 0))
    assert intraday_session(now) == _NORMAL_DAY
    assert intraday_session(now) != session_date(now)


def test_intraday_session_apos_fechamento_ainda_e_hoje() -> None:
    now = datetime.combine(_NORMAL_DAY, time(19, 0))
    assert intraday_session(now) == _NORMAL_DAY


# ---------- previous_session / next_session, atravessando feriado + fds -

def test_previous_next_session_ao_redor_da_sexta_santa_2026() -> None:
    # sexta-feira santa 2026-04-03 (sexta) + fim de semana 04-05 -> proximo
    # pregao e segunda 2026-04-06. Pregao anterior a sexta santa e
    # quinta 2026-04-02.
    sexta_santa = date(2026, 4, 3)
    assert previous_session(sexta_santa) == date(2026, 4, 2)
    assert next_session(sexta_santa) == date(2026, 4, 6)


def test_previous_next_session_sao_estritos() -> None:
    # um dia de pregao comum nao pode ser devolvido como seu proprio anterior/proximo
    d = date(2026, 4, 2)  # quinta, pregao normal
    assert previous_session(d) != d
    assert next_session(d) != d
    assert previous_session(d) < d < next_session(d)


def test_next_session_a_partir_de_dia_sem_pregao() -> None:
    # sabado 2026-04-04 -> proximo pregao e segunda 2026-04-06 (domingo de
    # pascoa cai no meio, mas domingo ja nao seria pregao de qualquer forma)
    assert next_session(date(2026, 4, 4)) == date(2026, 4, 6)


# ---------- sessions_between ------------------------------------------------

def test_sessions_between_contagem_conhecida() -> None:
    # semana comum sem feriado: segunda 2026-08-17 a sexta 2026-08-21 -> 5 pregoes
    dias = sessions_between(date(2026, 8, 17), date(2026, 8, 21))
    assert dias == [
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
        date(2026, 8, 21),
    ]


def test_sessions_between_exclui_feriado_no_meio() -> None:
    # semana da sexta-feira santa 2026 (30/03 a 03/04): sexta 03/04 cai fora
    dias = sessions_between(date(2026, 3, 30), date(2026, 4, 3))
    assert dias == [
        date(2026, 3, 30),
        date(2026, 3, 31),
        date(2026, 4, 1),
        date(2026, 4, 2),
    ]


def test_sessions_between_com_extremos_em_fim_de_semana() -> None:
    # extremos que nao sao pregao simplesmente nao entram na lista
    dias = sessions_between(date(2026, 8, 15), date(2026, 8, 16))  # sab, dom
    assert dias == []
