"""Estrategia semanal so nas empresas grandes (financeiro >= R$100 mi/dia).

Decisao do dono (2026-10-08): a estrategia nao pode depender de small caps; o
foco passa a ser as maiores (pode haver uma vertente de small depois), e o
refinamento parte daqui. Corte escolhido por ele: R$100 milhoes por dia
(~32 dos 187 papeis no periodo de pesquisa).

O corte e medido NO SINAL: mediana do financeiro diario dos 63 pregoes
anteriores. Um papel que era grande em 2023 conta em 2023, mesmo que tenha
encolhido depois -- e o que se veria na hora de operar.

Linha de base das grandes, IS e OOS (VALIDACAO nao e tocada):
  por operacao (14x2 e 21x3, com stop), ano a ano, e carteira de R$1.000
  (K=3 e K=5, caixa a 0% e a CDI) contra BOVA11 e so CDI.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
from semanal_estacionamento_2026_10_08 import carteira, selic_dia  # noqa: E402
from semanal_linha_de_base_2026_10_08 import CAP0, br, bh  # noqa: E402
from semanal_small_caps_2026_10_08 import estado_indices, linha, medir  # noqa: E402

CORTE = "fin>=100"


def main() -> None:
    idx = estado_indices()
    bova = pd.read_parquet(base.PASTA / "BOVA11.parquet")[["open", "close"]].loc[: base.PESQUISA[1]]
    selic = selic_dia()
    for conjunto in ("is", "oos"):
        ini, fim = base.janela(conjunto)
        tks = base.papeis(conjunto)
        trades, r52, closes = [], {}, {}
        with ProcessPoolExecutor(max_workers=2) as ex:
            for f in as_completed([ex.submit(medir, tk, conjunto, ["base", CORTE], idx) for tk in tks]):
                tk, tr, r, c = f.result()
                trades += tr; closes[tk] = c
                if r:
                    r52[tk] = pd.Series(r)
        T = pd.DataFrame(trades)
        G = T[T.filtro == CORTE]
        print(f"\n== {conjunto.upper()} — {ini} a {fim}: {G.ticker.nunique()} papéis grandes com sinal "
              f"(de {len(tks)} do conjunto): {' '.join(sorted(G.ticker.unique()))}", flush=True)

        print("POR OPERAÇÃO (com stop inicial)", flush=True)
        for v in ("atr14x2", "atr21x3"):
            print(linha(f"todos  {v}", T[(T.filtro == "base") & (T["var"] == v)]), flush=True)
            print(linha(f"grandes {v}", G[G["var"] == v]), flush=True)

        pct = pd.DataFrame(r52).rank(axis=1, pct=True)
        for t in trades:
            s = t["semana_sinal"]
            v = pct.at[s, t["ticker"]] if s in pct.index else np.nan
            t["pct12m"] = None if pd.isna(v) else float(v)
        cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]
        b = bh(bova["close"], ini, fim)
        cdi = CAP0 * float(np.prod(1 + selic.loc[ini:fim]))
        print(f"CARTEIRA R$1.000 — BOVA11 comprar e segurar R${br(b['final'], 0, pct=False, sinal=False)} "
              f"(MaxDD {br(b['dd'], 1)}) · só CDI R${br(cdi, 0, pct=False, sinal=False)}", flush=True)
        for filtro, nome in (("base", "todos"), (CORTE, "grandes")):
            for v in ("atr14x2", "atr21x3"):
                tv = [t for t in trades if t["filtro"] == filtro and t["var"] == v]
                cel = []
                for ocioso in ("zero", "cdi"):
                    for K in (3, 5):
                        r = carteira(tv, cl, K, ini, fim, ocioso, selic=selic)
                        cel.append(f"{'CDI' if ocioso == 'cdi' else '0% '} K{K} R${br(r['final'], 0, pct=False, sinal=False):>6s} dd{br(r['dd'], 0):>5s} n={r['n']:3d}")
                print(f"  {nome:7s} {v} " + " | ".join(cel), flush=True)


if __name__ == "__main__":
    main()
