"""Saidas que cortem a perda dos anos ruins, nas GRANDES com forca relativa.

Contexto (2026-10-08): nas grandes (financeiro >= R$100 mi/dia no sinal), o
melhor filtro de entrada no OOS foi rs>m21 (razao papel/IBOV acima da MME21
da razao). Nenhum filtro de entrada consertou 2022 e 2024; o dono escolheu
atacar pela SAIDA.

DECLARADO ANTES DE RODAR -- base = grandes + rs>m21 + stop inicial + ATR
(14x2 e 21x3). Cada candidato SOMA uma regra as saidas atuais:
  base       como esta
  stop5      stop inicial no maximo 5% abaixo da entrada
  stop8      idem, 8%
  ibov<m21   sai na abertura seguinte quando o IBOV semanal fecha abaixo da MME21
  ibov9<21   sai quando a MME9 do IBOV fica abaixo da MME21
  rs<m21     sai quando a razao papel/IBOV fecha abaixo da MME21 dela
  empate1R   depois de andar 1 risco a favor, o stop sobe para a entrada
  prazo8     se no fechamento da 8a semana o papel nao esta acima da entrada, sai
  Placar: media do capital final da carteira de R$1.000 (caixa a CDI, R$1,90/
  ordem) nas saidas 14x2 e 21x3 com K=3 e K=5. As 3 melhores do IS (fora a
  base) rodam no OOS automaticamente.
"""
from __future__ import annotations

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
from semanal_estacionamento_2026_10_08 import carteira, selic_dia  # noqa: E402
from semanal_grandes_refino_2026_10_08 import CORTE_FIN, ibov_semanal, imprimir  # noqa: E402

CONFIGS = ["base", "stop5", "stop8", "ibov<m21", "ibov9<21", "rs<m21", "empate1R", "prazo8"]


def medir(tk: str, conjunto: str, configs: list[str], ib: pd.Series):
    out = []
    with redirect_stdout(io.StringIO()):
        d = base.carregar(tk, conjunto)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        e = setup.ema
        sig = setup.sinais(w)
        fin = (d.close * d.volume).rolling(63, min_periods=40).median().reindex(w.index, method="ffill")
        ibw = ib.reindex(w.index, method="ffill")
        ratio = w.close / ibw
        sig["recuo_media"] = sig.recuo_media & (fin >= CORTE_FIN) & (ratio > e(ratio, 21))
        kw = {
            "base": {}, "stop5": dict(stop_max_pct=.05), "stop8": dict(stop_max_pct=.08),
            "ibov<m21": dict(sair_semana=(ibw < e(ibw, 21)).to_numpy(), motivo_semana="ibov"),
            "ibov9<21": dict(sair_semana=(e(ibw, 9) < e(ibw, 21)).to_numpy(), motivo_semana="ibov"),
            "rs<m21": dict(sair_semana=(ratio < e(ratio, 21)).to_numpy(), motivo_semana="forca"),
            "empate1R": dict(breakeven_r=1.0), "prazo8": dict(prazo_semanas=8),
        }
        ini, fim = base.janela(conjunto)
        for c in configs:
            for v in ("atr14x2", "atr21x3"):
                for t in setup.simular(d, w, sig, "recuo_media", v, **kw[c]):
                    if ini <= t.entrada_data <= fim:
                        out.append(t.__dict__ | {"ticker": tk, "cfg": c, "var": v})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def rodar(conjunto: str, configs: list[str]) -> list[dict]:
    from semanal_linha_de_base_2026_10_08 import br
    ib, selic = ibov_semanal(), selic_dia()
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
        for v in ("atr14x2", "atr21x3"):
            tv = [t for t in trades if t["cfg"] == c and t["var"] == v]
            for K in (3, 5):
                cart.append(carteira(tv, cl, K, ini, fim, "cdi", selic=selic) | {"rot": f"{v} K{K}"})
        anos = " ".join(f"{a[2:]}:{br(h.ret.mean(), 1)}({len(h)})" for a, h in g.groupby(g.entrada_data.str[:4]))
        motivos = " ".join(f"{m}:{n}" for m, n in g.motivo.value_counts().items())
        linhas.append(dict(cfg=c, score=np.mean([x["final"] for x in cart]), dd=np.mean([x["dd"] for x in cart]),
                           n=len(g) / 2, exp=g.ret.mean(), ic=1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)),
                           cel=" | ".join(f"{x['rot']} R${br(x['final'], 0, pct=False, sinal=False)} dd{br(x['dd'], 0)}" for x in cart)
                           + f"   saídas: {motivos}",
                           anos=anos))
    return linhas


def main() -> None:
    li = rodar("is", CONFIGS)
    imprimir("IS — saídas nas grandes + força relativa", li, "is")
    top = [r["cfg"] for r in sorted(li, key=lambda x: -x["score"]) if r["cfg"] != "base"][:3]
    print(f"\n  3 melhores do IS (vão para o OOS): {top}", flush=True)
    imprimir("OOS — base + 3 melhores do IS", rodar("oos", ["base"] + top), "oos")


if __name__ == "__main__":
    main()
