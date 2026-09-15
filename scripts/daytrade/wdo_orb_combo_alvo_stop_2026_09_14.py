"""COMBINACAO (2026-09-14) -- alvo 1,5x JUNTO com teto de stop 25.

## Por que combinar

Os dois eixos foram medidos separados hoje e cada um cobre o buraco do outro:

    candidata          R$/op no bootstrap   pregoes positivos no bootstrap
    T1.5  (alvo)              42,4%                    95,2%
    S20-25 (stop)             80,3%                    35,7%

O alvo mais curto melhora a REGULARIDADE sem mexer no dinheiro; o teto de stop
mais baixo melhora o DINHEIRO sem mexer na regularidade. Nenhum dos dois faz as
duas coisas. A pergunta e' se juntos fazem.

## O risco conhecido da combinacao

`alvo = alvo_multiplo x stop`, e `stop = clamp(faixa, stop_min, stop_max)`.
Baixar o teto do stop JA encurta o alvo; encurtar o multiplo por cima encurta
de novo. A combinacao pode cair no regime que o sweep de stop mostrou ser ruim
no IS -- onde stop curto piorava monotonicamente. Nao e' soma de dois ganhos
garantida; e' uma celula nova que precisa ser medida como tal.

Piso de seguranca: a celula mais curta da grade (T1.5 x S20) pede alvo de 30
ticks. Longe da proibicao do T1 (CLAUDE.md).

## A grade -- 2 x 3, com a VIZINHANCA de proposito

    alvo_multiplo  1,5 e 2,0        (2,0 = producao)
    stop_max       20, 25 e 30      (30 = producao)

Seis celulas, e a producao (T2.0/S30) e' uma delas. A vizinhanca nao esta' ali
para pescar o melhor numero: esta' para responder se a celula vencedora e' um
PLATO (vizinhas parecidas -- o efeito e' real e suave) ou um PICO ESTREITO
(vizinhas ruins -- assinatura de sobreajuste). Um otimo isolado numa grade e'
motivo para desconfiar, nao para promover.

## O que decide

Mesma disciplina das rodadas anteriores: tem de melhorar nas DUAS janelas
independentes, e passar no bootstrap por pregao emparelhado (5.000
reamostragens) contra a producao. O piso declarado e' 90% -- abaixo disso a
vantagem nao sobrevive ao reembaralhamento da propria amostra, quanto mais a
um pregao novo.

Uso: `python -u scripts/daytrade/wdo_orb_combo_alvo_stop_2026_09_14.py`
"""
from __future__ import annotations

import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    excursao, monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    JANELAS, classifica_saida, pregoes_da_janela,
)
from wdo_orb_geometria_is_oos_2026_09_14 import resumo_celula  # noqa: E402

MULTIPLOS = [1.5, 2.0]
STOPS_MAX = [20, 25, 30]
PRODUCAO = "T2.0/S30"
COMBINACAO = "T1.5/S25"
N_BOOT = 5000

CELULAS = [(f"T{m}/S{s}", dict(alvo_multiplo=m, stop_min_ticks=20, stop_max_ticks=s))
           for m in MULTIPLOS for s in STOPS_MAX]

SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


def roda_pregao_todas_celulas(dia: str) -> list[dict]:
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    linhas = []
    for nome, kwargs in CELULAS:
        strat = WdoOrbInstrumentado(**kwargs)
        cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
        res = run_intraday_backtest(bars, strat, cfg)
        ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
        for i, t in enumerate(sorted(res.trades, key=lambda x: x.entry_ts)):
            ordem = None
            for o in ordens:
                if o["sinal_ts"] <= t.entry_ts:
                    ordem = o
                else:
                    break
            pnl_ticks = (((t.exit_price - t.entry_price) if t.side == "long"
                          else (t.entry_price - t.exit_price)) / TICK_SIZE)
            razao = (t.exit_reason.value if hasattr(t.exit_reason, "value")
                     else str(t.exit_reason))
            alvo = ordem["alvo_ticks"] if ordem else float("nan")
            exc = excursao(bars, t.entry_ts, t.exit_ts, t.entry_price, t.side)
            linhas.append({
                "celula": nome, "data": dia, "op_do_dia": i + 1,
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2), "pnl_ticks": round(pnl_ticks, 1),
                "alvo_ticks": alvo,
                "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
                "saida_efetiva": classifica_saida(razao, pnl_ticks, alvo),
                "mfe_ticks": round(exc["mfe_ticks"], 1),
                "mae_ticks": round(exc["mae_ticks"], 1),
            })
    return linhas


