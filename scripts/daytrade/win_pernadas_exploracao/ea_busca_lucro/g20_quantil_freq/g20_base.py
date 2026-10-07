# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 20.

Geracao 20 ataca a CONCENTRACAO temporal do sinal cruzado WIN x WDO (G4/G17)
pela FREQUENCIA, nao pelo tamanho da aposta (G19 ja mostrou que graduar por
magnitude PIORA a concentracao, nao ajuda -- ver ORQUESTRACAO.md). A ideia:
baixar o QUANTIL que define "anomalo" (`estado_anomalo_cruzado`, funcao pura
da G4) para capturar mais episodios (inclusive os menos extremos, que a G19
mostrou estarem mais espalhados no tempo), na esperanca de diluir a
concentracao sem destruir o win%/IC95.

NAO reimplementa nada novo de estrategia -- a classe
`WinBuscaLucroG17CrossWdoCapital1000` ja aceita `alvo_multiplo` em grade
{2x..5x} e capital de teste R$1.000; `estado_anomalo_cruzado` ja aceita
`quantil` como parametro. Esta geracao e' puramente um SWEEP do harness sobre
`quantil` (e, nos quantis mais promissores, cruzado com `alvo_multiplo`) --
por isso reaproveita `g17_base` (que por sua vez reaproveita `g04_base`) por
IMPORT direto, sem copiar nenhuma funcao.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/tuning, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois, 44 pregoes)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior.

Capital de teste = R$1.000 (mandato de 2026-10-05, igual G17-G19). Fila WIN@
nao calibrada (`queue_ahead_qty=0`), premissa otimista identica a` linha
inteira.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g17_capital1000"))
import g17_base as g17b  # noqa: E402

# -- reaproveitado por import direto, nao reimplementado -----------------
br = g17b.br
carrega_win = g17b.carrega_win
carrega_wdo = g17b.carrega_wdo
dias_da_janela = g17b.dias_da_janela
bars_dos_dias = g17b.bars_dos_dias
consistencia = g17b.consistencia
computa_estado = g17b.computa_estado
monta_config = g17b.monta_config
concentracao_topn = g17b.concentracao_topn
maior_sequencia_perdas = g17b.maior_sequencia_perdas
ruina_do_resultado = g17b.ruina_do_resultado
censurado = g17b.censurado

SYMBOL = g17b.SYMBOL
CORTE_IS_INICIO = g17b.CORTE_IS_INICIO
CORTE_IS_FIM = g17b.CORTE_IS_FIM
CORTE_OOS1_FIM = g17b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g17b.CORTE_OOS2_FIM

CAPITAL = g17b.CAPITAL                 # R$1.000 (mandato 2026-10-05)
MARGEM_WIN_BRL = g17b.MARGEM_WIN_BRL    # R$100 -- margem crua, nao muda

# -- vencedor herdado da G17/G4, NAO retunado aqui exceto o quantil -------
JANELA_MIN = 20
DIRECAO_APOSTA = "continuacao"
BUFFER_ENTRADA = 30.0
#: Geometria vencedora da G17 (alvo=4x/stop=150) -- usada como geometria FIXA
#: na curva quantil x frequencia/concentracao (passo 1 do mandato da G20).
ALVO_G17 = 4.0
STOP_G17 = 150.0

QUANTIS = (0.60, 0.65, 0.70, 0.75, 0.80)


def roda(dias_operar: list, dias_historico: list | None = None,
         janela_min: int = JANELA_MIN, quantil: float = 0.75,
         capital: float = CAPITAL, congelado: bool = False,
         **kwargs_estrategia):
    """Repassa para `g17_base.roda` -- nenhuma classe nova nesta geracao."""
    return g17b.roda(dias_operar, dias_historico=dias_historico,
                      janela_min=janela_min, quantil=quantil,
                      capital=capital, congelado=congelado, **kwargs_estrategia)


def roda_congelado_v20(dias_operar: list, dias_historico: list | None = None,
                        janela_min: int = JANELA_MIN, quantil: float = 0.75,
                        capital: float = CAPITAL, **kwargs_estrategia):
    """Mesma coisa que `roda(congelado=True)`, mas importando o arquivo
    CONGELADO proprio desta geracao (`..._congelado_v20.py`, copia byte-a-
    byte da classe da G17/G4 no momento do congelamento) -- usar so' no
    OOS-1/OOS-2, depois que o IS ja' apontou o vencedor desta geracao."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g20_cross_wdo_freq_congelado_v20 import (
        WinBuscaLucroG20CrossWdoFreq,
    )

    hist = dias_historico if dias_historico is not None else dias_operar
    anomalo, direcao = computa_estado(hist, janela_min, quantil)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG20CrossWdoFreq(wdo_anomalo=anomalo, wdo_direcao=direcao,
                                          **kwargs_estrategia)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def episodios_stats(dias_operar: list, dias_historico: list,
                     janela_min: int, quantil: float) -> dict:
    """Frequencia BRUTA do sinal -- independente de alvo/stop/execucao.
    Conta ONSETS (transicao False->True de `anomalo`, com direcao!=0, dentro
    de `dias_operar`) e quantos PREGOES DISTINTOS tem pelo menos 1 onset.
    Calculado direto da serie pura `estado_anomalo_cruzado` (mesma funcao
    que a estrategia usa), sem rodar o motor de backtest -- e' a contagem
    "antes do filtro de pernada/execucao", o que o item 6.48 chama de
    ocorrencias BRUTAS do gatilho."""
    import pandas as pd

    anomalo, direcao = computa_estado(dias_historico, janela_min, quantil)
    win = carrega_win()
    bars = bars_dos_dias(win, dias_operar)
    idx = bars.index
    an = pd.Series(anomalo).reindex(idx, fill_value=False)
    di = pd.Series(direcao).reindex(idx, fill_value=0)
    onset = an & ~an.shift(1, fill_value=False) & (di != 0)
    dias_com_onset = {ts.date() for ts in idx[onset.values]}
    return dict(
        episodios_brutos=int(onset.sum()),
        pregoes_distintos=len(dias_com_onset),
        pregoes_totais=len(dias_operar),
    )
