"""Hipotese de CONTINUIDADE (pedido direto do dono, 2026-08-26): "se um dia
fechou positivo/negativo, as chances de repetir o lado no dia seguinte nao
sao maiores que o acaso? E isso vale para ciclos mais finos (hora, 15min,
5min) e para pernas de swing (zigzag)?"

ESTAGIO A (este script): so' descreve/testa a dependencia BRUTA de ordem
(autocorrelacao/Markov) das tres sub-hipoteses, IN-SAMPLE, com teste de
PERMUTACAO (nunca so' um p-valor parametrico -- retorno de futuro nao
respeita as premissas de um teste classico). Nao aplica custo nem vira regra
de trade aqui -- isso e' o ESTAGIO B (`continuidade_daily_rule.py`), so'
justificado SE alguma dependencia sobreviver aqui.

## As tres sub-hipoteses, cada uma para WIN@ E WDO@ SEPARADAMENTE

1. DIARIA: retorno fechamento-a-fechamento do dia D prediz o SINAL do dia
   D+1? Autocorrelacao lag-1/2/3 do retorno diario.
2. INTRADIARIA: o mesmo efeito em barras de 1 hora / 15min / 5min
   (reamostradas do M1 salvo, DENTRO de cada sessao -- nunca cruzando
   meia-noite, ver `continuidade_permutation.lag_pairs`)? Lag-1/2/3.
3. PERNA (swing): zigzag por limiar em TICKS sobre o preco continuo do IS
   inteiro (nao resetado por sessao -- um "ciclo de mercado" nao respeita
   fronteira de pregao). Depois de uma perna de alta seguida de queda, a
   proxima perna de alta SUPERA a anterior (nova maxima, "higher high") com
   probabilidade maior que o acaso? E o espelho para fundos (nova minima
   apos perna de baixa)? Ver a docstring de `continuidade_zigzag.
   continuation_series` para o motivo de NAO testar a direcao crua da perna
   (alterna low/high por CONSTRUCAO -- certeza, nao hipotese).

## Disciplina de teste (briefing da rodada)

- So' `LockedBars.in_sample()` -- `.unlock()` NUNCA chamado.
- Teste de PERMUTACAO para toda autocorrelacao/dependencia (embaralha a
  ORDEM `N_PERM` vezes, ve onde o valor real cai na distribuicao).
- TODOS os horizontes/lags testados sao reportados, nunca so' o melhor.
- PROMOCAO a regra de trade (estagio B) e' decidida ANTES de olhar o
  resultado, para nao virar "escolher o melhor de varios depois de olhar":
  * Diaria: promove lag-1 (o horizonte literal do pedido) se
    `p_two_sided < 0.05` da estatistica `corr`, por simbolo. Lag-2/3 sao
    reportados por transparencia, nunca usados pra promover.
  * Intradiaria: promove lag-1 por timeframe se `p_two_sided` bater
    Bonferroni sobre as 3 timeframes daquele simbolo (`0.05/3`).
  * Perna: promove lag-1 por (limiar, lado) se `p_two_sided` bater
    Bonferroni sobre os 3 limiares x 2 lados daquele simbolo (`0.05/6`).
  A estatistica `sign_match` (fracao de mesmo sinal - 0,5) e' SECUNDARIA,
  so' para leitura intuitiva -- nunca decide promocao (evita contar o
  mesmo teste duas vezes).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.intraday.continuidade_permutation import (  # noqa: E402
    PermutationResult,
    pearson_corr,
    permutation_test,
    sign_match_rate,
)
from backtest.intraday.continuidade_zigzag import (  # noqa: E402
    continuation_series,
    zigzag_pivots,
)
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

SYMBOLS = ("WIN@", "WDO@")

#: Mesmo filtro de `scripts/daytrade/copa_lab.py`/`win_orb_lab.py`: um
#: pregao incompleto (feriado de meio-expediente, inicio de coleta no meio
#: do dia) nao e' um pregao tipico e distorce media/variancia. So' derruba
#: 1-2 sessoes de ~125-130 em cada simbolo (medido).
MIN_BARRAS_POR_PREGAO = 400

STAT_FNS = {"corr": pearson_corr, "sign_match": sign_match_rate}
LAGS = (1, 2, 3)

N_PERM_DAILY = 20000
N_PERM_INTRADAY = 3000
# Reduzido de 20.000 para 4.000 (2026-08-26, meio da rodada): a maquina
# tinha ~50 processos python concorrentes de OUTRAS frentes de pesquisa
# disputando CPU ao mesmo tempo -- 20.000 tornava cada celula da secao de
# perna impraticavel neste ambiente compartilhado. 4.000 ainda da' precisao
# de percentil de 0,025pp (1/(4000+1)) no minimo de p_two_sided, suficiente
# para o corte de promocao desta rodada (`ALPHA`/bonferroni, nunca abaixo
# de ~0,004).
N_PERM_SWING = 4000
SEED = 20260826  # data da decisao de escopo desta rodada -- fixo, nao escolhido apos ver resultado

#: Limiares de zigzag em TICKS, um por simbolo, com a razao medida (ver
#: docstring do modulo): ~4-15x a mediana do movimento |M1| (ruido de 1
#: minuto) e ~5-20% da mediana do range diario -- ordem de grandeza
#: comparavel entre os dois simbolos, apesar de tick/ponto nao serem a
#: mesma coisa neles. Testar 3 escalas (nao 1) e' o pedido explicito do
#: briefing ("teste mais de um").
ZIGZAG_THRESHOLDS_TICKS = {
    # WIN@: mediana |M1|=8,2 ticks, mediana range diario=554,6 ticks (medido
    # no IS completo). 30/50/100 ticks = 3,7x/6,1x/12,2x o ruido de 1 minuto
    # e 5,4%/9,0%/18,0% do range diario tipico.
    "WIN@": (30, 50, 100),
    # WDO@: mediana |M1|=2,0 ticks, mediana range diario=97,1 ticks. 10/20/30
    # ticks = 4,9x/9,9x/14,8x o ruido de 1 minuto e 10,3%/20,6%/30,9% do
    # range diario tipico.
    "WDO@": (10, 20, 30),
}

ALPHA = 0.05


def carregar_is_bars(symbol: str) -> pd.DataFrame:
    df = load_m1(symbol)
    if df.empty:
        raise SystemExit(
            f"[continuidade_stats] sem dado M1 salvo para {symbol!r} -- rode "
            f"scripts/daytrade/backfill_m1.py --symbol {symbol} primeiro."
        )
    df = df.sort_index()
    profile = profile_for(symbol)
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    isb = LockedBars(df, split).in_sample()
    contagem = isb.groupby(isb.index.date).size()
    completos = set(contagem[contagem >= MIN_BARRAS_POR_PREGAO].index)
    return isb[[d in completos for d in isb.index.date]]


# --------------------------------------------------------- 1) DIARIA -------

def daily_returns(bars: pd.DataFrame) -> np.ndarray:
    closes = bars.groupby(bars.index.date)["close"].last().sort_index()
    return closes.pct_change().dropna().to_numpy()


# ------------------------------------------------------- 2) INTRADIARIA ----

def intraday_return_groups(bars: pd.DataFrame, rule: str) -> list[np.ndarray]:
    """Uma lista de arrays de retorno, UM POR SESSAO -- fechamento de barra
    reamostrada (`rule`: '1h'/'15min'/'5min') contra o fechamento anterior
    DENTRO da mesma sessao (`lag_pairs` ja garante nunca cruzar sessao, mas
    montar os grupos por sessao aqui e' o que faz isso valer -- ver
    docstring do modulo)."""
    groups: list[np.ndarray] = []
    for _, grp in bars.groupby(bars.index.date):
        closes = grp["close"].resample(rule, label="right", closed="right").last().dropna()
        rets = closes.pct_change().dropna().to_numpy()
        if len(rets) > 0:
            groups.append(rets)
    return groups


# ------------------------------------------------------------- 3) PERNA ----

def swing_series(bars: pd.DataFrame, threshold_ticks: float, tick_size: float) -> dict[str, np.ndarray]:
    """Preco CONTINUO do IS inteiro (nao resetado por sessao -- ver
    docstring do modulo), zigzag por `threshold_ticks x tick_size`, series
    de continuacao de topo/fundo."""
    pivots = zigzag_pivots(bars["close"], threshold_ticks * tick_size)
    cont = continuation_series(pivots)
    return {"high": np.array(cont["high"], dtype=float), "low": np.array(cont["low"], dtype=float)}


# --------------------------------------------------------- impressao -------

def _fmt_stat(name: str, r) -> str:
    return (f"{name}: real={r.real:+.4f} nulo(media={r.null_mean:+.4f} "
            f"dp={r.null_std:.4f}) percentil={r.percentile:5.1f}% "
            f"p2s={r.p_two_sided:.4f}")


def _print_result(rotulo: str, res: PermutationResult) -> None:
    linha = "  ".join(_fmt_stat(name, r) for name, r in res.stats.items())
    print(f"    lag={res.lag} n_pares={res.n_pairs:6d} n_grupos={res.n_groups:4d} "
          f"n_perm={res.n_perm:6d}  {linha}")


def _promove(res: PermutationResult, alpha: float) -> bool:
    return res.stats["corr"].p_two_sided < alpha


def main() -> None:
    t0 = time.time()
    promovidos: list[str] = []

    for symbol in SYMBOLS:
        print(f"\n{'='*100}\n{symbol}\n{'='*100}")
        bars = carregar_is_bars(symbol)
        n_sessoes = bars.index.normalize().nunique()
        print(f"IS: {len(bars)} barras M1, {n_sessoes} pregoes completos "
              f"({bars.index.min()} -> {bars.index.max()})")

        # ---------------------------------------------------- 1) DIARIA ---
        print("\n--- 1) CONTINUIDADE DIARIA (retorno fechamento-a-fechamento) ---")
        rets = daily_returns(bars)
        print(f"  {len(rets)} retornos diarios "
              f"(sinal + : {int((rets>0).sum())}  sinal - : {int((rets<0).sum())}  "
              f"zero : {int((rets==0).sum())})")
        lag1_daily = None
        for lag in LAGS:
            res = permutation_test([rets], lag=lag, stat_fns=STAT_FNS,
                                    n_perm=N_PERM_DAILY, seed=SEED)
            _print_result("dia", res)
            if lag == 1:
                lag1_daily = res
        if _promove(lag1_daily, ALPHA):
            direcao = "continuacao" if lag1_daily.stats["corr"].real > 0 else "reversao"
            promovidos.append(f"{symbol} diaria lag1 ({direcao}, p={lag1_daily.stats['corr'].p_two_sided:.4f})")
            print(f"  >>> PROMOVIDO ao estagio B: lag-1 p2s="
                  f"{lag1_daily.stats['corr'].p_two_sided:.4f} < {ALPHA} (direcao: {direcao})")

        # ------------------------------------------------- 2) INTRADIARIA -
        print("\n--- 2) CONTINUIDADE INTRADIARIA (bar-a-bar dentro da sessao) ---")
        alpha_intraday = ALPHA / 3.0  # bonferroni sobre 3 timeframes
        for rule, rotulo in (("1h", "1 hora"), ("15min", "15 minutos"), ("5min", "5 minutos")):
            groups = intraday_return_groups(bars, rule)
            n_pontos = sum(len(g) for g in groups)
            print(f"  [{rotulo}] {len(groups)} sessoes, {n_pontos} barras reamostradas no total")
            lag1_res = None
            for lag in LAGS:
                res = permutation_test(groups, lag=lag, stat_fns=STAT_FNS,
                                        n_perm=N_PERM_INTRADAY, seed=SEED)
                _print_result(rotulo, res)
                if lag == 1:
                    lag1_res = res
            if _promove(lag1_res, alpha_intraday):
                direcao = "continuacao" if lag1_res.stats["corr"].real > 0 else "reversao"
                promovidos.append(f"{symbol} intraday {rotulo} lag1 ({direcao}, "
                                   f"p={lag1_res.stats['corr'].p_two_sided:.4f})")
                print(f"    >>> PROMOVIDO ao estagio B: lag-1 p2s="
                      f"{lag1_res.stats['corr'].p_two_sided:.4f} < {alpha_intraday:.4f} "
                      f"(bonferroni/3) (direcao: {direcao})")

        # ------------------------------------------------------- 3) PERNA -
        print("\n--- 3) CONTINUIDADE DE PERNA (zigzag por limiar em ticks) ---")
        profile = profile_for(symbol)
        tick_size = profile.price_tick_size
        thresholds = ZIGZAG_THRESHOLDS_TICKS[symbol]
        alpha_swing = ALPHA / (len(thresholds) * 2)  # bonferroni sobre limiares x lados
        for thr in thresholds:
            series = swing_series(bars, thr, tick_size)
            for lado, rotulo in (("high", "topo (nova maxima?)"), ("low", "fundo (nova minima?)")):
                s = series[lado]
                print(f"  [limiar={thr}ticks, {rotulo}] {len(s)} pernas testadas "
                      f"({int(s.sum())} continuaram, {int(len(s)-s.sum())} falharam)")
                if len(s) < 10:
                    print("    (poucas pernas -- pulando teste de permutacao)")
                    continue
                lag1_res = None
                for lag in LAGS:
                    if len(s) <= lag + 5:
                        continue
                    res = permutation_test([s], lag=lag, stat_fns=STAT_FNS,
                                            n_perm=N_PERM_SWING, seed=SEED)
                    _print_result(f"perna/{rotulo}", res)
                    if lag == 1:
                        lag1_res = res
                if lag1_res is not None and _promove(lag1_res, alpha_swing):
                    direcao = "persistencia" if lag1_res.stats["corr"].real > 0 else "alternancia"
                    promovidos.append(f"{symbol} perna thr={thr} {lado} lag1 "
                                       f"({direcao}, p={lag1_res.stats['corr'].p_two_sided:.4f})")
                    print(f"    >>> PROMOVIDO ao estagio B: lag-1 p2s="
                          f"{lag1_res.stats['corr'].p_two_sided:.4f} < {alpha_swing:.4f} "
                          f"(bonferroni/{len(thresholds)*2}) (direcao: {direcao})")

    print(f"\n{'='*100}")
    print("RESUMO -- promovidos ao ESTAGIO B (regra de trade + custo):")
    if promovidos:
        for p in promovidos:
            print(f"  - {p}")
    else:
        print("  NENHUM -- nenhuma dependencia bruta sobreviveu ao criterio de promocao "
              "pre-registrado em nenhum simbolo/horizonte.")
    print(f"\n[continuidade_stats] tempo total: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