def bootstrap(df: pd.DataFrame, atual: str, cand: str) -> dict:
    base = df[df.janela.isin(["IS", "OOS_LIMPO"])]
    dias = base.data.unique()
    agr = {}
    for cel in (atual, cand):
        g = base[base.celula == cel].groupby("data")["pnl_brl"]
        agr[cel] = pd.DataFrame({"soma": g.sum(), "n": g.count()}).reindex(dias).fillna(0.0)
    rng = np.random.default_rng(20260914)
    g_rs = g_pr = g_ambos = 0
    d_rs, d_pr = [], []
    for _ in range(N_BOOT):
        idx = rng.integers(0, len(dias), len(dias))
        r = {}
        for cel in (atual, cand):
            somas = agr[cel]["soma"].values[idx]; ns = agr[cel]["n"].values[idx]
            r[cel] = {"rs": somas.sum() / ns.sum() if ns.sum() else np.nan,
                      "pr": 100.0 * (somas > 0).sum() / max((ns > 0).sum(), 1)}
        a = r[cand]["rs"] - r[atual]["rs"]; b = r[cand]["pr"] - r[atual]["pr"]
        d_rs.append(a); d_pr.append(b)
        if a > 0: g_rs += 1
        if b > 0: g_pr += 1
        if a > 0 and b > 0: g_ambos += 1
    return {"rs_pct": 100.0 * g_rs / N_BOOT, "pr_pct": 100.0 * g_pr / N_BOOT,
            "ambos_pct": 100.0 * g_ambos / N_BOOT,
            "d_rs": np.median(d_rs), "d_pr": np.median(d_pr),
            "ic_rs": (np.percentile(d_rs, 2.5), np.percentile(d_rs, 97.5)),
            "ic_pr": (np.percentile(d_pr, 2.5), np.percentile(d_pr, 97.5))}


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
    print(f"[combo] {len(todos)} pregoes x {len(CELULAS)} celulas "
          f"({[c for c, _ in CELULAS]}), {MAX_WORKERS} processos\n", flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao_todas_celulas, d): d for d in todos}
        for fut in as_completed(futuros):
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{futuros[fut]}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(todos)}", flush=True)

    df = pd.DataFrame(linhas)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    df.to_csv(SAIDA / "90_combo_trades.csv", index=False, encoding="utf-8")
    print(f"\n[combo] {len(df)} operacoes -> 90_combo_trades.csv")

    tabelas = []
    for rotulo, _, _, papel in JANELAS:
        n_pregoes = len(dias_por_janela[rotulo])
        print("\n" + "=" * 132)
        print(f"JANELA {rotulo}  ({n_pregoes} pregoes, {papel})")
        print("=" * 132)
        tab = pd.DataFrame([{"celula": nome,
                             **resumo_celula(df[(df.janela == rotulo) & (df.celula == nome)],
                                             n_pregoes)}
                            for nome, _ in CELULAS])
        print(tab.to_string(index=False))
        tab.insert(0, "janela", rotulo)
        tabelas.append(tab)
        assin = {}
        for nome, _ in CELULAS:
            ops = df[(df.janela == rotulo) & (df.celula == nome)]
            assin[nome] = (len(ops), round(ops["pnl_brl"].sum(), 2))
        rep = [k for k, v in assin.items() if list(assin.values()).count(v) > 1]
        if rep:
            print(f"  [EIXO MORTO] celulas identicas: {rep}")

    todas = pd.concat(tabelas)
    todas.to_csv(SAIDA / "91_combo_resumo.csv", index=False, encoding="utf-8")

    # ---- a GRADE, para ver plato x pico -----------------------------------
    print("\n" + "=" * 132)
    print("A GRADE -- plato ou pico estreito? (linhas = multiplo do alvo, colunas = teto do stop)")
    print("=" * 132)
    for metrica in ["rs_por_op", "pregoes_pos_pct"]:
        print(f"\n--- {metrica} ---")
        for janela in ["IS", "OOS_LIMPO"]:
            sub = todas[todas.janela == janela].set_index("celula")[metrica]
            grade = pd.DataFrame(
                [[sub.get(f"T{m}/S{s}", np.nan) for s in STOPS_MAX] for m in MULTIPLOS],
                index=[f"alvo {m}x" for m in MULTIPLOS],
                columns=[f"stop<={s}" for s in STOPS_MAX])
            print(f"  [{janela}]")
            print(grade.round(2).to_string())

    # ---- bootstrap da combinacao contra a producao ------------------------
    print("\n" + "=" * 132)
    print(f"BOOTSTRAP -- {COMBINACAO} contra {PRODUCAO} ({N_BOOT} reamostragens por pregao)")
    print("=" * 132)
    for cand in [COMBINACAO, "T1.5/S30", "T2.0/S25"]:
        if cand == PRODUCAO:
            continue
        b = bootstrap(df, PRODUCAO, cand)
        print(f"\n  {cand} contra {PRODUCAO}:")
        print(f"    R$/op maior em          {b['rs_pct']:5.1f}%  "
              f"(mediana {b['d_rs']:+.2f}, IC95 [{b['ic_rs'][0]:+.2f} ; {b['ic_rs'][1]:+.2f}])")
        print(f"    mais pregoes positivos: {b['pr_pct']:5.1f}%  "
              f"(mediana {b['d_pr']:+.2f}pp, IC95 [{b['ic_pr'][0]:+.2f} ; {b['ic_pr'][1]:+.2f}])")
        print(f"    as DUAS ao mesmo tempo: {b['ambos_pct']:5.1f}%")

    print("\n  [piso declarado] 90%. Abaixo disso a vantagem nao sobrevive ao")
    print("  reembaralhamento da propria amostra -- quanto mais a um pregao novo.")
    print(f"\n[combo] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
