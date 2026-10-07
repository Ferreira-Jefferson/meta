"""Utilitarios compartilhados pelos 29 conceitos de CALENDARIO/sazonalidade
(c700-c728): janela de almoco/fechamento, virada de mes, feriados, virada
de ano, vencimento aproximado e combinacoes.

Reaproveita a mecanica de execucao de `_common.py` (`montar_entrada`,
`EXIT_TTL_BARS_SEM_PRAZO`, `alvo_com_piso`) -- desenho de execucao FECHADO
(CLAUDE.md, ordem do dono 2026-09-10): entrada sempre `EnterLimit` parada no
livro, alvo sempre ordem-limite real fatiada SEM prazo, piso de 4 ticks no
alvo, todo preco na grade do tick.

O que muda aqui e' so' a DETECCAO de data especial -- regra deterministica a
partir do proprio indice de `bars` recebido em `initialize`, sem I/O
externo (AGENTS.md: `strategy/` so' importa `core`; nenhuma destas funcoes
faz rede/arquivo, so' olha o DataFrame que ja' chegou):

- `calendar_gaps`: feriado detectado como GAP DE CALENDARIO -- entre duas
  datas de pregao consecutivas, se existir >=1 dia UTIL (seg-sex) sem
  pregao no meio, um feriado se escondeu ali. Mais robusto que tabela fixa
  de feriados moveis (nao exige manutencao ano a ano) e cobre exatamente o
  caso pedido no catalogo.
- `month_boundaries` / `year_boundaries`: primeiro/ultimo pregao de cada
  mes/ano presente. O ULTIMO pregao do mes tambem serve de APROXIMACAO do
  "dia de vencimento" do WDO (o simbolo continuo `WDO@` nao carrega o mes
  do contrato; vencimento real e' o ultimo dia util do mes ANTERIOR ao
  mes-codigo, mas para o continuo a aproximacao razoavel e' o ultimo
  pregao do proprio mes -- documentado de novo em cada arquivo que usa
  isto).
- `nth_business_day_of_month` / `nth_business_day_of_month_from_end`: o
  N-esimo pregao (do inicio ou do fim) de cada mes -- "5o dia util",
  "1o/10o/20o dia util", "penultimo pregao do mes" (vespera do
  vencimento aproximado).
- `month_last_close` / `december_return_by_year`: series derivadas de
  PRECO fechadas em meses anteriores, usadas so' para o dia seguinte
  (gap de virada de mes, momentum de virada de ano) -- nunca olham o
  proprio dia em curso.
"""
from __future__ import annotations

from datetime import date, time

import pandas as pd

from strategy.daytrade.lab.lab_concepts2._common import (
    EXIT_TTL_BARS_SEM_PRAZO, PISO_ALVO_TICKS, alvo_com_piso, clamp_quantity,
    montar_entrada,
)

__all__ = [
    "EXIT_TTL_BARS_SEM_PRAZO", "PISO_ALVO_TICKS", "alvo_com_piso", "clamp_quantity",
    "montar_entrada", "trading_dates", "calendar_gaps", "month_boundaries",
    "year_boundaries", "nth_business_day_of_month", "nth_business_day_of_month_from_end",
    "month_last_close", "december_return_by_year", "week_of_month",
]


def trading_dates(bars: pd.DataFrame) -> list[date]:
    """Datas UNICAS (ordem crescente) em que houve pregao no historico
    recebido -- a base de tudo abaixo."""
    idx = pd.DatetimeIndex(bars.index)
    return sorted({ts.date() for ts in idx})


def calendar_gaps(dates: list[date]) -> tuple[set[date], set[date]]:
    """Detecta feriado via GAP DE CALENDARIO: entre duas datas de pregao
    consecutivas, se existir pelo menos um dia UTIL (seg-sex) sem pregao no
    meio, esse intervalo escondeu um feriado. Devolve `(vesperas,
    pos_feriado)` -- a ultima data ANTES do gap e a primeira data DEPOIS
    dele, para cada gap encontrado."""
    vesperas: set[date] = set()
    pos_feriado: set[date] = set()
    for prev, curr in zip(dates, dates[1:]):
        meio = pd.bdate_range(
            start=prev + pd.Timedelta(days=1), end=curr - pd.Timedelta(days=1),
        )
        if len(meio) > 0:
            vesperas.add(prev)
            pos_feriado.add(curr)
    return vesperas, pos_feriado


