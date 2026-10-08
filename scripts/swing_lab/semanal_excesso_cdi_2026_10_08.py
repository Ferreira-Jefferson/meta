"""Enquanto esta posicionada, a estrategia semanal rende mais que o CDI?

Pergunta (2026-10-08): no historico longo o filtro de estrutura (ZigZag 3 ATR)
ganhou da versao sem ele, mas nada bateu o CDI na carteira. Como o filtro deixa
o dinheiro mais tempo fora (rendendo CDI), parte da vantagem pode ser "ficar no
CDI" e nao "escolher melhor". Aqui cada operacao e comparada com o CDI dos
MESMOS dias em que o dinheiro esteve nela:
  excesso = (1 + retorno da operacao) / (1 + CDI do periodo) - 1
  taxa anual posicionada = exp(soma log(1+ret) / soma dias * 365) - 1, contra
  a mesma conta com o CDI desses dias.
CDI = Selic diaria (SGS 11). yfinance: entradas 2011-01 a 2021-09. MT5: IS e
OOS (out/22-set/25). VALIDACAO nao e tocada.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_estrutura_2026_10_08 as estr  # noqa: E402
import semanal_historico_yf_2026_10_08 as hist  # noqa: E402
from semanal_estacionamento_2026_10_08 import selic_dia  # noqa: E402
from semanal_grandes_refino_2026_10_08 import ibov_semanal as ibov_mt5  # noqa: E402
from semanal_linha_de_base_2026_10_08 import br  # noqa: E402


def fator_cdi() -> pd.Series:
    return (1 + selic_dia()).cumprod()


def resumo(nome: str, T: pd.DataFrame, f: pd.Series) -> None:
    fe = f.asof(pd.to_datetime(T.entrada_data)).to_numpy()
    fs = f.asof(pd.to_datetime(T.saida_data)).to_numpy()
    cdi = fs / fe - 1
    exc = (1 + T.ret.to_numpy()) / (1 + cdi) - 1
    dias = np.maximum(T.dias.to_numpy(), 1)
    taxa = np.exp(np.log1p(T.ret.to_numpy()).sum() / dias.sum() * 365) - 1
    taxa_cdi = np.exp(np.log1p(cdi).sum() / dias.sum() * 365) - 1
    print(f"  {nome:22s} n={len(T):5d}  excesso por op. {br(exc.mean()):>7s} ±{br(1.96 * exc.std(ddof=1) / np.sqrt(len(exc)), sinal=False):6s}"
          f"  bateram o CDI {br((exc > 0).mean(), 1, sinal=False):>6s}  |  posicionada {br(taxa, 1)}/ano  CDI dos mesmos dias {br(taxa_cdi, 1)}/ano"
          f"  dias méd {np.median(dias):.0f}", flush=True)


def main() -> None:
    f = fator_cdi()

    print("== yfinance, entradas 2011-01 a 2021-09 (14×2 e 21×3 juntas)", flush=True)
    ib = hist.ibov_semanal()
    tr = []
    with ProcessPoolExecutor(max_workers=2) as ex:
        for fu in as_completed([ex.submit(hist.medir, tk, ib) for tk, _ in base.universo()]):
            tr += fu.result()[1]
    T = pd.DataFrame(tr)
    for c in hist.CONFIGS:
        resumo(c, T[T.cfg == c], f)
    for nome, ini, fim in hist.JANELAS[1:]:
        print(f" {nome}", flush=True)
        for c in ("grandes+rs", "grandes+rs+zz3"):
            g = T[(T.cfg == c) & (T.entrada_data >= ini) & (T.entrada_data <= fim)]
            resumo(c, g, f)

    for conjunto in ("is", "oos"):
        print(f"\n== MT5 {conjunto.upper()} (out/22–set/25)", flush=True)
        ibm = ibov_mt5()
        tr = []
        with ProcessPoolExecutor(max_workers=2) as ex:
            for fu in as_completed([ex.submit(estr.medir, tk, conjunto, ["base", "zz3"], ibm) for tk in base.papeis(conjunto)]):
                tr += fu.result()[1]
        T = pd.DataFrame(tr)
        for (pop, cfg), nome in ((("todos", "base"), "todos"), (("grandes", "base"), "grandes+rs"), (("grandes", "zz3"), "grandes+rs+zz3")):
            resumo(nome, T[(T["pop"] == pop) & (T.cfg == cfg)], f)


if __name__ == "__main__":
    main()
