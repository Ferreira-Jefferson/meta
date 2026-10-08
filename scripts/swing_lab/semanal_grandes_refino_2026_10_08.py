"""Refino da estrategia semanal nas GRANDES (financeiro >= R$100 mi/dia no sinal).

Pedido do dono (2026-10-08): testar, a partir da linha de base das grandes,
(1) regime do Ibovespa, (2) inclinacao das medias, (3) forca do papel contra
o Ibovespa, e (4) outros tamanhos de media: 34, 100, 200, 300.

MEDIAS 100/200/300 NO DIARIO. A base do MT5 tem ~260 semanas (desde
out/2021); uma media de 200 ou 300 SEMANAS nunca se formaria. No diario elas
cabem (100/200/300 pregoes ~ 5/10/15 meses) e e assim que se usam: filtro de
tendencia longa. A MME300 diaria ainda carrega o valor inicial nos primeiros
meses de 2022-23 (peso ~19% em out/2022). A 34 entra no trio semanal.

DECLARADO ANTES DE RODAR (16 configuracoes, todas nas grandes, stop inicial):
  base       sinal atual (MMEs semanais 9/21/50)
  ibov>m21 / ibov>m50 / ibov9>21     regime do IBOV semanal
  E9q75      MME9 com inclinacao >= q75 (limiar congelado de inclinacao_limiares_is.json)
  S50vira    sai quando a MME50 vira para baixo, no lugar da linha ATR
  E9q75+S50  os dois
  rs>m21     razao papel/IBOV acima da MME21 da razao
  rs26 / rs52  retorno do papel em 26 / 52 semanas acima do retorno do IBOV
  d>m100 / d>m200 / d>m300   fechamento acima da MME diaria de 100/200/300
  d>m200sb   acima da MME200 diaria e ela subindo (contra 5 pregoes atras)
  trio9-21-34 / trio9-34-50  sinal com outro trio semanal
  Placar: media do capital final da carteira de R$1.000 (caixa a CDI, R$1,90/
  ordem) nas saidas 14x2 e 21x3 com K=3 e K=5 (S50vira: uma saida so).
  As 3 melhores do IS (fora a base) rodam no OOS automaticamente.
"""
from __future__ import annotations

import io
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
from semanal_estacionamento_2026_10_08 import carteira, selic_dia  # noqa: E402
from semanal_linha_de_base_2026_10_08 import CAP0, br, bh  # noqa: E402

LIM = json.loads(Path(__file__).with_name("inclinacao_limiares_is.json").read_text(encoding="utf-8"))
CORTE_FIN = 100e6
CONFIGS = ["base", "ibov>m21", "ibov>m50", "ibov9>21", "E9q75", "S50vira", "E9q75+S50", "rs>m21", "rs26", "rs52",
           "d>m100", "d>m200", "d>m300", "d>m200sb", "trio9-21-34", "trio9-34-50"]


def ibov_semanal() -> pd.Series:
    d = pd.read_parquet(base.PASTA / "IBOV.parquet").loc[: base.PESQUISA[1]]
    w = setup.semanal(d)
    return (w.iloc[:-1] if w.index[-1] > d.index[-1] else w)["close"]


def sinal(w: pd.DataFrame, trio: tuple[int, int, int]) -> pd.Series:
    """Mesma regra de `setup.sinais`, com o trio de medias como parametro."""
    a, b, c = (setup.ema(w.close, n) for n in trio)
    sobe = (a > a.shift()) & (b > b.shift()) & (c > c.shift())
    perto = (w.low <= a * (1 + setup.TOL_RECUO)) & (w.close > c)
    return sobe & perto & pd.Series(np.arange(len(w)) >= max(trio), index=w.index)