def _agrupar_por_mes(dates: list[date]) -> dict[tuple[int, int], list[date]]:
    by_month: dict[tuple[int, int], list[date]] = {}
    for d in dates:
        by_month.setdefault((d.year, d.month), []).append(d)
    return by_month


def month_boundaries(dates: list[date]) -> tuple[set[date], set[date]]:
    """`(primeiros_do_mes, ultimos_do_mes)` -- data de pregao INICIAL e
    FINAL de cada mes presente. `ultimos_do_mes` tambem aproxima o "dia de
    vencimento" do WDO continuo (ver docstring do modulo)."""
    by_month = _agrupar_por_mes(dates)
    primeiros = {v[0] for v in by_month.values()}
    ultimos = {v[-1] for v in by_month.values()}
    return primeiros, ultimos


def year_boundaries(dates: list[date]) -> tuple[set[date], set[date]]:
    """`(primeiros_do_ano, ultimos_do_ano)` -- primeiro e ultimo pregao de
    cada ano presente."""
    by_year: dict[int, list[date]] = {}
    for d in dates:
        by_year.setdefault(d.year, []).append(d)
    primeiros = {v[0] for v in by_year.values()}
    ultimos = {v[-1] for v in by_year.values()}
    return primeiros, ultimos


def nth_business_day_of_month(dates: list[date], n: int) -> set[date]:
    """Data que e' o N-esimo pregao (1-indexado, a partir do INICIO) de
    cada mes presente."""
    by_month = _agrupar_por_mes(dates)
    return {v[n - 1] for v in by_month.values() if len(v) >= n}


def nth_business_day_of_month_from_end(dates: list[date], n: int) -> set[date]:
    """Data que e' o N-esimo pregao contado a partir do FIM de cada mes
    (`n=1` = ultimo pregao, `n=2` = penultimo -- vespera do vencimento
    aproximado)."""
    by_month = _agrupar_por_mes(dates)
    return {v[-n] for v in by_month.values() if len(v) >= n}


def month_last_close(bars: pd.DataFrame) -> dict[tuple[int, int], float]:
    """Fechamento do ULTIMO pregao de cada mes -- para o robo de gap de
    virada de mes comparar a abertura do 1o pregao do mes NOVO contra o
    fechamento do mes ANTERIOR. Assume `bars` ordenado cronologicamente
    (sempre e' -- serie de mercado)."""
    idx = pd.DatetimeIndex(bars.index)
    out: dict[tuple[int, int], float] = {}
    for ts, c in zip(idx, bars["close"]):
        out[(ts.year, ts.month)] = float(c)
    return out


def december_return_by_year(bars: pd.DataFrame) -> dict[int, float]:
    """Retorno (fechamento/abertura - 1) do mes de DEZEMBRO de cada ano
    presente -- usado pelo momentum de "primeiro pregao do ano", que segue
    o movimento liquido do mes anterior (dezembro)."""
    idx = pd.DatetimeIndex(bars.index)
    df = pd.DataFrame({"open": bars["open"].to_numpy(), "close": bars["close"].to_numpy()}, index=idx)
    dez = df[df.index.month == 12]
    out: dict[int, float] = {}
    for ano, grupo in dez.groupby(dez.index.year):
        if len(grupo) == 0:
            continue
        abertura = float(grupo["open"].iloc[0])
        if abertura == 0:
            continue
        out[int(ano)] = float(grupo["close"].iloc[-1]) / abertura - 1.0
    return out


def week_of_month(dia: int) -> int:
    """Semana-do-mes 0-indexada a partir do DIA (1-31): dias 1-7 -> 0,
    8-14 -> 1, 15-21 -> 2, 22-28 -> 3, 29+ -> 4."""
    return (dia - 1) // 7


#: horarios fixos usados pelos conceitos de janela de almoco/fechamento --
#: nomeados para nao espalhar `time(12, 0)` cru pelos 29 arquivos.
INICIO_ALMOCO = time(12, 0)
FIM_ALMOCO = time(13, 30)
FIM_REABERTURA_ALMOCO = time(14, 0)
INICIO_ULTIMA_HORA = time(17, 0)
CORTE_ULTIMOS_20MIN = time(17, 40)
INICIO_COMPARACAO_20MIN = time(17, 20)
INICIO_RUSH_FECHAMENTO = time(17, 45)
FECHAMENTO_FORCADO = time(17, 55)
ABERTURA_SESSAO = time(9, 0)
FIM_FAIXA_ABERTURA = time(9, 30)
