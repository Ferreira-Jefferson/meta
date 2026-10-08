"""Quanto do resultado da carteira e sorte da selecao? (regua pura: caixa a 0%)

Contexto (2026-10-08): na v3 a carteira de R$1.000 executa so 27-56% dos
sinais; o resto fica sem vaga. Antes de confiar em diferencas entre versoes
medidas pela carteira, e preciso saber o tamanho do ruido da selecao.

Dois sorteios, 100 repeticoes cada, para v2, v3 e v3+ZigZag (a antiga v4):
  (a) ordem SORTEADA entre sinais do mesmo dia (em vez do ranking de 12m);
  (b) cada sinal DESCARTADO ao acaso com 20% de chance (mede o quanto o
      resultado depende de quais operacoes cairam na carteira).
Celula: saida 21x3 com K=3 e 14x2 com K=5 (as duas pontas da media usada).
Mostra p5 / mediana / p95 do capital final e, sorteio a sorteio, em quantos a
v3 termina acima da v2 e a v4 acima da v3 (sorteios independentes).
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
from semanal_estacionamento_2026_10_08 import carteira  # noqa: E402
from semanal_grandes_refino_2026_10_08 import ibov_semanal as ibov_mt5  # noqa: E402
from semanal_linha_de_base_2026_10_08 import br  # noqa: E402

N = 100
CFGS = ["v2", "v3", "v4"]
CELULAS = [("atr21x3", 3), ("atr14x2", 5)]
_G: dict = {}


def _init(trades, cl, ini, fim):
    _G.update(trades=trades, cl=cl, ini=ini, fim=fim)


def _rodada(cfg: str, v: str, K: int, modo: str, i: int) -> tuple:
    tv = [t for t in _G["trades"] if t["cfg"] == cfg and t["var"] == v]
    if modo == "ordem":
        r = carteira(tv, _G["cl"], K, _G["ini"], _G["fim"], "zero", semente=i)
    else:
        rng = np.random.default_rng(10_000 + i)
        tv = [t for t in tv if rng.random() >= 0.2]
        r = carteira(tv, _G["cl"], K, _G["ini"], _G["fim"], "zero")
    return cfg, v, K, modo, i, r["final"]


def main() -> None:
    for nome, fonte, conj in vp.FONTES:
        if fonte == "mt5":
            ib, tks = ibov_mt5(), base.papeis(conj)
            ini, fim = base.janela(conj)
        else:
            ib, tks = hist.ibov_semanal(), [t for t, _ in base.universo()]
            ini, fim = hist.INI_ENTRADA, hist.FIM
        trades, r52, closes = [], {}, {}
        with ProcessPoolExecutor(max_workers=2) as ex:
            for f in as_completed([ex.submit(vp.medir, tk, fonte, conj, ib) for tk in tks]):
                tk, tr, r, c = f.result()
                trades += [t for t in tr if t["cfg"] in CFGS]
                if len(c):
                    closes[tk] = c
                if r:
                    r52[tk] = pd.Series(r)
        pct = pd.DataFrame(r52).rank(axis=1, pct=True)
        for t in trades:
            s = t["semana_sinal"]
            v = pct.at[s, t["ticker"]] if s in pct.index else np.nan
            t["pct12m"] = None if pd.isna(v) else float(v)
        cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]
        base_res = {(c, v, K): carteira([t for t in trades if t["cfg"] == c and t["var"] == v], cl, K, ini, fim, "zero")["final"]
                    for c in CFGS for v, K in CELULAS}
        res: dict = {}
        with ProcessPoolExecutor(max_workers=2, initializer=_init, initargs=(trades, cl, ini, fim)) as ex:
            futs = [ex.submit(_rodada, c, v, K, modo, i) for c in CFGS for v, K in CELULAS for modo in ("ordem", "descarte") for i in range(N)]
            for f in as_completed(futs):
                c, v, K, modo, i, final = f.result()
                res.setdefault((c, v, K, modo), {})[i] = final
        print(f"\n== {nome} (caixa a 0%, {N} sorteios)", flush=True)
        for v, K in CELULAS:
            print(f"  {v} K{K}", flush=True)
            for c in CFGS:
                linha = f"    {c}  ranking 12m R${br(base_res[(c, v, K)], 0, pct=False, sinal=False):>6s}"
                for modo, rot in (("ordem", "(a) ordem sorteada"), ("descarte", "(b) 20% descartados")):
                    x = np.array([res[(c, v, K, modo)][i] for i in range(N)])
                    p5, p50, p95 = np.percentile(x, [5, 50, 95])
                    linha += f" | {rot}: {br(p5, 0, pct=False, sinal=False)} / {br(p50, 0, pct=False, sinal=False)} / {br(p95, 0, pct=False, sinal=False)}"
                print(linha, flush=True)
            for a, b in (("v3", "v2"), ("v4", "v3")):
                frac = {m: np.mean([res[(a, v, K, m)][i] > res[(b, v, K, m)][i] for i in range(N)]) for m in ("ordem", "descarte")}
                print(f"    {a} acima da {b} em: (a) {frac['ordem']:.0%} dos sorteios · (b) {frac['descarte']:.0%}", flush=True)


if __name__ == "__main__":
    main()
