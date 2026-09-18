"""AJUSTE DE GEOMETRIA POS-TOXICIDADE -- CAMADA 1: corrida generica alvo/stop
(2026-09-16).

## Pergunta

O achado anterior desta MESMA investigacao (hoje) mostrou que um pico de
toxicidade de fluxo (top decil, mesma calibracao de
`wdo_orb_toxicidade_fluxo_veto_2026_09_16.py`) prediz uma CONTRACAO
proporcional da amplitude de movimento nos 2 minutos seguintes -- range
mediano cai de 4,0 para 3,0 ticks, |drift| cai na MESMA proporcao (0,438 vs
0,439), e o tempo dentro de +-2 ticks do preco de referencia sobe de 72,5%
para 84,8%. Ja vetamos a ENTRADA do `wdo_orb` depois de um pico e o resultado
foi REFUTADO (`wdo_orb_toxicidade_veto_designs_2026_09_16.py`): cancelar
jogou fora mais vencedoras que perdedoras, porque a qualidade direcional do
sinal nao piora, so' a escala do movimento disponivel encolhe.

A pergunta nova: em vez de VETAR a entrada, dá pra AJUSTAR A GEOMETRIA (alvo
menor, mais tempo, ou uma regua continua) para aproveitar a contracao?

## Por que uma corrida GENERICA, e nao so' os ~10 trades reais do robo

10 operacoes reais nao tem poder estatistico nenhum. Este script simula uma
corrida alvo/stop hipotetica a partir de MILHARES de instantes do dia (grade
de 20 em 20 segundos, ambas as direcoes -- long e short, para cancelar
qualquer vies direcional residual do dia), tanto em regime de toxicidade
ALTA (dentro dos 120s depois de cruzar o corte -- mesma janela de veto ja'
calibrada) quanto em regime NORMAL (decil central 40-60% da propria
distribuicao do dia, fora de qualquer janela de pico). Isso e' o que da'
poder de verdade com so' 5 pregoes de dado bom.

## As 3 hipoteses (todas testadas nos MESMOS instantes, controle incluido)

  H_A -- alvo reduzido proporcionalmente (fator 0,75 = a razao medida
         3,0/4,0 da contracao) SO' quando o instante cai em regime ALTA.
         Controle: o MESMO alvo reduzido aplicado em regime NORMAL (se
         reduzir o alvo ajuda em qualquer hora do dia, o efeito nao e'
         especifico da toxicidade).
  H_B -- mesmo alvo, horizonte DOBRADO (10 -> 20 min) para dar mais tempo.
         Mesmo controle: horizonte maior tambem em regime NORMAL.
  H_C -- alvo escalado CONTINUAMENTE pelo NIVEL de toxicidade (percentil do
         dia), alvo_ajustado = alvo_base x (1 - 0,5 x percentil_toxicidade),
         piso de 2 ticks (nunca perto de 1 -- proibicao do T1, CLAUDE.md).

Todas comparadas contra o BASELINE: mesmo alvo, mesmo stop (20 ticks fixos,
o `stop_min_ticks` de producao do `wdo_orb`), horizonte de 10 minutos, SEM
condicionar em toxicidade.

## Limitacoes explicitas desta camada (nao e' o motor de producao)

  * Corrida por TOQUE de preco (`last` de cada tick, exatamente como o
    motor real percebe nivel: `bar.high==bar.low==last`), SEM fila --
    ela testa "o preco chegou ali", nao "minha ordem-limite preencheu".
    E' deliberado: aqui queremos a pergunta de ALCANCABILIDADE, a fila e'
    tema separado (`fidelidade.py`) e ja documentado noutro lugar.
  * Entrada hipotetica INSTANTANEA no preco do tick da grade -- nao passa
    pelo offset/prazo da `EnterLimit` real do `wdo_orb`. Por isso os
    resultados daqui NAO substituem a Camada 2 (o robo de verdade).
  * Timeout (nem alvo nem stop no horizonte) marca a mercado no ultimo preco
    da janela -- aproximacao do que um corte de tempo faria.

## Dado

So' 5 pregoes com `flags` confiavel: 2026-08-28 (exploracao/calibracao) e
2026-09-08..11 (confirmacao, 4 pregoes). NAO e' a IS/OOS oficial de 72/51
pregoes do `wdo_orb`.

Uso: `python -u scripts/daytrade/wdo_orb_toxicidade_geometria_camada1_2026_09_16.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wdo_orb_toxicidade_fluxo_veto_2026_09_16 import (  # noqa: E402
    DIA_CALIBRACAO, DIAS_CONFIRMACAO, TODOS_OS_DIAS, VETO_SEG, calibra,
    carregar_ticks_dia, gatilhos_de_veto, negocios_classificados,
    serie_toxicidade,
)

# ---------------------------------------------------------------------------
# constantes da corrida -- NADA daqui vem do motor de producao, e' proposital
# ---------------------------------------------------------------------------

TICK_SIZE = 0.5              # core/instruments.py: WDO@ price_tick_size
TICK_VALUE_BRL = 5.0         # core/instruments.py: WDO@ tick_value_brl
CORRETAGEM_ROUND_TRIP_BRL = 0.50  # backtest/intraday/profiles.py:262

STOP_TICKS_BASE = 20         # = wdo_orb.stop_min_ticks (piso real de producao)
TARGETS_BASE = (3, 5, 8, 10, 15)
ALVO_MIN_TICKS = 2           # nunca perto de 1 -- proibicao do T1, CLAUDE.md

HORIZON_BASE_MIN = 10
HORIZON_EXT_MIN = 20         # H_B
HORIZON_BASE_NS = np.int64(HORIZON_BASE_MIN * 60 * 1_000_000_000)
HORIZON_EXT_NS = np.int64(HORIZON_EXT_MIN * 60 * 1_000_000_000)
VETO_NS = np.int64(VETO_SEG * 1_000_000_000)

FATOR_HA = 0.75               # = razao medida 3,0/4,0 da contracao de range
K_HC = 0.5                    # inclinacao da regua continua (H_C)

STEP_SEGUNDOS = 20            # grade de amostragem de instantes de entrada
BUFFER_INICIO_MIN = 16        # range_minutos(15) + 1' de folga
BUFFER_FIM_MIN = HORIZON_EXT_MIN + 1

BANDA_NORMAL = (0.40, 0.60)   # decil central da propria distribuicao do dia

SAIDA = RAIZ / "scratch" / "wdo_orb_toxicidade_geometria_camada1_2026_09_16"


# ---------------------------------------------------------------------------
# corrida -- avalia 1 janela (rel ja' em ticks favoraveis, wt em ns) contra
# um alvo/stop/horizonte, reaproveitando o indice do stop (fixo, calculado
# 1x por entrada+direcao) para as 4 familias.
# ---------------------------------------------------------------------------

def _primeiro_indice(mask: np.ndarray) -> int:
    return int(np.argmax(mask)) if mask.any() else -1


def _avalia(rel: np.ndarray, wt: np.ndarray, t0: np.int64, idx_stop_global: int,
            stop_ticks: float, alvo_ticks: float, idx_cut: int) -> tuple[str, float, float]:
    """`idx_cut` = quantos elementos de `rel`/`wt` (a partir do inicio da
    janela, ja' EXCLUINDO o instante de entrada) cabem no horizonte desta
    familia. `idx_stop_global` e' o indice (na janela CHEIA, ate' o maior
    horizonte) em que o stop foi tocado, ou -1."""
    if idx_cut <= 0:
        return "sem_dado", 0.0, 0.0
    sub = rel[:idx_cut]
    idx_t = _primeiro_indice(sub >= alvo_ticks)
    idx_s = idx_stop_global if (idx_stop_global != -1 and idx_stop_global < idx_cut) else -1

    if idx_t == -1 and idx_s == -1:
        pnl = float(sub[-1])
        secs = float(wt[idx_cut - 1] - t0) / 1e9
        return "timeout", pnl, secs
    if idx_s == -1:
        return "alvo", float(alvo_ticks), float(wt[idx_t] - t0) / 1e9
    if idx_t == -1:
        return "stop", -float(stop_ticks), float(wt[idx_s] - t0) / 1e9
    if idx_t <= idx_s:
        return "alvo", float(alvo_ticks), float(wt[idx_t] - t0) / 1e9
    return "stop", -float(stop_ticks), float(wt[idx_s] - t0) / 1e9


# ---------------------------------------------------------------------------
# roda 1 pregao inteiro -- devolve o DataFrame longo de simulacoes
# ---------------------------------------------------------------------------

def roda_pregao(dia: str, corte: float, p90_tamanho: float) -> dict:
    ticks = carregar_ticks_dia(dia)
    if ticks.empty:
        return {"dia": dia, "erro": "sem ticks"}

    times_ns = ticks.index.values.astype("datetime64[ns]").astype(np.int64)
    prices = ticks["last"].to_numpy(dtype=float)
    n_ticks = prices.size

    negocios = negocios_classificados(ticks)
    tox = serie_toxicidade(negocios, p90_tamanho)
    gatilhos = gatilhos_de_veto(tox, corte)
    gatilhos_ns = gatilhos.astype("datetime64[ns]").astype(np.int64)

    tox_validos = tox.dropna()
    tox_times_ns = tox_validos.index.values.astype("datetime64[ns]").astype(np.int64)
    tox_vals = tox_validos.to_numpy(dtype=float)
    if tox_vals.size == 0:
        return {"dia": dia, "erro": "toxicidade vazia"}
    p40_dia = float(np.quantile(tox_vals, BANDA_NORMAL[0]))
    p60_dia = float(np.quantile(tox_vals, BANDA_NORMAL[1]))
    tox_vals_ordenados = np.sort(tox_vals)

    # ---- grade de instantes de entrada (20 em 20s, dentro da janela util) --
    t_ini = times_ns[0] + np.int64(BUFFER_INICIO_MIN * 60 * 1_000_000_000)
    t_fim = times_ns[-1] - np.int64(BUFFER_FIM_MIN * 60 * 1_000_000_000)
    if t_fim <= t_ini:
        return {"dia": dia, "erro": "pregao curto demais para a janela"}
    grade = np.arange(t_ini, t_fim, STEP_SEGUNDOS * 1_000_000_000, dtype=np.int64)

    idx_entrada = np.searchsorted(times_ns, grade, side="right") - 1
    idx_entrada = np.unique(idx_entrada[idx_entrada >= 0])
    # garante espaco para pelo menos 1 tick de janela adiante
    idx_entrada = idx_entrada[idx_entrada < n_ticks - 1]

    # ---- regime por entrada (vetorizado) -----------------------------------
    ts_entrada = times_ns[idx_entrada]
    if gatilhos_ns.size:
        pos_g = np.searchsorted(gatilhos_ns, ts_entrada, side="right") - 1
        tem_gatilho = pos_g >= 0
        alta = tem_gatilho & (ts_entrada < (gatilhos_ns[pos_g.clip(min=0)] + VETO_NS))
    else:
        alta = np.zeros_like(ts_entrada, dtype=bool)

    pos_tox = np.searchsorted(tox_times_ns, ts_entrada, side="right") - 1
    tem_tox = pos_tox >= 0
    tox_now = np.where(tem_tox, tox_vals[pos_tox.clip(min=0)], np.nan)
    normal_ref = (~alta) & tem_tox & (tox_now >= p40_dia) & (tox_now <= p60_dia)
    tox_rank = np.where(
        tem_tox,
        np.searchsorted(tox_vals_ordenados, np.nan_to_num(tox_now, nan=-1.0)) / tox_vals_ordenados.size,
        0.0,
    )

    regime = np.where(alta, "alta", np.where(normal_ref, "normal_ref", "outro"))

    # ---- simula, entrada a entrada, long e short ---------------------------
    linhas: list[dict] = []
    for k, i0 in enumerate(idx_entrada):
        t0 = times_ns[i0]
        p0 = prices[i0]
        j_end = np.searchsorted(times_ns, t0 + HORIZON_EXT_NS, side="right")
        if j_end <= i0 + 1:
            continue
        w = prices[i0 + 1:j_end]
        wt = times_ns[i0 + 1:j_end]
        idx_cut10 = int(np.searchsorted(wt, t0 + HORIZON_BASE_NS, side="right"))
        idx_cut20 = w.size

        reg_k = regime[k]
        rank_k = float(tox_rank[k])
        tox_now_k = float(tox_now[k]) if not np.isnan(tox_now[k]) else float("nan")

        for direcao in ("long", "short"):
            rel = (w - p0) / TICK_SIZE if direcao == "long" else (p0 - w) / TICK_SIZE
            idx_stop_global = _primeiro_indice(rel <= -STOP_TICKS_BASE)

            for alvo_base in TARGETS_BASE:
                alvo_ha = max(ALVO_MIN_TICKS, round(alvo_base * FATOR_HA))
                alvo_hc = max(ALVO_MIN_TICKS, round(alvo_base * (1.0 - K_HC * rank_k)))

                familias = [
                    ("baseline", alvo_base, idx_cut10),
                    ("H_A", alvo_ha, idx_cut10),
                    ("H_B", alvo_base, idx_cut20),
                    ("H_C", alvo_hc, idx_cut10),
                ]
                for nome_familia, alvo_usado, idx_cut in familias:
                    outcome, pnl_ticks, secs = _avalia(
                        rel, wt, t0, idx_stop_global, STOP_TICKS_BASE, alvo_usado, idx_cut)
                    if outcome == "sem_dado":
                        continue
                    pnl_brl = pnl_ticks * TICK_VALUE_BRL - CORRETAGEM_ROUND_TRIP_BRL
                    linhas.append({
                        "dia": dia, "k": int(k), "direcao": direcao, "regime": reg_k,
                        "familia": nome_familia, "alvo_base": alvo_base,
                        "alvo_usado": alvo_usado, "stop": STOP_TICKS_BASE,
                        "horizonte_min": HORIZON_EXT_MIN if nome_familia == "H_B" else HORIZON_BASE_MIN,
                        "tox_now": tox_now_k, "tox_rank": rank_k,
                        "outcome": outcome, "pnl_ticks": pnl_ticks, "pnl_brl": round(pnl_brl, 4),
                        "tempo_seg": secs,
                    })

    if not linhas:
        return {"dia": dia, "erro": "nenhuma simulacao produzida"}

    df = pd.DataFrame(linhas)
    return {
        "dia": dia, "erro": "",
        "n_entradas": int(idx_entrada.size),
        "n_alta": int(alta.sum()), "n_normal_ref": int(normal_ref.sum()),
        "n_gatilhos": int(gatilhos.size),
        "df": df,
    }


# ---------------------------------------------------------------------------
# resumo -- n, media, mediana, desvio, IC95% aproximado (normal) por grupo
# ---------------------------------------------------------------------------

def _resumo_grupo(g: pd.DataFrame) -> dict:
    n = len(g)
    if n == 0:
        return {"n": 0}
    win = float((g["outcome"] == "alvo").mean()) * 100.0
    liq = g["pnl_brl"]
    media = float(liq.mean())
    mediana = float(liq.median())
    desvio = float(liq.std(ddof=1)) if n > 1 else 0.0
    erro_padrao = desvio / (n ** 0.5) if n > 1 else 0.0
    ic95 = 1.96 * erro_padrao
    return {
        "n": n, "win_pct": round(win, 2),
        "media_brl": round(media, 3), "mediana_brl": round(mediana, 3),
        "desvio_brl": round(desvio, 3), "ic95_brl": round(ic95, 3),
        "tempo_seg_p50": round(float(g["tempo_seg"].median()), 1),
    }


def imprime_tabela(df: pd.DataFrame, titulo: str) -> None:
    print("\n" + "=" * 110)
    print(titulo)
    print("=" * 110)
    header = (f"{'familia':<10}{'alvo_base':>10}{'regime':>13}{'n':>9}"
              f"{'win%':>8}{'R$/op media':>14}{'R$/op mediana':>15}{'desvio':>10}{'IC95(+-)':>10}{'t_p50(s)':>10}")
    print(header)
    for familia in ("baseline", "H_A", "H_B", "H_C"):
        for alvo_base in TARGETS_BASE:
            for regime in ("alta", "normal_ref"):
                sub = df[(df.familia == familia) & (df.alvo_base == alvo_base) & (df.regime == regime)]
                r = _resumo_grupo(sub)
                if r["n"] == 0:
                    continue
                print(f"{familia:<10}{alvo_base:>10}{regime:>13}{r['n']:>9}"
                      f"{r['win_pct']:>8.2f}{r['media_brl']:>14.3f}{r['mediana_brl']:>15.3f}"
                      f"{r['desvio_brl']:>10.3f}{r['ic95_brl']:>10.3f}{r['tempo_seg_p50']:>10.1f}")


def imprime_tabela_independente(df: pd.DataFrame, titulo: str) -> None:
    """As janelas da grade (20s) se sobrepoem MUITO dentro do horizonte de
    10-20min -- o `n` bruto superestima a informacao independente (mesmo
    trecho de preco entra em dezenas de linhas vizinhas). Esta tabela
    resistra so' 1 a cada `stride` pontos da grade (stride = horizonte /
    20s), aproximando janelas NAO sobrepostas -- e' o teste que decide se o
    padrao sobrevive depois de remover a autocorrelacao, nao so' o IC ingenuo."""
    print("\n" + "=" * 110)
    print(titulo + "  [ROBUSTEZ -- so' 1 ponto a cada horizonte, sem sobreposicao]")
    print("=" * 110)
    header = (f"{'familia':<10}{'alvo_base':>10}{'regime':>13}{'n_indep':>9}"
              f"{'win%':>8}{'R$/op media':>14}{'desvio':>10}{'IC95(+-)':>10}")
    print(header)
    for familia in ("baseline", "H_A", "H_B", "H_C"):
        horizonte = HORIZON_EXT_MIN if familia == "H_B" else HORIZON_BASE_MIN
        stride = int(horizonte * 60 / STEP_SEGUNDOS)
        for alvo_base in TARGETS_BASE:
            for regime in ("alta", "normal_ref"):
                sub = df[(df.familia == familia) & (df.alvo_base == alvo_base) & (df.regime == regime)]
                if sub.empty:
                    continue
                sub_indep = sub[sub.k % stride == 0]
                r = _resumo_grupo(sub_indep)
                if r["n"] == 0:
                    continue
                print(f"{familia:<10}{alvo_base:>10}{regime:>13}{r['n']:>9}"
                      f"{r['win_pct']:>8.2f}{r['media_brl']:>14.3f}"
                      f"{r['desvio_brl']:>10.3f}{r['ic95_brl']:>10.3f}")


