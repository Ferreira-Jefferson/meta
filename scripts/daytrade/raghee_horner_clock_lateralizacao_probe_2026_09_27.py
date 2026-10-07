# -*- coding: utf-8 -*-
"""Sonda (estagio 1, sem motor) da "wave" de Raghee Horner ADAPTADA para
LATERALIZACAO -- WIN@ e WDO@ em paralelo.

## Por que esta sonda e diferente da ja refutada

O pullback-continuacao da wave classica (1 EMA34 de close, filtro de
tendencia) ja foi testado e REFUTADO em `raghee_horner_wave_probe_2026_09_27.py`
(0/6 sobrevivencias Bonferroni, alinhamento levemente NEGATIVO em 5 das 6
celulas). O pedido do dono agora e outra leitura do mesmo material -- a
variante do "relogio" (Big Dipper) com TRES EMAs de 34 periodos, uma de
cada preco (High, Low, Close): a EMA da MAXIMA fica, por construcao, quase
sempre ACIMA do preco; a da MINIMA quase sempre ABAIXO; a do FECHAMENTO
fica no meio e indica posicao/vies. As duas externas formam uma banda
visual (limite de cima e de baixo) igual ao pedido: "uma media que fique
acima do preco e outra que fique abaixo". O foco pedido e a LATERALIZACAO
-- o regime onde a familia do retangulo (`win_retangulo.py` / `wdo_retangulo.py`)
ja opera com outro detector (quantis q90/q10 + contagem de toques) -- e nao
a tendencia, que e onde a wave classica ja foi refutada.

## A hipotese

Dentro de um regime lateral (banda ESTREITA em relacao a sua propria
historia recente), um toque na banda de BAIXO (EMA34 da minima) e seguido
de reversao para CIMA, e um toque na banda de CIMA (EMA34 da maxima) e
seguido de reversao para BAIXO -- o OPOSTO do pullback-continuacao ja
refutado (ali era continuacao de tendencia; aqui e reversao dentro do
range).

### Regime lateral (decidido ANTES de olhar o resultado)

`largura[t] = ema34_high[t] - ema34_low[t]`. Lateral quando a largura atual
esta no percentil <= `WIDTH_PCTL` da sua propria distribuicao nos ultimos
`WIDTH_LOOKBACK_MIN` minutos (`largura.rolling(W).quantile(P)` -- so passado
+ barra atual, sem look-ahead). Fora disso (banda alargando = tendencia) o
periodo e descartado da sonda -- e o regime que a wave classica ja cobriu.

### Evento de toque

  * toque de BAIXO: `low[t] <= ema34_low[t] + threshold` E `close[t] >=
    ema34_low[t]` (encostou na banda inferior e fechou de volta pra
    dentro) -> direcao +1 (aposta em reversao pra cima);
  * toque de CIMA: espelhado -> direcao -1.

Cooldown de `COOLDOWN_MIN` barras entre toques contados (mesmo espirito da
sonda anterior: evita inflar a amostra com toques redundantes da mesma
oscilacao).

Sem look-ahead: o toque e conhecido no fechamento da barra t (as 3 EMAs sao
funcao de high/low/close[<=t]); a entrada hipotetica e `open[t+1]`; o
retorno mede ate `close[t+H]`, H em minutos, SO quando t+H cai no MESMO
pregao (data UTC) de t -- mesma regra da sonda anterior, evita contaminar
com o gap overnight (ja investigado em `wdo_gap_proprio_padrao_2026_09_27.py`).

`alinhado[t] = direcao[t] * (close[t+H] - open[t+1])`, em TICKS. Sob H0 ("a
direcao atribuida pelo toque na banda nao carrega informacao"), o sinal de
`alinhado` e livre (sign-flip exchangeable) -- mesmo teste de permutacao ja
usado nas sondas anteriores.

Familia PEQUENA, decidida ANTES do resultado: 2 simbolos (WIN@, WDO@) x 2
limiares de toque x 3 horizontes = 12 celulas, Bonferroni sobre as 12.

## Bases

WDO@ usa o M1 continuo reconstruido do tick
(`data/raw_intraday/WDO_A_M1_do_tick.parquet`, mesma base da sonda
anterior, 76.039 barras, 134 pregoes). WIN@ nao tem esse historico
reconstruido -- usa o M1 acumulado ao vivo
(`market_data_intraday.storage.load_m1("WIN@")`, mesma fonte dos backtests
de `win_retangulo`), amostra menor e mais recente (2025-12-01 em diante,
~110 mil barras, 196 pregoes).
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

EMA_SPAN = 34
WIDTH_LOOKBACK_MIN = 240
WIDTH_PCTL = 0.40
COOLDOWN_MIN = 30
THRESHOLDS_TICKS = [2, 4]
HORIZONS_MIN = [15, 30, 60]
N_PERM = 20_000
SEED = 20260927

SYMBOLS = ["WIN@", "WDO@"]


def _load_wdo() -> pd.DataFrame:
    path = REPO / "data" / "raw_intraday" / "WDO_A_M1_do_tick.parquet"
    df = pd.read_parquet(path, columns=["open", "high", "low", "close"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def _load_win() -> pd.DataFrame:
    from market_data_intraday.storage import load_m1

    df = load_m1("WIN@")[["open", "high", "low", "close"]]
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


_LOADERS = {"WIN@": _load_win, "WDO@": _load_wdo}


def _permutation_mean_ne_zero(y: np.ndarray, rng: np.random.Generator, n_perm: int) -> tuple[float, float]:
    """Sign-flip: sob H0 (media zero), o sinal de cada observacao e livre.
    Identico ao teste ja usado nas sondas anteriores."""
    obs = float(np.mean(y))
    abs_y = np.abs(y)
    perm = np.empty(n_perm)
    for i in range(n_perm):
        flips = rng.choice([-1.0, 1.0], size=len(y))
        perm[i] = np.mean(flips * abs_y)
    p2s = float(np.mean(np.abs(perm) >= abs(obs)))
    return obs, p2s


def _events(df: pd.DataFrame, threshold_ticks: int, tick_size: float) -> pd.DataFrame:
    """Toques na banda (baixo/cima) dentro de regime lateral, com cooldown."""
    ema_high = ema(df["high"], EMA_SPAN)
    ema_low = ema(df["low"], EMA_SPAN)
    largura = ema_high - ema_low
    largura_pctl = largura.rolling(WIDTH_LOOKBACK_MIN, min_periods=WIDTH_LOOKBACK_MIN).quantile(WIDTH_PCTL)
    lateral = largura <= largura_pctl

    band = threshold_ticks * tick_size
    toque_baixo = lateral & (df["low"] <= ema_low + band) & (df["close"] >= ema_low)
    toque_cima = lateral & (df["high"] >= ema_high - band) & (df["close"] <= ema_high)

    direcao = pd.Series(0, index=df.index, dtype=int)
    direcao[toque_baixo] = 1
    direcao[toque_cima] = -1
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


def _forward_aligned(df: pd.DataFrame, events: pd.DataFrame, horizon_min: int, tick_size: float) -> np.ndarray:
    """`direcao * (close[t+H] - open[t+1])`, em ticks, so quando t+H fica no
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
        out.append(direcao * (exit_px - entry_px) / tick_size)
    return np.array(out, dtype=float)


