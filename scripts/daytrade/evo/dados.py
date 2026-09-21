"""As BASES e as JANELAS do projeto evolutivo do WDO@ -- um lugar so', para
nenhum script redigitar um corte de data ou um caminho de parquet.

## Por que existem DUAS granularidades, e qual manda

Medido nesta maquina, um pregao do WDO@ pelo motor de producao
(`run_intraday_backtest`):

    base   barras/pregao   tempo/pregao
    tick      ~256.800        74,9 s
    M1            ~570         0,21 s      <- 357x mais barato

Uma evolucao de 120 individuos x 60 geracoes faz ~7.200 avaliacoes. Em tick
isso seria 7.200 x 72 x 75s = 43.200 horas de CPU. Nao ha escolha: a BUSCA
roda em M1.

Mas M1 nao e' o mundo -- e' um SURROGADO, e todo surrogado tem um desvio que
so' existe se for medido. O desvio conhecido aqui e' a FILA DA ENTRADA: o
motor credita o volume INTEIRO da barra contra a fila sempre que a barra toca
o nivel, e num minuto quase todo esse volume negociou em OUTROS precos. Em
base de tick a barra e' um negocio so', num preco so', e a conta e' honesta.
Consequencia: **em M1 a ordem-limite preenche facil demais** -- exatamente o
tipo de folga que uma busca evolutiva encontra e passa a explorar.

Por isso a regra deste projeto, que vale para toda medicao daqui:

  1. a BUSCA roda em M1 com a fila deliberadamente PESSIMISTA (ver
     `evo_m1_vs_tick_2026_09_18.py`, que mede de quanto tem de ser o
     agravamento para o M1 parar de ser mais generoso que o tick);
  2. todo FINALISTA e' re-medido no tick, pelo mesmo motor, e o numero que
     vale e' o do tick. Se os dois discordarem, quem manda e' o tick e o
     genoma morre;
  3. errar para o lado PESSIMISTA e' seguro e errar para o otimista nao e':
     um surrogado duro so' pode subestimar o individuo, e a confirmacao em
     tick so' pode melhorar. Foi o erro de sinal do motor sem fila
     (+R$3,82/op previsto contra -R$3,00 realizado) que ensinou a direcao em
     que vale a pena errar.

## As janelas

O corte IS/OOS NAO e' escolhido aqui: e' o mesmo que `WDO_A_f1.parquet`
carrega na coluna `janela` e que toda a linha do WDO ja' usou. Reusar o corte
de sempre e' o que mantem os resultados comparaveis com o que ja' foi medido;
inventar um corte novo agora seria escolher a janela depois de conhecer o
terreno.

    IS     2026-02-27 .. 2026-06-12   72 pregoes
    OOS    2026-06-15 .. 2026-08-25   51 pregoes

E o IS e' subdividido mais uma vez, e essa parte e' nova:

    TREINO 2026-02-27 .. 2026-05-14   48 pregoes  <- o fitness ve
    VALID  2026-05-15 .. 2026-06-12   24 pregoes  <- so' a escolha do finalista ve

A evolucao inteira acontece contra TREINO. VALID existe para escolher QUAL
individuo do hall da fama vai ao OOS, e nao entra no fitness de nenhuma
geracao. Sem essa terceira janela, escolher o melhor de 7.200 individuos pelo
proprio numero que os selecionou seria gastar o OOS para descobrir algo que o
IS ja' podia ter dito -- e o OOS so' pode ser gasto uma vez.
"""
from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]

SYMBOL = "WDO@"
TICK_SIZE = 0.5
#: (valor do tick de NEGOCIACAO, tamanho do tick de NEGOCIACAO) do WDO@ lidos
#: do terminal. Repetidos da linha do ORB de proposito -- a serie continua
#: reporta `0,001` como tick, que nao e' o que o WDOV26 negocia.
ECONOMIA_WDO = (0.01, 0.001)

MARGEM_WDO_BRL = 150.0
#: Capital de partida deste projeto. O dono autorizou "ate 500 reais", e a
#: propria docstring do `WdoOrb` ja' registra que R$375 (o piso oficial de
#: PARTIDA do WDO@) nao sobrevive ao azar COMUM da janela OOS -- so' com
#: R$500 a caminhada inteira se sustenta, e ainda assim tocando R$153,50.
#: Partir de R$375 aqui seria evoluir contra um portao de caixa em vez de
#: contra o mercado.
CAPITAL_PARTIDA_BRL = 500.0

TICK_CANONICO = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
TICK_SEMANA_NOVA = RAIZ / "data" / "raw_ticks" / "WDO_A_semana_2026_09_08.parquet"
#: M1 REAMOSTRADO DO PROPRIO TICK canonico -- e' de proposito, e nao um
#: capricho. O `data/raw_intraday/WDO_A_.parquet` do MT5 e' a serie CONTINUA
#: ajustada: os precos vem fracionarios (5769,053) e portanto FORA da grade
#: de 0,5 que o WDOV26 negocia. Nivel fora da grade nao existe no book, e uma
#: ordem-limite preenchida nele e' um trade impossivel (ver
#: `strategy.daytrade.base.no_tick`). Reamostrar do tick mantem a grade, o
#: volume e a fonte identicos aos da base de confirmacao.
M1_DO_TICK = RAIZ / "data" / "raw_intraday" / "WDO_A_M1_do_tick.parquet"

