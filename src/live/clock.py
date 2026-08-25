"""Relogio de pregao da B3 — a peca de AGENDAMENTO do ambiente ao vivo.

Responde tres perguntas, e SO estas tres:

    - Que dia de pregao e este? (`is_trading_day`, `is_half_day`)
    - O mercado esta aberto agora? (`phase`)
    - Qual e o pregao de referencia / anterior / seguinte? (`session_date`,
      `previous_session`, `next_session`, `sessions_between`)

O que este modulo NAO faz: validar se um preco e fresco, se um feed caiu, se
um candle esta completo. Isso e responsabilidade do `live.runtime`, porque o
relogio da maquina pode mentir (fuso trocado, feriado nao mapeado, pregao
estendido por evento excepcional da B3) enquanto o DADO observado e a fonte
de verdade final. Ver o comentario "relogio agenda, dado decide" em
`core.live_models.SessionPhase`.

Regra 6 do AGENTS.md tambem vale aqui: nenhuma regra de DECISAO de trade
mora neste arquivo. `phase()` e `session_date()` sao puramente sobre TEMPO —
nunca sobre se um sinal deve ou nao ser executado.

Horarios de pregao — de onde vem
---------------------------------
Este modulo responde QUE DIA (feriado, meio pregao, pregao anterior); a HORA
DO DIA vem toda de `core.b3_session`, que e' o dono unico desses numeros
porque o backtest intradiario e a conversao de fuso do MT5 precisam
exatamente dos mesmos (ver a docstring de la, com a medicao).

O ponto que essa separacao conserta: o fim do pregao de ACOES da B3 NAO e'
uma constante. Ele anda 1h para tras quando o horario de verao dos EUA entra
(16:55 em vez de 17:55, em hora de Brasilia) porque parte da liquidez
arbitra contra Nova York. Este arquivo declarava 17:55 fixo e portanto ficava
uma hora errado por ~8 meses do ano — medido em barras M1 reais, ver
`core.b3_session`. A abertura, essa sim, e' fixa em 10:00 nos dois regimes.

Confira sempre em b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/
para-participantes-e-traders/horario-de-negociacao/ antes de operar dinheiro
real com base nestes numeros.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache

from core.b3_session import (  # noqa: F401 (reexport: API historica deste modulo)
    OPEN,
    OPEN_HALF_DAY,
    PRE_OPEN_LEAD as _PRE_OPEN_LEAD,
    SAO_PAULO,
    after_hours_end,
    closing_auction_end,
    continuous_end,
)
from core.live_models import SessionPhase

# ---------- feriados ----------------------------------------------------

# feriados nacionais de data fixa que a B3 observa (mes, dia)
_FIXED_HOLIDAYS: tuple[tuple[int, int], ...] = (
    (1, 1),    # confraternizacao universal
    (4, 21),   # tiradentes
    (5, 1),    # dia do trabalho
    (9, 7),    # independencia
    (10, 12),  # nossa senhora aparecida
    (11, 2),   # finados
    (11, 15),  # proclamacao da republica
    (12, 25),  # natal
)

# ano a partir do qual 20/11 (Consciencia Negra) e feriado nacional.
# Lei 14.759/2023, sancionada em dezembro de 2023 — o primeiro 20/11 que
# ela alcanca e o de 2024. Anos anteriores NAO tem este feriado.
_CONSCIENCIA_NEGRA_START_YEAR: int = 2024


def easter(year: int) -> date:
    """Domingo de Pascoa do ano, pelo algoritmo gregoriano anonimo.

    Tambem conhecido como algoritmo de Meeus/Jones/Butcher. E "anonimo"
    porque nao tem autor atribuido de forma inequivoca na literatura — so
    o metodo aritmetico, valido para qualquer ano do calendario gregoriano
    (1583 em diante). Usado aqui porque todo feriado movel da B3 (carnaval,
    sexta-feira santa, corpus christi, quarta de cinzas) e definido como um
    deslocamento fixo de dias a partir desta data.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def b3_holidays(year: int) -> frozenset[date]:
    """Conjunto de datas em que a B3 nao opera no ano informado.

    Mistura tres origens deliberadamente:

    1. Feriados nacionais fixos (`_FIXED_HOLIDAYS`).
    2. Feriados nacionais moveis, derivados de `easter(year)`: carnaval
       (segunda e terca, easter-48/-47), sexta-feira santa (easter-2) e
       corpus christi (easter+60). Note que a QUARTA DE CINZAS (easter-46)
       fica de fora de proposito — ela e meio pregao, nao feriado (ver
       `is_half_day`).
    3. Fechamentos que sao praxe de mercado, nao feriado nacional: a B3
       historicamente nao opera em 24/12 e 31/12 (ponte de fim de ano),
       mesmo quando a data cai em dia util. Isto e convencao da bolsa, e
       vale a pena reconferir no calendario oficial publicado a cada ano.

    `lru_cache` porque `is_trading_day` chama esta funcao para cada data
    verificada — sem cache, `sessions_between` sobre um intervalo longo
    recalcularia a Pascoa do mesmo ano centenas de vezes.
    """
    e = easter(year)
    holidays = {date(year, month, day) for month, day in _FIXED_HOLIDAYS}
    holidays.add(e - timedelta(days=48))  # carnaval, segunda-feira
    holidays.add(e - timedelta(days=47))  # carnaval, terca-feira
    holidays.add(e - timedelta(days=2))   # sexta-feira santa
    holidays.add(e + timedelta(days=60))  # corpus christi
    if year >= _CONSCIENCIA_NEGRA_START_YEAR:
        holidays.add(date(year, 11, 20))  # consciencia negra (Lei 14.759/2023)
    holidays.add(date(year, 12, 24))  # vespera de natal — B3 nao opera
    holidays.add(date(year, 12, 31))  # vespera de ano novo — B3 nao opera
    return frozenset(holidays)


