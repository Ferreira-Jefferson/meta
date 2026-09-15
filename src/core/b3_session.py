"""Horarios do mercado a vista da B3 e o fuso do relogio do servidor MT5.

Mora em `core/` porque TRES camadas precisam exatamente dos mesmos numeros, e
um numero declarado em tres lugares e' um numero que vai divergir:

  - `live/clock.py` (orquestracao) monta `phase()` sobre estas fronteiras;
  - `backtest/intraday/profiles.py` (feature) tira daqui o corte de flatten,
    para o robo ao vivo achatar no MESMO minuto que o backtest validou;
  - `market_data_intraday/mt5_source.py` (feature) converte o relogio cru do
    servidor MT5 para UTC com o mesmo fuso.

Este modulo cuida so de HORA DO DIA. Que DIA e' pregao (feriado, meio
pregao, pascoa) continua em `live/clock.py` — sao perguntas diferentes, e
esta separacao evita arrastar o calendario de feriados para `core/`.

MEDIDO, nao suposto (terminal Rico-PRD, 2026-08-21)
====================================================

**O relogio do servidor MT5 da Rico e a hora de BRASILIA.** O campo `time`
que `copy_rates_*`/`symbol_info_tick` devolvem parece epoch UTC mas e' o
relogio LOCAL do servidor codificado como se fosse UTC. Verificado de tres
formas independentes:

  - tick vivo: `PETR4` cru = 18:40:11 enquanto o relogio local marcava
    18:42:44 (Brasilia) e UTC marcava 21:42:44 — o cru acompanha Brasilia;
  - primeira barra M1 do pregao de `PMAM3` = 10:00..10:03 cru em TODAS as
    janelas de 2024-01 a 2026-08 (a B3 abre 10:00 em Brasilia);
  - o mesmo 10:03 cru para `PETR4` nos dois lados de cada troca de horario
    de verao — ou seja, o servidor NAO desloca.

Como Brasilia nao tem horario de verao desde 2019 (Decreto 9.772/2019), isso
da +3.0h fixo hoje. Ainda assim a conversao aqui e' feita pelo FUSO
(`MT5_SERVER_TIMEZONE`), nunca por uma constante: se o horario de verao
brasileiro voltar, um escalar ficaria errado metade do ano em silencio, e
esta e' precisamente a familia de bug que ja matou todo stop intradiario uma
vez (ver `live_stop_intraday_2026_08_20` na memoria do projeto).

**O pregao de ACOES desloca 1h com o horario de verao dos EUA.** A B3
mantem a abertura em 10:00 e move o FECHAMENTO, porque parte da liquidez
arbitra contra Nova York (16:00 em NY = 17:00 em Brasilia sob DST, 18:00 sob
horario padrao). Medido em barras M1 de `PETR4` (barra crua = hora de
Brasilia), com o negocio do leilao de fechamento identificavel pelo volume
(~2,9M contra ~80k de uma barra normal):

    2026-03-06 sex  ultima barra 17:54     <- DST dos EUA ligou domingo 08/03
    2026-03-09 seg  ultima barra 16:54
    2025-10-31 sex  ultima barra 16:54     <- DST dos EUA desligou domingo 02/11
    2025-11-03 seg  ultima barra 17:54

A virada acontece no primeiro pregao depois da mudanca nos EUA, e por isso a
regra aqui e' derivada de `America/New_York` — nao de uma tabela de datas que
alguem precisaria manter todo ano.

**Futuro (WIN) NAO desloca**: 09:00..18:24 cru nos dois lados das duas
viradas. Por isso este modulo fala de ACAO, e o perfil do WIN em
`backtest/intraday/profiles.py` segue com corte fixo proprio.

Fronteira mais fraca declarada: o after-market. Ele quase nao imprime
negocio em `PETR4` (14 de 15 sessoes de agosto/2026 sem nenhuma barra depois
do leilao), entao `after_hours_end` e' o numero pesquisado deslocado pelo
mesmo 1h, e nao uma medicao. Isso e' aceitavel porque essa fronteira nao
muda decisao nenhuma: `live.clock.session_date` trata `AFTER_HOURS` e
`POST_CLOSE` do mesmo jeito.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

#: fuso do mercado (e do relogio do servidor MT5 da Rico — ver docstring).
SAO_PAULO: ZoneInfo = ZoneInfo("America/Sao_Paulo")

#: fuso que DIRIGE o deslocamento de 1h do pregao de acoes da B3.
NEW_YORK: ZoneInfo = ZoneInfo("America/New_York")

#: fuso em que o servidor MT5 da corretora entrega `time` (medido, ver
#: docstring). E' um FUSO, nao um offset, de proposito.
MT5_SERVER_TIMEZONE: ZoneInfo = SAO_PAULO

#: papel de referencia para CONFERIR o relogio do servidor. Tem de ser o mais
#: liquido possivel: a conferencia compara a idade do ultimo tick com o offset
#: declarado, e num papel iliquido "tick velho" e "fuso errado" sao
#: indistinguiveis — foi exatamente assim que uma autocalibracao adotou +4h
#: usando o tick parado da PMAM3 (ver `live/feed.py::MT5Feed`).
CLOCK_REFERENCE_TICKER: str = "PETR4.SA"

# ---------- fronteiras do dia (hora de Brasilia) ------------------------

#: abertura do continuo. NAO desloca com o horario de verao dos EUA —
#: medido igual (10:00..10:03 cru) nos dois regimes.
OPEN: time = time(10, 0)

#: abertura do continuo na quarta-feira de cinzas (meio pregao).
OPEN_HALF_DAY: time = time(13, 0)

#: quanto o leilao de abertura antecede a abertura do continuo. A B3 nao muda
#: a DURACAO do leilao no meio pregao, so o horario — por isso e' um
#: deslocamento, nao um horario fixo.
PRE_OPEN_LEAD: timedelta = timedelta(minutes=15)

# Fronteiras de FECHAMENTO no regime de horario PADRAO dos EUA (inverno no
# hemisferio norte). Sob horario de verao americano, todas as tres andam
# `_US_DST_SHIFT` para tras — ver `us_dst` e a medicao na docstring.
_CONTINUOUS_END_US_STANDARD: time = time(17, 55)
_CLOSING_AUCTION_END_US_STANDARD: time = time(18, 0)
_AFTER_HOURS_END_US_STANDARD: time = time(18, 30)

_US_DST_SHIFT: timedelta = timedelta(hours=1)


@lru_cache(maxsize=None)
def us_dst(d: date) -> bool:
    """True se o horario de verao dos EUA esta em vigor em `d`.

    Meio-dia em Nova York e' usado como instante de referencia so para ficar
    longe das duas horas ambiguas da propria virada (que acontece as 02:00
    local, num domingo — nunca num dia de pregao).
    """
    meio_dia_ny = datetime(d.year, d.month, d.day, 12, tzinfo=NEW_YORK)
    return meio_dia_ny.dst() != timedelta(0)


def _shift(t: time, d: date) -> time:
    """Aplica o deslocamento de horario de verao americano a uma fronteira de
    fechamento. Aritmetica de `time` via `datetime` porque `time` nao soma."""
    if not us_dst(d):
        return t
    base = datetime.combine(date(2000, 1, 1), t) - _US_DST_SHIFT
    return base.time()


def continuous_end(d: date) -> time:
    """Fim da negociacao continua em `d` (hora de Brasilia): 16:55 sob horario
    de verao dos EUA, 17:55 fora dele."""
    return _shift(_CONTINUOUS_END_US_STANDARD, d)


def closing_auction_end(d: date) -> time:
    """Fim do leilao de fechamento em `d` (hora de Brasilia). E' a fronteira
    a partir da qual o dado do pregao esta COMPLETO — `live.clock.session_date`
    so passa a apontar para hoje depois dela."""
    return _shift(_CLOSING_AUCTION_END_US_STANDARD, d)


def after_hours_end(d: date) -> time:
    """Fim do after-market em `d` (hora de Brasilia). Fronteira mais fraca
    deste modulo (ver docstring) — nao muda decisao nenhuma."""
    return _shift(_AFTER_HOURS_END_US_STANDARD, d)


@lru_cache(maxsize=None)
def closing_bar_minute_utc(d: date) -> time:
    """Rotulo, em UTC, da ULTIMA barra M1 do pregao de acoes de `d`.

    E' o corte de flatten forcado de um robo intradiario, e por isso tem de
    ser o rotulo da ultima barra — nao o instante do fechamento. Uma barra M1
    do MT5 e' rotulada pela ABERTURA dela (a barra "16:54" cobre
    16:54:00..16:54:59 e carrega o negocio do leilao), entao o corte e'
    `continuous_end - 1min`:

        16:55 Brasilia (DST dos EUA)   -> barra 16:54 -> 19:54 UTC
        17:55 Brasilia (padrao)        -> barra 17:54 -> 20:54 UTC

    Um corte em 16:55 cheio nunca casaria com barra nenhuma e o flatten
    dependeria do fim do DADO, nao do fim do PREGAO — que e' diferente no dia
    em que o papel para de negociar mais cedo.
    """
    fim = datetime.combine(d, continuous_end(d), tzinfo=SAO_PAULO) - timedelta(minutes=1)
    return fim.astimezone(timezone.utc).time()


#: Quantos minutos ANTES do fim do pregao o robo tem de estar achatado.
#:
#: Ordem do dono, 2026-09-14, depois de ver a posicao do `copa_win` atravessar
#: o corte das 18:25 sem fechar: "finalizar as ordens ao menos uns 5 minutos
#: antes do pregao finalizar".
#:
#: Nao e' margem de PRECO -- medido nos parquets canonicos, o livro nao alarga
#: no fim (spread mediano 1 tick ate' a ultima barra) e ate' o pior minuto tem
#: contraparte de sobra para 1-2 contratos (WIN@ minimo 766 contratos na barra
#: 21:24; WDO@ minimo 43 na 21:29). E' margem de CHANCES: o achatamento dispara
#: na PRIMEIRA barra a partir do corte (`ts.time() >= corte`, `machine.
#: on_closed_bar` secao 2), entao a distancia entre o corte e o fim da janela
#: de atividade e' literalmente quantas barras o robo tem para conseguir sair.
#: Com corte colado no fim, essa distancia e' ZERO e basta um engasgo do feed
#: para a posicao virar overnight -- o terminal MT5 ja parou de entregar tick
#: novo por 44,8 min sem erro nenhum (2026-09-08, custou R$116). Ver o item
#: 4.28 de LICOES_DE_PRODUCAO.md.
FOLGA_ACHATAMENTO_MINUTOS: int = 5


@lru_cache(maxsize=None)
def flatten_cut_utc(d: date) -> time:
    """Rotulo, em UTC, da barra a partir da qual um robo de ACAO acha a posicao.

    E' `closing_bar_minute_utc` recuado de `FOLGA_ACHATAMENTO_MINUTOS` -- o
    corte que o motor compara, enquanto aquela funcao continua respondendo a
    pergunta FACTUAL que ela sempre respondeu ("qual e' o rotulo da ultima
    barra do pregao"). Sao duas perguntas diferentes e por isso duas funcoes:
    misturar as duas foi exatamente o que quebrou o lado do FUTURO (item 4.28
    de LICOES_DE_PRODUCAO.md), onde um campo so' fazia o trabalho de tres.

        16:55 Brasilia (DST dos EUA)   -> corte 16:50 -> 19:50 UTC
        17:55 Brasilia (padrao)        -> corte 17:50 -> 20:50 UTC

    O robo continua autorizado a agir ate' o fim do leilao de fechamento
    (`live.clock.phase` devolve `CLOSING_AUCTION` depois de `continuous_end`,
    e `run_once` aceita essa fase), entao o corte tem ~10 minutos de barras
    para acontecer em vez de uma so'."""
    fim = datetime.combine(d, continuous_end(d), tzinfo=SAO_PAULO) - timedelta(
        minutes=FOLGA_ACHATAMENTO_MINUTOS)
    return fim.astimezone(timezone.utc).time()


# ---------- relogio do servidor MT5 ------------------------------------

def server_utc_offset_hours(instant: datetime | None = None) -> float:
    """Horas a SOMAR ao relogio cru do servidor MT5 para chegar em UTC.

    Derivado de `MT5_SERVER_TIMEZONE`, nunca de uma constante — ver a
    justificativa na docstring do modulo. Hoje devolve sempre +3.0.

    `instant` e' o momento a que o offset se refere (default: agora). Importa
    apenas se o fuso do servidor passar a ter horario de verao.
    """
    ref = instant or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    deslocamento = ref.astimezone(MT5_SERVER_TIMEZONE).utcoffset()
    assert deslocamento is not None  # ZoneInfo sempre resolve
    return -deslocamento.total_seconds() / 3600.0


def server_wall_clock_to_utc(wall: datetime) -> datetime:
    """Converte um instante lido do relogio do servidor MT5 (o campo `time`
    cru, que parece UTC mas e' hora local do servidor) para UTC de verdade.

    Recebe o valor CRU, ja decodificado como datetime naive ou marcado como
    UTC por engano — os dois casos sao tratados como "hora de parede do
    servidor", que e' o que o numero realmente e'.
    """
    parede = wall.replace(tzinfo=MT5_SERVER_TIMEZONE)
    return parede.astimezone(timezone.utc)


def utc_to_server_wall_clock(instant: datetime) -> datetime:
    """Inverso de `server_wall_clock_to_utc`: o instante UTC escrito no
    relogio de parede do servidor, NAIVE.

    Existe porque as APIs de JANELA do terminal (`copy_rates_range`,
    `copy_ticks_range`) interpretam os limites que recebem no relogio do
    SERVIDOR, nao em UTC. Quem pede "os ticks desde 19:30 UTC" sem converter
    pede, na verdade, 19:30 de Brasilia — tres horas de dado a mais ou a
    menos, dependendo do sinal.

    Devolve naive de proposito: um datetime com `tzinfo` faria o pacote
    `MetaTrader5` reinterpreta-lo, e o valor tem de chegar la exatamente como
    o numero de parede que e'.
    """
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(MT5_SERVER_TIMEZONE).replace(tzinfo=None)
