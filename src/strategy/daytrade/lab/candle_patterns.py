"""Deteccao de padroes de candlestick classicos — OHLC puro -> booleano por
barra, sem I/O (mesma disciplina de `core/indicators.py`: funcao pura
`(pd.Series...) -> pd.Series`). Existe para a frente de pesquisa "padroes de
candle" (pedido do dono, 2026-08-26): quantificar se o catalogo vendido em
livro/curso ("alta acertividade") sobrevive a medicao honesta em WIN@/WDO@.

## Escopo — por que estes padroes e nao outros

Cobre o catalogo PRINCIPAL de candlestick de 1-3 velas (nao exaustivo, listado
explicitamente abaixo o que ficou de fora e por que — pedido explicito do
dono, nunca recorte silencioso):

- **1 vela**: doji (padrao + dragonfly + gravestone), marubozu (alta/baixa),
  martelo/martelo-invertido (e suas variantes de CONTEXTO DE TENDENCIA
  identicas em forma — enforcado/estrela-cadente).
- **2 velas**: engolfo (alta/baixa), harami (alta/baixa), linha-de-perfuracao,
  nuvem-negra (dark cloud cover), pinca de topo/fundo (tweezer).
- **3 velas**: estrela da manha/tarde, tres soldados brancos/corvos negros.

**Ficou de fora desta rodada** (documentado, nao escondido):
- *Bebe abandonado* (variante com GAP da estrela da manha/tarde): gap
  intrabarra e raro numa serie continua de futuro negociada quase 24/6 em
  M15/M1 (o unico gap de verdade e' a abertura do pregao) — o efeito seria
  quase identico ao da estrela da manha/tarde sem o gap, entao testar os
  dois separadamente adicionaria celulas ao teste multiplo sem
  informacao nova.
- *Harami cross* (harami com a segunda vela sendo doji): subconjunto raro do
  harami normal, mesma logica de "sem informacao nova por celula extra".
  *Three inside/outside up/down*, *kicker*, *tasuki*, *ladder*,
  *bloqueio avancado* (`advance block`), *dois corvos*: padroes de 2-4
  velas menos citados no catalogo "classico" (Nison 1991) e mais raros —
  fica para rodada 2/3 se sobrar tempo, priorizado explicitamente pelo
  dono ("nao precisa ser exaustivo").
- *Figuras de grafico* (topo/fundo duplo, OCO, triangulo, bandeira,
  rompimento de suporte/resistencia): fora do escopo desta rodada por
  pedido explicito (exigem deteccao de pivo/zigzag, definicao muito mais
  subjetiva) — rodada 2/3 se sobrar tempo.

## Convencao de deteccao

Cada `detect_*` recebe um DataFrame OHLC (colunas `open`/`high`/`low`/`close`,
qualquer index) e devolve `pd.Series[bool]` do MESMO index — `True` na barra
em que o padrao COMPLETA (a ultima vela do padrao). Sem look-ahead: cada
padrao so' usa a barra atual e barras ANTERIORES (`shift(1)`, `shift(2)`) —
nunca `shift(-N)`. A barra em que o padrao "completa" e' a barra de DECISAO;
quem for medir excursao/retorno entra na ABERTURA da barra seguinte (mesma
convencao de `IntradayStrategy`/`AGENTS.md` regra 4).

## Contexto de tendencia (martelo/enforcado, martelo-invertido/estrela-cadente)

Quatro padroes tem a MESMA forma de vela e so' se diferenciam pelo contexto:
um corpo pequeno com sombra inferior longa e' "martelo" (sinal de ALTA) se
aparecer apos tendencia de BAIXA, ou "enforcado" (sinal de BAIXA) se aparecer
apos tendencia de ALTA — o inverso (sombra superior longa) e' "martelo
invertido"/"estrela cadente". `prior_trend()` decide o contexto com uma regra
DELIBERADAMENTE simples e documentada (sinal do deslocamento do fechamento
nas `TREND_LOOKBACK` barras anteriores a' vela do padrao) — e' a mesma
arbitrariedade que qualquer limiar de tendencia tem; declarada aqui, nao
escondida atras de "deteccao de tendencia" generica.
"""
from __future__ import annotations

from typing import Callable, Literal, NamedTuple

import numpy as np
import pandas as pd

Direction = Literal["bullish", "bearish", "neutral"]

