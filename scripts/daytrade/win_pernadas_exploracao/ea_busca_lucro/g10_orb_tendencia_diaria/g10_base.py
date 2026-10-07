# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 10
(`WinBuscaLucroG10OrbTendenciaDiaria`).

Reusa `g08_base` por IMPORT (nao duplica) para tudo que nao muda entre as
duas geracoes -- `br`, `carrega_win`, `dias_da_janela`, `bars_dos_dias`,
`ic95_wilson`, `consistencia`, `concentracao_topn`, `monta_config`,
`ruina_do_resultado`, `constancia_motor`, `sizing_motor`, `CAPITAL`,
`MARGEM_WIN_BRL`, os cortes de janela, e a propria `roda` da G08 (usada aqui
so' para recalcular a linha de REFERENCIA "sem filtro" lado a lado). A UNICA
coisa nova desta geracao e' o filtro de tendencia diaria: `compute_direcao_
diaria` (causal) e `roda`/`roda_congelado` da classe G10.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior PARA MEDIR P&L -- mas o calculo da media/
inclinacao de N dias PODE (e precisa) olhar para tras de jan/2026 so' para
ter burn-in (ex.: MA50 em 2/jan/2026 usa fechamentos diarios de nov-dez/2025,
ja' presentes no CSV completo desde 2021) -- mesmo espirito do burn-in causal
da Geracao 4. Isto e' so' CALCULAR o indicador, nunca abre a janela de
jan/2026 pra tras como periodo de medicao/trade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g08_orb_sobrevivencia"))
import g08_base as g08b  # noqa: E402

br = g08b.br
carrega_win = g08b.carrega_win
dias_da_janela = g08b.dias_da_janela
bars_dos_dias = g08b.bars_dos_dias
ic95_wilson = g08b.ic95_wilson
consistencia = g08b.consistencia
concentracao_topn = g08b.concentracao_topn
monta_config = g08b.monta_config
ruina_do_resultado = g08b.ruina_do_resultado
constancia_motor = g08b.constancia_motor
sizing_motor = g08b.sizing_motor

CSV_WIN = g08b.CSV_WIN
SYMBOL = g08b.SYMBOL
CAPITAL = g08b.CAPITAL
MARGEM_WIN_BRL = g08b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g08b.CORTE_IS_INICIO
CORTE_IS_FIM = g08b.CORTE_IS_FIM
CORTE_OOS1_FIM = g08b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g08b.CORTE_OOS2_FIM

#: Geometria herdada do vencedor composto da G8 -- esta geracao NAO revisita
#: o eixo de stop/alvo, so' o filtro de tendencia por cima dele.
GEOMETRIA_G8_VENCEDORA = dict(
    range_minutos=5.0,
    stop_min_pontos=50.0,
    stop_max_pontos=140.0,
    alvo_multiplo=3.0,
    buffer_entrada_pontos=20.0,
    ttl_barras_entrada=10,
)


def compute_direcao_diaria(win_full: pd.DataFrame, modo: str, n: int,
                            janela_inclinacao: int = 5) -> dict:
    """Filtro de tendencia diaria, CAUSAL por construcao -- o fechamento do
    proprio dia D NUNCA entra no calculo usado para decidir o dia D (so'
    fechamentos ATE' D-1, via `.shift(1)` depois de agregar o M1 em
    fechamento diario).

    `win_full` e' o DataFrame M1 completo (2021-2026, carregado uma vez por
    `carrega_win()`) -- usar a base inteira aqui e' so' BURN-IN do indicador
    (a MA de N dias precisa de N dias ANTERIORES para existir ja' em
    jan/2026), nunca abertura de 2025 como periodo de medicao de P&L: nenhuma
    operacao e' simulada fora das janelas IS/OOS-1/OOS-2 definidas acima.

    `modo`:
      - "nivel": `direcao[D] = sinal(fechamento[D-1] - MA_N[D-1])` -- posicao
        do fechamento de ONTEM em relacao a` media movel de N dias (tambem
        calculada so' com dados ate' D-1).
      - "inclinacao": `direcao[D] = sinal(MA_N[D-1] - MA_N[D-1-janela_inclinacao])`
        -- se a propria media esta' subindo ou descendo nos ultimos
        `janela_inclinacao` dias (medida ate' D-1).

    Retorna `dict[date, int]` com `1`=favorece LONG, `-1`=favorece SHORT,
    `0`=neutro ou burn-in insuficiente (bloqueia os dois lados -- "nunca
    contra a tendencia" inclui "nunca sem tendencia definida")."""
    daily_close = win_full.groupby(win_full.index.date)["close"].last()
    daily_close.index = pd.to_datetime(daily_close.index)
    daily_close = daily_close.sort_index()

    ma = daily_close.rolling(n).mean()
    close_prev = daily_close.shift(1)
    ma_prev = ma.shift(1)

    sinal = pd.Series(0, index=daily_close.index, dtype=int)
    if modo == "nivel":
        valido = ma_prev.notna() & close_prev.notna()
        sinal[valido & (close_prev > ma_prev)] = 1
        sinal[valido & (close_prev < ma_prev)] = -1
    elif modo == "inclinacao":
        ma_prev_ref = ma_prev.shift(janela_inclinacao)
        slope = ma_prev - ma_prev_ref
        valido = slope.notna()
        sinal[valido & (slope > 0)] = 1
        sinal[valido & (slope < 0)] = -1
    else:
        raise ValueError(f"modo desconhecido: {modo!r}")

    return {idx.date(): int(v) for idx, v in sinal.items()}


def roda(dias_operar: list, direcao_kwargs: dict, capital: float = CAPITAL,
         **kwargs_estrategia):
    """Roda `WinBuscaLucroG10OrbTendenciaDiaria` nos `dias_operar`. A
    tendencia e' computada sobre a base COMPLETA (`carrega_win()`, 2021-2026)
    para ter burn-in causal -- ver `compute_direcao_diaria`."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g10_orb_tendencia_diaria import (
        WinBuscaLucroG10OrbTendenciaDiaria,
    )

    win = carrega_win()
    direcao = compute_direcao_diaria(win, **direcao_kwargs)
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG10OrbTendenciaDiaria(direcao_diaria=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_congelado(dias_operar: list, direcao_kwargs: dict, capital: float = CAPITAL,
                    **kwargs_estrategia):
    """Mesmo papel de `g08_base.roda_congelado` -- importa a classe do
    modulo CONGELADO (`..._congelado_v10`), nunca do modulo vivo."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g10_orb_tendencia_diaria_congelado_v10 import (
        WinBuscaLucroG10OrbTendenciaDiaria as WinBuscaLucroG10OrbTendenciaDiariaCongelado,
    )

    win = carrega_win()
    direcao = compute_direcao_diaria(win, **direcao_kwargs)
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG10OrbTendenciaDiariaCongelado(direcao_diaria=direcao, **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_referencia_sem_filtro(dias_operar: list, capital: float = CAPITAL):
    """Recalcula a linha de REFERENCIA (vencedor composto da G8, SEM filtro
    de tendencia) dentro desta geracao, reusando `g08_base.roda` direto, para
    comparacao lado a lado na mesma tabela/janela."""
    return g08b.roda(dias_operar, capital=capital, **GEOMETRIA_G8_VENCEDORA)