def is_trading_day(d: date) -> bool:
    """True se a B3 opera em `d`: dia util e fora do conjunto de feriados."""
    if d.weekday() >= 5:  # 5=sabado, 6=domingo
        return False
    return d not in b3_holidays(d.year)


def is_half_day(d: date) -> bool:
    """True se `d` e quarta-feira de cinzas (easter-46).

    Meio pregao: o dia E de negociacao (`is_trading_day(d)` e True), mas o
    continuo so abre 13:00 em vez de 10:00 — tradicionalmente a B3 fecha a
    manha em solidariedade ao feriado catolico do dia anterior sem fechar
    o dia inteiro.
    """
    return d == easter(d.year) - timedelta(days=46)


def session_open(d: date) -> time:
    """Horario de abertura do continuo em `d`: 13:00 se meio pregao, 10:00 caso contrario."""
    return OPEN_HALF_DAY if is_half_day(d) else OPEN


def _normalize(now: datetime | None) -> datetime:
    """Resolve `now` para um datetime AWARE em America/Sao_Paulo.

    - `None` -> horario atual real.
    - naive -> assumido como ja sendo horario de Sao Paulo (e o uso mais
      comum: o resto do sistema trabalha com datetimes naive "locais").
    - aware -> convertido, nunca reinterpretado.
    """
    if now is None:
        return datetime.now(SAO_PAULO)
    if now.tzinfo is None:
        return now.replace(tzinfo=SAO_PAULO)
    return now.astimezone(SAO_PAULO)


def phase(now: datetime | None = None) -> SessionPhase:
    """Em que fase do pregao `now` cai (default: agora).

    Decisoes de fronteira, documentadas porque nao sao obvias:

    - Fora de dia de pregao (fim de semana, feriado) -> sempre `CLOSED`,
      independente da hora do relogio.
    - Antes do inicio do leilao de abertura (`session_open(d) - 15min`) num
      dia de pregao -> `CLOSED`, nao `PRE_OPEN`. O leilao ainda nao
      comecou a formar preco; chamar isso de "pre-abertura" sugeriria que
      ja ha alguma atividade de mercado, e nao ha. No meio pregao esse
      limiar desloca junto (12:45 em vez de 09:45), porque o leilao
      antecede a abertura do continuo pelo mesmo intervalo nos dois casos.
    - Depois do after-market, ainda em dia de pregao -> `POST_CLOSE`
      (pregao encerrado, mas o dia-calendario ainda e o do pregao — ver
      `session_date` para o motivo disso importar).
    - As tres fronteiras de FECHAMENTO andam 1h para tras sob horario de
      verao dos EUA (ver `core.b3_session`). Nao ha um horario de fechamento
      "do dia normal" — ha o do regime em que `now` cai.
    """
    now = _normalize(now)
    d = now.date()
    if not is_trading_day(d):
        return SessionPhase.CLOSED

    open_dt = datetime.combine(d, session_open(d), tzinfo=SAO_PAULO)
    pre_open_dt = open_dt - _PRE_OPEN_LEAD
    continuous_end_dt = datetime.combine(d, continuous_end(d), tzinfo=SAO_PAULO)
    closing_auction_end_dt = datetime.combine(d, closing_auction_end(d), tzinfo=SAO_PAULO)
    after_hours_end_dt = datetime.combine(d, after_hours_end(d), tzinfo=SAO_PAULO)

    if now < pre_open_dt:
        return SessionPhase.CLOSED
    if now < open_dt:
        return SessionPhase.PRE_OPEN
    if now < continuous_end_dt:
        return SessionPhase.OPEN
    if now < closing_auction_end_dt:
        return SessionPhase.CLOSING_AUCTION
    if now < after_hours_end_dt:
        return SessionPhase.AFTER_HOURS
    return SessionPhase.POST_CLOSE


_ACTIVE_WINDOW_PAD: timedelta = timedelta(hours=1)


def _active_window(d: date) -> tuple[datetime, datetime]:
    """Janela [1h antes da abertura, 1h depois do fim do leilao de fechamento]
    de um dia de pregao `d`. Usada por quem faz trabalho PERIODICO (loops de
    atualizacao, polling do dashboard) para saber quando vale a pena rodar —
    nao tem nenhum uso em decisao de trade (isso continua sendo so `phase()`)."""
    start = datetime.combine(d, session_open(d), tzinfo=SAO_PAULO) - _ACTIVE_WINDOW_PAD
    end = datetime.combine(d, closing_auction_end(d), tzinfo=SAO_PAULO) + _ACTIVE_WINDOW_PAD
    return start, end


