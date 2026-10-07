# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 11
(`WinBuscaLucroG11OrbTamanhoGraduado`).

Mesmo molde de `g08_orb_sobrevivencia/g08_base.py` -- importado DIRETO
(nao duplicado): `carrega_win`, `dias_da_janela`, `bars_dos_dias`,
`ic95_wilson`, `consistencia`, `concentracao_topn`, `monta_config`,
`ruina_do_resultado`, `constancia_motor`, `sizing_motor`, `motor` (modulo
`rodada4/decisao/motor.py` -- `ruina_mc`, `ruina_formula`, `p_encolhido`,
`tamanho`, `metricas_constancia`). So' a FUNCAO `roda`/`roda_congelado` e'
nova aqui, apontando para a classe da G11 em vez da G08.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes -- toda definicao
          de corte de balde de forca, so' aqui)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente `WinRetangulo`/G1-G10).

Capital: R$250,00 (margem crua R$100 x buffer 2,0 x reserva 1,25 -- o piso de
PARTIDA real do WIN@, ver CLAUDE.md "Capital inicial: sempre o minimo real").
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g08_orb_sobrevivencia"))
import g08_base as g08b  # noqa: E402

motor = g08b.motor

br = g08b.br
carrega_win = g08b.carrega_win
dias_da_janela = g08b.dias_da_janela
bars_dos_dias = g08b.bars_dos_dias
ic95_wilson = g08b.ic95_wilson
consistencia = g08b.consistencia
concentracao_topn = g08b.concentracao_topn
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

#: Geometria herdada do vencedor composto da G8 -- esta geracao NAO
#: revisita stop/alvo, so' o filtro de forca (ver docstring da classe).
GEOMETRIA_G8 = dict(
    range_minutos=5.0,
    stop_min_pontos=50.0,
    stop_max_pontos=140.0,
    alvo_multiplo=3.0,
    buffer_entrada_pontos=20.0,
    ttl_barras_entrada=10,
)


def monta_config(capital: float = CAPITAL):
    return g08b.monta_config(capital)


def roda(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Roda `WinBuscaLucroG11OrbTamanhoGraduado` nos `dias_operar`. Sem pool
    causal externo -- o ORB nao depende de historico de dias ANTERIORES (a
    faixa de abertura e' calculada dentro do proprio pregao); o filtro de
    forca tambem e' causal dentro do proprio pregao (so' usa a faixa ja'
    fechada e o fechamento da barra de rompimento)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g11_orb_tamanho_graduado import (
        WinBuscaLucroG11OrbTamanhoGraduado,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG11OrbTamanhoGraduado(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def roda_congelado(dias_operar: list, capital: float = CAPITAL, **kwargs_estrategia):
    """Mesmo papel de `g08_base.roda_congelado` -- importa a classe do
    modulo CONGELADO (`..._congelado_v11`), nunca do modulo vivo, para o
    OOS-1/OOS-2 nao poderem ser afetados por uma edicao posterior de
    `win_busca_lucro_g11_orb_tamanho_graduado.py`."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g11_orb_tamanho_graduado_congelado_v11 import (
        WinBuscaLucroG11OrbTamanhoGraduado as WinBuscaLucroG11Congelado,
    )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG11Congelado(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def quantis_forca(forcas: list, cortes=(1 / 3, 2 / 3)) -> tuple[float, float]:
    """Cortes de balde (tercis por default), calculados SO' sobre a
    populacao de forca BRUTA do IS (`strat.stats_forcas` de uma rodada com
    `forca_min=0, forca_max=inf` -- sem filtro nenhum, idêntico a` G8)."""
    arr = np.asarray(forcas, dtype=float)
    q_baixo, q_alto = np.quantile(arr, cortes)
    return float(q_baixo), float(q_alto)
