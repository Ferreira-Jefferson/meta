"""Filtro de mercado para a estrategia semanal: so abre posicao quando o BOVA11 esta em alta.

Hipotese (2026-10-08): a linha de base mostrou o mesmo padrao ano a ano no IS e
no OOS (2023 positivo, 2024 negativo, 2025 forte), com papeis diferentes.
O resultado e do regime do mercado, nao da regra; barrar sinais quando o
indice esta fraco deveria cortar o 2024.

DECLARADO ANTES DE RODAR:
  Candidatos (estado do BOVA11 no FECHAMENTO da semana do sinal, ja conhecido
  na hora de decidir):
    sem      sem filtro (linha de base)
    c>m21    fechamento acima da MME21
    c>m50    fechamento acima da MME50
    m21sobe  MME21 acima dela mesma na semana anterior
    m9>m21   MME9 acima da MME21
    c>m21sb  fechamento acima da MME21 E MME21 subindo
  Criterio: vence a maior expectativa media por operacao nas 4 saidas
  (14x2, 14x2 so ATR, 21x3, 21x3 so ATR) no IS, desde que mantenha pelo menos
  40% das operacoes da linha de base. So o vencedor roda no OOS.

O filtro entra no sinal ANTES da simulacao: um sinal barrado deixa o papel
livre para o proximo sinal, como aconteceria de verdade.

Uso:
  .venv/Scripts/python.exe scripts/swing_lab/semanal_filtro_mercado_2026_10_08.py --conjunto is
  .venv/Scripts/python.exe scripts/swing_lab/semanal_filtro_mercado_2026_10_08.py --conjunto oos --filtros sem c>m21
"""
from __future__ import annotations

import argparse
import io
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
from semanal_linha_de_base_2026_10_08 import VARIANTES, br, bh, carteira, linha_op  # noqa: E402

FILTROS = ["sem", "c>m21", "c>m50", "m21sobe", "m9>m21", "c>m21sb"]


def estado_mercado() -> pd.DataFrame:
    """Uma linha por semana (sexta) com cada filtro True/False, pelo BOVA11."""
    d = pd.read_parquet(base.PASTA / "BOVA11.parquet").loc[: base.PESQUISA[1]]
    w = setup.semanal(d)
    if w.index[-1] > d.index[-1]:
        w = w.iloc[:-1]
    c, m9, m21, m50 = w.close, setup.ema(w.close, 9), setup.ema(w.close, 21), setup.ema(w.close, 50)
    return pd.DataFrame({"sem": True, "c>m21": c > m21, "c>m50": c > m50, "m21sobe": m21 > m21.shift(),
                         "m9>m21": m9 > m21, "c>m21sb": (c > m21) & (m21 > m21.shift())}, index=w.index)


def medir(tk: str, conjunto: str, filtros: list[str], mercado: pd.DataFrame):
    out = []
    with redirect_stdout(io.StringIO()):
        d = base.carregar(tk, conjunto)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        sig0 = setup.sinais(w)
        ini, fim = base.janela(conjunto)
        for f in filtros:
            sig = sig0.copy()
            sig["recuo_media"] &= mercado[f].reindex(w.index).fillna(False).astype(bool)
            for v, si, rot in VARIANTES:
                for t in setup.simular(d, w, sig, "recuo_media", v, stop_inicial=si):
                    if ini <= t.entrada_data <= fim:
                        out.append(t.__dict__ | {"ticker": tk, "rot": rot, "filtro": f})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", choices=["is", "oos"], required=True)
    ap.add_argument("--filtros", nargs="+", default=FILTROS)
    a = ap.parse_args()
    mercado = estado_mercado()
    tks = base.papeis(a.conjunto)
    ini, fim = base.janela(a.conjunto)
    sem_por_ano = mercado.loc[ini:fim]
    print(f"== {a.conjunto.upper()} — {len(tks)} papéis, entradas {ini} a {fim}", flush=True)
    print("semanas liberadas por filtro: " + "  ".join(f"{f} {sem_por_ano[f].mean():.0%}" for f in a.filtros), flush=True)
    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(medir, tk, a.conjunto, a.filtros, mercado) for tk in tks]
        for f in as_completed(futs):
            tk, tr, r, c = f.result()
            trades += tr; closes[tk] = c
            if r:
                r52[tk] = pd.Series(r)
    pct = pd.DataFrame(r52).rank(axis=1, pct=True)
    for t in trades:
        s = t["semana_sinal"]
        v = pct.at[s, t["ticker"]] if s in pct.index else np.nan
        t["pct12m"] = None if pd.isna(v) else float(v)
    T = pd.DataFrame(trades)
    T["ano"] = T.entrada_data.str[:4]
    cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]
    base_n = T[T.filtro == "sem"].groupby("rot").size()

    print("\n1. POR OPERAÇÃO", flush=True)
    placar = {}
    for f in a.filtros:
        g = T[T.filtro == f]
        print(f" [{f}]", flush=True)
        for _, _, rot in VARIANTES:
            print(linha_op(rot, g[g.rot == rot]), flush=True)
        exp = np.mean([g[g.rot == rot].ret.mean() for _, _, rot in VARIANTES])
        frac = np.mean([len(g[g.rot == rot]) / base_n[rot] for _, _, rot in VARIANTES]) if "sem" in a.filtros else 1.0
        placar[f] = (exp, frac)

    print("\n2. ANO A ANO (por operação, com stop inicial)", flush=True)
    for f in a.filtros:
        for rot in ("14×2", "21×3"):
            g = T[(T.filtro == f) & (T.rot == rot)]
            print(f"  {f:8s} {rot:5s} " + "  |  ".join(f"{y}: {br(h.ret.mean())} (n={len(h)})" for y, h in g.groupby("ano")), flush=True)

    print("\n3. CARTEIRA R$1.000 (R$1,90/ordem + 0,21%/perna)", flush=True)
    b = bh(pd.read_parquet(base.PASTA / "BOVA11.parquet")["close"], ini, fim)
    print(f"  BOVA11 comprar e segurar R${br(b['final'], 0, pct=False, sinal=False)}  MaxDD {br(b['dd'], 1)}", flush=True)
    for f in a.filtros:
        for _, _, rot in VARIANTES:
            tv = [t for t in trades if t["rot"] == rot and t["filtro"] == f]
            cel = []
            for K in (1, 3, 5):
                r = carteira(tv, cl, K, ini, fim, False)
                cel.append(f"K{K} R${br(r['final'], 0, pct=False, sinal=False):>6s} dd{br(r['dd'], 0):>5s} n={r['n']:3d}")
            print(f"  {f:8s} {rot:12s} " + " | ".join(cel), flush=True)

    print("\n4. PLACAR (critério declarado: maior média por operação nas 4 saídas, mantendo >= 40% das operações)", flush=True)
    for f, (exp, frac) in sorted(placar.items(), key=lambda x: -x[1][0]):
        print(f"  {f:8s} média por op. {br(exp)}  operações mantidas {frac:.0%}{'' if frac >= .4 else '  (abaixo de 40%: fora)'}", flush=True)


if __name__ == "__main__":
    main()
