# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 24
(`WinBuscaLucroG24WdoLiderContinuo`) -- Fase 3 (fonte EXTERNA), direcao B
("WDO como lider continuo"), `ORQUESTRACAO.md`.

Reaproveita `g04_base` (carregamento de WIN@D e WDO@D, ambos M1 ajuste por
diferenca -- ja' usado na G4 para o estado anomalo BINARIO) para o dado bruto,
e `g21_base` (CAPITAL=1.000, concentracao_topn/ruina_do_resultado/
censura_separada/monta_config, ja' composto de g05_base/g13_base/g15_base)
para o capital e os helpers de validacao -- mesmo padrao que `g23_base`
(Geracao 23) usou. Nenhuma logica de carregamento ou de metricas duplicada.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (medicao de magnitude + desenvolvimento, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar depois)
  OOS-2 = set/2026 (SO' se OOS-1 passar "com folga")
Nunca abre 2025 ou anterior.

Esta geracao e' sobre o WDO como sinal CONTINUO (nao mais o estado binario
da G4) -- os passos 1 e 2 do mandato medem a MAGNITUDE do lead-lag ANTES de
cogitar montar qualquer estrategia completa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g04_cross_wdo"))
import g04_base as g04b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g21_retangulo_1000"))
import g21_base as g21b  # noqa: E402

br = g04b.br
carrega_win = g04b.carrega_win
carrega_wdo = g04b.carrega_wdo
dias_da_janela = g04b.dias_da_janela
bars_dos_dias = g04b.bars_dos_dias

ic95_wilson = g21b.ic95_wilson
consistencia = g21b.consistencia
CAPITAL = g21b.CAPITAL                      # R$1.000
MARGEM_WIN_BRL = g21b.MARGEM_WIN_BRL        # R$100
CORTE_IS_INICIO = g21b.CORTE_IS_INICIO
CORTE_IS_FIM = g21b.CORTE_IS_FIM
CORTE_OOS1_FIM = g21b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g21b.CORTE_OOS2_FIM
concentracao_topn = g21b.concentracao_topn
maior_sequencia_perdas = g21b.maior_sequencia_perdas
censura_separada = g21b.censura_separada
ruina_do_resultado = g21b.ruina_do_resultado
monta_config = g21b.monta_config

#: Dias INTEIROS de burn-in antes do quantil causal comecar a valer --
#: mesma constante/disciplina da G4 (`MIN_DIAS_BURN_IN`).
MIN_DIAS_BURN_IN = 20


def retornos_1min(df: pd.DataFrame, dias: list) -> pd.Series:
    """Retorno de 1 MINUTO (`close.diff(1)`), DENTRO do pregao -- nunca
    atravessa a virada de sessao (`groupby(dia).diff`)."""
    fatia = bars_dos_dias(df, dias)["close"]
    dia = pd.Series(fatia.index.date, index=fatia.index)
    return fatia.groupby(dia).diff(1)


def retorno_k_min(df: pd.DataFrame, dias: list, k: int) -> pd.Series:
    """Retorno de `k` MINUTOS (`close.diff(k)`), DENTRO do pregao."""
    fatia = bars_dos_dias(df, dias)["close"]
    dia = pd.Series(fatia.index.date, index=fatia.index)
    return fatia.groupby(dia).diff(k)


def desloca_dentro_do_dia(serie: pd.Series, lag: int) -> pd.Series:
    """Desloca `serie` `lag` barras para TRAS no tempo (equivalente a
    `serie.shift(-lag)`, isto e', `resultado[t] = serie[t+lag]`), SEM
    atravessar a virada de sessao -- usa o MESMO `dia` que indexou `serie`
    para fazer o shift por grupo."""
    dia = pd.Series(serie.index.date, index=serie.index)
    return serie.groupby(dia).shift(-lag)


def corr_com_ic(x: pd.Series, y: pd.Series) -> dict:
    """Correlacao de Pearson entre duas series JA alinhadas pelo MESMO
    indice (linhas com NaN em qualquer uma das duas sao descartadas), com
    IC95% via transformacao z de Fisher -- apropriado para n grande (milhares
    de minutos), onde o p-valor sozinho nao diz nada sobre MAGNITUDE
    economica (e' exatamente a ressalva do mandato desta geracao)."""
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(df)
    if n < 10:
        return dict(r=float("nan"), n=n, lo=float("nan"), hi=float("nan"))
    r = float(df["x"].corr(df["y"]))
    r_clip = max(min(r, 0.999999), -0.999999)
    z = np.arctanh(r_clip)
    se = 1.0 / np.sqrt(n - 3)
    lo = float(np.tanh(z - 1.959964 * se))
    hi = float(np.tanh(z + 1.959964 * se))
    return dict(r=r, n=n, lo=lo, hi=hi)


def quantil_causal_abs(serie: pd.Series, quantil: float,
                        min_dias_burn_in: int = MIN_DIAS_BURN_IN) -> pd.Series:
    """Limiar causal do quantil `quantil` de `|serie|`, calculado dia a dia
    SO' com dias INTEIROS estritamente ANTERIORES ao dia de cada observacao
    (burn-in de `min_dias_burn_in` dias) -- mesma disciplina da G4
    (`estado_anomalo_cruzado`). Devolve uma serie de limiares alinhada ao
    indice de `serie` (NaN onde ainda nao ha' burn-in suficiente)."""
    dia = pd.Series(serie.index.date, index=serie.index)
    abs_s = serie.abs()
    dias_ordenados = sorted(dia.unique())
    thr_por_dia: dict = {}
    acumulado: list[np.ndarray] = []
    for i, d in enumerate(dias_ordenados):
        if i >= min_dias_burn_in:
            vals = np.concatenate(acumulado)
            thr_por_dia[d] = float(np.nanquantile(vals, quantil)) if len(vals) else float("nan")
        else:
            thr_por_dia[d] = float("nan")
        mask_dia = (dia == d).values
        valores_do_dia = abs_s.values[mask_dia]
        acumulado.append(valores_do_dia[~np.isnan(valores_do_dia)])
    return dia.map(thr_por_dia).astype(float)
