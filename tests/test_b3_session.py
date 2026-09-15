"""Testes de `core.b3_session` — os horarios do mercado a vista da B3 e o
fuso do relogio do servidor MT5.

Cada numero aqui foi MEDIDO contra o terminal real (Rico-PRD, 2026-08-21) e
esta documentado na docstring do modulo. Estes testes existem para travar as
medicoes: sem eles, a proxima pessoa a mexer nas fronteiras nao tem como saber
que 17:55 e' o fechamento de INVERNO no hemisferio norte e nao "o
fechamento".
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

from core.b3_session import (
    CLOCK_REFERENCE_TICKER,
    MT5_SERVER_TIMEZONE,
    OPEN,
    OPEN_HALF_DAY,
    after_hours_end,
    closing_auction_end,
    FOLGA_ACHATAMENTO_MINUTOS,
    closing_bar_minute_utc,
    flatten_cut_utc,
    continuous_end,
    server_utc_offset_hours,
    server_wall_clock_to_utc,
    us_dst,
)


# ---------- horario de verao dos EUA ------------------------------------

@pytest.mark.parametrize(
    "d, esperado",
    [
        # DST dos EUA em 2026: 08/03 a 01/11 (2o domingo de marco, 1o de novembro)
        (date(2026, 3, 6), False),   # sexta antes da virada
        (date(2026, 3, 9), True),    # segunda depois da virada
        (date(2026, 8, 21), True),   # pleno verao americano
        (date(2026, 11, 2), False),  # segunda depois de desligar
        # 2025: 09/03 a 01/11
        (date(2025, 10, 31), True),
        (date(2025, 11, 3), False),
        (date(2026, 1, 19), False),  # janeiro: inverno no hemisferio norte
    ],
)
def test_us_dst_nas_datas_medidas(d: date, esperado: bool) -> None:
    assert us_dst(d) is esperado


# ---------- fronteiras do pregao a vista --------------------------------

def test_abertura_nao_desloca_com_o_dst_americano() -> None:
    """Medido: primeira barra M1 em 10:00..10:03 (cru = Brasilia) nos DOIS
    regimes, para PMAM3 e PETR4. So o fechamento anda."""
    assert OPEN == time(10, 0)
    assert OPEN_HALF_DAY == time(13, 0)


@pytest.mark.parametrize(
    "d, fim_continuo, fim_leilao, fim_after",
    [
        # sob DST dos EUA: ultima barra M1 medida em 16:54 -> continuo acaba 16:55
        (date(2026, 8, 21), time(16, 55), time(17, 0), time(17, 30)),
        (date(2026, 3, 9), time(16, 55), time(17, 0), time(17, 30)),
        (date(2025, 10, 31), time(16, 55), time(17, 0), time(17, 30)),
        # fora dele: ultima barra M1 medida em 17:54
        (date(2026, 1, 19), time(17, 55), time(18, 0), time(18, 30)),
        (date(2026, 3, 6), time(17, 55), time(18, 0), time(18, 30)),
        (date(2025, 11, 3), time(17, 55), time(18, 0), time(18, 30)),
    ],
)
def test_fronteiras_de_fechamento_por_regime(
    d: date, fim_continuo: time, fim_leilao: time, fim_after: time
) -> None:
    assert continuous_end(d) == fim_continuo
    assert closing_auction_end(d) == fim_leilao
    assert after_hours_end(d) == fim_after


def test_corte_de_flatten_em_utc_bate_com_a_ultima_barra_medida() -> None:
    """19:54 e 20:54 UTC sao EXATAMENTE as duas modas de ultima barra no
    parquet M1 salvo de PMAM3 (440 e 120 pregoes) — o que confirma que os
    dois valores sao regimes, e nao um regime e um punhado de excecoes."""
    assert closing_bar_minute_utc(date(2026, 8, 21)) == time(19, 54)
    assert closing_bar_minute_utc(date(2026, 1, 19)) == time(20, 54)


def test_corte_de_flatten_e_um_minuto_antes_do_fim_do_continuo() -> None:
    """A barra M1 do MT5 e' rotulada pela ABERTURA: o corte tem de ser o
    ROTULO da ultima barra, senao nenhuma barra o alcanca e o flatten passa a
    depender do fim do DADO em vez do fim do PREGAO."""
    for d in (date(2026, 8, 21), date(2026, 1, 19)):
        fim_local = datetime.combine(d, continuous_end(d), tzinfo=MT5_SERVER_TIMEZONE)
        corte_utc = datetime.combine(d, closing_bar_minute_utc(d), tzinfo=timezone.utc)
        assert (fim_local - corte_utc).total_seconds() == 60.0


def test_o_corte_de_achatamento_da_acao_tem_a_folga_pedida() -> None:
    """Ordem do dono, 2026-09-14: achatar ao menos 5 minutos antes do fim do
    pregao. `closing_bar_minute_utc` continua respondendo "qual e' o rotulo da
    ULTIMA barra" (pergunta factual, usada para validar dado); quem o motor
    compara e' `flatten_cut_utc`, que recua a folga.

    Duas funcoes de proposito: enquanto era uma so', o numero que dizia onde o
    pregao acaba era o mesmo que dizia onde o robo devia sair -- e no lado do
    FUTURO essa fusao tornou o achatamento impossivel (item 4.28 de
    LICOES_DE_PRODUCAO.md)."""
    for d in (date(2026, 8, 21), date(2026, 1, 19)):
        fim_local = datetime.combine(d, continuous_end(d), tzinfo=MT5_SERVER_TIMEZONE)
        corte_utc = datetime.combine(d, flatten_cut_utc(d), tzinfo=timezone.utc)
        assert (fim_local - corte_utc).total_seconds() == FOLGA_ACHATAMENTO_MINUTOS * 60.0
        # e sempre ANTES da ultima barra, nunca depois dela
        assert flatten_cut_utc(d) < closing_bar_minute_utc(d)

    assert flatten_cut_utc(date(2026, 8, 21)) == time(19, 50)   # 16:50 BRT
    assert flatten_cut_utc(date(2026, 1, 19)) == time(20, 50)   # 17:50 BRT



# ---------- fuso do servidor MT5 ----------------------------------------

def test_offset_do_servidor_e_mais_tres_horas() -> None:
    """Medido de tres formas independentes (tick vivo, abertura da B3 em 2,5
    anos de barras, contraprova no WIN) — ver docstring do modulo."""
    assert server_utc_offset_hours(datetime(2026, 8, 21, 21, 42, tzinfo=timezone.utc)) == 3.0
    # e nao muda com a estacao, porque o Brasil nao tem horario de verao
    assert server_utc_offset_hours(datetime(2026, 1, 19, 12, 0, tzinfo=timezone.utc)) == 3.0


def test_offset_aceita_naive_como_utc() -> None:
    assert server_utc_offset_hours(datetime(2026, 8, 21, 21, 42)) == 3.0


def test_converte_hora_de_parede_do_servidor_para_utc() -> None:
    """O caso concreto medido: tick cru 18:40:11 com UTC real em 21:40:11."""
    parede = datetime(2026, 8, 21, 18, 40, 11)
    assert server_wall_clock_to_utc(parede) == datetime(
        2026, 8, 21, 21, 40, 11, tzinfo=timezone.utc
    )


def test_ticker_de_referencia_do_relogio_e_liquido() -> None:
    """Nao ha como testar liquidez aqui; o que se trava e' a INTENCAO — o
    papel de referencia nao pode ser o papel operado (PMAM3), senao "sem
    tick" volta a ser explicacao aceitavel e a conferencia perde o sentido."""
    assert CLOCK_REFERENCE_TICKER == "PETR4.SA"