def medir(tk: str, conjunto: str, configs: list[str], ib: pd.Series):
    out = []
    with redirect_stdout(io.StringIO()):
        d = base.carregar(tk, conjunto)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        sig0 = setup.sinais(w)
        fin = (d.close * d.volume).rolling(63, min_periods=40).median().reindex(w.index, method="ffill")
        grande = (fin >= CORTE_FIN).to_numpy()
        ibw = ib.reindex(w.index, method="ffill")
        e = setup.ema
        inc9 = e(w.close, 9) / e(w.close, 9).shift() - 1
        inc50 = e(w.close, 50) / e(w.close, 50).shift() - 1
        ratio = w.close / ibw

        def diario(n, subindo=False):
            m = e(d.close, n)
            ok = d.close > m
            if subindo:
                ok &= m > m.shift(5)
            return ok.reindex(w.index, method="ffill").fillna(False)

        filtros = {
            "base": True, "S50vira": True,
            "ibov>m21": ibw > e(ibw, 21), "ibov>m50": ibw > e(ibw, 50), "ibov9>21": e(ibw, 9) > e(ibw, 21),
            "E9q75": inc9 >= LIM["9"]["q75"], "E9q75+S50": inc9 >= LIM["9"]["q75"],
            "rs>m21": ratio > e(ratio, 21),
            "rs26": w.close.pct_change(26) > ibw.pct_change(26), "rs52": w.close.pct_change(52) > ibw.pct_change(52),
            "d>m100": diario(100), "d>m200": diario(200), "d>m300": diario(300), "d>m200sb": diario(200, True),
        }
        ini, fim = base.janela(conjunto)
        for c in configs:
            if c.startswith("trio"):
                s = sinal(w, tuple(int(x) for x in c[4:].split("-")))
            else:
                f = filtros[c]
                s = sig0.recuo_media & (f if isinstance(f, bool) else pd.Series(f, index=w.index).fillna(False).astype(bool))
            sig = sig0.copy()
            sig["recuo_media"] = s.to_numpy() & grande
            if c in ("S50vira", "E9q75+S50"):
                runs = [("S50", dict(usar_atr=False, sair_semana=(inc50 < 0).to_numpy()), "atr21x3")]
            else:
                runs = [(v, {}, v) for v in ("atr14x2", "atr21x3")]
            for nome_v, kw, v in runs:
                for t in setup.simular(d, w, sig, "recuo_media", v, **kw):
                    if ini <= t.entrada_data <= fim:
                        out.append(t.__dict__ | {"ticker": tk, "cfg": c, "var": nome_v})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def rodar(conjunto: str, configs: list[str]) -> list[dict]:
    ib = ibov_semanal()
    selic = selic_dia()
    ini, fim = base.janela(conjunto)
    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(medir, tk, conjunto, configs, ib) for tk in base.papeis(conjunto)]):
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
    cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]
    linhas = []
    for c in configs:
        g = T[T.cfg == c]
        cart = []
        for v in g["var"].unique():
            tv = [t for t in trades if t["cfg"] == c and t["var"] == v]
            for K in (3, 5):
                cart.append(carteira(tv, cl, K, ini, fim, "cdi", selic=selic) | {"rot": f"{v} K{K}"})
        anos = " ".join(f"{a[2:]}:{br(h.ret.mean(), 1)}({len(h)})" for a, h in g.groupby(g.entrada_data.str[:4]))
        linhas.append(dict(cfg=c, score=np.mean([x["final"] for x in cart]), dd=np.mean([x["dd"] for x in cart]),
                           n=len(g) / g["var"].nunique(), exp=g.ret.mean(), ic=1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)),
                           cel=" | ".join(f"{x['rot']} R${br(x['final'], 0, pct=False, sinal=False)} dd{br(x['dd'], 0)}" for x in cart),
                           anos=anos))
    return linhas


def imprimir(titulo: str, linhas: list[dict], conjunto: str) -> None:
    ini, fim = base.janela(conjunto)
    b = bh(pd.read_parquet(base.PASTA / "BOVA11.parquet")["close"].loc[: base.PESQUISA[1]], ini, fim)
    cdi = CAP0 * float(np.prod(1 + selic_dia().loc[ini:fim]))
    print(f"\n{titulo} — BOVA11 comprar e segurar R${br(b['final'], 0, pct=False, sinal=False)} (dd {br(b['dd'], 0)}) · "
          f"só CDI R${br(cdi, 0, pct=False, sinal=False)}", flush=True)
    for r in sorted(linhas, key=lambda x: -x["score"]):
        print(f"  {r['cfg']:12s} carteira média R${br(r['score'], 0, pct=False, sinal=False):>6s} dd méd {br(r['dd'], 0):>5s}"
              f"  por op. {br(r['exp']):>7s} ±{br(r['ic'], sinal=False):6s} n={r['n']:4.0f}  | {r['anos']}", flush=True)
        print(f"  {'':12s} {r['cel']}", flush=True)


def main() -> None:
    li = rodar("is", CONFIGS)
    imprimir("IS — 16 configurações nas grandes", li, "is")
    top = [r["cfg"] for r in sorted(li, key=lambda x: -x["score"]) if r["cfg"] != "base"][:3]
    print(f"\n  3 melhores do IS (vão para o OOS): {top}", flush=True)
    lo = rodar("oos", ["base"] + top)
    imprimir("OOS — base + 3 melhores do IS", lo, "oos")


if __name__ == "__main__":
    main()
