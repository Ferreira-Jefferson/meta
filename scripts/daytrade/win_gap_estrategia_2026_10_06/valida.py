# -*- coding: utf-8 -*-
"""Validacao da celula CONGELADA (out/escolha_congelada.json), rodada UMA vez, sem reajuste.

Gasta, para estas hipoteses, as janelas: 2022-01..2025-09 (por ano) e 2026-02-20..2026-04-03.
As duas sao PROXY nos precos de leilao/call (abertura e fechamento aproximados), declarado.
O que sai: tabela padrao (modo A conta continua R$250 por janela; modo B R$250 por pregao), BE
empirico, nulo de direcao aleatoria, sem fill, atraso, saidas no ultimo bar, sensibilidade de fill
(toque x atravessa >=1 tick) e o teste do INDICIO cru (sem geometria, sem custo).
"""
from __future__ import annotations

import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

JANELAS = [
    ("IS 2026-04-06..10-05", "2026", "2026-04-06", "2026-10-05"),
    ("VAL2 2026-02-20..04-03", "2026", "2026-02-20", "2026-04-03"),
    ("VAL1 2022", "2022_25", "2022-01-01", "2022-12-31"),
    ("VAL1 2023", "2022_25", "2023-01-01", "2023-12-31"),
    ("VAL1 2024", "2022_25", "2024-01-01", "2024-12-31"),
    ("VAL1 2025 jan-set", "2022_25", "2025-01-01", "2025-09-30"),
    ("VAL1 2022-2025 (B junto)", "2022_25", "2022-01-01", "2025-09-30"),
]


def indicio_cru(base: str, ini: str, fim: str) -> dict:
    """O indicio SEM geometria e SEM custo: so' precos. V1: mov do pregao (abertura do continuo ->
    ultimo negocio do continuo) contra o gap. V2: resto do pregao depois da 1a barra M5, na direcao
    dela, nos dias em que ela fechou contra o gap."""
    import runner
    bars, dj, ctx = runner.dados_da_janela(base, ini, fim)
    dia = bars.index.normalize()
    linhas = []
    for d, g in bars.groupby(dia):
        if d.date() not in ctx:
            continue
        gap = ctx[d.date()][0]
        b1 = g.iloc[0]
        linhas.append(dict(dia=d, gap=gap, o1=b1.open, c1=b1.close, cl=g.iloc[-1].close,
                           rng=g.high.max() - g.low.min(), volcall=dj.loc[d, "vol_call_prev"]))
    t = pd.DataFrame(linhas).set_index("dia")
    t["mov"] = t.cl - t.o1
    rng = np.random.default_rng(1)

    def perm(x):
        x = np.asarray(x, float)
        if len(x) == 0:
            return float("nan")
        obs = x.mean()
        sg = rng.choice([-1, 1], size=(5000, len(x)))
        return float((1 + (np.abs((sg * np.abs(x)).mean(axis=1)) >= abs(obs)).sum() / 1) / 5001) if False else \
            float((1 + (((sg * np.abs(x)).mean(axis=1)) >= obs).sum()) / 5001)
    v1 = -np.sign(t.gap) * t.mov                       # fade do gap
    cont = np.sign(t.c1 - t.o1) * (t.cl - t.c1)
    against = (np.sign(t.c1 - t.o1) * np.sign(t.gap) < 0)
    v2 = cont[against]
    up = t.gap > 0
    out = dict(
        n=len(t),
        v1_media=float(v1.mean()), v1_pct_pos=float((v1 > 0).mean() * 100), v1_p=perm(v1.values),
        gap_up_mov=float(t.mov[up].mean()), gap_up_pct_alta=float((t.mov[up] > 0).mean() * 100), n_up=int(up.sum()),
        gap_dn_mov=float(t.mov[~up].mean()), gap_dn_pct_alta=float((t.mov[~up] > 0).mean() * 100), n_dn=int((~up).sum()),
        rho_gap_mov=float(t.gap.rank().corr(t.mov.rank())),
        v2_n=int(against.sum()), v2_media=float(v2.mean()) if len(v2) else float("nan"),
        v2_pct_pos=float((v2 > 0).mean() * 100) if len(v2) else float("nan"), v2_p=perm(v2.values),
        rho_volcall_rng=float(t.volcall.rank().corr(t.rng.rank())),
    )
    return out