# ---------------------------------------------------------------------------
# Limiares — todos documentados aqui, em UM lugar, para nenhum detector
# esconder um numero magico dentro da formula.
# ---------------------------------------------------------------------------

#: Corpo <= 10% do range da barra = "sem corpo" (doji). Valor comum na
#: literatura (Nison 1991 usa "abertura e fechamento aproximadamente iguais",
#: sem numero fixo — 10% e' a convencao mais citada em implementacoes
#: computacionais, ex.: TA-Lib usa 5% como piso mais estrito; 10% aqui e'
#: deliberadamente mais PERMISSIVO, gerando mais ocorrencias — testar com
#: um filtro apertado demais e nunca achar amostra nao distingue "padrao
#: nao funciona" de "padrao nunca ocorre").
DOJI_BODY_RATIO = 0.10

#: Corpo >= 90% do range e sombras <= 5% cada = marubozu ("careca" — sem
#: sombra nenhuma). Simetrico ao limiar de doji (mesma folga de 10% total,
#: dividida entre as duas pontas).
MARUBOZU_BODY_RATIO = 0.90
MARUBOZU_SHADOW_RATIO = 0.05

#: Martelo/martelo-invertido: sombra longa >= 2x o corpo (definicao mais
#: citada; Bulkowski/Nison usam 2x-3x — 2x e' o piso mais PERMISSIVO das
#: fontes revisadas, mesma logica do doji acima). Sombra curta do lado
#: oposto <= 10% do range (quase inexistente).
LONG_SHADOW_BODY_MULT = 2.0
SHORT_SHADOW_RANGE_RATIO = 0.10

#: Janela (em barras) para decidir se a vela do padrao aparece apos
#: tendencia de ALTA ou de BAIXA — decide martelo-vs-enforcado e
#: martelo-invertido-vs-estrela-cadente. Usa o fechamento da barra
#: IMEDIATAMENTE anterior a' vela do padrao contra o fechamento
#: `TREND_LOOKBACK` barras antes dela — nunca a propria vela do padrao
#: (sem look-ahead dentro do proprio padrao).
TREND_LOOKBACK = 10

#: Engolfo/harami: o corpo da vela 2 tem que engolfar/estar dentro do corpo
#: da vela 1 com folga minima (evita "engolfo" por 1 tick de arredondamento
#: contar como padrao). 0.0 = sem folga (estrito); mantido em 0.0 e
#: documentado — folga extra e' outro grau de liberdade que so' vale a pena
#: adicionar se o padrao estrito sobreviver e precisar de robustez.
ENGULF_MARGIN = 0.0

#: Pinca (tweezer): topos/fundos "iguais" com tolerancia de ate 5% do range
#: medio das duas velas (nunca vao bater exatamente no preco real).
TWEEZER_TOLERANCE_RATIO = 0.05

#: Estrela da manha/tarde: a vela central precisa ser "pequena" (indecisao)
#: — corpo <= 50% do corpo da vela 1 — e a vela 3 precisa fechar pelo menos
#: na METADE do corpo da vela 1 (reversao "de verdade", nao so' uma pausa).
STAR_MIDDLE_BODY_RATIO = 0.50
STAR_CLOSE_INTO_BODY1_RATIO = 0.50

#: Tres soldados/corvos: cada vela abre DENTRO do corpo da anterior e fecha
#: alem do fechamento da anterior, com sombra superior/inferior pequena
#: (< 25% do corpo) — regra padrao (Nison 1991, Morris 2006).
SOLDIERS_SHADOW_BODY_RATIO = 0.25


def _ohlc(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    return df["open"].astype(float), df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)


def _safe_range(high: pd.Series, low: pd.Series) -> pd.Series:
    """`high-low`, com range zero (barra sem movimento nenhum, raro mas
    acontece em book fino) virando `NaN` — divisao por ele nunca produz
    `inf`/`-inf` silencioso que passaria por um filtro `> limiar`."""
    r = (high - low).astype(float)
    return r.mask(r <= 0, np.nan)


