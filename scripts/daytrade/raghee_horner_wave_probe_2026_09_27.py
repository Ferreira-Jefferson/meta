"""Sonda (estagio 1, sem motor) do metodo "wave" de Raghee Horner no WDO@.

Pedido do dono: o que se sabe do metodo de Raghee Horner (autora de "Forex
Trading for Maximum Profit") e' util pro projeto? O elemento mais objetivavel
do metodo dela e' a "34 EMA wave": uma EMA de 34 periodos usada como filtro
de tendencia (preco acima = vies comprado, abaixo = vendido) e como zona de
entrada -- ela entra no PULLBACK ate' a wave (preco toca a EMA34 e volta),
nao no rompimento. Isso e' testavel sem motor: a EMA34 e o toque sao
calculaveis de OHLCV puro, sem look-ahead (a EMA no fechamento da barra t e'
so' funcao de close[<=t]).

Convencao do projeto ("o minimo que refuta primeiro",
feedback_teste_pequeno_valida_hipotese): correlacao/preditividade bruta, SEM
custo, SEM motor de execucao, familia PEQUENA de celulas (o suficiente pra
decidir se vale construir a IntradayStrategy completa). So' testamos aqui o
elemento mais forte do metodo (a wave/pullback); "squat candle" (candle de
range comprimido que ela usa como sinal auxiliar de exaustao) fica de fora
deste estagio -- so' voltaria se a wave sobrevivesse.

## A hipotese

Base: M1 continuo do WDO@ (`data/raw_intraday/WDO_A_M1_do_tick.parquet`,
76.039 barras, 134 pregoes, 2026-02-27..2026-09-11, indice UTC). A EMA34 e'
calculada de forma CONTINUA sobre a serie inteira (inclusive atravessando o
gap overnight) -- e' assim que um grafico real mostra a wave, ela nao reseta
por pregao.

Estado de tendencia na barra t: inclinacao da EMA34 nos ultimos
`SLOPE_LOOKBACK_MIN` minutos.
  * subindo -> tendencia de ALTA (espera-se continuacao para cima);
  * descendo -> tendencia de BAIXA.

Evento de toque na barra t (pullback ate' a wave):
  * em tendencia de ALTA: `low[t] <= ema34[t] + threshold` E `close[t] >=
    ema34[t]` (o preco desceu ate' perto/dentro da banda e fechou de volta
    por cima -- rejeicao, no espirito do metodo dela);
  * em tendencia de BAIXA: espelhado (toca por cima, fecha de volta por
    baixo).
Eventos muito proximos no tempo sao um UNICO evento (cooldown de
`COOLDOWN_MIN` barras entre toques contados) para nao inflar a amostra com
toques redundantes da mesma oscilacao.

Sem look-ahead: o toque e' conhecido no fechamento da barra t (EMA e' funcao
de close[<=t]); a "entrada" hipotetica e' `open[t+1]`; o retorno-alvo mede
ate' `close[t+H]`, H em minutos, SOMENTE quando t+H cai no MESMO pregao (UTC
date) de t -- um evento perto do fechamento cujo horizonte estouraria para o
pregao seguinte e' descartado (evitaria contaminar com o gap overnight, que
e' outro fenomeno, ja investigado em wdo_gap_proprio_padrao_2026_09_27.py).

`alinhado[t] = direcao[t] * (close[t+H] - open[t+1])`, em TICKS. `direcao` e'
+1 em toque de alta, -1 em toque de baixa. Sob H0 ("a direcao atribuida pela
tendencia da EMA34 nao carrega informacao"), o sinal de `alinhado` e' livre
(sign-flip exchangeable) -- mesmo teste de permutacao ja usado no estagio 3
de wdo_gap_proprio_padrao_2026_09_27.py (`_permutation_mean_ne_zero`).

Familia pequena, DECIDIDA ANTES de olhar o resultado (nao apos): 2 limiares
de toque (`THRESHOLDS_TICKS`) x 3 horizontes (`HORIZONS_MIN`) = 6 celulas,
Bonferroni sobre as 6.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from core.indicators import ema  # noqa: E402
from core.instruments import FUTUROS  # noqa: E402

WDO_TICK = FUTUROS["WDO@"].price_tick_size  # 0.5 ponto

EMA_SPAN = 34
SLOPE_LOOKBACK_MIN = 15
COOLDOWN_MIN = 30
THRESHOLDS_TICKS = [2, 4]
HORIZONS_MIN = [15, 30, 60]
N_PERM = 20_000
SEED = 20260927


def _load_m1() -> pd.DataFrame:
    path = REPO / "data" / "raw_intraday" / "WDO_A_M1_do_tick.parquet"
    df = pd.read_parquet(path, columns=["open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    return df


def _permutation_mean_ne_zero(y: np.ndarray, rng: np.random.Generator, n_perm: int) -> tuple[float, float]:
    """Sign-flip: sob H0 (media zero), o sinal de cada observacao e' livre.
    Identico ao teste do estagio 3 de wdo_gap_proprio_padrao_2026_09_27.py."""
    obs = float(np.mean(y))
    abs_y = np.abs(y)
    perm = np.empty(n_perm)
    for i in range(n_perm):
        flips = rng.choice([-1.0, 1.0], size=len(y))
        perm[i] = np.mean(flips * abs_y)
    p2s = float(np.mean(np.abs(perm) >= abs(obs)))
    return obs, p2s


def _events(df: pd.DataFrame, threshold_ticks: int) -> pd.DataFrame:
    """Toques (evento + direcao), com cooldown, sem olhar horizonte ainda."""
    ema34 = ema(df["close"], EMA_SPAN)
    slope = ema34.diff(SLOPE_LOOKBACK_MIN)
    uptrend = slope > 0
    downtrend = slope < 0
    band = threshold_ticks * WDO_TICK

    touch_long = uptrend & (df["low"] <= ema34 + band) & (df["close"] >= ema34)
    touch_short = downtrend & (df["high"] >= ema34 - band) & (df["close"] <= ema34)

    direcao = pd.Series(0, index=df.index, dtype=int)
    direcao[touch_long] = 1
    direcao[touch_short] = -1
    positions = np.flatnonzero(direcao.to_numpy() != 0)

    kept = []
    last_pos = -10**9
    for pos in positions:
        if pos - last_pos < COOLDOWN_MIN:
            continue
        kept.append(pos)
        last_pos = pos

    return pd.DataFrame(
        {
            "pos": kept,
            "ts": df.index[kept],
            "direcao": direcao.iloc[kept].to_numpy(),
        }
    )


def _forward_aligned(df: pd.DataFrame, events: pd.DataFrame, horizon_min: int) -> np.ndarray:
    """`direcao * (close[t+H] - open[t+1])`, em ticks, so' quando t+H fica no
    MESMO pregao (data UTC) de t -- sem contaminar com o gap overnight."""
    n = len(df)
    open_px = df["open"].to_numpy()
    close_px = df["close"].to_numpy()
    session_date = df.index.date

    out = []
    for pos, direcao in zip(events["pos"].to_numpy(), events["direcao"].to_numpy()):
        entry_pos = pos + 1
        exit_pos = pos + horizon_min
        if exit_pos >= n:
            continue
        if session_date[pos] != session_date[exit_pos]:
            continue
        entry_px = open_px[entry_pos]
        exit_px = close_px[exit_pos]
        out.append(direcao * (exit_px - entry_px) / WDO_TICK)
    return np.array(out, dtype=float)


def main() -> None:
    print("=== Sonda 'wave' (34 EMA, Raghee Horner) no WDO@ -- ESTAGIO 1 (sem motor) ===")
    df = _load_m1()
    print(f"{len(df):,} barras M1, {df.index.min()} .. {df.index.max()}, "
          f"{len(pd.Series(df.index.date).unique())} pregoes")

    rng = np.random.default_rng(SEED)
    results = []

    for threshold in THRESHOLDS_TICKS:
        events = _events(df, threshold)
        n_long = int((events["direcao"] == 1).sum())
        n_short = int((events["direcao"] == -1).sum())
        print(f"\n-- limiar={threshold}t: {len(events)} toques ({n_long} alta / {n_short} baixa) --")
        for h in HORIZONS_MIN:
            y = _forward_aligned(df, events, h)
            n = len(y)
            if n < 15:
                print(f"  h={h:>3d}m  n={n:4d}  -- amostra pequena demais, pulado")
                continue
            obs, p2s = _permutation_mean_ne_zero(y, rng, N_PERM)
            results.append({
                "limiar_ticks": threshold, "horizonte_min": h, "n": n,
                "alinhado_medio_ticks": obs, "p2s_perm": p2s,
            })
            print(f"  h={h:>3d}m  n={n:4d}  alinhado_medio={obs:+.4f}t  p2s={p2s:.4f}")

    df_res = pd.DataFrame(results)
    n_tests = len(df_res)
    bonf = 0.05 / n_tests if n_tests else float("nan")
    print(f"\n=== RESUMO -- {n_tests} testes, Bonferroni alpha={bonf:.5f} ===")
    df_res = df_res.sort_values("p2s_perm")
    print(df_res.to_string(index=False))

    survivors = df_res[df_res["p2s_perm"] < bonf]
    print(f"\nSobrevivem Bonferroni: {len(survivors)}")
    if len(survivors):
        print(survivors.to_string(index=False))

    out_csv = Path(__file__).resolve().with_suffix(".csv")
    df_res.to_csv(out_csv, index=False)
    print(f"\nTabela salva em {out_csv}")


if __name__ == "__main__":
    main()
