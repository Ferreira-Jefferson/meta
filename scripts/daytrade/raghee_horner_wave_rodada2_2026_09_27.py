"""Sonda (estagio 1, sem motor) -- RODADA 2 do conceito "wave" (Raghee
Horner) apos a rodada 1 (`raghee_horner_wave_probe_2026_09_27.py`, 0/6, e
`raghee_horner_wave_variacoes_2026_09_27.py`, 0/60) ter refutado a variante
literal e 60 variacoes dela, todas no WDO@ M1 (76 mil barras, 8 meses).

## Por que uma rodada 2, e por que ela e' DIFERENTE, nao mais do mesmo

Pedido do dono: nao aceitar "nao funciona" sem testar a estrategia no
TIMEFRAME e no MERCADO onde ela faz sentido, e sem tentar construcoes que ela
de fato ensina (nao so' o toque literal). Duas lacunas reais da rodada 1:

  1. **Timeframe errado.** Raghee Horner e' trader de SWING (Forex, posicoes
     de dias), nao de scalp de M1. A rodada 1 testou touch-e-solta em M1 --
     o timeframe mais dificil para qualquer sinal de tendencia sobreviver ao
     ruido/custo. Aqui a familia G roda a wave no DIARIO de verdade, usando
     M15 continuo (`WDO_A_M15.parquet`/`WIN_A_M15.parquet`, ~5 ANOS de
     historico, 2021-08..2026-08, contra os 8 meses do M1) resample para
     barra diaria -- e' o timeframe e o tamanho de amostra que da' a ela a
     melhor chance real de aparecer, se existir.
  2. **So' o toque literal.** O metodo dela combina MAIS elementos que nunca
     foram testados: vies de tendencia no timeframe MAIOR + gatilho no
     MENOR (ela ensina isso explicitamente -- familia H), squat candle
     (familia I), rejection candle com proporcao de pabvio estrita (familia
     J), banda adaptativa a volatilidade tipo Keltner em vez de limiar fixo
     (familia L), e periodos de media alem do trio 21/34/55 (familia K).

## As 6 familias, 2 instrumentos (WDO@ e WIN@), 72 celulas pre-registradas

  G. Wave DIARIA -- pullback-continuacao no timeframe de verdade dela.
     span{21,34}d x limiar{0,25;0,5}xATR14(diario) x horizonte{3,5,10}
     PREGOES. Sem exigencia de "mesmo pregao" (e' swing, atravessar dia e'
     o ponto).
  H. Multi-timeframe -- vies de tendencia no DIARIO (EMA34, confirmado),
     gatilho de pullback no M15 (mesma logica de toque, banda 0,25xATR15).
     O vies do dia D so' pode usar o FECHAMENTO do dia D-1 (sem
     look-ahead). horizonte{8,16,32} barras M15 (~2h/4h/8h), mesmo pregao.
  I. Squat candle -- candle de range comprimido (<=50% da mediana movel de
     20 barras) E volume abaixo da mediana movel de 20 barras, no M15,
     apostando CONTINUACAO da tendencia dos 20 barras anteriores.
     horizonte{4,8,16} barras M15, mesmo pregao.
  J. Rejection candle -- toque na wave (span=34, M15, banda 0,25xATR15) com
     pavio (na direcao da rejeicao) >= X% do range da barra. X in
     {40%,60%}. horizonte{4,8,16} barras M15, mesmo pregao.
  K. Periodos alternativos de EMA -- span{13,20,50,100} (fora do trio
     Fibonacci ja' testado), M15, banda 0,25xATR15. horizonte{8,16} barras.
  L. Banda tipo Keltner (adaptativa a volatilidade, em vez de limiar fixo em
     ticks como na rodada 1) -- span=34, banda = mult x ATR15, mult in
     {1,0; 1,5}. horizonte{8,16} barras.

Mesmo desenho de medicao das rodadas anteriores: evento conhecido no
fechamento da barra t (EMA/ATR sao funcao de close[<=t], sem look-ahead),
retorno alinhado `direcao * (close[t+H] - open[t+1]) * valor_do_ponto`, em
REAIS por contrato (nao mais "ticks" -- a nota em `core/instruments.py` sobre
a serie continua nao reportar o tick REAL do contrato com vencimento nao se
aplica a preco/pontos, so' ao passo de grade; R$ e' comparavel entre WDO@ e
WIN@ sem essa ressalva). Permutacao sign-flip (`_permutation_mean_ne_zero`,
identica as rodadas anteriores). Cooldown entre eventos para nao inflar a
amostra com toques redundantes da mesma oscilacao.

72 celulas, Bonferroni sobre as 72 (alpha=0,05/72=0,000694), decidido ANTES
de rodar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from core.indicators import atr, ema  # noqa: E402
from core.instruments import FUTUROS  # noqa: E402

DAILY_SLOPE_LOOKBACK = 5
M15_SLOPE_LOOKBACK = 20
COOLDOWN_DAILY = 3
COOLDOWN_M15 = 8
N_PERM = 10_000
SEED = 20260927

INSTRUMENTS = {
    "WDO@": "WDO_A_M15.parquet",
    "WIN@": "WIN_A_M15.parquet",
}


def _load_m15(fname: str) -> pd.DataFrame:
    df = pd.read_parquet(REPO / "data" / "raw_intraday" / fname,
                          columns=["open", "high", "low", "close", "tick_volume"])
    df = df.rename(columns={"tick_volume": "volume"})
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def _to_daily(m15: pd.DataFrame) -> pd.DataFrame:
    g = m15.resample("1D")
    daily = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(),
        "low": g["low"].min(), "close": g["close"].last(),
        "volume": g["volume"].sum(),
    })
    return daily.dropna(subset=["close"])


def _permutation_mean_ne_zero(y: np.ndarray, rng: np.random.Generator, n_perm: int) -> tuple[float, float]:
    obs = float(np.mean(y))
    abs_y = np.abs(y)
    perm = np.empty(n_perm)
    for i in range(n_perm):
        flips = rng.choice([-1.0, 1.0], size=len(y))
        perm[i] = np.mean(flips * abs_y)
    p2s = float(np.mean(np.abs(perm) >= abs(obs)))
    return obs, p2s


def _cooldown_events(mask: np.ndarray, direcao: np.ndarray, cooldown: int) -> pd.DataFrame:
    positions = np.flatnonzero(mask)
    kept = []
    last_pos = -10 ** 9
    for pos in positions:
        if pos - last_pos < cooldown:
            continue
        kept.append(pos)
        last_pos = pos
    return pd.DataFrame({"pos": kept, "direcao": direcao[kept]})


def _forward_aligned(df: pd.DataFrame, events: pd.DataFrame, horizon_bars: int,
                      point_value: float, same_session: bool) -> np.ndarray:
    n = len(df)
    entry_px = df["open"].to_numpy()
    exit_px = df["close"].to_numpy()
    session_date = df.index.date if same_session else None

    out = []
    for pos, direcao in zip(events["pos"].to_numpy(), events["direcao"].to_numpy()):
        entry_pos = pos + 1
        exit_pos = pos + horizon_bars
        if exit_pos >= n:
            continue
        if same_session and session_date[pos] != session_date[exit_pos]:
            continue
        out.append(direcao * (exit_px[exit_pos] - entry_px[entry_pos]) * point_value)
    return np.array(out, dtype=float)


def _touch_mask_direcao(close, low, high, ema_arr, slope_arr, band):
    uptrend = slope_arr > 0
    downtrend = slope_arr < 0
    touch_long = uptrend & (low <= ema_arr + band) & (close >= ema_arr)
    touch_short = downtrend & (high >= ema_arr - band) & (close <= ema_arr)
    direcao = np.where(touch_long, 1, np.where(touch_short, -1, 0))
    return (touch_long | touch_short), direcao


def build_cells(symbol: str, m15: pd.DataFrame, daily: pd.DataFrame, point_value: float) -> list[dict]:
    cells: list[dict] = []

    close_d, high_d, low_d = (daily[c].to_numpy() for c in ("close", "high", "low"))
    atr_d = atr(daily["high"], daily["low"], daily["close"], 14).to_numpy()

    close15, high15, low15, open15 = (m15[c].to_numpy() for c in ("close", "high", "low", "open"))
    vol15 = m15["volume"].to_numpy()
    atr15 = atr(m15["high"], m15["low"], m15["close"], 14).to_numpy()
    ema15_34 = ema(m15["close"], 34).to_numpy()
    slope15_34 = pd.Series(ema15_34).diff(M15_SLOPE_LOOKBACK).to_numpy()
    band15_ref = 0.25 * atr15

    def add(familia, params, events, horizons, df, same_session):
        for h in horizons:
            cells.append({
                "instrumento": symbol, "familia": familia, "params": params,
                "horizonte": h, "events": events, "df": df,
                "same_session": same_session,
            })

    # --- G: wave DIARIA (pullback-continuacao no timeframe real dela) -----
    for span in [21, 34]:
        ema_d = ema(daily["close"], span).to_numpy()
        slope_d = pd.Series(ema_d).diff(DAILY_SLOPE_LOOKBACK).to_numpy()
        for thr_atr in [0.25, 0.5]:
            band = thr_atr * atr_d
            mask, direcao = _touch_mask_direcao(close_d, low_d, high_d, ema_d, slope_d, band)
            events = _cooldown_events(mask, direcao, COOLDOWN_DAILY)
            add("G_wave_diaria", f"span={span}d thr={thr_atr}xATR", events,
                [3, 5, 10], daily, same_session=False)

    # --- H: multi-timeframe (vies diario + gatilho M15) --------------------
    ema_d34 = ema(daily["close"], 34)
    slope_d34 = ema_d34.diff(DAILY_SLOPE_LOOKBACK)
    side_d = np.sign(daily["close"] - ema_d34)
    slope_sign_d = np.sign(slope_d34)
    confirmed_d = (slope_sign_d != 0) & (side_d == slope_sign_d)
    daily_trend = pd.Series(np.where(confirmed_d, slope_sign_d, 0.0), index=daily.index)
    daily_trend_prev = daily_trend.shift(1)  # vies conhecido no FECHAMENTO do dia anterior
    m15_day = m15.index.normalize()
    bias = daily_trend_prev.reindex(m15_day).to_numpy()

    touch_long15 = (low15 <= ema15_34 + band15_ref) & (close15 >= ema15_34)
    touch_short15 = (high15 >= ema15_34 - band15_ref) & (close15 <= ema15_34)
    mask_long = touch_long15 & (bias == 1.0)
    mask_short = touch_short15 & (bias == -1.0)
    mask_h = mask_long | mask_short
    direcao_h = np.where(mask_long, 1, np.where(mask_short, -1, 0))
    events_h = _cooldown_events(mask_h, direcao_h, COOLDOWN_M15)
    add("H_mtf_diario_gatilho_m15", "bias=diario(D-1) gatilho=m15", events_h,
        [8, 16, 32], m15, same_session=True)

    # --- I: squat candle (range comprimido + volume baixo) -----------------
    range15 = high15 - low15
    range_ma = pd.Series(range15).rolling(20, min_periods=20).median().to_numpy()
    vol_ma = pd.Series(vol15).rolling(20, min_periods=20).median().to_numpy()
    squat = (range15 <= 0.5 * range_ma) & (vol15 <= vol_ma)
    prior_close = pd.Series(close15).shift(20).to_numpy()
    prior_trend = np.sign(close15 - prior_close)
    mask_i = squat & (prior_trend != 0) & ~np.isnan(prior_trend)
    direcao_i = np.where(mask_i, prior_trend, 0).astype(int)
    events_i = _cooldown_events(mask_i, direcao_i, COOLDOWN_M15)
    add("I_squat_candle_continuacao", "range<=50%med20 vol<=med20", events_i,
        [4, 8, 16], m15, same_session=True)

    # --- J: rejection candle (pavio estrito) --------------------------------
    range15_safe = np.where(range15 <= 0, np.nan, range15)
    lower_wick = np.minimum(open15, close15) - low15
    upper_wick = high15 - np.maximum(open15, close15)
    uptrend15 = slope15_34 > 0
    downtrend15 = slope15_34 < 0
    near_long = low15 <= ema15_34 + band15_ref
    near_short = high15 >= ema15_34 - band15_ref
    for wick_ratio in [0.4, 0.6]:
        rej_long = (uptrend15 & near_long & (close15 >= ema15_34)
                    & (lower_wick / range15_safe >= wick_ratio))
        rej_short = (downtrend15 & near_short & (close15 <= ema15_34)
                     & (upper_wick / range15_safe >= wick_ratio))
        rej_long = np.nan_to_num(rej_long.astype(float)).astype(bool)
        rej_short = np.nan_to_num(rej_short.astype(float)).astype(bool)
        mask_j = rej_long | rej_short
        direcao_j = np.where(rej_long, 1, np.where(rej_short, -1, 0))
        events_j = _cooldown_events(mask_j, direcao_j, COOLDOWN_M15)
        add("J_rejection_candle", f"pavio>={int(wick_ratio*100)}%", events_j,
            [4, 8, 16], m15, same_session=True)

    # --- K: periodos alternativos de EMA ------------------------------------
    for span in [13, 20, 50, 100]:
        ema15 = ema(m15["close"], span).to_numpy()
        slope15 = pd.Series(ema15).diff(M15_SLOPE_LOOKBACK).to_numpy()
        mask_k, direcao_k = _touch_mask_direcao(close15, low15, high15, ema15, slope15, band15_ref)
        events_k = _cooldown_events(mask_k, direcao_k, COOLDOWN_M15)
        add("K_periodo_alternativo", f"span={span}", events_k, [8, 16], m15, same_session=True)

    # --- L: banda tipo Keltner (adaptativa, span=34) ------------------------
    for atr_mult in [1.0, 1.5]:
        band_l = atr_mult * atr15
        mask_l, direcao_l = _touch_mask_direcao(close15, low15, high15, ema15_34, slope15_34, band_l)
        events_l = _cooldown_events(mask_l, direcao_l, COOLDOWN_M15)
        add("L_banda_keltner", f"mult={atr_mult}xATR15", events_l, [8, 16], m15, same_session=True)

    return cells


def main() -> None:
    print("=== RODADA 2 -- 'wave' (Raghee Horner), WDO@ e WIN@, diario+M15+MTF -- ESTAGIO 1 ===")
    rng = np.random.default_rng(SEED)
    results = []

    for symbol, fname in INSTRUMENTS.items():
        point_value = FUTUROS[symbol].point_value_brl
        m15 = _load_m15(fname)
        daily = _to_daily(m15)
        print(f"\n--- {symbol}: {len(m15):,} barras M15 ({m15.index.min()} .. {m15.index.max()}), "
              f"{len(daily)} pregoes diarios, valor_ponto=R${point_value} ---")

        cells = build_cells(symbol, m15, daily, point_value)
        for cell in cells:
            y = _forward_aligned(cell["df"], cell["events"], cell["horizonte"], point_value, cell["same_session"])
            n = len(y)
            label = f"[{symbol} {cell['familia']:26s}] {cell['params']:28s} h={cell['horizonte']:>3d}"
            if n < 15:
                print(f"  {label}  n={n:4d}  -- pulado")
                continue
            obs, p2s = _permutation_mean_ne_zero(y, rng, N_PERM)
            results.append({
                "instrumento": symbol, "familia": cell["familia"], "params": cell["params"],
                "horizonte": cell["horizonte"], "n": n, "alinhado_medio_brl": obs, "p2s_perm": p2s,
            })
            print(f"  {label}  n={n:4d}  alinhado_medio=R${obs:+.2f}  p2s={p2s:.4f}")

    df_res = pd.DataFrame(results)
    n_tests = len(df_res)
    bonf = 0.05 / n_tests if n_tests else float("nan")
    print(f"\n=== RESUMO -- {n_tests} testes, Bonferroni alpha={bonf:.6f} ===")
    df_res = df_res.sort_values("p2s_perm")
    print(df_res.to_string(index=False))

    survivors = df_res[df_res["p2s_perm"] < bonf]
    print(f"\nSobrevivem Bonferroni: {len(survivors)}")
    if len(survivors):
        print(survivors.to_string(index=False))

    print(f"\nCelulas com sinal POSITIVO (alinhado_medio>0): "
          f"{int((df_res['alinhado_medio_brl'] > 0).sum())}/{n_tests}")
    for instr in INSTRUMENTS:
        sub = df_res[df_res["instrumento"] == instr]
        print(f"  {instr}: {int((sub['alinhado_medio_brl'] > 0).sum())}/{len(sub)} positivas, "
              f"melhor p2s={sub['p2s_perm'].min():.4f}")

    out_csv = Path(__file__).resolve().with_suffix(".csv")
    df_res.to_csv(out_csv, index=False)
    print(f"\nTabela salva em {out_csv}")


if __name__ == "__main__":
    main()
