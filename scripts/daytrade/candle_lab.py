"""Infra COMPARTILHADA da frente "padroes de candlestick" (pedido do dono,
2026-08-26) -- carregar dado M5/M15/M30 de WIN@/WDO@, aplicar o split
CONGELADO oficial (`backtest.intraday.profiles.OOS_CUTOFF`, so `.in_sample()`
-- nunca `.unlock()`) e medir excursao/retorno APOS uma barra qualquer, sem
look-ahead. Mesmo papel que `copa_lab.py` tem para a familia `copa`: um
lugar so' para o fio carregar-dado -> preparar -> medir, para
`candle_measure.py` e `candle_null_calibration.py` nao duplicarem a
montagem.

Mora em `scripts/` (orquestracao), nao em `backtest/`/`strategy/`, pela mesma
regra de fronteira que `copa_lab.py` documenta: precisa importar
`market_data_intraday`, `backtest` e `strategy` ao mesmo tempo, e uma
feature so' pode importar `core/` (AGENTS.md #1).

## Por que M15 (nao M1) por padrao

Padroes de candlestick sao desenhados para timeframes onde uma vela
representa uma decisao de mercado com algum peso -- em M1 o ruido
microestrutural (book fino, 1 negocio decidindo o candle inteiro) domina a
FORMA da vela, e o catalogo classico (Nison 1991) foi calibrado em barras
diarias. M15 e' o meio-termo: agrega ruido de M1 mas ainda da' ~38 velas por
pregao (amostra grande) em vez de 1 vela/dia. Os parquets M5/M30 tambem
existem em `data/raw_intraday/` (mesmo `INTRADAY_DATA_DIR`) para quem quiser
comparar timeframe sem reamostrar.

## Por que a serie e' mais LONGA que o M1 usado no resto do projeto

`market_data_intraday.storage.load_m1` so' tem WIN@ desde 2025-12-01/WDO@
desde 2025-12-08 (9 meses). Os parquets M5/M15/M30 foram baixados
DIRETAMENTE do MT5 nesses timeframes (nao reamostrados do M1 salvo aqui) e o
terminal guarda historico muito mais longo para barras de timeframe maior --
a serie M15 comeca em 2021-08-25. Isso muda o carater da amostra: anos de
regime de preco/volatilidade diferentes da serie continua WIN@/WDO@, dado
que ela EMENDA vencimentos (`SymbolProfile.price_tick_size`, ver
`profiles.py`) -- um padrao de vela (razao corpo/sombra, RELATIVA ao range
da propria barra) e' escala-invariante a isso, mas vale registrar que a
amostra cobre um periodo bem mais amplo que o resto da pesquisa de day
trade neste repo.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import OOS_CUTOFF, profile_for  # noqa: E402
from core.config import INTRADAY_DATA_DIR  # noqa: E402

Timeframe = Literal["M5", "M15", "M30"]

_FROZEN_NOTE = (
    "corte OFICIAL reaproveitado de `backtest.intraday.profiles.OOS_CUTOFF` "
    "(congelado 2026-08-22, antes desta frente de pesquisa existir) -- so' "
    "`.in_sample()` e' usado aqui; OOS fica travado ate' decisao do dono."
)


def _safe_symbol(symbol: str) -> str:
    """Mesma sanitizacao de `market_data_intraday.storage._parquet_path` --
    duplicada aqui (nao importada) porque aquela funcao e' privada e o nome
    de arquivo do M15/M5/M30 tem um SUFIXO que `storage.py` nao conhece."""
    return symbol.replace("$", "_D_").replace("@", "_A_").replace(".", "_")


def _timeframe_path(symbol: str, timeframe: Timeframe) -> Path:
    # `_safe_symbol` ja' termina em "_" para simbolo de futuro (`WIN@` ->
    # `WIN_A_`) -- SEM separador extra aqui, ou o nome fica `WIN_A__M15`
    # (dois underscores) em vez do arquivo real `WIN_A_M15.parquet`.
    return INTRADAY_DATA_DIR / f"{_safe_symbol(symbol)}{timeframe}.parquet"


def load_timeframe_bars(symbol: str, timeframe: Timeframe = "M15") -> pd.DataFrame:
    """OHLCV bruto do parquet `{symbol}_{timeframe}.parquet` -- `SystemExit`
    (nao excecao generica) se o arquivo nao existir, mesmo estilo de
    `copa_lab.barras` para uma varredura interativa falhar com instrucao
    clara em vez de traceback."""
    path = _timeframe_path(symbol, timeframe)
    if not path.exists():
        raise SystemExit(
            f"[candle_lab] sem parquet {timeframe} para {symbol!r} em {path} -- "
            f"esperado ja' existir em `data/raw_intraday/` (ver docstring do modulo)."
        )
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def in_sample_bars(symbol: str, timeframe: Timeframe = "M15") -> pd.DataFrame:
    """Barras `timeframe` de `symbol`, JA' recortadas para o trecho
    IN-SAMPLE do split congelado oficial -- unico caminho que este modulo
    oferece (nada aqui chama `.unlock()`)."""
    bars = load_timeframe_bars(symbol, timeframe)
    split = declare_frozen_split(cutoff=OOS_CUTOFF, note=_FROZEN_NOTE)
    locked = LockedBars(bars, split)
    return locked.in_sample()


@dataclass(frozen=True)
class ForwardStats:
    """Estatisticas de excursao/retorno apos CADA barra `t`, olhando so'
    para a frente (`t+1..t+horizon`) -- nunca a propria barra `t` nem
    qualquer coisa antes dela. Entrada = ABERTURA da barra `t+1` (mesma
    disciplina anti-look-ahead de `IntradayStrategy`: decisao no fechamento
    de `t`, execucao na abertura de `t+1`, AGENTS.md regra 4). Todas as
    series sao RETORNO percentual sobre o preco de entrada (adimensional,
    comparavel entre WIN@ e WDO@ apesar da escala de preco diferente).

    `ret`: retorno da entrada ate' o FECHAMENTO da barra `t+horizon`
    (resultado de "comprar/vender e segurar `horizon` barras").
    `mfe_up`/`mfe_down`: excursao maxima FAVORAVEL a um LONG / a um SHORT
    dentro da janela `t+1..t+horizon` -- `mfe_up` e' o MFE de quem comprou,
    `mfe_down` e' o MFE de quem vendeu (== MAE de quem comprou). Um padrao
    de hipotese ALTISTA usa `mfe_up` como "favoravel" e `mfe_down` como
    "adverso"; um padrao BAIXISTA usa o inverso.
    """

    horizon: int
    entry: pd.Series
    ret: pd.Series
    mfe_up: pd.Series
    mfe_down: pd.Series

    def valid_mask(self) -> pd.Series:
        """Barras onde a janela `t+1..t+horizon` existe INTEIRA (nao corta
        o fim da serie) -- exclui as ultimas `horizon` barras."""
        return self.ret.notna() & self.mfe_up.notna() & self.mfe_down.notna()


def _forward_rolling(series: pd.Series, window: int, how: Literal["max", "min"]) -> pd.Series:
    """Rolling PARA A FRENTE: no indice `t`, agrega `series[t..t+window-1]`
    (nao `series[t-window+1..t]`, que e' o rolling padrao do pandas).
    Truque: reverte a serie, aplica rolling padrao (agora "para tras" na
    serie revertida == "para frente" na original), reverte de volta.
    `min_periods=window` -- janela incompleta no fim da serie vira `NaN`,
    nunca um numero calculado sobre menos barras do que o horizonte pede."""
    reversed_series = series.iloc[::-1]
    if how == "max":
        rolled = reversed_series.rolling(window, min_periods=window).max()
    else:
        rolled = reversed_series.rolling(window, min_periods=window).min()
    return rolled.iloc[::-1]


def forward_stats(df: pd.DataFrame, horizon: int) -> ForwardStats:
    """Constroi `ForwardStats` para TODAS as barras de `df` de uma vez
    (vetorizado) -- quem for medir um padrao especifico so' precisa indexar
    pelas posicoes onde o padrao ocorreu (`series[mask]`)."""
    if horizon < 1:
        raise ValueError(f"horizon precisa ser >= 1, recebeu {horizon!r}")
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    entry = open_.shift(-1)
    fwd_high = high.shift(-1)
    fwd_low = low.shift(-1)
    fwd_close = close.shift(-horizon)

    roll_max = _forward_rolling(fwd_high, horizon, "max")
    roll_min = _forward_rolling(fwd_low, horizon, "min")

    ret = (fwd_close - entry) / entry
    mfe_up = (roll_max - entry) / entry
    mfe_down = (entry - roll_min) / entry
    return ForwardStats(horizon=horizon, entry=entry, ret=ret, mfe_up=mfe_up, mfe_down=mfe_down)


def point_value_brl(symbol: str) -> float:
    """`R$ por PONTO de preco` do simbolo, lido do perfil economico oficial
    (`backtest.intraday.profiles`) -- usado so' para traduzir um retorno
    percentual medido em R$/contrato aproximado (nivel de preco atual x
    ponto), NUNCA para decidir se um padrao "funciona" (isso e' o teste de
    permutacao em cima do RETORNO, escala-invariante)."""
    profile = profile_for(symbol)
    # Mesma tabela de fallback de `copa_lab._ECONOMIA_CONHECIDA` -- point
    # value = trade_tick_value / trade_tick_size, deriva do TICK REAL do
    # contrato (nao da serie continua, que reporta o tick errado -- ver
    # `SymbolProfile.price_tick_size`).
    economia_conhecida = {"WIN@": (0.2, 1.0), "WDO@": (0.01, 0.001)}
    trade_tick_value, trade_tick_size = economia_conhecida[symbol]
    if profile.price_tick_size is not None:
        base_point_value = trade_tick_value / trade_tick_size
        return base_point_value  # ja' e' R$/ponto de preco, independente do tick de exibicao
    return trade_tick_value / trade_tick_size


def round_trip_cost_brl(symbol: str) -> float:
    """Custo de ida-e-volta de 1 contrato, em R$ -- `FUTURES_FEE_ROUND_TRIP_
    BRL` (corretagem) + 2x `slippage_ticks` (entrada e saida, cada uma
    "paga" a slippage do motor). Referencia HONESTA para saber se um
    retorno medio conditional a um padrao teria ALGUMA chance de sobreviver
    a custo, antes de se dar ao trabalho de montar uma `IntradayStrategy`
    de verdade."""
    from backtest.intraday.costs import IntradayCostModel

    profile = profile_for(symbol)
    economia_conhecida = {"WIN@": (0.2, 1.0), "WDO@": (0.01, 0.001)}
    trade_tick_value, trade_tick_size = economia_conhecida[symbol]
    if profile.price_tick_size is not None:
        pv = trade_tick_value / trade_tick_size
        trade_tick_size = profile.price_tick_size
        trade_tick_value = pv * trade_tick_size
    model = IntradayCostModel.from_symbol_info(
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        fee_round_trip_brl=profile.fee_round_trip_brl,
        exchange_fee_pct_per_leg=profile.exchange_fee_pct_per_leg,
    )
    slippage_brl = 2.0 * model.slippage_ticks * model.tick_size * model.point_value_brl
    return model.fee_round_trip_brl + slippage_brl


SYMBOLS: tuple[str, ...] = ("WIN@", "WDO@")
HORIZONS: tuple[int, ...] = (4, 16, 37)  # ~1h, ~4h, ~1 pregao (38 barras M15/dia)


def mirror_signflip_synthetic(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """CALIBRACAO NULA (pedido do dono): serie sintetica SEM ESTRUTURA
    direcional, construida a partir das barras REAIS -- mesma familia do
    "sign-flip nos dias" ja' usado no resto do projeto
    (`metodo_nulo_signflip_custo`), so' que por BARRA (nao por dia, ja' que
    aqui a unidade e' M15) e por ESPELHAMENTO da vela inteira, nao so' do
    retorno.

    Para cada barra `t` (exceto a primeira), sorteia um sinal `s ~
    Rademacher(+-1)` e:
    - se `s=+1`: mantem a barra like real (gap de abertura, corpo, sombra
      superior/inferior todos preservados em % sobre o fechamento/abertura
      anteriores).
    - se `s=-1`: ESPELHA a barra verticalmente em torno da propria abertura
      -- o corpo troca de sinal (bull vira bear com o MESMO tamanho) e as
      sombras trocam de papel (a sombra que era superior vira inferior,
      preservando a MAGNITUDE de cada uma).

    O resultado preserva, barra a barra, a MESMA distribuicao de tamanho de
    corpo/sombra/gap que a serie real (portanto os detectores de padrao
    ainda encontram "padroes" nela com taxa de ocorrencia parecida) mas
    destroi qualquer dependencia serial genuina (tendencia, autocorrelacao,
    e qualquer relacao real entre "este padrao apareceu" e "o que veio
    depois") -- exatamente o que a calibracao nula precisa isolar.

    Reconstrucao 100% VETORIZADA via produto acumulado dos fatores
    multiplicativos de cada barra (gap + corpo), preservando continuidade
    de preco (`open[t]` deriva de `close[t-1]`, nunca solto no ar)."""
    o = df["open"].to_numpy(dtype=np.float64)
    h = df["high"].to_numpy(dtype=np.float64)
    l = df["low"].to_numpy(dtype=np.float64)
    c = df["close"].to_numpy(dtype=np.float64)
    n = len(df)

    rng = np.random.default_rng(seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=n)
    signs[0] = 1.0  # 1a barra sem `prevclose` sintetico -- mantida como veio

    o_ret = np.zeros(n)
    o_ret[1:] = (o[1:] - c[:-1]) / c[:-1]
    h_ret = (h - o) / o
    l_ret = (l - o) / o
    c_ret = (c - o) / o

    factor = np.ones(n)
    factor[1:] = (1.0 + signs[1:] * o_ret[1:]) * (1.0 + signs[1:] * c_ret[1:])
    new_close = c[0] * np.cumprod(factor)
    new_open = new_close.copy()
    new_open[1:] = new_close[:-1] * (1.0 + signs[1:] * o_ret[1:])
    new_open[0] = o[0]
    new_close[0] = c[0]

    new_high = np.where(signs > 0, new_open * (1.0 + h_ret), new_open * (1.0 - l_ret))
    new_low = np.where(signs > 0, new_open * (1.0 + l_ret), new_open * (1.0 - h_ret))
    new_high[0], new_low[0] = h[0], l[0]

    out = df.copy()
    out["open"], out["high"], out["low"], out["close"] = new_open, new_high, new_low, new_close
    return out


#: Numero de PERMUTACOES por celula (padrao x simbolo x horizonte). 300 da'
#: resolucao de p-valor ~0,0033 (1/(300+1)) -- suficiente para separar
#: "nada aqui" de "candidato a olhar melhor" num lote de ~126 celulas sem
#: gastar minutos por celula. Quem quiser confirmar um sobrevivente de
#: verdade sobe isto na chamada (ver `candle_measure.py --confirm`).
DEFAULT_N_PERM = 300


@dataclass(frozen=True)
class PermutationResult:
    observed: float
    p_value: float
    n_occurrences: int
    n_population: int


def permutation_test(
    values: pd.Series,
    occurs: pd.Series,
    valid: pd.Series,
    *,
    two_sided: bool,
    n_perm: int = DEFAULT_N_PERM,
    seed: int = 0,
) -> PermutationResult:
    """Teste de permutacao: embaralha QUAL barra "teria" o padrao (sorteia
    `k` posicoes ao acaso dentre as `n` validas, sem reposicao, `n_perm`
    vezes) e compara a media observada nas posicoes REAIS do padrao contra
    essa distribuicao nula -- exatamente o pedido do dono ("embaralhe a
    OCORRENCIA do padrao"), nao um z-test com desvio-padrao classico.

    `values`/`occurs`/`valid` tem que compartilhar o MESMO index (todos
    vem de `ForwardStats` + `PatternSpec.detector` sobre o mesmo `df`).
    `two_sided=True` para hipotese SEM direcao a priori (doji generico):
    `p = P(|nulo| >= |observado|)`. `two_sided=False` para hipotese
    DIRECIONAL (a maioria dos padroes, ja' orientada pelo sinal de
    `values` -- ver `evaluate_pattern`): `p = P(nulo >= observado)`.

    Correcao de +1 no numerador/denominador (`(hits+1)/(n_perm+1)`) e'
    convencao padrao para nunca reportar `p=0,0` de um numero finito de
    permutacoes -- p-valor exato so' pode ser tao pequeno quanto
    `1/(n_perm+1)`, nunca zero."""
    v = values[valid].to_numpy(dtype=np.float64)
    m = occurs[valid].to_numpy(dtype=bool)
    n = v.shape[0]
    k = int(m.sum())
    if k == 0 or k >= n:
        return PermutationResult(observed=float("nan"), p_value=float("nan"), n_occurrences=k, n_population=n)
    observed = float(v[m].mean())
    rng = np.random.default_rng(seed)
    # Um `rng.permutation(n)[:k]` POR ITERACAO (em vez de materializar uma
    # matriz `(n_perm, n)` de chaves aleatorias de uma vez) -- mesmo
    # resultado estatistico (sorteio de `k` posicoes sem reposicao dentre
    # `n`, `n_perm` vezes), pico de memoria O(n) em vez de O(n_perm*n)
    # (que para n~45.000 e n_perm~300 já passava de 50 MB por chamada, x2
    # chamadas por celula x ~126 celulas -- alocacao/liberacao repetida
    # grande o bastante para dominar o tempo de parede medido na pratica).
    null_means = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        idx = rng.permutation(n)[:k]
        null_means[i] = v[idx].mean()
    if two_sided:
        hits = int(np.sum(np.abs(null_means) >= abs(observed)))
    else:
        hits = int(np.sum(null_means >= observed))
    p_value = (hits + 1) / (n_perm + 1)
    return PermutationResult(observed=observed, p_value=p_value, n_occurrences=k, n_population=n)


@dataclass(frozen=True)
class PatternCellResult:
    """Uma CELULA da varredura (1 padrao x 1 simbolo x 1 horizonte) --
    `candle_measure.py` monta uma linha de tabela por celula, e reporta
    TODAS (nao so' as "boas"), regra explicita do dono contra recorte
    silencioso em teste multiplo."""

    symbol: str
    timeframe: str
    horizon_bars: int
    pattern: str
    direction: str  # "bullish" | "bearish" | "neutral"
    n_occurrences: int
    n_population: int
    mean_ret_pct: float  # retorno medio NA DIRECAO da hipotese (>0 = a favor)
    ret_p_value: float
    mean_favorable_pct: float  # MFE do lado favoravel a` hipotese
    mean_adverse_pct: float  # MFE do lado adverso (== MAE do lado favoravel)
    asymmetry_pct: float  # favoravel - adverso; 0 sob simetria MFE=MAE
    asymmetry_p_value: float
    mean_ret_brl_per_contract: float
    round_trip_cost_brl: float
    net_brl_per_contract: float

    @property
    def occurrence_rate_pct(self) -> float:
        return 100.0 * self.n_occurrences / self.n_population if self.n_population else 0.0


def evaluate_pattern(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    pattern_name: str,
    detector,
    direction: str,
    horizon: int,
    *,
    n_perm: int = DEFAULT_N_PERM,
    seed: int = 0,
) -> PatternCellResult:
    """Uma celula completa: detecta o padrao em `df`, mede retorno e
    MFE/MAE condicionais no horizonte `horizon`, roda os DOIS testes de
    permutacao (retorno direcional + assimetria MFE/MAE) e converte o
    retorno medio para R$/contrato usando a economia REAL do simbolo."""
    occurs = detector(df)
    stats = forward_stats(df, horizon)
    valid = stats.valid_mask()

    two_sided = direction == "neutral"
    if direction == "bearish":
        ret_dir = -stats.ret
        favorable, adverse = stats.mfe_down, stats.mfe_up
    else:  # "bullish" ou "neutral" -- ret cru, sem inverter sinal
        ret_dir = stats.ret
        favorable, adverse = stats.mfe_up, stats.mfe_down

    ret_result = permutation_test(ret_dir, occurs, valid, two_sided=two_sided, n_perm=n_perm, seed=seed)

    asym = favorable - adverse
    asym_result = permutation_test(asym, occurs, valid, two_sided=two_sided, n_perm=n_perm, seed=seed + 1)

    mask = valid & occurs
    mean_fav = float(favorable[mask].mean()) if mask.any() else float("nan")
    mean_adv = float(adverse[mask].mean()) if mask.any() else float("nan")

    entry_price = float(stats.entry[mask].mean()) if mask.any() else float("nan")
    pv = point_value_brl(symbol)
    mean_ret_brl = ret_result.observed * entry_price * pv if not np.isnan(ret_result.observed) else float("nan")
    cost = round_trip_cost_brl(symbol)
    net_brl = mean_ret_brl - cost if not np.isnan(mean_ret_brl) else float("nan")

    return PatternCellResult(
        symbol=symbol, timeframe=timeframe, horizon_bars=horizon, pattern=pattern_name, direction=direction,
        n_occurrences=ret_result.n_occurrences, n_population=ret_result.n_population,
        mean_ret_pct=ret_result.observed * 100.0, ret_p_value=ret_result.p_value,
        mean_favorable_pct=mean_fav * 100.0, mean_adverse_pct=mean_adv * 100.0,
        asymmetry_pct=asym_result.observed * 100.0, asymmetry_p_value=asym_result.p_value,
        mean_ret_brl_per_contract=mean_ret_brl, round_trip_cost_brl=cost, net_brl_per_contract=net_brl,
    )
