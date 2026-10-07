# -*- coding: utf-8 -*-
"""Base compartilhada dos scripts da Geracao 22 -- filtro de PREGAO (proxy de
regime diario) sobre o vencedor do retangulo da G21
(`WinBuscaLucroG21Retangulo1000`, `stop_fracao_largura=0,45`,
`alvo_multiplo=2,0x`, capital de teste R$1.000).

Reusa, por import direto, SEM reimplementar:
  - `g21_base` (roda/monta_config/dias_da_janela/CORTE_IS_*/CORTE_OOS1_FIM/
    censura_separada/ruina_do_resultado) -- harness da propria G21
  - `g05_base` (br/carrega_win/carrega_wdo/bars_dos_dias/ic95_wilson/
    consistencia) -- utilitarios gerais de toda a busca
  - `g15_base` (concentracao_topn)

Janelas (regra do dono, `ORQUESTRACAO.md` -- NUNCA violar):
  IS    = jan-jun/2026 (desenvolvimento/estratificacao, 122 pregoes)
  OOS-1 = jul-ago/2026 (gate UNICO, roda uma vez, SEM reajustar o limiar)
  OOS-2 = set/2026 (gate final, SO' para quem passar o OOS-1 "com folga")
Nunca abre 2025 ou anterior PARA MEDIR DESEMPENHO DE ESTRATEGIA. Os proxies
desta geracao leem NIVEL DE PRECO historico (amplitude/fechamento do pregao
anterior, que para o 1o dia do IS cai em 2025) -- isso NAO e' usar 2025 como
janela de validacao de performance, e' o mesmo dado que um robo ao vivo teria
disponivel na manha de 02/01/2026 (o pregao anterior ja aconteceu). Nenhuma
metrica de P&L de estrategia e' medida em 2025 nesta geracao.

Metodo de estratificacao (item 3 do mandato desta geracao -- ESTRATIFICACAO
POS-HOC, nunca simulacoes exclusivas separadas, mesma lesson do item 6.50 de
LICOES_DE_PRODUCAO.md): a G21 roda UMA UNICA VEZ sobre o IS inteiro, sem
filtro de dia nenhum; os proxies sao calculados por pregao; so' DEPOIS os
mesmos trades (ja ocorridos) sao particionados pelo proxy.

Unidade de analise: o PREGAO, nao o trade (item 6.49 -- mais trades nao e'
mais amostra independente quando o gatilho pode reentrar varias vezes no
MESMO dia, como e' o caso do retangulo). O teste de significancia
(`permutation_test_grupos`) opera sobre a serie de liquido POR PREGAO
(zeros incluidos nos dias sem trade), nao sobre o liquido por trade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g21_retangulo_1000"))
import g21_base as g21b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "daytrade" / "win_pernadas_exploracao"
                       / "ea_busca_lucro" / "g15_portfolio_orcamento"))
import g15_base as g15b  # noqa: E402

br = g05b.br
carrega_win = g05b.carrega_win
carrega_wdo = g05b.carrega_wdo
dias_da_janela = g05b.dias_da_janela
bars_dos_dias = g05b.bars_dos_dias
ic95_wilson = g05b.ic95_wilson
consistencia = g05b.consistencia
concentracao_topn = g15b.concentracao_topn
maior_sequencia_perdas = g15b.maior_sequencia_perdas
censura_separada = g21b.censura_separada
ruina_do_resultado = g21b.ruina_do_resultado

CAPITAL = g21b.CAPITAL
MARGEM_WIN_BRL = g21b.MARGEM_WIN_BRL
CORTE_IS_INICIO = g21b.CORTE_IS_INICIO
CORTE_IS_FIM = g21b.CORTE_IS_FIM
CORTE_OOS1_FIM = g21b.CORTE_OOS1_FIM
CORTE_OOS2_FIM = g21b.CORTE_OOS2_FIM

monta_config = g21b.monta_config

#: Geometria VENCEDORA do IS da G21 -- congelada aqui, esta geracao nao
#: retune nenhum parametro de geometria, so' testa um filtro de DIA por cima.
STOP_FRACAO_G21 = 0.45
ALVO_MULTIPLO_G21 = 2.0
ALVO_FRACAO_G21 = STOP_FRACAO_G21 * ALVO_MULTIPLO_G21  # 0,90

#: Primeiros N minutos do WDO@ (ambos WIN@/WDO@ abrem as 09:00) usados como
#: proxy (d). O 1o trade possivel do G21 exige 3*janela_barras=60 barras M1
#: acumuladas (~10:00) -- 30min de WDO (09:00-09:30) e' lido bem antes disso,
#: entao e' causal em relacao ao proprio pregao que esta sendo decidido.
WDO_MINUTOS_ABERTURA = 30


def roda_g21_vencedor(dias_operar: list, capital: float = CAPITAL, congelado: bool = False):
    """Roda a geometria vencedora do IS da G21 (stop=0,45xL / alvo=2,0x) UMA
    VEZ sobre `dias_operar`, sem filtro de dia nenhum."""
    return g21b.roda(dias_operar, capital=capital, congelado=congelado,
                      stop_fracao_largura=STOP_FRACAO_G21,
                      alvo_fracao_largura=ALVO_FRACAO_G21)


def roda_g22_filtrado(dias_operar: list, win_full: pd.DataFrame | None = None,
                       capital: float = CAPITAL, congelado: bool = False,
                       limiar_pontos: float | None = None):
    """Roda `WinBuscaLucroG22RetanguloFiltroAmplitude` (ou a versao
    `_congelado_v22` se `congelado=True`) sobre `dias_operar`. O proxy
    (`dias_elegiveis_por_amplitude`) e' calculado FORA do motor, com o limiar
    CONGELADO no IS (ou o explicitamente passado) -- `win_full` deve cobrir
    pelo menos 1 pregao antes do primeiro dia de `dias_operar` (default:
    carrega a serie COMPLETA do WIN@, que cobre 2021-2026)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    if congelado:
        from strategy.daytrade.lab.win_busca_lucro_g22_retangulo_filtro_amplitude_congelado_v22 import (
            LIMIAR_AMPLITUDE_ONTEM_PONTOS,
            WinBuscaLucroG22RetanguloFiltroAmplitude as Estrategia,
            dias_elegiveis_por_amplitude,
        )
    else:
        from strategy.daytrade.lab.win_busca_lucro_g22_retangulo_filtro_amplitude import (
            LIMIAR_AMPLITUDE_ONTEM_PONTOS,
            WinBuscaLucroG22RetanguloFiltroAmplitude as Estrategia,
            dias_elegiveis_por_amplitude,
        )

    limiar = limiar_pontos if limiar_pontos is not None else LIMIAR_AMPLITUDE_ONTEM_PONTOS
    win = win_full if win_full is not None else carrega_win()
    dias_habilitados = dias_elegiveis_por_amplitude(dias_operar, win, limiar)
    bars = bars_dos_dias(win, dias_operar)
    strat = Estrategia(dias_habilitados=dias_habilitados,
                        stop_fracao_largura=STOP_FRACAO_G21,
                        alvo_fracao_largura=ALVO_FRACAO_G21)
    cfg = monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat, dias_habilitados