def main() -> None:
    print("=== Sonda 'relogio' (3 EMA34 H/L/C, Raghee Horner) em LATERALIZACAO -- WIN@ e WDO@ ===")
    rng = np.random.default_rng(SEED)
    results = []

    for symbol in SYMBOLS:
        tick_size = FUTUROS[symbol].price_tick_size
        df = _LOADERS[symbol]()
        print(f"\n### {symbol}: {len(df):,} barras M1, {df.index.min()} .. {df.index.max()}, "
              f"{len(pd.Series(df.index.date).unique())} pregoes, tick={tick_size}")

        for threshold in THRESHOLDS_TICKS:
            events = _events(df, threshold, tick_size)
            n_baixo = int((events["direcao"] == 1).sum())
            n_cima = int((events["direcao"] == -1).sum())
            print(f"\n-- {symbol} limiar={threshold}t: {len(events)} toques ({n_baixo} baixo / {n_cima} cima) --")
            for h in HORIZONS_MIN:
                y = _forward_aligned(df, events, h, tick_size)
                n = len(y)
                if n < 15:
                    print(f"  h={h:>3d}m  n={n:4d}  -- amostra pequena demais, pulado")
                    continue
                obs, p2s = _permutation_mean_ne_zero(y, rng, N_PERM)
                results.append({
                    "simbolo": symbol, "limiar_ticks": threshold, "horizonte_min": h, "n": n,
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
