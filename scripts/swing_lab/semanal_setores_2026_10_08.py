"""Resultado da estrategia semanal POR SETOR (regua pura: todos os sinais, caixa fora).

Pedido do dono (2026-10-08): "faca um calculo por setor e veja se algum se destaca".

Mede a v2 (so as grandes, mais operacoes por setor) e a v5 (atual) por setor,
nas tres fontes: MT5 IS, MT5 OOS e yfinance 2011-21 (contexto). O sorteio
IS/OOS foi equilibrado por setor, entao cada setor aparece nos dois conjuntos.

Um setor "se destaca" so se ficar acima da media da propria versao no MT5 IS
E no MT5 OOS, com >= 10 operacoes em cada. Com ~10 setores, um deles fica
acima so por acaso em uma fonte com facilidade; nas duas, menos.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_historico_yf_2026_10_08 as hist  # noqa: E402
import semanal_versoes_puro_2026_10_08 as vp  # noqa: E402
from semanal_grandes_refino_2026_10_08 import ibov_semanal as ibov_mt5  # noqa: E402
from semanal_linha_de_base_2026_10_08 import br  # noqa: E402

# roda tambem nos processos filhos (spawn reimporta este modulo)
vp.VERSOES = {"v2": vp.VERSOES["v2"], "v5": vp.VERSOES["v4+prazo8"]}
SETOR = dict(base.universo())
MIN_N = 10


def resumo(g: pd.DataFrame) -> dict:
    if not len(g):
        return dict(n=0, exp=np.nan, ic=np.nan, acerto=np.nan, taxa=np.nan)
    dias = np.maximum(g.dias.to_numpy(), 1).sum()
    return dict(n=len(g) / 2, exp=g.ret.mean(),
                ic=1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan,
                acerto=(g.ret > 0).mean(), taxa=np.exp(np.log1p(g.ret.to_numpy()).sum() / dias * 365) - 1)


def coletar(fonte: str, conjunto: str | None) -> pd.DataFrame:
    if fonte == "mt5":
        ib, tks = ibov_mt5(), base.papeis(conjunto)
    else:
        ib, tks = hist.ibov_semanal(), list(SETOR)
    trades = []
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(vp.medir, tk, fonte, conjunto, ib) for tk in tks]):
            trades += f.result()[1]
    T = pd.DataFrame(trades)
    T["setor"] = T.ticker.map(SETOR)
    return T


def main() -> None:
    res: dict = {}
    for nome, fonte, conj in vp.FONTES:
        T = coletar(fonte, conj)
        print(f"\n== {nome} (todos os sinais, 14x2 e 21x3 juntas, caixa fora)", flush=True)
        for cfg in vp.VERSOES:
            g = T[T.cfg == cfg]
            tot = resumo(g)
            res[(nome, cfg, "TODOS")] = tot
            print(f"  {cfg}  TODOS{'':17s} n={tot['n']:4.0f}  por op. {br(tot['exp']):>7s} ±{br(tot['ic'], sinal=False):6s}"
                  f"  acerto {tot['acerto']:4.0%}  posicionada {br(tot['taxa'], 1)}/ano", flush=True)
            for s, gs in sorted(g.groupby("setor"), key=lambda x: -x[1].ret.mean()):
                r = resumo(gs)
                res[(nome, cfg, s)] = r
                print(f"      {s:24s} n={r['n']:4.0f}  por op. {br(r['exp']):>7s} ±{br(r['ic'], sinal=False):6s}"
                      f"  acerto {r['acerto']:4.0%}  posicionada {br(r['taxa'], 1)}/ano"
                      f"  papeis {gs.ticker.nunique()}", flush=True)

    print("\nDESTAQUE — acima da media da versao no MT5 IS E no MT5 OOS, >= 10 operacoes em cada; yfinance = contexto", flush=True)
    mt5 = [n for n, f, _ in vp.FONTES if f == "mt5"]
    yf = [n for n, f, _ in vp.FONTES if f == "yf"][0]
    for cfg in vp.VERSOES:
        print(f"  {cfg}", flush=True)
        for s in sorted(set(SETOR.values())):
            cel = [res.get((f, cfg, s)) for f in mt5]
            if any(c is None for c in cel):
                print(f"    {s:24s} sem operacoes em alguma fonte do MT5", flush=True)
                continue
            acima = [c["exp"] > res[(f, cfg, "TODOS")]["exp"] and c["taxa"] > res[(f, cfg, "TODOS")]["taxa"]
                     for c, f in zip(cel, mt5)]
            n_ok = all(c["n"] >= MIN_N for c in cel)
            y = res.get((yf, cfg, s))
            ytxt = f"yf n={y['n']:.0f} {br(y['exp'])}" if y else "yf sem operacoes"
            sit = "DESTACA" if all(acima) and n_ok else ("abaixo nas duas" if not any(acima) else "misto")
            if all(acima) and not n_ok:
                sit = "acima nas duas, poucas operacoes"
            det = "  ".join(f"{f}: n={c['n']:.0f} {br(c['exp'])}" for c, f in zip(cel, mt5))
            print(f"    {s:24s} {sit:34s} | {det} | {ytxt}", flush=True)


if __name__ == "__main__":
    main()