# ---------------------------------------------------------------------------
# Proxies diarios causais
# ---------------------------------------------------------------------------

def _fatia_do_dia(df: pd.DataFrame, dia) -> pd.DataFrame:
    return df[df.index.date == dia]


def _amplitude_diaria(df: pd.DataFrame, dia) -> float:
    f = _fatia_do_dia(df, dia)
    return float(f["high"].max() - f["low"].min()) if len(f) else float("nan")


def _fechamento(df: pd.DataFrame, dia) -> float:
    f = _fatia_do_dia(df, dia)
    return float(f["close"].iloc[-1]) if len(f) else float("nan")


def _abertura(df: pd.DataFrame, dia) -> float:
    f = _fatia_do_dia(df, dia)
    return float(f["open"].iloc[0]) if len(f) else float("nan")


def _range_abertura(df: pd.DataFrame, dia, minutos: int) -> float:
    f = _fatia_do_dia(df, dia)
    if not len(f):
        return float("nan")
    fim = f.index[0] + pd.Timedelta(minutes=minutos)
    janela = f[f.index < fim]
    return float(janela["high"].max() - janela["low"].min()) if len(janela) else float("nan")


def calcula_proxies(dias: list, win_full: pd.DataFrame, wdo_full: pd.DataFrame,
                     wdo_minutos_abertura: int = WDO_MINUTOS_ABERTURA) -> pd.DataFrame:
    """4 proxies DIARIOS causais por pregao de `dias` (lista de `date`):

    - `amplitude_ontem`: high-low do PREGAO ANTERIOR do WIN@ (ultimo pregao
      com dado estritamente antes de `dia` na serie COMPLETA, pode cair em
      2025 para o 1o dia do IS -- ver nota do modulo).
    - `gap_abertura`: |abertura de HOJE do WIN@ - fechamento do pregao
      anterior|.
    - `dia_semana`: 0=segunda .. 4=sexta (`pd.Timestamp.dayofweek`).
    - `wdo_range_abertura`: high-low dos primeiros `wdo_minutos_abertura`
      minutos do WDO@ no MESMO dia (causal -- ver nota WDO_MINUTOS_ABERTURA).
    """
    todos_dias = sorted(set(win_full.index.date))
    pos = {d: i for i, d in enumerate(todos_dias)}
    linhas = []
    for d in dias:
        i = pos.get(d)
        dia_ant = todos_dias[i - 1] if (i is not None and i > 0) else None
        amp_ontem = _amplitude_diaria(win_full, dia_ant) if dia_ant else float("nan")
        fech_ontem = _fechamento(win_full, dia_ant) if dia_ant else float("nan")
        abert_hoje = _abertura(win_full, d)
        gap = (abs(abert_hoje - fech_ontem)
               if fech_ontem == fech_ontem and abert_hoje == abert_hoje else float("nan"))
        dia_semana = pd.Timestamp(d).dayofweek
        wdo_range = _range_abertura(wdo_full, d, wdo_minutos_abertura)
        linhas.append(dict(dia=d, amplitude_ontem=amp_ontem, gap_abertura=gap,
                            dia_semana=dia_semana, wdo_range_abertura=wdo_range))
    return pd.DataFrame(linhas).set_index("dia")


