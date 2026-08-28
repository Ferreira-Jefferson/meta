"""Frente F7 -- spread relativo WIN@ x WDO@: PASSO 1 (investigacao pura).

Pergunta: existe estrutura de REVERSAO genuina na relacao WIN@/WDO@ (estilo
par cointegrado), alem da correlacao contemporanea ja conhecida e ja
refutada como preditiva (r=-0,52, sem defasagem exploravel)? Este script
NAO negocia nada -- so mede. Se a estrutura nao aparecer aqui, a frente para
e reporta ABANDON (regra da missao).

Desenho da medicao
-------------------
As duas series nao tem a mesma unidade de preco (pontos de indice x pontos
de dolar), entao "cointegracao de nivel" (Engle-Granger classico) nao tem
leitura economica direta. O que a missao pede e' reversao do SPREAD -- o
angulo certo e' RETORNO, nao preco: regressa o retorno-por-minuto do WIN no
retorno-por-minuto do WDO (pool de todo o IS, so dias com as duas pontas) e
usa o RESIDUO dessa regressao como "spread ortogonalizado" (a parte do
movimento do WIN que a co-movimentacao contemporanea com o WDO NAO explica).
Se esse residuo tiver estrutura de reversao (autocorrelacao negativa,
variance ratio < 1 em horizontes crescentes, z-score extremo prevendo
retorno futuro oposto), ha' alguma coisa para desenhar uma regra em cima.
Se nao, e' ruido e a frente para no passo 1.

Nulo por REPAREAMENTO DE DIA (nao sign-flip -- sign-flip e' para P&L de uma
REGRA, que so existe no passo 2; aqui ainda nao ha regra). A hipotese nula
relevante do passo 1 nao e' "o sinal do lucro poderia ser trocado", e' "o
que parece reversao do PAR e' so a dinamica de cada perna sozinha". O nulo
troca, para cada dia do WIN, a perna WDO por OUTRO dia (pareado por posicao
dentro do pregao, nao por relogio) -- preserva a autocorrelacao propria de
cada serie mas destroi a relacao contemporanea DAQUELE dia especifico. Se a
estatistica real nao for mais extrema que a distribuicao desse nulo, a
"reversao" medida e' artefato de cada perna isolada, nao do PAR.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

MIN_BARRAS_POR_PREGAO = 400
SEED_BASE = 20260827  # data da rodada -- deterministico, nao escolhido a dedo


def _sessoes_completas(bars: pd.DataFrame, minimo: int = MIN_BARRAS_POR_PREGAO) -> pd.DataFrame:
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= minimo}
    return bars[[d in completos for d in bars.index.date]]


def carregar_is(symbol: str) -> pd.DataFrame:
    """Barras M1 do simbolo, so' pregoes completos, so' o trecho IN-SAMPLE
    (`.in_sample()` -- `.out_of_sample()` nunca e' chamado nesta frente)."""
    df = load_m1(symbol)
    if df.empty:
        raise SystemExit(f"[f7] sem dado M1 salvo para {symbol!r}.")
    profile = profile_for(symbol)
    df = _sessoes_completas(df.sort_index())
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(df, split)
    return locked.in_sample()


def dias_por_simbolo(bars: pd.DataFrame) -> dict:
    """`{data: DataFrame do pregao}`, ordenado, so' com a coluna `close`."""
    out = {}
    for d, g in bars.groupby(bars.index.date):
        out[d] = g[["close"]].copy()
    return dict(sorted(out.items()))


def retornos_do_dia(dia: pd.DataFrame) -> np.ndarray:
    """Retorno percentual barra-a-barra dentro do pregao (1a barra descartada
    -- nao ha retorno "antes" dela dentro do dia)."""
    c = dia["close"].to_numpy(dtype=float)
    return c[1:] / c[:-1] - 1.0


def main() -> None:
    win_is = carregar_is("WIN@")
    wdo_is = carregar_is("WDO@")

    win_dias_all = dias_por_simbolo(win_is)
    wdo_dias_all = dias_por_simbolo(wdo_is)

    dias_comuns = sorted(set(win_dias_all) & set(wdo_dias_all))
    print(f"[f7] pregoes completos WIN IS: {len(win_dias_all)} | WDO IS: {len(wdo_dias_all)} "
          f"| comuns: {len(dias_comuns)}")
    print(f"[f7] janela comum: {dias_comuns[0]} .. {dias_comuns[-1]}")

    # --- pareamento REAL por timestamp comum (inner join minuto-a-minuto) ---
    win_ret_by_day: dict = {}
    wdo_ret_by_day: dict = {}
    for d in dias_comuns:
        j = win_dias_all[d].rename(columns={"close": "win"}).join(
            wdo_dias_all[d].rename(columns={"close": "wdo"}), how="inner"
        )
        if len(j) < 100:  # dia com pouquissima sobreposicao de relogio -- descarta
            continue
        win_r = j["win"].to_numpy(dtype=float)
        win_r = win_r[1:] / win_r[:-1] - 1.0
        wdo_r = j["wdo"].to_numpy(dtype=float)
        wdo_r = wdo_r[1:] / wdo_r[:-1] - 1.0
        win_ret_by_day[d] = win_r
        wdo_ret_by_day[d] = wdo_r

    dias_usados = sorted(win_ret_by_day)
    print(f"[f7] pregoes usados (>=100 minutos sobrepostos): {len(dias_usados)}")

    win_pool = np.concatenate([win_ret_by_day[d] for d in dias_usados])
    wdo_pool = np.concatenate([wdo_ret_by_day[d] for d in dias_usados])
    n = len(win_pool)
    print(f"[f7] total de minutos pareados no IS: {n}")

    corr = np.corrcoef(win_pool, wdo_pool)[0, 1]
    print(f"\n[sanidade] correlacao contemporanea retorno-a-retorno (1 min), IS: {corr:.4f} "
          f"(esperado ~-0,5, ja documentado)")

    # --- hedge ratio via OLS pooled: win_ret = a + b*wdo_ret + resid ---
    b = np.cov(win_pool, wdo_pool, ddof=1)[0, 1] / np.var(wdo_pool, ddof=1)
    a = win_pool.mean() - b * wdo_pool.mean()
    print(f"[hedge] beta={b:.4f}  alpha={a:.6f} (pooled OLS, retorno win ~ retorno wdo)")

    def spread_ret(win_r: np.ndarray, wdo_r: np.ndarray) -> np.ndarray:
        return win_r - a - b * wdo_r

    spread_by_day = {d: spread_ret(win_ret_by_day[d], wdo_ret_by_day[d]) for d in dias_usados}
    spread_pool = np.concatenate([spread_by_day[d] for d in dias_usados])
    print(f"[spread] media={spread_pool.mean():.6f}  desvio={spread_pool.std(ddof=1):.6f} "
          f"(retorno-residuo por minuto, pooled)")

    # ================= TESTE A: autocorrelacao do retorno-residuo =================
    def acf_intraday(by_day: dict, lag: int) -> float:
        """Autocorrelacao pooled em lag `lag`, SO' pares dentro do mesmo dia."""
        xs, ys = [], []
        for d, arr in by_day.items():
            if len(arr) <= lag:
                continue
            xs.append(arr[:-lag])
            ys.append(arr[lag:])
        x = np.concatenate(xs)
        y = np.concatenate(ys)
        return np.corrcoef(x, y)[0, 1]

    lags = [1, 2, 3, 5, 10, 15, 30]
    acf_real = {lag: acf_intraday(spread_by_day, lag) for lag in lags}
    print("\n[TESTE A] autocorrelacao do retorno-residuo (spread), pooled intradiario:")
    for lag in lags:
        print(f"  lag={lag:>3} min: acf={acf_real[lag]:+.4f}")

    # ================= TESTE B: variance ratio do NIVEL do spread ==============
    def cumsum_by_day(by_day: dict) -> dict:
        return {d: np.concatenate([[0.0], np.cumsum(arr)]) for d, arr in by_day.items()}

    nivel_by_day = cumsum_by_day(spread_by_day)
    var1 = np.var(spread_pool, ddof=1)

    def variance_ratio(nivel_by_day: dict, q: int) -> float:
        diffs = []
        for d, lvl in nivel_by_day.items():
            if len(lvl) <= q:
                continue
            diffs.append(lvl[q:] - lvl[:-q])
        d_all = np.concatenate(diffs)
        return np.var(d_all, ddof=1) / (q * var1)

    qs = [2, 5, 15, 30, 60]
    vr_real = {q: variance_ratio(nivel_by_day, q) for q in qs}
    print("\n[TESTE B] variance ratio do nivel do spread (VR<1 => reversao, VR=1 => passeio "
          "aleatorio, VR>1 => tendencia):")
    for q in qs:
        print(f"  q={q:>3} min: VR={vr_real[q]:.4f}")

    # ============= TESTE C: z-score extremo prediz retorno futuro? =============
    JANELA_Z = 30
    HORIZONTE = 15

    def zscore_e_forward(nivel_by_day: dict, janela: int, horizonte: int):
        zs, fwd = [], []
        for d, lvl in nivel_by_day.items():
            n_d = len(lvl)
            if n_d <= janela + horizonte:
                continue
            for t in range(janela, n_d - horizonte):
                trecho = lvl[t - janela:t]
                mu, sd = trecho.mean(), trecho.std(ddof=1)
                if sd <= 0:
                    continue
                z = (lvl[t] - mu) / sd
                delta_fwd = lvl[t + horizonte] - lvl[t]
                zs.append(z)
                fwd.append(delta_fwd)
        return np.array(zs), np.array(fwd)

    z_real, fwd_real = zscore_e_forward(nivel_by_day, JANELA_Z, HORIZONTE)
    corr_zc_real = np.corrcoef(z_real, fwd_real)[0, 1]
    print(f"\n[TESTE C] z-score (janela {JANELA_Z}min) do nivel do spread vs retorno futuro "
          f"{HORIZONTE}min a frente. n={len(z_real)}")
    print(f"  correlacao(z, delta_futuro) = {corr_zc_real:+.4f} "
          f"(negativa => reversao: z alto -> queda futura)")

    decis = pd.qcut(z_real, 10, labels=False, duplicates="drop")
    tab = pd.DataFrame({"decil_z": decis, "z": z_real, "fwd": fwd_real})
    resumo = tab.groupby("decil_z").agg(z_medio=("z", "mean"), fwd_medio=("fwd", "mean"),
                                          n=("fwd", "size"))
    print(resumo.to_string(float_format=lambda x: f"{x:.5f}"))

    # ================= NULO: repareamento de dia (posicional) ==================
    rng_seeds = list(range(5))  # minimo 5 sementes exigido pela disciplina
    n_dias = len(dias_usados)

    def spread_repareado(seed: int) -> tuple[dict, dict]:
        """Para cada dia do WIN, sorteia OUTRO dia (sem reposicao ateh acabar,
        DERANGEMENT simples via shuffle) para fornecer a perna WDO, pareada
        por POSICAO (nao por relogio) e truncada ao menor comprimento comum.
        Preserva a autocorrelacao propria de cada perna; destroi a relacao
        contemporanea real daquele dia."""
        rng = np.random.default_rng(SEED_BASE + seed)
        ordem = np.arange(n_dias)
        # derangement: embaralha ate nenhum dia mapear pra si mesmo (n_dias>=2)
        for _ in range(200):
            rng.shuffle(ordem)
            if n_dias < 2 or not np.any(ordem == np.arange(n_dias)):
                break
        by_day_fake = {}
        nivel_fake = {}
        for i, d in enumerate(dias_usados):
            d_wdo = dias_usados[ordem[i]]
            win_r = win_ret_by_day[d]
            wdo_r = wdo_ret_by_day[d_wdo]
            m = min(len(win_r), len(wdo_r))
            s = spread_ret(win_r[:m], wdo_r[:m])
            by_day_fake[d] = s
            nivel_fake[d] = np.concatenate([[0.0], np.cumsum(s)])
        return by_day_fake, nivel_fake

    print(f"\n[NULO] repareamento de dia (posicional), {len(rng_seeds)} sementes:")
    acf1_nulo, vr30_nulo, corrzc_nulo = [], [], []
    for seed in rng_seeds:
        by_day_fake, nivel_fake = spread_repareado(seed)
        acf1_nulo.append(acf_intraday(by_day_fake, 1))
        vr30_nulo.append(variance_ratio(nivel_fake, 30))
        z_f, fwd_f = zscore_e_forward(nivel_fake, JANELA_Z, HORIZONTE)
        corrzc_nulo.append(np.corrcoef(z_f, fwd_f)[0, 1] if len(z_f) > 10 else np.nan)

    def resumo_dispersao(nome: str, real: float, nulo: list) -> None:
        nulo = np.array(nulo, dtype=float)
        nulo = nulo[~np.isnan(nulo)]
        pct = 100.0 * (nulo < real).mean() if len(nulo) else float("nan")
        print(f"  {nome}: real={real:+.4f}  nulo(media={nulo.mean():+.4f}, "
              f"min={nulo.min():+.4f}, max={nulo.max():+.4f}, dp={nulo.std(ddof=1):+.4f}, "
              f"n={len(nulo)})  percentil do real no nulo = {pct:.1f}%")

    resumo_dispersao("acf lag1", acf_real[1], acf1_nulo)
    resumo_dispersao("VR q=30", vr_real[30], vr30_nulo)
    resumo_dispersao("corr(z, fwd15)", corr_zc_real, corrzc_nulo)

    # ================= TESTE de METADE (1a metade do IS escolhe, 2a confere) ===
    meio = dias_usados[len(dias_usados) // 2]
    metade1 = [d for d in dias_usados if d < meio]
    metade2 = [d for d in dias_usados if d >= meio]
    print(f"\n[METADE] 1a metade: {len(metade1)} pregoes ({metade1[0]}..{metade1[-1]}) | "
          f"2a metade: {len(metade2)} pregoes ({metade2[0]}..{metade2[-1]})")

    def acf1_de(dias_sub: list) -> float:
        sub = {d: spread_by_day[d] for d in dias_sub}
        return acf_intraday(sub, 1)

    def corrzc_de(dias_sub: list) -> float:
        sub_nivel = {d: nivel_by_day[d] for d in dias_sub}
        z, fwd = zscore_e_forward(sub_nivel, JANELA_Z, HORIZONTE)
        return np.corrcoef(z, fwd)[0, 1] if len(z) > 10 else float("nan")

    print(f"  acf lag1:        1a metade={acf1_de(metade1):+.4f}   2a metade={acf1_de(metade2):+.4f}")
    print(f"  corr(z, fwd15):  1a metade={corrzc_de(metade1):+.4f}   2a metade={corrzc_de(metade2):+.4f}")


if __name__ == "__main__":
    main()