def prior_trend(df: pd.DataFrame, lookback: int = TREND_LOOKBACK) -> pd.Series:
    """`+1` (alta) / `-1` (baixa) / `0` (lateral/indefinido) — fechamento da
    barra ANTERIOR a` vela do padrao contra o fechamento `lookback` barras
    antes dela. So' usa `close.shift(1)` e `close.shift(1+lookback)`: nunca
    olha a propria vela do padrao (barra `t`), preservando a disciplina
    anti-look-ahead mesmo para o contexto de tendencia."""
    close = df["close"].astype(float)
    ref = close.shift(1)
    past = close.shift(1 + lookback)
    trend = pd.Series(0, index=df.index, dtype=int)
    trend = trend.mask(ref > past, 1)
    trend = trend.mask(ref < past, -1)
    trend = trend.mask(ref.isna() | past.isna(), 0)
    return trend


# ---------------------------------------------------------------------------
# 1 vela
# ---------------------------------------------------------------------------

def _shape_doji(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = _ohlc(df)
    body = (c - o).abs()
    rng = _safe_range(h, l)
    return (body <= DOJI_BODY_RATIO * rng).fillna(False)


def detect_doji(df: pd.DataFrame) -> pd.Series:
    """Doji "generico" — indecisao, sem hipotese direcional propria (por
    isso testado com hipotese NEUTRA/dois-lados na medicao, nao alta/baixa)."""
    return _shape_doji(df)


def _shape_dragonfly(df: pd.DataFrame) -> pd.Series:
    """Doji com sombra inferior longa e quase nenhuma superior — abertura e
    fechamento perto da MAXIMA."""
    o, h, l, c = _ohlc(df)
    rng = _safe_range(h, l)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return (_shape_doji(df) & (upper <= SHORT_SHADOW_RANGE_RATIO * rng)
            & (lower >= (1 - 2 * SHORT_SHADOW_RANGE_RATIO) * rng)).fillna(False)


def _shape_gravestone(df: pd.DataFrame) -> pd.Series:
    """Doji com sombra superior longa e quase nenhuma inferior — abertura e
    fechamento perto da MINIMA."""
    o, h, l, c = _ohlc(df)
    rng = _safe_range(h, l)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return (_shape_doji(df) & (lower <= SHORT_SHADOW_RANGE_RATIO * rng)
            & (upper >= (1 - 2 * SHORT_SHADOW_RANGE_RATIO) * rng)).fillna(False)


def detect_dragonfly_doji_bullish(df: pd.DataFrame) -> pd.Series:
    """Dragonfly doji apos tendencia de BAIXA — variante altista (mesma
    leitura do martelo, corpo em doji)."""
    return (_shape_dragonfly(df) & (prior_trend(df) == -1)).fillna(False)


def detect_gravestone_doji_bearish(df: pd.DataFrame) -> pd.Series:
    """Gravestone doji apos tendencia de ALTA — variante baixista (leitura
    da estrela cadente, corpo em doji)."""
    return (_shape_gravestone(df) & (prior_trend(df) == 1)).fillna(False)


def detect_marubozu_bullish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = _ohlc(df)
    rng = _safe_range(h, l)
    body = (c - o).abs()
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return ((c > o) & (body >= MARUBOZU_BODY_RATIO * rng)
            & (upper <= MARUBOZU_SHADOW_RATIO * rng)
            & (lower <= MARUBOZU_SHADOW_RATIO * rng)).fillna(False)


def detect_marubozu_bearish(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = _ohlc(df)
    rng = _safe_range(h, l)
    body = (c - o).abs()
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return ((c < o) & (body >= MARUBOZU_BODY_RATIO * rng)
            & (upper <= MARUBOZU_SHADOW_RATIO * rng)
            & (lower <= MARUBOZU_SHADOW_RATIO * rng)).fillna(False)


def _shape_small_body_long_lower_shadow(df: pd.DataFrame) -> pd.Series:
    """Forma de martelo/enforcado: corpo pequeno perto do topo, sombra
    inferior longa, sombra superior curta."""
    o, h, l, c = _ohlc(df)
    rng = _safe_range(h, l)
    body = (c - o).abs()
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return ((body > 0) & (lower >= LONG_SHADOW_BODY_MULT * body)
            & (upper <= SHORT_SHADOW_RANGE_RATIO * rng)).fillna(False)


def _shape_small_body_long_upper_shadow(df: pd.DataFrame) -> pd.Series:
    """Forma de martelo-invertido/estrela-cadente: corpo pequeno perto da
    base, sombra superior longa, sombra inferior curta."""
    o, h, l, c = _ohlc(df)
    rng = _safe_range(h, l)
    body = (c - o).abs()
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return ((body > 0) & (upper >= LONG_SHADOW_BODY_MULT * body)
            & (lower <= SHORT_SHADOW_RANGE_RATIO * rng)).fillna(False)


def detect_hammer(df: pd.DataFrame) -> pd.Series:
    """Martelo — sombra inferior longa apos tendencia de BAIXA (altista)."""
    return (_shape_small_body_long_lower_shadow(df) & (prior_trend(df) == -1)).fillna(False)


def detect_hanging_man(df: pd.DataFrame) -> pd.Series:
    """Enforcado — MESMA forma do martelo, apos tendencia de ALTA (baixista)."""
    return (_shape_small_body_long_lower_shadow(df) & (prior_trend(df) == 1)).fillna(False)


def detect_inverted_hammer(df: pd.DataFrame) -> pd.Series:
    """Martelo invertido — sombra superior longa apos tendencia de BAIXA
    (altista)."""
    return (_shape_small_body_long_upper_shadow(df) & (prior_trend(df) == -1)).fillna(False)


def detect_shooting_star(df: pd.DataFrame) -> pd.Series:
    """Estrela cadente — MESMA forma do martelo invertido, apos tendencia
    de ALTA (baixista)."""
    return (_shape_small_body_long_upper_shadow(df) & (prior_trend(df) == 1)).fillna(False)


# ---------------------------------------------------------------------------
# 2 velas
# ---------------------------------------------------------------------------

def detect_bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    """Corpo da vela 2 (alta) precisa CONTER e EXCEDER o corpo inteiro da
    vela 1 (baixa, range `[c1, o1]`) dos DOIS lados: abre <= `c1` (a base
    do corpo anterior) e fecha >= `o1` (o topo dele) -- nao so' "abre mais
    baixo que a abertura anterior e fecha mais alto que o fechamento
    anterior" (condicao MUITO mais fraca, quase sempre verdadeira quando a
    abertura de hoje ~= fechamento de ontem, que e' o caso tipico em serie
    continua sem gap -- bug medido 2026-08-26: essa versao fraca dava
    22-24% de ocorrencia em M15, contra a expectativa de um padrao raro)."""
    o, h, l, c = _ohlc(df)
    o1, c1 = o.shift(1), c.shift(1)
    prev_bear = c1 < o1
    curr_bull = c > o
    engulfs = (o <= c1 + ENGULF_MARGIN) & (c >= o1 - ENGULF_MARGIN)
    return (prev_bear & curr_bull & engulfs).fillna(False)


def detect_bearish_engulfing(df: pd.DataFrame) -> pd.Series:
    """Espelho de `detect_bullish_engulfing` -- corpo da vela 2 (baixa)
    contem e excede o corpo inteiro da vela 1 (alta, range `[o1, c1]`):
    abre >= `c1` (topo do corpo anterior) e fecha <= `o1` (base dele)."""
    o, h, l, c = _ohlc(df)
    o1, c1 = o.shift(1), c.shift(1)
    prev_bull = c1 > o1
    curr_bear = c < o
    engulfs = (o >= c1 - ENGULF_MARGIN) & (c <= o1 + ENGULF_MARGIN)
    return (prev_bull & curr_bear & engulfs).fillna(False)


def detect_bullish_harami(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = _ohlc(df)
    o1, c1 = o.shift(1), c.shift(1)
    prev_bear = c1 < o1
    inside = (np.maximum(o, c) <= o1 + ENGULF_MARGIN) & (np.minimum(o, c) >= c1 - ENGULF_MARGIN)
    return (prev_bear & inside).fillna(False)


def detect_bearish_harami(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = _ohlc(df)
    o1, c1 = o.shift(1), c.shift(1)
    prev_bull = c1 > o1
    inside = (np.maximum(o, c) <= c1 + ENGULF_MARGIN) & (np.minimum(o, c) >= o1 - ENGULF_MARGIN)
    return (prev_bull & inside).fillna(False)


def detect_piercing_line(df: pd.DataFrame) -> pd.Series:
    """Vela 1 de baixa, vela 2 de alta abrindo ABAIXO da minima da vela 1 e
    fechando acima do MEIO do corpo da vela 1 (mas abaixo da abertura dela)."""
    o, h, l, c = _ohlc(df)
    o1, c1, l1 = o.shift(1), c.shift(1), l.shift(1)
    mid1 = (o1 + c1) / 2.0
    prev_bear = c1 < o1
    curr_bull = c > o
    return (prev_bear & curr_bull & (o < l1) & (c > mid1) & (c < o1)).fillna(False)


def detect_dark_cloud_cover(df: pd.DataFrame) -> pd.Series:
    """Espelho do piercing line: vela 1 de alta, vela 2 de baixa abrindo
    ACIMA da maxima da vela 1 e fechando abaixo do meio do corpo da vela 1."""
    o, h, l, c = _ohlc(df)
    o1, c1, h1 = o.shift(1), c.shift(1), h.shift(1)
    mid1 = (o1 + c1) / 2.0
    prev_bull = c1 > o1
    curr_bear = c < o
    return (prev_bull & curr_bear & (o > h1) & (c < mid1) & (c > o1)).fillna(False)


def detect_tweezer_bottom(df: pd.DataFrame) -> pd.Series:
    """Duas minimas praticamente iguais apos tendencia de BAIXA (altista)."""
    o, h, l, c = _ohlc(df)
    l1 = l.shift(1)
    rng_avg = (_safe_range(h, l) + _safe_range(h.shift(1), l1)) / 2.0
    close_lows = (l - l1).abs() <= TWEEZER_TOLERANCE_RATIO * rng_avg
    return (close_lows & (prior_trend(df, TREND_LOOKBACK) == -1)).fillna(False)


def detect_tweezer_top(df: pd.DataFrame) -> pd.Series:
    """Duas maximas praticamente iguais apos tendencia de ALTA (baixista)."""
    o, h, l, c = _ohlc(df)
    h1 = h.shift(1)
    rng_avg = (_safe_range(h, l) + _safe_range(h1, l.shift(1))) / 2.0
    close_highs = (h - h1).abs() <= TWEEZER_TOLERANCE_RATIO * rng_avg
    return (close_highs & (prior_trend(df, TREND_LOOKBACK) == 1)).fillna(False)


# ---------------------------------------------------------------------------
# 3 velas
# ---------------------------------------------------------------------------

def detect_morning_star(df: pd.DataFrame) -> pd.Series:
    """Vela 1 (D-2) de baixa e corpo grande, vela 2 (D-1) pequena
    (indecisao), vela 3 (D) de alta fechando pelo menos na metade do corpo
    da vela 1."""
    o, h, l, c = _ohlc(df)
    o2, c2 = o.shift(2), c.shift(2)
    o1, c1 = o.shift(1), c.shift(1)
    body1 = (c1 - o1).abs()
    body2 = (c2 - o2).abs()
    # nivel a partir do qual o fechamento da vela 3 conta como "entrou de
    # verdade" no corpo da vela 1 (D-2, baixista: o2 > c2) — 0.5 = metade.
    threshold1 = c2 + STAR_CLOSE_INTO_BODY1_RATIO * (o2 - c2)
    prev2_bear = c2 < o2
    middle_small = body1 <= STAR_MIDDLE_BODY_RATIO * body2
    curr_bull = c > o
    closes_into_body1 = c >= threshold1
    return (prev2_bear & middle_small & curr_bull & closes_into_body1).fillna(False)


def detect_evening_star(df: pd.DataFrame) -> pd.Series:
    """Espelho da estrela da manha: vela 1 (D-2) de alta e corpo grande,
    vela 2 (D-1) pequena, vela 3 (D) de baixa fechando pelo menos na metade
    do corpo da vela 1."""
    o, h, l, c = _ohlc(df)
    o2, c2 = o.shift(2), c.shift(2)
    o1, c1 = o.shift(1), c.shift(1)
    body1 = (c1 - o1).abs()
    body2 = (c2 - o2).abs()
    # nivel a partir do qual o fechamento da vela 3 conta como "entrou de
    # verdade" no corpo da vela 1 (D-2, altista: c2 > o2) — 0.5 = metade.
    threshold1 = c2 - STAR_CLOSE_INTO_BODY1_RATIO * (c2 - o2)
    prev2_bull = c2 > o2
    middle_small = body1 <= STAR_MIDDLE_BODY_RATIO * body2
    curr_bear = c < o
    closes_into_body1 = c <= threshold1
    return (prev2_bull & middle_small & curr_bear & closes_into_body1).fillna(False)


def detect_three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    """Tres velas de alta consecutivas, cada uma abrindo dentro do corpo da
    anterior e fechando acima do fechamento anterior, sombras pequenas."""
    o, h, l, c = _ohlc(df)
    o1, h1, c1 = o.shift(1), h.shift(1), c.shift(1)
    o2, h2, c2 = o.shift(2), h.shift(2), c.shift(2)
    body0 = c - o
    body1 = c1 - o1
    body2 = c2 - o2
    upper0 = h - c
    upper1 = h1 - c1
    all_bull = (c > o) & (c1 > o1) & (c2 > o2)
    opens_inside = (o > o1) & (o < c1) & (o1 > o2) & (o1 < c2)
    progressive = (c > c1) & (c1 > c2)
    small_upper = (upper0 <= SOLDIERS_SHADOW_BODY_RATIO * body0) & (upper1 <= SOLDIERS_SHADOW_BODY_RATIO * body1)
    return (all_bull & opens_inside & progressive & small_upper).fillna(False)


def detect_three_black_crows(df: pd.DataFrame) -> pd.Series:
    """Espelho: tres velas de baixa consecutivas, cada uma abrindo dentro
    do corpo da anterior e fechando abaixo, sombras pequenas."""
    o, h, l, c = _ohlc(df)
    o1, l1, c1 = o.shift(1), l.shift(1), c.shift(1)
    o2, l2, c2 = o.shift(2), l.shift(2), c.shift(2)
    body0 = o - c
    body1 = o1 - c1
    body2 = o2 - c2
    lower0 = c - l
    lower1 = c1 - l1
    all_bear = (c < o) & (c1 < o1) & (c2 < o2)
    opens_inside = (o < o1) & (o > c1) & (o1 < o2) & (o1 > c2)
    progressive = (c < c1) & (c1 < c2)
    small_lower = (lower0 <= SOLDIERS_SHADOW_BODY_RATIO * body0) & (lower1 <= SOLDIERS_SHADOW_BODY_RATIO * body1)
    return (all_bear & opens_inside & progressive & small_lower).fillna(False)


# ---------------------------------------------------------------------------
# Registro — nome -> (detector, direcao esperada pela literatura)
# ---------------------------------------------------------------------------

class PatternSpec(NamedTuple):
    detector: Callable[[pd.DataFrame], pd.Series]
    direction: Direction
    n_bars: int  # quantas velas o padrao consome (para descartar o inicio da serie)


PATTERNS: dict[str, PatternSpec] = {
    "doji": PatternSpec(detect_doji, "neutral", 1),
    "dragonfly_doji": PatternSpec(detect_dragonfly_doji_bullish, "bullish", 1),
    "gravestone_doji": PatternSpec(detect_gravestone_doji_bearish, "bearish", 1),
    "marubozu_bullish": PatternSpec(detect_marubozu_bullish, "bullish", 1),
    "marubozu_bearish": PatternSpec(detect_marubozu_bearish, "bearish", 1),
    "hammer": PatternSpec(detect_hammer, "bullish", 1),
    "hanging_man": PatternSpec(detect_hanging_man, "bearish", 1),
    "inverted_hammer": PatternSpec(detect_inverted_hammer, "bullish", 1),
    "shooting_star": PatternSpec(detect_shooting_star, "bearish", 1),
    "bullish_engulfing": PatternSpec(detect_bullish_engulfing, "bullish", 2),
    "bearish_engulfing": PatternSpec(detect_bearish_engulfing, "bearish", 2),
    "bullish_harami": PatternSpec(detect_bullish_harami, "bullish", 2),
    "bearish_harami": PatternSpec(detect_bearish_harami, "bearish", 2),
    "piercing_line": PatternSpec(detect_piercing_line, "bullish", 2),
    "dark_cloud_cover": PatternSpec(detect_dark_cloud_cover, "bearish", 2),
    "tweezer_bottom": PatternSpec(detect_tweezer_bottom, "bullish", 2),
    "tweezer_top": PatternSpec(detect_tweezer_top, "bearish", 2),
    "morning_star": PatternSpec(detect_morning_star, "bullish", 3),
    "evening_star": PatternSpec(detect_evening_star, "bearish", 3),
    "three_white_soldiers": PatternSpec(detect_three_white_soldiers, "bullish", 3),
    "three_black_crows": PatternSpec(detect_three_black_crows, "bearish", 3),
}
