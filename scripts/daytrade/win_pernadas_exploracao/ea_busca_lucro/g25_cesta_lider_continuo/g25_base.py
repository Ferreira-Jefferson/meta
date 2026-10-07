# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts de teste da Geracao 25 -- Fase 3 (fonte
EXTERNA), extensao do mandato da G23 (amplitude/folego da cesta) e da G24
(metodo de lead-lag continuo), `ORQUESTRACAO.md`.

A pergunta desta geracao: a cesta de acoes tem um LEAD genuino sobre o WIN --
nao so' como CONFIRMACAO de uma pernada ja' nascente (G23, que ja' media
fôlego CONCORRENTE ao instante em que o WIN ja' tinha cruzado um limiar
pequeno), mas como PREDITOR continuo, no mesmo molde exato do metodo da G24
(que testou o WDO): correlacao cruzada em defasagens {0,1,2,3,5}min e
magnitude condicional (`ret_cesta_passado_k` -> `ret_win_futuro_k`, causal,
janelas NAO sobrepostas).

Reaproveita DUAS bases ja' existentes, nenhuma logica de carregamento
duplicada:
  - `g23_base` -- carregamento/conversao de fuso da cesta de 24 acoes
    liquidas (`carrega_cesta`, `TICKERS_CESTA`, `CORTE_COBERTURA_CESTA`).
  - `g24_base` -- carregamento do WIN@D, helpers causais ja' usados para o
    WDO (`retornos_1min`, `retorno_k_min`, `desloca_dentro_do_dia`,
    `corr_com_ic`, `quantil_causal_abs`, `ic95_wilson`, janelas IS/OOS).

## O indice sintetico causal da cesta -- escolha de metodo DECLARADA

Os 24 papeis tem precos em escalas heterogeneas (VALE3 ~60, ITUB4 ~30,
BPAC11 ~30, KLBN11 ~20 etc.) -- ao contrario de WIN/WDO (G24), que sao dois
futuros no MESMO instrumento de pontos, nao da' para somar/subtrair precos
cruz-papel. A unidade comum e' RETORNO PERCENTUAL, nao pontos.

Para cada papel: reindexa o fechamento M1 na GRADE do WIN com `ffill`
limitado (`ffill_limite_min`, mesma disciplina causal de `folego_ibov` da
G23 -- nunca atravessa a virada de sessao porque o `groupby(dia).diff`
reseta por pregao independente do que o `ffill` carregou), calcula o retorno
percentual de `k` minutos DENTRO do mesmo pregao
(`precos.groupby(dia).diff(k) / precos.groupby(dia).shift(k)`). O indice da
cesta e' a MEDIA SIMPLES (equal-weight, nao ponderada por liquidez/peso no
Ibovespa -- escolha mais simples e mais barata de defender; pesos por
liquidez ficariam para uma proxima geracao SE esta mostrar sinal) dos
retornos validos naquele instante, exigindo pelo menos `min_fracao_validos`
dos papeis com dado (mesmo piso da G23). Generaliza `folego_ibov` (que so'
usava o SINAL do delta) para a MAGNITUDE do retorno -- e' o analogo direto
de `retorno_k_min(wdo, ...)` da G24, so' que agregado sobre 24 papeis em vez
de 1 instrumento.

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (medicao de magnitude, 122 pregoes) -- cesta cobre
          o IS INTEIRO (confirmado em g23_base/CORTE_COBERTURA_CESTA)
  OOS-1 = jul-ago/2026 (gate UNICO) -- cesta so' cobre ate' 21/08 (ver
          g23_base), truncar se algum dia for usado
  OOS-2 = set/2026 -- ESTRUTURALMENTE FORA DE ALCANCE com este dado (cesta
          nao cobre)
Esta geracao so' usa o IS (mandato: medir magnitude ANTES de montar
qualquer estrategia).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g23_amplitude_ibov"))
import g23_base as g23b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g24_wdo_lider_continuo"))
import g24_base as g24b  # noqa: E402

# -- cesta (G23) --------------------------------------------------------------
carrega_cesta = g23b.carrega_cesta
cobertura_cesta = g23b.cobertura_cesta
TICKERS_CESTA = g23b.TICKERS_CESTA
CORTE_COBERTURA_CESTA = g23b.CORTE_COBERTURA_CESTA

# -- WIN + helpers causais (G24) -----------------------------------------------
carrega_win = g24b.carrega_win
dias_da_janela = g24b.dias_da_janela
bars_dos_dias = g24b.bars_dos_dias
retornos_1min = g24b.retornos_1min
retorno_k_min = g24b.retorno_k_min
desloca_dentro_do_dia = g24b.desloca_dentro_do_dia
corr_com_ic = g24b.corr_com_ic
quantil_causal_abs = g24b.quantil_causal_abs
ic95_wilson = g23b.ic95_wilson
CAPITAL = g24b.CAPITAL
MARGEM_WIN_BRL = g24b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g24b.CORTE_IS_INICIO
CORTE_IS_FIM = g24b.CORTE_IS_FIM
CORTE_OOS1_FIM = g24b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g24b.CORTE_OOS2_FIM
MIN_DIAS_BURN_IN = g24b.MIN_DIAS_BURN_IN


def retorno_k_cesta(
    cesta: dict[str, pd.Series],
    grade: pd.DatetimeIndex,
    k: int,
    ffill_limite_min: int = 10,
    min_fracao_validos: float = 0.5,
) -> pd.Series:
    """Indice sintetico CAUSAL de retorno percentual de `k` minutos da
    cesta, na `grade` do WIN -- media simples (equal-weight) dos retornos
    percentuais validos de cada papel, dentro do mesmo pregao (nunca
    atravessa a virada de sessao). NaN onde menos de `min_fracao_validos`
    dos papeis tem dado (ex.: antes da abertura das acoes). Generaliza
    `folego_ibov` (G23, so' usava sinal) para magnitude -- analogo de
    `retorno_k_min(wdo, ...)` da G24, agregado sobre a cesta."""
    if k <= 0:
        raise ValueError("k tem que ser positivo")
    if not cesta:
        raise ValueError("cesta vazia -- nenhum papel")
    dia = pd.Series(grade.date, index=grade)
    retornos = []
    for serie in cesta.values():
        s = serie.sort_index()
        s = s[~s.index.duplicated(keep="first")]
        precos = s.reindex(grade, method="ffill", limit=ffill_limite_min)
        delta = precos.groupby(dia).diff(k)
        nivel_anterior = precos.groupby(dia).shift(k)
        with np.errstate(invalid="ignore", divide="ignore"):
            ret = (delta / nivel_anterior).to_numpy()
        retornos.append(ret)
    mat = np.vstack(retornos)  # (n_papeis, len(grade))
    validos = (~np.isnan(mat)).sum(axis=0)
    soma = np.nansum(mat, axis=0)
    minimo = min_fracao_validos * len(cesta)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = soma / np.maximum(validos, 1)
    media = np.where(validos >= minimo, media, np.nan)
    return pd.Series(media, index=grade)


def retorno_cesta_1min(
    cesta: dict[str, pd.Series],
    grade: pd.DatetimeIndex,
    ffill_limite_min: int = 10,
    min_fracao_validos: float = 0.5,
) -> pd.Series:
    """Caso especial `k=1` de `retorno_k_cesta` -- retorno percentual de 1
    MINUTO da cesta, usado no passo 1 (correlacao cruzada lag a lag)."""
    return retorno_k_cesta(cesta, grade, 1, ffill_limite_min, min_fracao_validos)