def in_active_window(now: datetime | None = None) -> bool:
    """True se `now` cai dentro da janela de pregao +/- 1h de folga (default:
    agora). Fora de dia de pregao (fim de semana, feriado) e sempre False —
    a unica informacao que isto precisa e a DATA exata, ja resolvida por
    `is_trading_day`/`b3_holidays`."""
    now = _normalize(now)
    d = now.date()
    if not is_trading_day(d):
        return False
    start, end = _active_window(d)
    return start <= now <= end


def seconds_until_active_window(now: datetime | None = None) -> float:
    """Quantos segundos faltam ate a janela ativa (`in_active_window`) abrir
    de novo. Devolve `0.0` se ja estamos dentro dela agora — quem chama so
    precisa disto para saber quanto DORMIR quando `in_active_window` for
    False, em vez de acordar toda hora (dia inteiro, fim de semana incluso)
    so para constatar que nao ha nada a fazer."""
    now = _normalize(now)
    d = now.date()
    if is_trading_day(d):
        start, end = _active_window(d)
        if now < start:
            return (start - now).total_seconds()
        if now <= end:
            return 0.0
        # now > end: janela de hoje ja fechou, cai para o proximo pregao.
    nxt = next_session(d)
    start, _ = _active_window(nxt)
    return (start - now).total_seconds()


def previous_session(d: date) -> date:
    """Ultimo pregao ANTES de `d` (estrito: nunca devolve `d`, mesmo se `d` for pregao)."""
    cur = d - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def next_session(d: date) -> date:
    """Proximo pregao DEPOIS de `d` (estrito: nunca devolve `d`, mesmo se `d` for pregao)."""
    cur = d + timedelta(days=1)
    while not is_trading_day(cur):
        cur += timedelta(days=1)
    return cur


def session_date(now: datetime | None = None) -> date:
    """Pregao de REFERENCIA para uma decisao tomada em `now` (default: agora).

    Esta e a data que o resto do sistema (runtime, robos) deve usar para
    perguntar "qual e o pregao de hoje". Regra:

    - Se hoje e dia de pregao e a fase ja passou do fechamento (`POST_CLOSE`
      ou `AFTER_HOURS`), a referencia e HOJE — o pregao fechou, os dados do
      dia estao completos, e uma decisao tomada agora e sobre o fecho de
      hoje.
    - Em qualquer outro caso — mercado ainda aberto (`PRE_OPEN`, `OPEN`,
      `CLOSING_AUCTION`), mercado fechado num dia sem pregao (`CLOSED` fora
      de dia util), ou mesmo `CLOSED` num dia de pregao que ainda nao
      abriu — a referencia e o ULTIMO PREGAO JA ENCERRADO
      (`previous_session`). O motivo e a regra 4 do AGENTS.md aplicada ao
      relogio: decidir sobre uma barra que ainda esta se formando (ou que
      nem comecou) e look-ahead invertido — o robo estaria "vendo" um
      fecho que ainda nao existe.
    """
    now = _normalize(now)
    d = now.date()
    if is_trading_day(d) and phase(now) in (SessionPhase.AFTER_HOURS, SessionPhase.POST_CLOSE):
        return d
    return previous_session(d)


def intraday_session(now: datetime | None = None) -> date:
    """Pregao de day trade EM CURSO em `now` (default: agora) — o dia-
    calendario real, nunca o pregao anterior.

    Diferente de `session_date()`: aquela e a referencia do SWING, que decide
    sobre um fecho ja completo (por isso aponta pro ULTIMO pregao encerrado
    enquanto o continuo de hoje ainda esta aberto). Day trade decide dentro do
    proprio pregao que esta rolando agora — chamar `session_date()` dali
    devolvia o pregao anterior o dia inteiro (confirmado ao vivo em
    2026-08-24: mercado aberto, `session_date()` apontando pra sexta-feira),
    o que journalizava toda operacao de hoje com a data de ontem e desalinhava
    a janela de semente (`_seed_volume_window`/`_seed_daily_volatility`) em um
    pregao. So faz sentido chamar isto durante `OPEN`/`CLOSING_AUCTION` — quem
    chama fora dessa janela ja devolveu `idle` antes."""
    return _normalize(now).date()


def sessions_between(start: date, end: date) -> list[date]:
    """Lista (ordenada, crescente) de pregoes com `start <= d <= end`.

    Ambos os extremos sao inclusivos SE forem pregoes; se `start` ou `end`
    cairem em fim de semana/feriado, simplesmente nao aparecem na lista —
    esta funcao nao "arredonda" para o pregao mais proximo, apenas filtra.
    """
    days: list[date] = []
    cur = start
    one_day = timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur):
            days.append(cur)
        cur += one_day
    return days
