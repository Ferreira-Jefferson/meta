"""Sonda (teste pequeno primeiro) da hipotese de lead-lag externo overnight.

Hipotese: o retorno overnight de um mercado-lider EXTERNO (S&P futuro ES=F,
indice do dolar DX-Y.NYB) que ja se moveu ANTES da abertura da B3 (defasagem
real de horas) prediz o sentido do movimento de abertura do WIN@/WDO@.

Este script e' o estagio 1 (correlacao/preditividade bruta, sem custo, sem
motor de execucao) -- convencao do projeto "o minimo que refuta primeiro"
(ver MEMORY.md: feedback_teste_pequeno_valida_hipotese). So' se houver sinal
aqui com significancia (permutacao, Bonferroni pela familia de testes) vale a
pena construir a IntradayStrategy completa e rodar no motor com fidelidade de
fila + desenho de execucao fechado.

Sem look-ahead: o "retorno overnight" so' usa precos externos ANTERIORES ao
instante real de abertura da B3 (com folga de 30min), e a resposta medida e'
o retorno da B3 ESTRITAMENTE DEPOIS da abertura.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

REPO = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\leadlag_cache"
)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

EXTERNAL_TICKERS = {"ES=F": "sp500_fut", "DX-Y.NYB": "dxy"}
HORIZONS_MIN = [5, 15, 30, 60]
N_PERM = 20_000
SEED = 20260911


def _fetch_external(ticker: str) -> pd.Series:
    cache_path = CACHE_DIR / f"{ticker.replace('=', '_').replace('.', '_')}.parquet"
    if cache_path.exists():
        s = pd.read_parquet(cache_path)["close"]
        s.index = pd.to_datetime(s.index, utc=True)
        return s
    df = yf.download(ticker, period="730d", interval="1h", progress=False)
    if df.empty:
        raise RuntimeError(f"yfinance devolveu vazio para {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    close = df["Close"].copy()
    close.index = pd.to_datetime(close.index, utc=True)
    close.name = "close"
    close.to_frame().to_parquet(cache_path)
    return close


def _load_b3_ticks(symbol_file: str, price_col: str) -> pd.DataFrame:
    path = REPO / "data" / "raw_ticks" / symbol_file
    df = pd.read_parquet(path, columns=[price_col])
    df = df.rename(columns={price_col: "last"})
    df = df[df["last"] > 0]
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    return df


def _session_table(ticks: pd.DataFrame) -> pd.DataFrame:
    """Para cada pregao: instante/preco de abertura, instante/preco de
    fechamento, e o preco em open+H minutos para cada horizonte."""
    ticks = ticks.copy()
    ticks["session_date"] = ticks.index.tz_convert("UTC").date  # BRT=UTC-3, mesmo dia de calendario
    rows = []
    for date, day_df in ticks.groupby("session_date"):
        if len(day_df) < 10:
            continue
        open_ts = day_df.index[0]
        open_px = float(day_df["last"].iloc[0])
        close_ts = day_df.index[-1]
        close_px = float(day_df["last"].iloc[-1])
        row = {
            "session_date": date,
            "open_ts": open_ts,
            "open_px": open_px,
            "close_ts": close_ts,
            "close_px": close_px,
            "eod_return": close_px / open_px - 1.0,
        }
        for h in HORIZONS_MIN:
            target_ts = open_ts + pd.Timedelta(minutes=h)
            sub = day_df[day_df.index <= target_ts]
            if len(sub) < 2:
                row[f"ret_{h}m"] = np.nan
                continue
            px_h = float(sub["last"].iloc[-1])
            row[f"ret_{h}m"] = px_h / open_px - 1.0
        rows.append(row)
    return pd.DataFrame(rows).set_index("session_date").sort_index()


def _overnight_return(external: pd.Series, open_ts: pd.Timestamp, prev_close_ts: pd.Timestamp) -> float:
    """Retorno do mercado externo entre o fechamento B3 do dia anterior e
    30min ANTES da abertura B3 de hoje -- so' informacao ja disponivel antes
    do sinal precisar ser tomado."""
    buffer_open = open_ts - pd.Timedelta(minutes=30)
    before_open = external[external.index <= buffer_open]
    before_prev_close = external[external.index <= prev_close_ts]
    if before_open.empty or before_prev_close.empty:
        return np.nan
    px_pre_open = float(before_open.iloc[-1])
    px_prev_close = float(before_prev_close.iloc[-1])
    if px_prev_close == 0:
        return np.nan
    return px_pre_open / px_prev_close - 1.0


def _permutation_pvalue(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, n_perm: int) -> tuple[float, float]:
    obs = np.corrcoef(x, y)[0, 1]
    perm_corrs = np.empty(n_perm)
    y_work = y.copy()
    for i in range(n_perm):
        rng.shuffle(y_work)
        perm_corrs[i] = np.corrcoef(x, y_work)[0, 1]
    # p bicaudal: fracao de |perm| >= |obs|
    p2s = float(np.mean(np.abs(perm_corrs) >= abs(obs)))
    return obs, p2s


def main() -> None:
    print("=== Sonda lead-lag externo overnight -- ESTAGIO 1 (correlacao bruta) ===")
    print(f"Horizontes testados (min): {HORIZONS_MIN}")

    externals = {}
    for ticker, label in EXTERNAL_TICKERS.items():
        s = _fetch_external(ticker)
        externals[label] = s
        print(f"externo {label} ({ticker}): {len(s)} barras 1h, {s.index.min()} .. {s.index.max()}")

    instruments = {
        "WIN@": ("WIN_A_.parquet", "last"),
        "WDO@": ("WDO_A_f1.parquet", "close"),
    }

    rng = np.random.default_rng(SEED)
    results = []

    for instr_label, (fname, price_col) in instruments.items():
        print(f"\n--- Carregando ticks de {instr_label} ({fname}) ---")
        ticks = _load_b3_ticks(fname, price_col)
        print(f"{len(ticks):,} ticks, {ticks.index.min()} .. {ticks.index.max()}")
        sess = _session_table(ticks)
        print(f"{len(sess)} pregoes com dado suficiente")

        prev_close_ts = sess["close_ts"].shift(1)

        for ext_label, ext_series in externals.items():
            overnight = []
            for date, row in sess.iterrows():
                pc_ts = prev_close_ts.loc[date]
                if pd.isna(pc_ts):
                    overnight.append(np.nan)
                    continue
                overnight.append(_overnight_return(ext_series, row["open_ts"], pc_ts))
            sess[f"overnight_{ext_label}"] = overnight

            for h in HORIZONS_MIN + ["eod"]:
                col_y = f"ret_{h}m" if h != "eod" else "eod_return"
                sub = sess[[f"overnight_{ext_label}", col_y]].dropna()
                n = len(sub)
                if n < 20:
                    continue
                x = sub[f"overnight_{ext_label}"].to_numpy()
                y = sub[col_y].to_numpy()
                obs_corr, p2s = _permutation_pvalue(x, y, rng, N_PERM)
                results.append(
                    {
                        "instrumento": instr_label,
                        "externo": ext_label,
                        "horizonte": h,
                        "n": n,
                        "corr": obs_corr,
                        "p2s_perm": p2s,
                    }
                )
                print(
                    f"  {instr_label:5s} x {ext_label:12s} h={str(h):>4s}  "
                    f"n={n:3d}  corr={obs_corr:+.4f}  p2s(perm,{N_PERM})={p2s:.4f}"
                )

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

    out_csv = REPO / "scripts" / "daytrade" / "leadlag_externo_overnight_probe_2026_09_11.csv"
    df_res.to_csv(out_csv, index=False)
    print(f"\nTabela completa salva em {out_csv}")


if __name__ == "__main__":
    main()
