# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 16
(`WinBuscaLucroG16Retangulo250`).

Nao reimplementa utilitarios ja genericos desta linha de pesquisa -- importa:
  - `g05_base` (br/carrega_win/dias_da_janela/bars_dos_dias/ic95_wilson/
    consistencia/monta_config/CAPITAL/MARGEM_WIN_BRL/cortes IS-OOS1)
  - `g15_base` (concentracao_topn/maior_sequencia_perdas/ruina_do_resultado/
    constancia_motor/resumo/censurado/imprime_resumo -- generico, nao
    especifico da G15, usa `motor.py` de rodada4/decisao por baixo)
  - `g13_base` (censura_separada -- item 6.51 de LICOES_DE_PRODUCAO.md,
    generico, e CORTE_OOS2_FIM)

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Fila: WIN@ NAO tem fidelidade calibrada -- toda ordem-limite enche no TOQUE
(`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`), premissa OTIMISTA e
IDENTICA em todas as janelas (precedente `WinRetangulo`/G1-G15). Para o ALVO
desta geracao (que pode mirar bem alem da borda oposta do retangulo) essa
premissa e' mais otimista do que para a entrada -- ver docstring da classe.

Capital: R$250,00 real (NAO R$1.100 da producao do `WinRetangulo`), 1
contrato FIXO -- mandato da G16.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g15_portfolio_orcamento"))
import g15_base as g15b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g13_orb_grade_fina"))
import g13_base as g13b  # noqa: E402

br = g05b.br
carrega_win = g05b.carrega_win
dias_da_janela = g05b.dias_da_janela
bars_dos_dias = g05b.bars_dos_dias
ic95_wilson = g05b.ic95_wilson
consistencia = g05b.consistencia

CSV_WIN = g05b.CSV_WIN
SYMBOL = g05b.SYMBOL
CAPITAL = g05b.CAPITAL
MARGEM_WIN_BRL = g05b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g05b.CORTE_IS_INICIO
CORTE_IS_FIM = g05b.CORTE_IS_FIM
CORTE_OOS1_FIM = g05b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g13b.CORTE_OOS2_FIM

concentracao_topn = g15b.concentracao_topn
maior_sequencia_perdas = g15b.maior_sequencia_perdas
ruina_do_resultado = g15b.ruina_do_resultado
constancia_motor = g15b.constancia_motor
resumo = g15b.resumo
censurado = g15b.censurado
imprime_resumo = g15b.imprime_resumo
censura_separada = g13b.censura_separada


def monta_config(capital: float = CAPITAL):
    return g05b.monta_config(capital)


def roda(dias_operar: list, capital: float = CAPITAL, congelado: bool = False,
         **kwargs_estrategia):
    """Roda `WinBuscaLucroG16Retangulo250` (ou `_congelado_v16` se
    `congelado=True`) nos `dias_operar`. Sem pool causal externo -- a
    deteccao do retangulo usa so' a propria janela deslizante do WIN@."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    if congelado:
        from strategy.daytrade.lab.win_busca_lucro_g16_retangulo_250_congelado_v16 import (
            WinBuscaLucroG16Retangulo250 as Estrategia,
        )
    else:
        from strategy.daytrade.lab.win_busca_lucro_g16_retangulo_250 import (
            WinBuscaLucroG16Retangulo250 as Estrategia,
        )

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(**kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def contagem_bruta_retangulos(dias_operar: list, **kwargs_estrategia) -> dict:
    """Audita (lição 6.48/6.49): quantos retângulos a DETECÇÃO achou (campo
    `_retangulo` setado em algum momento, contado via instrumentação externa)
    vs quantas ordens o motor de fato emitiu. Usa `detecta_retangulo`
    diretamente sobre a mesma janela deslizante, fora da classe, para contar
    ocorrências BRUTAS sem depender de nenhum portão de capital/pendência."""
    sys.path.insert(0, str(ROOT / "src"))
    import numpy as np
    from strategy.daytrade.lab.win_retangulo import detecta_retangulo

    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    janela_barras = int(kwargs_estrategia.get("janela_barras", 20))
    tolerancia = float(kwargs_estrategia.get("tolerancia_borda", 0.20))
    largura_minima = float(kwargs_estrategia.get("largura_minima_pontos", 328.0))

    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)
    dias_arr = bars.index.date

    brutos = 0
    brutos_largura_ok = 0
    dias_com_deteccao = set()
    W = janela_barras
    n = len(bars)
    dia_inicio = {}
    for i, d in enumerate(dias_arr):
        if d not in dia_inicio:
            dia_inicio[d] = i
    for i in range(3 * W, n):
        # nunca cruza a virada do pregao -- mesma regra de on_session_start
        if dia_inicio[dias_arr[i]] > i - 3 * W:
            continue
        h, l, c = high[i - W:i], low[i - W:i], close[i - W:i]
        ha = high[i - 3 * W:i - W]
        la = low[i - 3 * W:i - W]
        amplitude_anterior = float(ha.max() - la.min()) if len(ha) else None
        ret = detecta_retangulo(h, l, c, amplitude_anterior, tolerancia=tolerancia)
        if ret is None:
            continue
        brutos += 1
        dias_com_deteccao.add(dias_arr[i])
        if ret["largura"] >= largura_minima:
            brutos_largura_ok += 1
    return dict(brutos=brutos, brutos_largura_ok=brutos_largura_ok,
                dias_com_deteccao=len(dias_com_deteccao))