def tercis_com_corte(valores: pd.Series) -> tuple[pd.Series, float, float]:
    """Corta `valores` (indexado por dia) em 3 grupos (0=baixo,1=medio,2=alto)
    pelos quantis 1/3 e 2/3 calculados SO' sobre os dias validos (sem NaN).
    Devolve os rotulos e os 2 limiares NUMERICOS ABSOLUTOS -- sao esses 2
    numeros que devem ser CONGELADOS se um candidato for promovido ao OOS-1,
    nunca recalculados sobre o OOS-1."""
    validos = valores.dropna()
    c1, c2 = np.quantile(validos.to_numpy(), [1 / 3, 2 / 3])
    rotulos = pd.cut(valores, bins=[-np.inf, c1, c2, np.inf], labels=[0, 1, 2])
    return rotulos, float(c1), float(c2)


def metricas_por_grupo(trades: list, dias_grupo: list, rotulo: str) -> dict:
    """Filtra `trades` cujo `exit_ts.date()` cai em `dias_grupo` e reusa
    `consistencia` (BE empirico/IC95/concentracao) SO' sobre esse subconjunto
    -- `dias_grupo` inclui os dias SEM trade do grupo (denominador correto de
    liquido/pregao, nao so' liquido/pregao OPERADO)."""
    dias_set = set(dias_grupo)
    trades_grupo = [t for t in trades if t.exit_ts.date() in dias_set]
    c = consistencia(trades_grupo, sorted(dias_grupo))
    com_trade = c["com_trade"]
    liquido_por_pregao = c["liquido"] / len(dias_grupo) if dias_grupo else float("nan")
    liquido_por_pregao_operado = (c["liquido"] / com_trade) if com_trade else float("nan")
    return dict(
        rotulo=rotulo, n_dias=len(dias_grupo), com_trade=com_trade,
        sem_trade=c["sem_trade"], n_trades=c["n"], liquido=c["liquido"],
        liquido_por_pregao=liquido_por_pregao,
        liquido_por_pregao_operado=liquido_por_pregao_operado,
        win=c["win"], be=c["be"], lo=c["lo"], hi=c["hi"], veredito=c["veredito"],
        top3=c["concentracao_top3"], serie=c["serie"],
    )


def permutation_test_grupos(serie_total: pd.Series, grupos: dict[object, list],
                            n_perm: int = 5000, seed: int = 0) -> tuple[float, float]:
    """Teste de permutacao: estatistica = amplitude entre as medias de
    liquido/pregao dos grupos (max - min). Embaralha o ROTULO entre os dias
    (mantendo os TAMANHOS de grupo fixos -- nao gera grupo novo, so' re-liga
    os mesmos dias/valores a rotulos aleatorios) e recomputa a estatistica
    `n_perm` vezes. Devolve `(estatistica_observada, p_valor)` -- fracao de
    permutacoes com estatistica >= a observada. Opera sobre a serie DIARIA
    (zeros incluidos), nao sobre trade -- respeita o item 6.49."""
    idx_por_dia = {d.date() if hasattr(d, "date") else d: i
                   for i, d in enumerate(serie_total.index)}
    valores = serie_total.to_numpy()
    tamanhos, posicoes = [], []
    for dias_lista in grupos.values():
        idxs = [idx_por_dia[d] for d in dias_lista if d in idx_por_dia]
        posicoes.append(idxs)
        tamanhos.append(len(idxs))

    def estatistica(ordem: np.ndarray) -> float:
        medias, cursor = [], 0
        for t in tamanhos:
            medias.append(valores[ordem[cursor:cursor + t]].mean())
            cursor += t
        return float(max(medias) - min(medias))

    base = np.array([p for grupo in posicoes for p in grupo])
    observado = estatistica(base)
    rng = np.random.default_rng(seed)
    maior_igual = 0
    for _ in range(n_perm):
        perm = rng.permutation(base)
        if estatistica(perm) >= observado:
            maior_igual += 1
    return observado, maior_igual / n_perm
