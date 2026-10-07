"""Bateria ampla (estagio 1, sem motor) de padroes NAO-lineares/estruturais
do gap overnight PROPRIO do WDO@, pedida pelo dono depois que a versao
linear (`wdo_gap_proprio_padrao_2026_09_27.py`, 18 celulas) e o lead-lag
EXTERNO (`leadlag_externo_overnight_probe_2026_09_11.py`, 20 celulas) deram
0 sobreviventes -- "teste padroes nao lineares e outros, teste 50 variantes
diferentes".

Familias novas (nao repetem as 18 celulas ja testadas):
  A. |gap| x volatilidade/range da sessao (nao-direcional)               (5)
  C. dinamica de preenchimento do gap (fill-rate, fracao fechada no EOD) (4)
  D. dia-da-semana / calendario categorico (nao gap-linear)              (3)
  E. participacao/volume na abertura, isolado e interagindo com gap      (3)
  F. gap de hoje x retorno intradiario de ONTEM (continuidade cross-day) (3)
  G. so' os extremos (decil), nao a amostra inteira (efeito de cauda)    (2)
  H. estabilidade IS vs OOS da relacao gap x retorno EOD                 (2)
  J. autocorrelacao do proprio gap (gap de hoje prediz gap de amanha?)   (1)
  K. fim-de-semana PURO (3 dias corridos) vs feriado-no-meio (2 ou 4)    (2)
  L. "tendencia" na 1a hora (drift monotonico) grande-gap vs pequeno-gap (1)
  M. interacao magnitude x calendario (gap grande + fim-de-semana)       (2)
  N. volatilidade clusteriza entre dias? gap grande hoje -> dia seguinte
     mais volatil / com excursao maior contra a posicao?                (2)

Total: 30 celulas novas. Somadas as 18 anteriores = 48 (a familia
declarada e' so' as 30 daqui; a correcao de Bonferroni desta bateria usa
n=30, nao mistura com o arquivo anterior -- misturar dois estudos rodados
em dias diferentes como uma unica familia seria inventar correcao depois
de ver os dois resultados).

Convencao do projeto: correlacao/teste bruto, SEM custo, SEM motor. So' se
sobreviver a correcao vale construir IntradayStrategy e custear no motor
real (fila, deslize, execucao fechada).

Sem look-ahead: todo preditor usa so' informacao conhecida na abertura
(gap) ou em dias ANTERIORES; toda resposta usa so' dado de DENTRO do
proprio pregao (ou do pregao seguinte, explicitamente rotulado como tal).
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
SEED = 20260927002

WDO_TICK = FUTUROS["WDO@"].price_tick_size  # 0.5 ponto


def _load_wdo_ticks() -> pd.DataFrame:
    path = REPO / "data" / "raw_ticks" / "WDO_A_f1.parquet"
    df = pd.read_parquet(path, columns=["close", "volume"])
    df = df.rename(columns={"close": "last"})
    df = df[df["last"] > 0]
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    return df


def _realized_var(sub: pd.DataFrame) -> float:
    """Variancia realizada (soma dos retornos^2) em barras de 1min -- proxy
    de volatilidade robusto a ruido de microestrutura tick-a-tick."""
    if len(sub) < 3:
        return np.nan
    m1 = sub["last"].resample("1min").last().ffill()
    r = np.log(m1 / m1.shift(1)).dropna()
    if len(r) < 2:
        return np.nan
    return float((r**2).sum())


def _build_sessions(ticks: pd.DataFrame) -> pd.DataFrame:
    ticks = ticks.copy()
    ticks["session_date"] = ticks.index.tz_convert("UTC").date
    rows = []
    prev_close_px = None
    prev_date = None
    for date, day_df in ticks.groupby("session_date"):
        if len(day_df) < 10:
            continue
        open_ts = day_df.index[0]
        open_px = float(day_df["last"].iloc[0])
        close_ts = day_df.index[-1]
        close_px = float(day_df["last"].iloc[-1])
        vol_total = float(day_df["volume"].sum())

        row = {
            "session_date": date,
            "dow": pd.Timestamp(date).weekday(),  # 0=segunda
            "open_ts": open_ts,
            "open_px": open_px,
            "close_ts": close_ts,
            "close_px": close_px,
            "eod_return": close_px / open_px - 1.0,
            "range_total_ticks": (day_df["last"].max() - day_df["last"].min()) / WDO_TICK,
            "realized_var_total": _realized_var(day_df),
            "vol_total": vol_total,
        }
        for h in HORIZONS_MIN:
            target_ts = open_ts + pd.Timedelta(minutes=h)
            sub = day_df[day_df.index <= target_ts]
            if len(sub) < 2:
                row[f"ret_{h}m"] = np.nan
                row[f"range_{h}m_ticks"] = np.nan
                row[f"realized_var_{h}m"] = np.nan
                row[f"vol_{h}m"] = np.nan
                continue
            px_h = float(sub["last"].iloc[-1])
            row[f"ret_{h}m"] = px_h / open_px - 1.0
            row[f"range_{h}m_ticks"] = (sub["last"].max() - sub["last"].min()) / WDO_TICK
            row[f"realized_var_{h}m"] = _realized_var(sub)
            row[f"vol_{h}m"] = float(sub["volume"].sum())

        # tendencia (Spearman) na 1a hora: elapsed vs preco
        first60 = day_df[day_df.index <= open_ts + pd.Timedelta(minutes=60)]
        if len(first60) >= 20:
            elapsed = pd.Series((first60.index - open_ts).total_seconds())
            # Spearman = Pearson sobre os postos -- evita depender de scipy
            # (nao e' dependencia deste projeto, ver CLAUDE.md).
            row["trend_r_first60"] = float(
                elapsed.rank().corr(pd.Series(first60["last"].to_numpy()).rank())
            )
        else:
            row["trend_r_first60"] = np.nan

        # gap e' contra o FECHAMENTO ANTERIOR -- calculado aqui (passo
        # sequencial, nao look-ahead: so' usa o `prev_close_px` de uma
        # sessao ja' concluida).
        if prev_close_px is not None:
            row["gap_ticks"] = (open_px - prev_close_px) / WDO_TICK
            row["calendar_days"] = (date - prev_date).days
            row["prev_close_px"] = prev_close_px
            # preenchimento do gap: o preco volta a tocar o fechamento anterior?
            gap_sign = np.sign(row["gap_ticks"])
            if gap_sign > 0:
                touched = day_df["last"] <= prev_close_px
            elif gap_sign < 0:
                touched = day_df["last"] >= prev_close_px
            else:
                touched = pd.Series(dtype=bool)
            row["filled"] = bool(touched.any()) if gap_sign != 0 else np.nan
            if gap_sign != 0:
                total_gap_dist = open_px - prev_close_px
                row["frac_gap_closed_eod"] = 1.0 - (close_px - prev_close_px) / total_gap_dist
            else:
                row["frac_gap_closed_eod"] = np.nan
        else:
            row["gap_ticks"] = np.nan
            row["calendar_days"] = np.nan
            row["filled"] = np.nan
            row["frac_gap_closed_eod"] = np.nan

        rows.append(row)
        prev_close_px = close_px
        prev_date = date

    sess = pd.DataFrame(rows).set_index("session_date").sort_index()
    return sess


def _perm_corr(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, n_perm: int = N_PERM) -> tuple[float, float]:
    obs = np.corrcoef(x, y)[0, 1]
    y_work = y.copy()
    perm = np.empty(n_perm)
    for i in range(n_perm):
        rng.shuffle(y_work)
        perm[i] = np.corrcoef(x, y_work)[0, 1]
    p2s = float(np.mean(np.abs(perm) >= abs(obs)))
    return obs, p2s


def _perm_diff_means(a: np.ndarray, b: np.ndarray, rng: np.random.Generator, n_perm: int = N_PERM) -> tuple[float, float]:
    obs = float(np.mean(a) - np.mean(b))
    pooled = np.concatenate([a, b])
    na = len(a)
    perm = np.empty(n_perm)
    for i in range(n_perm):
        rng.shuffle(pooled)
        perm[i] = np.mean(pooled[:na]) - np.mean(pooled[na:])
    p2s = float(np.mean(np.abs(perm) >= abs(obs)))
    return obs, p2s


def _perm_omnibus_groups(groups: list[np.ndarray], rng: np.random.Generator, n_perm: int = N_PERM) -> tuple[float, float]:
    """Teste omnibus tipo-ANOVA (variancia entre medias dos grupos, ponderada
    pelo n de cada grupo) via permutacao -- sem depender de scipy."""

    def _stat(vals: list[np.ndarray]) -> float:
        grand_mean = np.concatenate(vals).mean()
        return float(sum(len(v) * (v.mean() - grand_mean) ** 2 for v in vals))

    obs = _stat(groups)
    sizes = [len(g) for g in groups]
    pooled = np.concatenate(groups)
    perm = np.empty(n_perm)
    for i in range(n_perm):
        rng.shuffle(pooled)
        cursor = 0
        vals = []
        for s in sizes:
            vals.append(pooled[cursor:cursor + s])
            cursor += s
        perm[i] = _stat(vals)
    p2s = float(np.mean(perm >= obs))
    return obs, p2s


def main() -> None:
    print("=== Bateria NAO-LINEAR/estrutural -- gap overnight proprio WDO@ (estagio 1) ===")
    ticks = _load_wdo_ticks()
    print(f"{len(ticks):,} ticks, {ticks.index.min()} .. {ticks.index.max()}")
    sess = _build_sessions(ticks)
    sess_g = sess.dropna(subset=["gap_ticks"]).copy()
    print(f"{len(sess)} pregoes totais, {len(sess_g)} com gap valido")

    sess_g["abs_gap"] = sess_g["gap_ticks"].abs()
    terciles = sess_g["abs_gap"].quantile([1 / 3, 2 / 3]).to_numpy()
    sess_g["magnitude"] = np.where(
        sess_g["abs_gap"] <= terciles[0], "pequeno",
        np.where(sess_g["abs_gap"] <= terciles[1], "medio", "grande"),
    )
    sess_g["bucket"] = np.where(sess_g["calendar_days"] == 1, "curto", "longo")

    rng = np.random.default_rng(SEED)
    results = []

    def add(familia, recorte, estat, n, valor, p, extra=""):
        results.append({"familia": familia, "recorte": recorte, "estatistica": estat, "n": n, "valor": valor, "p2s_perm": p, "obs": extra})
        print(f"  [{familia}] {recorte:28s} {estat:22s} n={n:3d}  valor={valor:+.5f}  p2s={p:.4f}  {extra}")

    # --- A: |gap| x volatilidade/range (nao-direcional), todos os pregoes ---
    for label, col in [
        ("range_total", "range_total_ticks"),
        ("range_60m", "range_60m_ticks"),
        ("realized_var_total", "realized_var_total"),
        ("realized_var_60m", "realized_var_60m"),
        ("vol_60m(participacao)", "vol_60m"),
    ]:
        sub = sess_g[["abs_gap", col]].dropna()
        x, y = sub["abs_gap"].to_numpy(), sub[col].to_numpy()
        obs, p = _perm_corr(x, y, rng)
        add("A.vol", label, "corr(|gap|,y)", len(sub), obs, p)

    # --- C: dinamica de preenchimento do gap ---
    a = sess_g.loc[sess_g["bucket"] == "curto", "filled"].dropna().astype(float).to_numpy()
    b = sess_g.loc[sess_g["bucket"] == "longo", "filled"].dropna().astype(float).to_numpy()
    obs, p = _perm_diff_means(a, b, rng)
    add("C.fill", "fillrate curto-longo", "diff_proporcao", len(a) + len(b), obs, p, f"curto={a.mean():.3f} longo={b.mean():.3f}")

    a = sess_g.loc[sess_g["magnitude"] == "pequeno", "filled"].dropna().astype(float).to_numpy()
    b = sess_g.loc[sess_g["magnitude"] == "grande", "filled"].dropna().astype(float).to_numpy()
    obs, p = _perm_diff_means(a, b, rng)
    add("C.fill", "fillrate pequeno-grande", "diff_proporcao", len(a) + len(b), obs, p, f"pequeno={a.mean():.3f} grande={b.mean():.3f}")

    sub = sess_g[["abs_gap", "frac_gap_closed_eod"]].dropna()
    obs, p = _perm_corr(sub["abs_gap"].to_numpy(), sub["frac_gap_closed_eod"].to_numpy(), rng)
    add("C.fill", "|gap| x frac_fechada_eod", "corr", len(sub), obs, p)

    sub = sess_g[["gap_ticks", "frac_gap_closed_eod"]].dropna()
    obs, p = _perm_corr(sub["gap_ticks"].to_numpy(), sub["frac_gap_closed_eod"].to_numpy(), rng)
    add("C.fill", "gap(sinal) x frac_fechada_eod", "corr", len(sub), obs, p)

    # --- D: dia-da-semana / calendario categorico ---
    seg = sess_g.loc[sess_g["dow"] == 0, "eod_return"].dropna().to_numpy()
    resto = sess_g.loc[sess_g["dow"] != 0, "eod_return"].dropna().to_numpy()
    obs, p = _perm_diff_means(seg, resto, rng)
    add("D.dow", "segunda vs resto (eod_ret)", "diff_media", len(seg) + len(resto), obs, p)

    sexta = sess_g.loc[sess_g["dow"] == 4, "eod_return"].dropna().to_numpy()
    resto2 = sess_g.loc[sess_g["dow"] != 4, "eod_return"].dropna().to_numpy()
    obs, p = _perm_diff_means(sexta, resto2, rng)
    add("D.dow", "sexta vs resto (eod_ret)", "diff_media", len(sexta) + len(resto2), obs, p)

    # omnibus (permutacao, sem scipy) entre os 5 dias da semana
    groups = [sess_g.loc[sess_g["dow"] == d, "eod_return"].dropna().to_numpy() for d in range(5)]
    groups = [g for g in groups if len(g) >= 5]
    if len(groups) >= 2:
        stat, p_omni = _perm_omnibus_groups(groups, rng)
        add("D.dow", "omnibus dia-da-semana", "var_entre_grupos", sum(len(g) for g in groups), stat, p_omni)

    # --- E: participacao/volume ---
    sub = sess_g[["abs_gap", "vol_60m"]].dropna()
    obs, p = _perm_corr(sub["abs_gap"].to_numpy(), sub["vol_60m"].to_numpy(), rng)
    add("E.vol", "|gap| x volume_60m", "corr", len(sub), obs, p)

    med_vol = sess_g["vol_60m"].median()
    hi = sess_g[sess_g["vol_60m"] > med_vol][["gap_ticks", "eod_return"]].dropna()
    lo = sess_g[sess_g["vol_60m"] <= med_vol][["gap_ticks", "eod_return"]].dropna()
    obs_hi, p_hi = _perm_corr(hi["gap_ticks"].to_numpy(), hi["eod_return"].to_numpy(), rng)
    add("E.vol", "gap x eod_ret | volume ALTO", "corr", len(hi), obs_hi, p_hi)
    obs_lo, p_lo = _perm_corr(lo["gap_ticks"].to_numpy(), lo["eod_return"].to_numpy(), rng)
    add("E.vol", "gap x eod_ret | volume BAIXO", "corr", len(lo), obs_lo, p_lo)

    # --- F: gap de hoje x retorno intradiario de ONTEM ---
    sess_full = sess.sort_index().copy()
    sess_full["gap_ticks_shift"] = sess_full["gap_ticks"]
    prev_intra = sess_full["eod_return"].shift(1)
    sub = pd.DataFrame({"gap_hoje": sess_full["gap_ticks"], "intra_ontem": prev_intra}).dropna()
    obs, p = _perm_corr(sub["gap_hoje"].to_numpy(), sub["intra_ontem"].to_numpy(), rng)
    add("F.crossday", "gap_hoje x intradia_ontem", "corr", len(sub), obs, p)

    sign_match = np.sign(sub["gap_hoje"]) == np.sign(sub["intra_ontem"])
    joined = sess_full.loc[sub.index, "eod_return"]
    a = joined[sign_match.to_numpy()].dropna().to_numpy()
    b = joined[~sign_match.to_numpy()].dropna().to_numpy()
    obs, p = _perm_diff_means(a, b, rng)
    add("F.crossday", "eod_ret | sinais concordam vs nao", "diff_media", len(a) + len(b), obs, p)

    combo = sub["gap_hoje"] + sub["intra_ontem"] * (1 / sub["intra_ontem"].abs().median()) * sub["gap_hoje"].abs().median()
    sub2 = pd.DataFrame({"combo": combo, "eod_ret": joined}).dropna()
    obs, p = _perm_corr(sub2["combo"].to_numpy(), sub2["eod_ret"].to_numpy(), rng)
    add("F.crossday", "(gap+intradia_ontem) x eod_ret", "corr", len(sub2), obs, p)

    # --- G: extremos (decil) ---
    dec_hi = sess_g["abs_gap"].quantile(0.90)
    top = sess_g[sess_g["abs_gap"] >= dec_hi]
    rest = sess_g[sess_g["abs_gap"] < dec_hi]
    a = top["eod_return"].abs().dropna().to_numpy()
    b = rest["eod_return"].abs().dropna().to_numpy()
    obs, p = _perm_diff_means(a, b, rng)
    add("G.extremo", "|eod_ret| decil-top-|gap| vs resto", "diff_media", len(a) + len(b), obs, p, f"n_top={len(a)}")

    q_hi = sess_g["gap_ticks"].quantile(0.90)
    q_lo = sess_g["gap_ticks"].quantile(0.10)
    a = sess_g.loc[sess_g["gap_ticks"] >= q_hi, "eod_return"].dropna().to_numpy()
    b = sess_g.loc[sess_g["gap_ticks"] <= q_lo, "eod_return"].dropna().to_numpy()
    obs, p = _perm_diff_means(a, b, rng)
    add("G.extremo", "eod_ret decil+ vs decil-", "diff_media", len(a) + len(b), obs, p, f"n+={len(a)} n-={len(b)}")

    # --- H: estabilidade IS vs OOS (usa a coluna 'janela' original do parquet) ---
    janela_por_dia = ticks_janela = None
    raw = pd.read_parquet(REPO / "data" / "raw_ticks" / "WDO_A_f1.parquet", columns=["janela"])
    raw.index = pd.to_datetime(raw.index, utc=True)
    raw["session_date"] = raw.index.tz_convert("UTC").date
    janela_por_dia = raw.groupby("session_date")["janela"].first()
    sess_g["janela"] = sess_g.index.map(janela_por_dia)
    for jan in ["IS", "OOS"]:
        sub = sess_g[sess_g["janela"] == jan][["gap_ticks", "eod_return"]].dropna()
        if len(sub) < 15:
            continue
        obs, p = _perm_corr(sub["gap_ticks"].to_numpy(), sub["eod_return"].to_numpy(), rng)
        add("H.estabilidade", f"gap x eod_ret | janela={jan}", "corr", len(sub), obs, p)

    # --- J: autocorrelacao do proprio gap ---
    g_series = sess_full["gap_ticks"].dropna()
    g_today = g_series.iloc[:-1].to_numpy()
    g_next = g_series.iloc[1:].to_numpy()
    obs, p = _perm_corr(g_today, g_next, rng)
    add("J.autocorr", "gap(t) x gap(t+1)", "corr", len(g_today), obs, p)

    # --- K: fim-de-semana puro (3 dias corridos) vs feriado-no-meio (2 ou 4) ---
    puro = sess_g[sess_g["calendar_days"] == 3]
    feriado = sess_g[sess_g["calendar_days"].isin([2, 4])]
    a = puro["eod_return"].dropna().to_numpy()
    b = feriado["eod_return"].dropna().to_numpy()
    if len(a) >= 10 and len(b) >= 10:
        obs, p = _perm_diff_means(a, b, rng)
        add("K.fds_vs_feriado", "eod_ret fds(3d) vs feriado(2/4d)", "diff_media", len(a) + len(b), obs, p)
    a = puro["filled"].dropna().astype(float).to_numpy()
    b = feriado["filled"].dropna().astype(float).to_numpy()
    if len(a) >= 10 and len(b) >= 10:
        obs, p = _perm_diff_means(a, b, rng)
        add("K.fds_vs_feriado", "fillrate fds(3d) vs feriado(2/4d)", "diff_proporcao", len(a) + len(b), obs, p, f"fds={a.mean():.3f} feriado={b.mean():.3f}")

    # --- L: tendencia na 1a hora, gap grande vs pequeno ---
    med_abs = sess_g["abs_gap"].median()
    a = sess_g.loc[sess_g["abs_gap"] > med_abs, "trend_r_first60"].dropna().to_numpy()
    b = sess_g.loc[sess_g["abs_gap"] <= med_abs, "trend_r_first60"].dropna().to_numpy()
    obs, p = _perm_diff_means(np.abs(a), np.abs(b), rng)
    add("L.tendencia", "|trend_r_1a_hora| gap-grande vs gap-pequeno", "diff_media", len(a) + len(b), obs, p)

    # --- M: interacao magnitude x calendario ---
    a = sess_g.loc[(sess_g["magnitude"] == "grande") & (sess_g["bucket"] == "longo"), "eod_return"].dropna().to_numpy()
    b = sess_g.loc[(sess_g["magnitude"] == "grande") & (sess_g["bucket"] == "curto"), "eod_return"].dropna().to_numpy()
    if len(a) >= 8 and len(b) >= 8:
        obs, p = _perm_diff_means(a, b, rng)
        add("M.interacao", "eod_ret gap-grande: longo vs curto", "diff_media", len(a) + len(b), obs, p)
    a2 = sess_g.loc[(sess_g["magnitude"] == "grande") & (sess_g["bucket"] == "longo"), "filled"].dropna().astype(float).to_numpy()
    b2 = sess_g.loc[(sess_g["magnitude"] == "grande") & (sess_g["bucket"] == "curto"), "filled"].dropna().astype(float).to_numpy()
    if len(a2) >= 8 and len(b2) >= 8:
        obs, p = _perm_diff_means(a2, b2, rng)
        add("M.interacao", "fillrate gap-grande: longo vs curto", "diff_proporcao", len(a2) + len(b2), obs, p, f"longo={a2.mean():.3f} curto={b2.mean():.3f}")

    # --- N: volatilidade clusteriza entre dias? ---
    rv_today = sess_full["realized_var_total"]
    rv_next = rv_today.shift(-1)
    sub = pd.DataFrame({"abs_gap_hoje": sess_full["gap_ticks"].abs(), "rv_amanha": rv_next}).dropna()
    obs, p = _perm_corr(sub["abs_gap_hoje"].to_numpy(), sub["rv_amanha"].to_numpy(), rng)
    add("N.cluster", "|gap|_hoje x realized_var_AMANHA", "corr", len(sub), obs, p)

    range_next = sess_full["range_total_ticks"].shift(-1)
    sub = pd.DataFrame({"abs_gap_hoje": sess_full["gap_ticks"].abs(), "range_amanha": range_next}).dropna()
    obs, p = _perm_corr(sub["abs_gap_hoje"].to_numpy(), sub["range_amanha"].to_numpy(), rng)
    add("N.cluster", "|gap|_hoje x range_AMANHA", "corr", len(sub), obs, p)

    df_res = pd.DataFrame(results)
    n_tests = len(df_res)
    bonf = 0.05 / n_tests if n_tests else float("nan")
    print(f"\n=== RESUMO -- {n_tests} testes (familia declarada desta bateria), Bonferroni alpha={bonf:.5f} ===")
    df_res_sorted = df_res.sort_values("p2s_perm")
    print(df_res_sorted.drop(columns=["obs"]).to_string(index=False))

    survivors = df_res_sorted[df_res_sorted["p2s_perm"] < bonf]
    print(f"\nSobrevivem Bonferroni: {len(survivors)}")
    if len(survivors):
        print(survivors.to_string(index=False))

    n_nominal = (df_res_sorted["p2s_perm"] < 0.05).sum()
    print(f"\n(referencia, NAO decide nada sozinho) celulas com p<0,05 SEM correcao: {n_nominal}/{n_tests}")

    out_csv = Path(__file__).resolve().with_suffix(".csv")
    df_res.to_csv(out_csv, index=False)
    sess_csv = Path(__file__).resolve().with_name("wdo_gap_padrao_nao_linear_2026_09_27_sessoes.csv")
    sess.to_csv(sess_csv)
    print(f"\nTabela de testes salva em {out_csv}")
    print(f"Tabela por pregao salva em {sess_csv}")


if __name__ == "__main__":
    main()