#: Mediana de barras por minuto na base de TICK do WDO@, MEDIDA (nao
#: chutada) em `evo_m1_vs_tick_2026_09_18.py` sobre os 52 pregoes do TREINO:
#: mediana 349, p25 278, p75 419. Serve para traduzir prazo em MINUTOS (que
#: e' como o genoma pensa) para prazo em BARRAS (que e' o que o motor conta),
#: sem o erro que o CLAUDE.md descreve: `ttl_bars` conta BARRAS, e em base de
#: tick isso nao e' tempo.
#:
#: A dispersao (278 a 419 entre o 1o e o 3o quartil) e' o motivo de o prazo
#: NAO poder morar em barras no genoma: o mesmo `ttl_bars` significa 20% a
#: menos de tempo num pregao agitado, que e' exatamente quando o prazo
#: importa.
BARRAS_POR_MINUTO = {"m1": 1.0, "tick": 349.0}

#: Agravamento da fila aplicado SO' na base M1, medido em
#: `evo_m1_vs_tick_2026_09_18.py`. O motor credita o volume INTEIRO da barra
#: contra a fila quando a barra toca o nivel, e num minuto do WDO isso sao
#: milhares de contratos negociados em varios precos -- a fila calibrada
#: (329/494) e' varrida por um unico minuto ativo e nao morde nada.
#:
#: Medido com o `wdo_orb` de producao, 52 pregoes, contra a referencia em
#: TICK (73 operacoes, +R$44,36/op):
#:
#:     multiplicador   trades   R$/op
#:     x1                  77   +38,33
#:     x3 / x6 / x10       77   ~+38
#:     x20                 77   +38,01
#:     x40                 73   +28,61   <- unico nao-generoso nos DOIS eixos
#:
#: LIMITACAO, e ela e' seria: o `wdo_orb` faz ~1,5 operacao por pregao e
#: posta pouquissimas ordens. Como sonda do mecanismo de preenchimento ele e'
#: FRACO -- de x1 a x20 a contagem de operacoes nem se mexe (77 nas quatro),
#: o que significa que esta calibracao nao distingue esses quatro casos, so'
#: sabe que x40 aperta. Um genoma que opere muito mais vezes por dia apoia-se
#: no preenchimento muito mais do que esta sonda apoiou.
#:
#: Por isso x40 nao e' "o numero certo": e' o mais duro que foi medido, na
#: direcao em que errar e' seguro (o M1 so' pode subestimar o individuo). O
#: que fecha a conta de verdade e' a re-medicao de todo finalista em TICK,
#: que deixa de ser zelo e vira condicao.
FILA_MULTIPLICADOR_M1 = 40.0

JANELAS = {
    "TREINO": ("2026-02-27", "2026-05-14"),
    "VALID": ("2026-05-15", "2026-06-12"),
    "IS": ("2026-02-27", "2026-06-12"),
    "OOS": ("2026-06-15", "2026-08-25"),
}


def ttl_barras(minutos: float, feed: str) -> int:
    """Prazo em MINUTOS -> prazo em BARRAS do feed. O genoma so' conhece
    minutos; quem sabe quantas barras cabem num minuto e' a base."""
    return max(1, int(round(minutos * BARRAS_POR_MINUTO[feed])))


@functools.lru_cache(maxsize=1)
def _m1_completo() -> pd.DataFrame:
    df = pd.read_parquet(M1_DO_TICK)
    return df[["open", "high", "low", "close", "volume"]]


def pregoes(janela: str) -> list[str]:
    """Os dias de pregao de uma janela, em ordem. Sai da base M1 (que cobre
    os mesmos dias do tick, por construcao)."""
    ini, fim = JANELAS[janela]
    df = _m1_completo()
    dias = pd.Series(pd.DatetimeIndex(df.index).date).astype(str).unique()
    return sorted(d for d in dias if ini <= d <= fim)


def bars_m1(dia: str) -> pd.DataFrame:
    """Barras M1 de UM pregao, direto do cache em memoria."""
    df = _m1_completo()
    return df.loc[dia]


def bars_tick(dia: str) -> pd.DataFrame:
    """Barras DEGENERADAS (1 negocio = 1 barra) de UM pregao. Le' o parquet a
    cada chamada de proposito: a base inteira nao cabe confortavelmente em
    memoria, e a confirmacao em tick roda um pregao por processo."""
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars

    ini = pd.Timestamp(dia, tz="UTC")
    fim = ini + pd.Timedelta(days=1)
    pedacos = []
    for caminho in (TICK_CANONICO, TICK_SEMANA_NOVA):
        if not caminho.exists():
            continue
        df = pd.read_parquet(
            caminho, columns=["last", "volume", "volume_real"],
            filters=[("time", ">=", ini), ("time", "<", fim)],
        )
        if not df.empty:
            pedacos.append(df)
    if not pedacos:
        return pd.DataFrame()
    ticks = pd.concat(pedacos).sort_index(kind="mergesort")
    ticks = ticks[~ticks.reset_index().duplicated().values]
    return ticks_to_degenerate_bars(ticks)
