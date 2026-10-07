"""Sonda (estagio 1, sem motor) do padrao overnight PROPRIO do WDO@.

Pedido do dono: o preco se move de noite (pregao fechado); quando reabre nao
esta necessariamente onde fechou. Existe padrao no que acontece DEPOIS desse
gap, dentro do pregao -- continuacao, fade (reversao), efeito concentrado na
abertura ou que so aparece perto do fechamento -- e esse padrao muda entre
gap normal (dia util seguinte) e gap de fim-de-semana/feriado?

Diferenca do lead-lag EXTERNO (leadlag_externo_overnight_probe_2026_09_11.py,
REFUTADO -- 0/20 celulas sobrevivem Bonferroni, ver MEMORY.md
nova_fronteira_10_lentes_2026_09_11): aqui o preditor e' o proprio gap do
WDO@ (fechamento[d-1] -> abertura[d]), sem precisar de nenhuma base externa,
so' os ticks que ja' temos em data/raw_ticks/.

Convencao do projeto ("o minimo que refuta primeiro",
feedback_teste_pequeno_valida_hipotese): correlacao/preditividade bruta,
SEM custo, SEM motor de execucao. So' se houver sinal com significancia
(permutacao, Bonferroni pela familia de testes) vale a pena construir a
IntradayStrategy completa.

Sem look-ahead: o gap e' conhecido no instante da abertura (open_px vs
close_px do pregao anterior); toda resposta usa so' ticks ESTRITAMENTE
depois da abertura.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from core.instruments import FUTUROS  # noqa: E402

HORIZONS_MIN = [5, 15, 30, 60, 120, 240]
N_PERM = 20_000
SEED = 20260927

WDO_TICK = FUTUROS["WDO@"].price_tick_size  # 0.5 ponto


def _load_wdo_ticks() -> pd.DataFrame:
    path = REPO / "data" / "raw_ticks" / "WDO_A_f1.parquet"
    df = pd.read_parquet(path, columns=["close"])
    df = df.rename(columns={"close": "last"})
    df = df[df["last"] > 0]
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    return df


def _session_table(ticks: pd.DataFrame) -> pd.DataFrame:
    """Por pregao: abertura/fechamento e retorno acumulado a partir da
    abertura em cada horizonte (mesmo padrao de
    leadlag_externo_overnight_probe_2026_09_11.py, sem look-ahead)."""
    ticks = ticks.copy()
    ticks["session_date"] = ticks.index.tz_convert("UTC").date
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


def _add_gap_columns(sess: pd.DataFrame) -> pd.DataFrame:
    sess = sess.copy()
    prev_close_px = sess["close_px"].shift(1)
    prev_date = pd.Series(sess.index, index=sess.index).shift(1)
    sess["gap_ret"] = sess["open_px"] / prev_close_px - 1.0
    sess["gap_ticks"] = (sess["open_px"] - prev_close_px) / WDO_TICK
    sess["calendar_days"] = [
        (d - pd_ if pd.notna(pd_) else np.nan)
        for d, pd_ in zip(sess.index, prev_date)
    ]
    sess["calendar_days"] = sess["calendar_days"].apply(
        lambda x: x.days if pd.notna(x) else np.nan
    )
    sess["gap_bucket"] = np.where(
        sess["calendar_days"] == 1, "curto(1d)",
        np.where(sess["calendar_days"] >= 2, "longo(fds/feriado)", "n/a"),
    )
    return sess.dropna(subset=["gap_ticks"])


def _permutation_corr(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, n_perm: int) -> tuple[float, float]:
    obs = np.corrcoef(x, y)[0, 1]
    perm_corrs = np.empty(n_perm)
    y_work = y.copy()
    for i in range(n_perm):
        rng.shuffle(y_work)
        perm_corrs[i] = np.corrcoef(x, y_work)[0, 1]
    p2s = float(np.mean(np.abs(perm_corrs) >= abs(obs)))
    return obs, p2s


def _permutation_mean_ne_zero(y: np.ndarray, rng: np.random.Generator, n_perm: int) -> tuple[float, float]:
    """Sign-flip: sob H0 (media zero), o sinal de cada observacao e' livre."""
    obs = float(np.mean(y))
    signs = np.empty(n_perm)
    abs_y = np.abs(y)
    for i in range(n_perm):
        flips = rng.choice([-1.0, 1.0], size=len(y))
        signs[i] = np.mean(flips * abs_y)
    p2s = float(np.mean(np.abs(signs) >= abs(obs)))
    return obs, p2s


