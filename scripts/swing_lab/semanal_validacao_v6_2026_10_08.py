"""VALIDACAO (conjunto travado) da cadeia de versoes ate a v6.

Autorizado pelo dono em 2026-10-08 ("sim, tudo"), depois de a v6 (volume do
recuo abaixo da media de 20 semanas) passar no nivel 1 por pouco.

CONGELADO ANTES DE OLHAR: as regras v2..v6 exatamente como em
semanal_versoes_puro_2026_10_08.py, todos os 187 papeis, entradas de
2025-10-01 ate o ultimo pregao da base. Operacao aberta no fim entra marcada
no ultimo fechamento. Mesmas metricas da regua (todos os sinais, caixa fora).

Perguntas:
  nivel 1  cada versao melhora a anterior tambem aqui?
  nivel 2  (portao final) a versao atual bate o CDI e o BOVA11 no periodo?
Se a regra for mudada depois de ver isto, este conjunto deixa de validar a
regra nova.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
import semanal_versoes_puro_2026_10_08 as vp  # noqa: E402
from semanal_estacionamento_2026_10_08 import selic_dia  # noqa: E402
from semanal_linha_de_base_2026_10_08 import br  # noqa: E402

AUTORIZACAO = ("dono autorizou na conversa de 2026-10-08 ('sim, tudo'): validar a cadeia v2..v6 "
               "da estrategia semanal (v6 = v5 + volume do recuo abaixo da media de 20 semanas), regua pura")
_carregar = base.carregar


def _ibov_completo() -> pd.Series:
    d = pd.read_parquet(base.PASTA / "IBOV.parquet")
    w = setup.semanal(d)
    return (w.iloc[:-1] if w.index[-1] > d.index[-1] else w)["close"]


# roda tambem nos processos filhos (spawn reimporta este modulo)
base.carregar = lambda tk, conjunto, autorizacao=None: _carregar(tk, conjunto, autorizacao=AUTORIZACAO)
vp.ibov_mt5 = _ibov_completo
vp.VERSOES = {k: vp.VERSOES[k] for k in ("v2", "v3", "v4", "v4+prazo8", "v6 volume baixo")}


def main() -> None:
    res = vp.avaliar("VALIDAÇÃO 2025-10 em diante (todos os papéis)", "mt5", "validacao")
    print("\nNÍVEL 1 — a versão melhora a anterior (por operação E posicionada)?", flush=True)
    for nome, (_, _, _, ant) in vp.VERSOES.items():
        if ant:
            a, b = res[ant], res[nome]
            ok = b["exp"] > a["exp"] and b["taxa"] > a["taxa"]
            print(f"  {nome:16s} x {ant:10s} {'melhora' if ok else 'NAO melhora':12s} n={b['n']:.0f}  "
                  f"op {br(a['exp'], 2)} -> {br(b['exp'], 2)}  pos {br(a['taxa'], 1)} -> {br(b['taxa'], 1)}", flush=True)

    ini, fim = base.VALIDACAO[0], pd.read_parquet(base.PASTA / "IBOV.parquet").index[-1]
    bova = pd.read_parquet(base.PASTA / "BOVA11.parquet").close.loc[ini:fim]
    s = selic_dia().loc[ini:fim]
    anos = (bova.index[-1] - bova.index[0]).days / 365
    cdi = float(np.prod(1 + s) - 1)
    print(f"\nNÍVEL 2 — portão final ({bova.index[0].date()} a {bova.index[-1].date()}, {anos:.2f} anos)", flush=True)
    print(f"  BOVA11 comprar e segurar {br(bova.iloc[-1] / bova.iloc[0] - 1, 1)}  ({br((bova.iloc[-1] / bova.iloc[0]) ** (1 / anos) - 1, 1)}/ano)", flush=True)
    print(f"  CDI (até {s.index[-1].date()})       {br(cdi, 1)}  ({br((1 + cdi) ** (365 / max((s.index[-1] - s.index[0]).days, 1)) - 1, 1)}/ano)", flush=True)
    for nome in vp.VERSOES:
        r = res[nome]
        print(f"  {nome:16s} posicionada {br(r['taxa'], 1)}/ano  carteira R$1.000 (caixa 0%) -> R${br(r['final'], 0, pct=False, sinal=False)}"
              f"  ({br(r['final'] / 1000 - 1, 1)}, queda {br(r['dd'], 0)})", flush=True)


if __name__ == "__main__":
    main()
