"""Small caps e a perda de 2024 na estrategia semanal.

Hipotese (2026-10-08): 2024 e negativo em todas as configuracoes testadas ate
aqui (linha de base, filtro pelo BOVA11, inclinacao das MMEs), no IS e no OOS.
2024 foi o ano em que as small caps desabaram, e o universo e pesado em
consumo ciclico e empresas menores. O regime que importa pode ser o das
small caps, nao o do indice -- ou o problema pode ser do papel pequeno em si.

DECLARADO ANTES DE RODAR:
  Diagnostico (IS, linha de base 14x2 e 21x3 com stop): resultado por ano
  separado (a) pelo estado do SMLL na semana do sinal e (b) pelo financeiro
  do papel (tercis dos 63 pregoes anteriores ao sinal).
  Candidatos (8), aplicados no sinal ANTES da simulacao:
    base       linha de base
    smll>m21   SMLL fechou acima da MME21 semanal
    smll>m50   SMLL fechou acima da MME50 semanal
    smll9>21   MME9 do SMLL acima da MME21
    rs>m21     razao SMLL/IBOV acima da MME21 da razao (small caps ganhando)
    rs9>21     MME9 da razao acima da MME21 da razao
    fin>=20    papel com mediana de financeiro diario >= R$20 mi (63 pregoes)
    fin>=50    idem, >= R$50 mi
  Criterio: maior media por operacao nas saidas 14x2 e 21x3 (com stop
  inicial), mantendo >= 40% das operacoes da base; empate -> mais operacoes.
  So o vencedor roda no OOS (--conjunto oos --filtros base <vencedor>).

Indices (SMLL, IBOV) cortados no fim do periodo de pesquisa: nada da
VALIDACAO entra.
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
from semanal_linha_de_base_2026_10_08 import br, bh, carteira  # noqa: E402

FILTROS = ["base", "smll>m21", "smll>m50", "smll9>21", "rs>m21", "rs9>21", "fin>=20", "fin>=50"]
VARS = ("atr14x2", "atr21x3")


def semanal_indice(tk: str) -> pd.Series:
    d = pd.read_parquet(base.PASTA / f"{tk}.parquet").loc[: base.PESQUISA[1]]
    w = setup.semanal(d)
    return (w.iloc[:-1] if w.index[-1] > d.index[-1] else w)["close"]


def estado_indices() -> pd.DataFrame:
    s, i = semanal_indice("SMLL"), semanal_indice("IBOV")
    rs = (s / i).dropna()
    e = setup.ema
    # smll<m21: hipotese NOVA, saida do diagnostico do IS (sinal com SMLL abaixo da MME21
    # rendeu +7,59% contra -0,20% acima); nao estava entre os candidatos, so o OOS a testa.
    return pd.DataFrame({"base": True, "smll>m21": s > e(s, 21), "smll<m21": s <= e(s, 21),
                         "smll>m50": s > e(s, 50), "smll9>21": e(s, 9) > e(s, 21),
                         "rs>m21": rs > e(rs, 21), "rs9>21": e(rs, 9) > e(rs, 21)})


def medir(tk: str, conjunto: str, filtros: list[str], idx: pd.DataFrame):
    out = []
    with redirect_stdout(io.StringIO()):
        d = base.carregar(tk, conjunto)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        sig0 = setup.sinais(w)
        fin = (d.close * d.volume).rolling(63, min_periods=40).median()
        fin_w = fin.reindex(w.index, method="ffill")
        ini, fim = base.janela(conjunto)
        for f in filtros:
            if f.startswith("fin>="):
                ok = (fin_w >= float(f[5:]) * 1e6).to_numpy()
            else:
                ok = idx[f].reindex(w.index).fillna(False).astype(bool).to_numpy()
            sig = sig0.copy()
            sig["recuo_media"] = sig0.recuo_media & ok
            for v in VARS:
                for t in setup.simular(d, w, sig, "recuo_media", v):
                    if ini <= t.entrada_data <= fim:
                        s = pd.Timestamp(t.semana_sinal)
                        out.append(t.__dict__ | {"ticker": tk, "filtro": f, "var": v, "fin": float(fin_w.get(s, np.nan)),
                                                 "smll_alta": bool(idx["smll>m21"].get(s, False)),
                                                 "rs_alta": bool(idx["rs>m21"].get(s, False))})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def linha(nome: str, g: pd.DataFrame, n_base: float | None = None) -> str:
    r = g.ret
    anos = " ".join(f"{a[2:]}:{br(h.ret.mean(), 1)}({len(h)})" for a, h in g.groupby(g.entrada_data.str[:4]))
    frac = f" ({len(g) / n_base:4.0%})" if n_base else ""
    return (f"  {nome:28s} n={len(g):4d}{frac}  por op.={br(r.mean()):>7s} ±{br(1.96 * r.std(ddof=1) / np.sqrt(len(r)), sinal=False):6s}"
            f"  acerto={br((r > 0).mean(), 1, sinal=False):>6s}  | {anos}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", choices=["is", "oos"], required=True)
    ap.add_argument("--filtros", nargs="+", default=FILTROS)
    a = ap.parse_args()
    idx = estado_indices()
    ini, fim = base.janela(a.conjunto)
    tks = base.papeis(a.conjunto)
    janela_idx = idx.loc[ini:fim]
    print(f"== {a.conjunto.upper()} — {len(tks)} papéis, entradas {ini} a {fim}", flush=True)
    print("  semanas liberadas: " + "  ".join(f"{f} {janela_idx[f].mean():.0%}" for f in a.filtros if f in idx), flush=True)
    for ano, g in janela_idx.groupby(janela_idx.index.year):
        print(f"    {ano}: SMLL acima da MME21 em {g['smll>m21'].mean():.0%} das semanas, small caps ganhando do IBOV em {g['rs>m21'].mean():.0%}", flush=True)

    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(medir, tk, a.conjunto, a.filtros, idx) for tk in tks]):
            tk, tr, r, c = f.result()
            trades += tr; closes[tk] = c
            if r:
                r52[tk] = pd.Series(r)
    T = pd.DataFrame(trades)

    if a.conjunto == "is":
        B = T[T.filtro == "base"].copy()
        print("\nDIAGNÓSTICO — linha de base, 14×2 e 21×3 juntas", flush=True)
        print(" (a) estado das small caps na semana do sinal", flush=True)
        for k, nome in ((True, "SMLL acima da MME21"), (False, "SMLL abaixo da MME21")):
            print(linha(nome, B[B.smll_alta == k]), flush=True)
        for k, nome in ((True, "small caps ganhando do IBOV"), (False, "small caps perdendo do IBOV")):
            print(linha(nome, B[B.rs_alta == k]), flush=True)
        print(" (b) financeiro do papel (tercis, 63 pregões antes do sinal)", flush=True)
        q = B.fin.quantile([1 / 3, 2 / 3]).to_numpy()
        print(f"     cortes: R${q[0] / 1e6:.1f} mi e R${q[1] / 1e6:.1f} mi por dia", flush=True)
        B["terc"] = np.select([B.fin <= q[0], B.fin <= q[1]], ["1 menor", "2 médio"], "3 maior")
        for t, g in B.groupby("terc"):
            print(linha(f"tercil {t}", g), flush=True)

    print("\nCANDIDATOS — por operação (14×2 e 21×3 juntas)", flush=True)
    n_base = len(T[T.filtro == "base"])
    placar = {}
    for f in a.filtros:
        g = T[T.filtro == f]
        print(linha(f, g, n_base), flush=True)
        placar[f] = (np.mean([g[g["var"] == v].ret.mean() for v in VARS]), len(g) / n_base)

    pct = pd.DataFrame(r52).rank(axis=1, pct=True)
    T["pct12m"] = [pct.at[s, t] if s in pct.index else np.nan for s, t in zip(T.semana_sinal, T.ticker)]
    cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]
    b = bh(pd.read_parquet(base.PASTA / "BOVA11.parquet")["close"], ini, fim)
    print(f"\nCARTEIRA R$1.000 (BOVA11 comprar e segurar R${br(b['final'], 0, pct=False, sinal=False)})", flush=True)
    for f in a.filtros:
        for v in VARS:
            tv = [dict(r._asdict()) for r in T[(T.filtro == f) & (T["var"] == v)].itertuples(index=False)]
            for t in tv:
                t["pct12m"] = None if pd.isna(t["pct12m"]) else t["pct12m"]
            cel = []
            for K in (3, 5):
                r = carteira(tv, cl, K, ini, fim, False)
                cel.append(f"K{K} R${br(r['final'], 0, pct=False, sinal=False):>6s} dd{br(r['dd'], 0):>5s} n={r['n']:3d}")
            print(f"  {f:9s} {v:8s} " + " | ".join(cel), flush=True)

    print("\nPLACAR (média por op. nas 2 saídas; precisa manter >= 40% das operações)", flush=True)
    for f, (e, fr) in sorted(placar.items(), key=lambda x: -x[1][0]):
        print(f"  {f:9s} {br(e)}  operações {fr:4.0%}{'' if fr >= .4 else '  (fora)'}", flush=True)


if __name__ == "__main__":
    main()