def main() -> None:
    print("=== Sonda gap overnight PROPRIO do WDO@ -- ESTAGIO 1 (correlacao bruta) ===")
    ticks = _load_wdo_ticks()
    print(f"{len(ticks):,} ticks, {ticks.index.min()} .. {ticks.index.max()}")
    sess = _session_table(ticks)
    print(f"{len(sess)} pregoes com dado suficiente")
    sess = _add_gap_columns(sess)
    print(f"{len(sess)} pregoes com gap valido (exclui o 1o pregao da serie)")
    print(sess["gap_bucket"].value_counts().to_string())
    print(f"calendar_days: {sorted(sess['calendar_days'].unique())}")

    rng = np.random.default_rng(SEED)
    results = []

    # --- Estagio 1: gap x retorno intradiario, TODOS os pregoes ---
    horizons_all = HORIZONS_MIN + ["eod"]
    for h in horizons_all:
        col_y = f"ret_{h}m" if h != "eod" else "eod_return"
        sub = sess[["gap_ticks", col_y]].dropna()
        n = len(sub)
        x = sub["gap_ticks"].to_numpy()
        y = sub[col_y].to_numpy()
        obs, p2s = _permutation_corr(x, y, rng, N_PERM)
        results.append({"familia": "gap_x_retorno(todos)", "recorte": "todos", "horizonte": str(h), "n": n, "estatistica": "corr", "valor": obs, "p2s_perm": p2s})
        print(f"  [F1] todos      h={str(h):>4s}  n={n:3d}  corr={obs:+.4f}  p2s={p2s:.4f}")

    # --- Estagio 2: gap x retorno, por bucket de calendario (curto vs longo) ---
    for bucket in ["curto(1d)", "longo(fds/feriado)"]:
        bsub = sess[sess["gap_bucket"] == bucket]
        for h in [30, "eod"]:
            col_y = f"ret_{h}m" if h != "eod" else "eod_return"
            sub = bsub[["gap_ticks", col_y]].dropna()
            n = len(sub)
            if n < 15:
                print(f"  [F2] {bucket:20s} h={str(h):>4s}  n={n:3d}  -- amostra pequena demais, pulado")
                continue
            x = sub["gap_ticks"].to_numpy()
            y = sub[col_y].to_numpy()
            obs, p2s = _permutation_corr(x, y, rng, N_PERM)
            results.append({"familia": "gap_x_retorno(calendario)", "recorte": bucket, "horizonte": str(h), "n": n, "estatistica": "corr", "valor": obs, "p2s_perm": p2s})
            print(f"  [F2] {bucket:20s} h={str(h):>4s}  n={n:3d}  corr={obs:+.4f}  p2s={p2s:.4f}")

    # --- Estagio 3: assimetria -- gap positivo vs negativo, retorno medio != 0 ---
    for sign_label, mask in [("gap>0", sess["gap_ticks"] > 0), ("gap<0", sess["gap_ticks"] < 0)]:
        ssub = sess[mask]
        for h in [30, "eod"]:
            col_y = f"ret_{h}m" if h != "eod" else "eod_return"
            y = ssub[col_y].dropna().to_numpy()
            n = len(y)
            if n < 15:
                continue
            obs, p2s = _permutation_mean_ne_zero(y, rng, N_PERM)
            results.append({"familia": "assimetria(media!=0)", "recorte": sign_label, "horizonte": str(h), "n": n, "estatistica": "media_ret", "valor": obs, "p2s_perm": p2s})
            print(f"  [F3] {sign_label:8s}       h={str(h):>4s}  n={n:3d}  media={obs:+.6f}  p2s={p2s:.4f}")

    # --- Estagio 4: magnitude do gap (tercil) x retorno EOD ---
    abs_gap = sess["gap_ticks"].abs()
    terciles = abs_gap.quantile([1 / 3, 2 / 3]).to_numpy()
    sess["magnitude"] = np.where(
        abs_gap <= terciles[0], "pequeno",
        np.where(abs_gap <= terciles[1], "medio", "grande"),
    )
    for mag in ["pequeno", "medio", "grande"]:
        msub = sess[sess["magnitude"] == mag]
        sub = msub[["gap_ticks", "eod_return"]].dropna()
        n = len(sub)
        if n < 15:
            continue
        x = sub["gap_ticks"].to_numpy()
        y = sub["eod_return"].to_numpy()
        obs, p2s = _permutation_corr(x, y, rng, N_PERM)
        results.append({"familia": "magnitude_x_retorno", "recorte": mag, "horizonte": "eod", "n": n, "estatistica": "corr", "valor": obs, "p2s_perm": p2s})
        print(f"  [F4] {mag:8s}        h= eod  n={n:3d}  corr={obs:+.4f}  p2s={p2s:.4f}")

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
    sess_csv = Path(__file__).resolve().with_name("wdo_gap_proprio_padrao_2026_09_27_sessoes.csv")
    sess.to_csv(sess_csv)
    print(f"\nTabela de testes salva em {out_csv}")
    print(f"Tabela por pregao salva em {sess_csv}")


if __name__ == "__main__":
    main()
