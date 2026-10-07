"""Sonda (estagio 1, sem motor) -- 60 VARIACOES do conceito "wave" (34 EMA,
Raghee Horner) no WDO@, apos o teste pequeno inicial
(`raghee_horner_wave_probe_2026_09_27.py`, 0/6 Bonferroni, sinal negativo)
ter refutado a variante mais literal (toque na EMA34, espera continuacao).

Pedido do dono: usar o CONCEITO (a EMA como "onda" -- filtro de tendencia e
zona de decisao) e testar variacoes dele, nao repetir a mesma celula. As 60
celulas abaixo foram DECIDIDAS ANTES de rodar (pre-registro -- ver
`metodo_nulo_signflip_custo` / convencao de nao escolher parametro que
encaixa depois de ver o resultado) e cobrem 6 familias, cada uma usando a
wave de um jeito estruturalmente diferente:

  A. Pullback-continuacao (a celula original, variando span/limiar/horizonte)
     -- toca a wave em tendencia, aposta que ela segura e o preco continua.
  B. Lado da wave, SEM toque (span x horizonte, amostrado a cada 30min) --
     so' estar do lado certo da EMA (tendencia "confirmada") ja' prediz
     retorno futuro, sem esperar pullback?
  C. Esticamento / rubber band (span x distancia x horizonte) -- quando o
     preco fica MUITO longe da wave, ela funciona como imã (fade, reversao a
     media) em vez de continuacao?
  D. Onda dupla (par rapida/lenta) -- toque na wave RAPIDA so' conta se a
     wave LENTA confirmar o mesmo lado (filtro macro de tendencia)?
  E. Toque + volume (squat/rejeicao) -- toque com volume ABAIXO da mediana
     (pullback fraco) vs ACIMA da mediana (rejeicao forte) tem forca
     diferente?
  F. Sensibilidade do lookback de inclinacao (10 vs 20 min) na celula
     canonica (span=34, limiar=4t).

Todas as familias reaproveitam o MESMO desenho de medicao do teste pequeno:
M1 continuo do WDO@ (`data/raw_intraday/WDO_A_M1_do_tick.parquet`), EMA
calculada sem reset por pregao, evento conhecido no fechamento da barra t
(sem look-ahead), retorno alinhado `direcao * (close[t+H] - open[t+1])` em
TICKS, so' quando t+H fica no MESMO pregao (UTC date) de t, permutacao
sign-flip (H0: direcao nao carrega informacao, `_permutation_mean_ne_zero`,
identica a `wdo_gap_proprio_padrao_2026_09_27.py` e ao teste pequeno
anterior), cooldown entre eventos para nao inflar a amostra com toques
redundantes da mesma oscilacao.

Familia B usa "direcao" = lado da wave (sem toque), entao o cooldown vira o
STRIDE_MIN (amostragem a cada N minutos) em vez de gatilho de evento --
senao praticamente toda barra confirmada vira 1 evento e a serie fica
dominada por autocorrelacao.

60 celulas, Bonferroni sobre as 60 (alpha=0.05/60=0.000833).
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

SLOPE_LOOKBACK_MIN = 15
COOLDOWN_MIN = 30
STRIDE_MIN = 30
VOLUME_WINDOW_MIN = 60
HORIZONS_MIN = [15, 30, 60]
N_PERM = 10_000
SEED = 20260927


def _load_m1() -> pd.DataFrame:
    path = REPO / "data" / "raw_intraday" / "WDO_A_M1_do_tick.parquet"
    df = pd.read_parquet(path, columns=["open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    return df


def _permutation_mean_ne_zero(y: np.ndarray, rng: np.random.Generator, n_perm: int) -> tuple[float, float]:
    """Sign-flip: sob H0 (media zero), o sinal de cada observacao e' livre.
    Identica ao teste ja' usado em wdo_gap_proprio_padrao_2026_09_27.py e no
    teste pequeno raghee_horner_wave_probe_2026_09_27.py."""
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


def _forward_aligned(df: pd.DataFrame, events: pd.DataFrame, horizon_min: int) -> np.ndarray:
    """`direcao * (close[t+H] - open[t+1])`, em ticks, so' quando t+H fica no
    MESMO pregao (data UTC) de t."""
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


def _touch_mask_direcao(close, low, high, ema_arr, slope_arr, band):
    uptrend = slope_arr > 0
    downtrend = slope_arr < 0
    touch_long = uptrend & (low <= ema_arr + band) & (close >= ema_arr)
    touch_short = downtrend & (high >= ema_arr - band) & (close <= ema_arr)
    direcao = np.where(touch_long, 1, np.where(touch_short, -1, 0))
    return (touch_long | touch_short), direcao


def build_cells(df: pd.DataFrame) -> list[dict]:
    """Pre-registro das 60 celulas: cada uma vira um dict com `familia`,
    `params` (para o relatorio) e os arrays de `mask`/`direcao` prontos,
    consultados so' na hora de rodar o horizonte (o mesmo evento serve para
    varios horizontes)."""
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    volume = df["volume"].to_numpy()
    vol_ma = df["volume"].rolling(VOLUME_WINDOW_MIN, min_periods=VOLUME_WINDOW_MIN).median().to_numpy()

    ema_cache: dict[int, np.ndarray] = {}

    def get_ema(span: int) -> np.ndarray:
        if span not in ema_cache:
            ema_cache[span] = ema(df["close"], span).to_numpy()
        return ema_cache[span]

    cells: list[dict] = []

    # --- Familia A: pullback-continuacao (span x limiar x horizonte) ------
    for span in [21, 34, 55]:
        ema_arr = get_ema(span)
        slope = pd.Series(ema_arr).diff(SLOPE_LOOKBACK_MIN).to_numpy()
        for threshold in [2, 4]:
            band = threshold * WDO_TICK
            mask, direcao = _touch_mask_direcao(close, low, high, ema_arr, slope, band)
            events = _cooldown_events(mask, direcao, COOLDOWN_MIN)
            for h in HORIZONS_MIN:
                cells.append({
                    "familia": "A_pullback_continuacao",
                    "params": f"span={span} limiar={threshold}t",
                    "horizonte": h, "events": events,
                })

    # --- Familia B: lado da wave, SEM toque (span x horizonte) ------------
    for span in [21, 34, 55]:
        ema_arr = get_ema(span)
        slope = pd.Series(ema_arr).diff(SLOPE_LOOKBACK_MIN).to_numpy()
        side = np.sign(close - ema_arr)
        slope_sign = np.sign(slope)
        confirmed = (slope_sign != 0) & (side == slope_sign)
        events = _cooldown_events(confirmed, slope_sign.astype(int), STRIDE_MIN)
        for h in HORIZONS_MIN + [120]:
            cells.append({
                "familia": "B_lado_sem_toque",
                "params": f"span={span}",
                "horizonte": h, "events": events,
            })

    # --- Familia C: esticamento / rubber band (span x distancia x horiz) --
    for span in [21, 34]:
        ema_arr = get_ema(span)
        dist_ticks = (close - ema_arr) / WDO_TICK
        for dist_threshold in [8, 15]:
            mask = np.abs(dist_ticks) >= dist_threshold
            direcao = (-np.sign(dist_ticks)).astype(int)
            events = _cooldown_events(mask, direcao, COOLDOWN_MIN)
            for h in HORIZONS_MIN:
                cells.append({
                    "familia": "C_esticamento_fade",
                    "params": f"span={span} dist>={dist_threshold}t",
                    "horizonte": h, "events": events,
                })

    # --- Familia D: onda dupla, rapida confirmada pela lenta --------------
    for fast, slow in [(21, 34), (34, 55)]:
        ema_fast = get_ema(fast)
        ema_slow = get_ema(slow)
        slope_fast = pd.Series(ema_fast).diff(SLOPE_LOOKBACK_MIN).to_numpy()
        band = 4 * WDO_TICK
        mask_touch, direcao_touch = _touch_mask_direcao(close, low, high, ema_fast, slope_fast, band)
        macro_agree = np.sign(close - ema_slow) == direcao_touch
        mask = mask_touch & macro_agree
        events = _cooldown_events(mask, direcao_touch, COOLDOWN_MIN)
        for h in HORIZONS_MIN:
            cells.append({
                "familia": "D_onda_dupla",
                "params": f"rapida={fast} lenta={slow}",
                "horizonte": h, "events": events,
            })

    # --- Familia E: toque + volume (squat vs rejeicao forte) --------------
    ema34 = get_ema(34)
    slope34 = pd.Series(ema34).diff(SLOPE_LOOKBACK_MIN).to_numpy()
    mask_e, direcao_e = _touch_mask_direcao(close, low, high, ema34, slope34, 4 * WDO_TICK)
    events_e = _cooldown_events(mask_e, direcao_e, COOLDOWN_MIN)
    vol_at_event = vol_ma[events_e["pos"].to_numpy()] if len(events_e) else np.array([])
    vol_evt = volume[events_e["pos"].to_numpy()] if len(events_e) else np.array([])
    valid = ~np.isnan(vol_at_event)
    for label, cond in [("vol_baixo(squat)", vol_evt <= vol_at_event), ("vol_alto(rejeicao)", vol_evt > vol_at_event)]:
        sub = events_e[valid & cond]
        for h in HORIZONS_MIN:
            cells.append({
                "familia": "E_toque_volume",
                "params": label,
                "horizonte": h, "events": sub,
            })

    # --- Familia F: sensibilidade do lookback de inclinacao ---------------
    for lookback in [10, 20]:
        slope = pd.Series(ema34).diff(lookback).to_numpy()
        mask_f, direcao_f = _touch_mask_direcao(close, low, high, ema34, slope, 4 * WDO_TICK)
        events = _cooldown_events(mask_f, direcao_f, COOLDOWN_MIN)
        for h in HORIZONS_MIN:
            cells.append({
                "familia": "F_lookback_inclinacao",
                "params": f"lookback={lookback}min",
                "horizonte": h, "events": events,
            })

    return cells


def main() -> None:
    print("=== 60 variacoes do conceito 'wave' (Raghee Horner) no WDO@ -- ESTAGIO 1 ===")
    df = _load_m1()
    print(f"{len(df):,} barras M1, {df.index.min()} .. {df.index.max()}, "
          f"{len(pd.Series(df.index.date).unique())} pregoes")

    cells = build_cells(df)
    print(f"{len(cells)} celulas pre-registradas\n")

    rng = np.random.default_rng(SEED)
    results = []
    for cell in cells:
        events = cell["events"]
        y = _forward_aligned(df, events, cell["horizonte"])
        n = len(y)
        if n < 15:
            print(f"  [{cell['familia']:22s}] {cell['params']:22s} h={cell['horizonte']:>3d}m  n={n:4d}  -- pulado")
            continue
        obs, p2s = _permutation_mean_ne_zero(y, rng, N_PERM)
        results.append({
            "familia": cell["familia"], "params": cell["params"], "horizonte_min": cell["horizonte"],
            "n": n, "alinhado_medio_ticks": obs, "p2s_perm": p2s,
        })
        print(f"  [{cell['familia']:22s}] {cell['params']:22s} h={cell['horizonte']:>3d}m  "
              f"n={n:4d}  alinhado_medio={obs:+.4f}t  p2s={p2s:.4f}")

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
          f"{int((df_res['alinhado_medio_ticks'] > 0).sum())}/{n_tests}")

    out_csv = Path(__file__).resolve().with_suffix(".csv")
    df_res.to_csv(out_csv, index=False)
    print(f"\nTabela salva em {out_csv}")


if __name__ == "__main__":
    main()