def unidade(nome: str, base: str, ini: str, fim: str, spec: dict) -> dict:
    import runner
    import tabela
    saida = dict(nome=nome, base=base, ini=ini, fim=fim, indicio=indicio_cru(base, ini, fim))
    pooled = nome.startswith("VAL1 2022-2025")
    for fill in ("toque", "atrav+1t"):
        if not pooled:
            a = runner.roda(spec, base, ini, fim, fill, detalhe=False)
            saida[("a", fill)] = dict(
                linha=tabela.linha_a(a, spec), res={k: v for k, v in a.items() if k not in ("_linha", "trades")})
        rp = runner.roda_pregao(spec, base, ini, fim, fill)
        r = runner.resume_pregao(rp, spec)
        saida[("b", fill)] = dict(linha=tabela.linha_b(r, spec, fill),
                                  res={k: v for k, v in r.items() if k not in ("trades", "dir_real", "pos", "neg", "pnl_dia", "dias_sessao")})
    return saida


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from tabela import EXTRAS, nome, tabela
    spec = json.load(open(AQUI / "out" / "escolha_congelada.json"))["escolha"]
    print("CELULA CONGELADA:", nome(spec), spec, flush=True)
    res = {}
    with ProcessPoolExecutor(max_workers=5) as pool:
        fut = {pool.submit(unidade, n, b, i, f, spec): n for n, b, i, f in JANELAS}
        for f in as_completed(fut):
            u = f.result()
            res[u["nome"]] = u
            print(f"\n## {u['nome']}", flush=True)
            ls = [u[k]["linha"] for k in (("a", "toque"), ("b", "toque"), ("a", "atrav+1t"), ("b", "atrav+1t")) if k in u]
            print(tabela(ls, EXTRAS, 11), flush=True)
    pickle.dump(res, open(AQUI / "out" / "valida_resultados.pkl", "wb"))

    print("\n\n######## RESUMO ORDENADO ########")
    for n, *_ in JANELAS:
        u = res[n]
        print(f"\n## {n}")
        ls = [u[k]["linha"] for k in (("a", "toque"), ("b", "toque"), ("a", "atrav+1t"), ("b", "atrav+1t")) if k in u]
        print(tabela(ls, EXTRAS, 11))
        for fill in ("toque", "atrav+1t"):
            b = u[("b", fill)]["res"]
            print(f"  B {fill:<8}: sinais={b['dias_gatilho']} fills={b['n']} sem_fill={b['sem_fill']} ({b['taxa_sem_fill']:.1f}%) "
                  f"atraso mediana/p90 (min)={b['atraso_med']:.1f}/{b['atraso_p90']:.1f} win={b['win']:.1f}% BE emp={b['be']:.1f}% "
                  f"liquido={b['liquido']:.2f} nulo medio={b['nulo_med']:.1f} [p5 {b['nulo_p5']:.1f} ; p95 {b['nulo_p95']:.1f}] p={b['p_nulo']:.3f} "
                  f"saidas={b['motivos']} flatten={b['ff']} (no ultimo bar do continuo={b['ff_ultima_continua']}) saidas na barra do call={b['saidas_barra_call']} "
                  f"stop tocado na barra do fill={b['stop_na_barra_do_fill']} pior op={b['pior']:.2f}")
            if ("a", fill) in u:
                a = u[("a", fill)]["res"]
                print(f"  A {fill:<8}: trades={a['n']} recusadas por capital={a['recusadas']} caixa min (MtM)={a['eq_min']:.2f} "
                      f"sem trade={a['sem_trade']}/{a['pregoes']} liquido={a['liquido']:.2f} zerado={a['zerado']} saidas={a['motivos']} "
                      f"flatten={a['ff']} (ultimo bar={a['ff_ultima_continua']}; call={a['saidas_barra_call']})")
        print("  excluidos:", u["toque"]["a"]["res"]["excl"] if False else "", end="")
        i = u["indicio"]
        print(f"  INDICIO CRU: n={i['n']} | V1 fade: media {i['v1_media']:.0f} pts, {i['v1_pct_pos']:.0f}% dias +, p={i['v1_p']:.3f}; "
              f"gap alta (n={i['n_up']}) mov {i['gap_up_mov']:.0f} pts, {i['gap_up_pct_alta']:.0f}% altas; gap baixa (n={i['n_dn']}) mov {i['gap_dn_mov']:.0f} pts, "
              f"{i['gap_dn_pct_alta']:.0f}% altas; rho(gap,mov)={i['rho_gap_mov']:.2f} | V2: n={i['v2_n']} resto na direcao da 1a barra "
              f"{i['v2_media']:.0f} pts, {i['v2_pct_pos']:.0f}% dias +, p={i['v2_p']:.3f} | rho(vol call D-1, amplitude D)={i['rho_volcall_rng']:.2f}")


if __name__ == "__main__":
    main()