def imprime_decis(df: pd.DataFrame, alvo_base_ref: int) -> None:
    """Win%/EV por DECIL de toxicidade no instante da entrada, alvo=alvo_base_ref,
    familia baseline (10 min) -- reproduz o molde decil a decil do achado
    anterior de range/drift, agora em cima do resultado da corrida."""
    sub = df[(df.familia == "baseline") & (df.alvo_base == alvo_base_ref)
             & df["tox_now"].notna()].copy()
    if sub.empty:
        print(f"\n[decis] sem dado valido para alvo_base={alvo_base_ref}")
        return
    sub["decil"] = pd.qcut(sub["tox_now"], 10, labels=False, duplicates="drop")
    print(f"\n{'-'*90}\nDECIS de toxicidade no instante da entrada -- baseline, alvo={alvo_base_ref}t/stop={STOP_TICKS_BASE}t, 10min")
    print(f"{'-'*90}")
    print(f"{'decil':>6}{'n':>8}{'win%':>8}{'R$/op media':>14}{'tox_now p50':>14}")
    for d, g in sub.groupby("decil"):
        print(f"{int(d):>6}{len(g):>8}{100.0*(g.outcome=='alvo').mean():>8.2f}"
              f"{g.pnl_brl.mean():>14.3f}{g.tox_now.median():>14.4f}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    corte, p90_tamanho = calibra()
    print(f"[camada1] toxicidade calibrada em {DIA_CALIBRACAO} (congelada): "
          f"corte top-decil={corte:.4f}, p90 tamanho={p90_tamanho:.1f} contratos")
    print(f"[camada1] stop fixo={STOP_TICKS_BASE}t | alvos base={TARGETS_BASE} | "
          f"horizonte base={HORIZON_BASE_MIN}min (H_B={HORIZON_EXT_MIN}min) | "
          f"fator H_A={FATOR_HA} | k H_C={K_HC} | grade={STEP_SEGUNDOS}s\n", flush=True)

    resultados = {}
    with ProcessPoolExecutor(max_workers=min(5, len(TODOS_OS_DIAS))) as pool:
        futuros = {pool.submit(roda_pregao, d, corte, p90_tamanho): d for d in TODOS_OS_DIAS}
        for fut in as_completed(futuros):
            dia = futuros[fut]
            try:
                r = fut.result()
            except Exception as exc:
                print(f"[{dia}] ERRO: {exc!r}", flush=True)
                continue
            resultados[dia] = r
            if r["erro"]:
                print(f"[{dia}] {r['erro']}", flush=True)
                continue
            print(f"[{dia}] entradas_grade={r['n_entradas']:>5} alta={r['n_alta']:>4} "
                  f"normal_ref={r['n_normal_ref']:>4} gatilhos={r['n_gatilhos']:>3} "
                  f"linhas={len(r['df']):>7}", flush=True)

    ok = {d: r for d, r in resultados.items() if r["erro"] == ""}
    if not ok:
        print("Nenhum pregao produziu dado. Abortando.")
        return

    todas = pd.concat([r["df"] for r in ok.values()], ignore_index=True)
    todas.to_csv(SAIDA / "corridas.csv", index=False, encoding="utf-8")

    for rotulo, dias in [("CALIBRACAO/EXPLORACAO (08-28, 1 pregao)", [DIA_CALIBRACAO]),
                          ("CONFIRMACAO (09-08..09-11, 4 pregoes)", DIAS_CONFIRMACAO),
                          ("AGREGADO (5 pregoes)", TODOS_OS_DIAS)]:
        sub = todas[todas.dia.isin(dias)]
        if sub.empty:
            continue
        imprime_tabela(sub, rotulo)
        imprime_tabela_independente(sub, rotulo)

    imprime_decis(todas, alvo_base_ref=8)

    print(f"\n[camada1] {len(todas):,} linhas de simulacao salvas em {SAIDA / 'corridas.csv'}")


if __name__ == "__main__":
    main()
