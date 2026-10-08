"""So entrar com topos e fundos claros (sem lateralizacao) -- estrategia semanal.

Observacao do dono (2026-10-08), olhando o print do LOGN3: "este ponto de
entrada eu jamais entraria: apesar da alta anterior, o preco esta lateralizado;
eu so entraria em mercados que vem marcando topos e fundos claros, deixando a
tendencia visivel". A regra atual so olha medias subindo + recuo a MME9.

DECLARADO ANTES DE RODAR -- base = grandes (financeiro >= R$100 mi/dia no
sinal) + rs>m21 (razao papel/IBOV acima da MME21), stop inicial + ATR:
  base         como esta
  estrut2      os 2 ultimos TOPOS semanais confirmados sao ascendentes E os 2
               ultimos FUNDOS tambem. Topo = maxima maior que as 2 semanas de
               cada lado, so CONFIRMADO 2 semanas depois (sem olhar o futuro);
               fundo, o espelho com a minima
  estrut3      o mesmo com 3 semanas de cada lado (pernas maiores)
  adx>20       ADX(14) semanal acima de 20 (Wilder)
  adx>25       idem, 25
  semlateral   amplitude das 6 semanas antes do sinal >= 2,5 x ATR(14) semanal
  estrut2+adx20  as duas
  Placar: media do capital final da carteira de R$1.000 (caixa a CDI, R$1,90/
  ordem), saidas 14x2 e 21x3, K=3 e K=5. As 3 melhores do IS (fora a base)
  rodam no OOS. Tambem imprime, so como direcao, a regra no UNIVERSO TODO
  (sem os filtros de grandes e forca), por operacao.
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
from semanal_linha_de_base_2026_10_08 import br  # noqa: E402

CONFIGS = ["base", "estrut2", "estrut3", "adx>20", "adx>25", "semlateral", "estrut2+adx20"]


def estrutura(w: pd.DataFrame, k: int) -> pd.Series:
    """True na semana t se, com os pivos ja CONFIRMADOS ate t, os dois ultimos
    topos e os dois ultimos fundos sao ascendentes."""
    H, L = w.high.to_numpy(), w.low.to_numpy()
    n = len(w)
    topos, fundos, out = [], [], np.zeros(n, bool)
    for t in range(n):
        i = t - k  # candidato a pivo que fica confirmado agora
        if i - k >= 0:
            jan_h, jan_l = H[i - k:i + k + 1], L[i - k:i + k + 1]
            if H[i] == jan_h.max() and (jan_h == H[i]).sum() == 1:
                topos.append(H[i])
            if L[i] == jan_l.min() and (jan_l == L[i]).sum() == 1:
                fundos.append(L[i])
        out[t] = len(topos) >= 2 and len(fundos) >= 2 and topos[-1] > topos[-2] and fundos[-1] > fundos[-2]
    return pd.Series(out, index=w.index)


def zigzag(w: pd.DataFrame, atr: pd.Series, mult: float) -> pd.Series:
    """Rodada 2 (depois de o dono comparar os prints): ele le a estrutura nas
    PERNAS GRANDES e ignora recuos curtos. ZigZag: um topo so conta quando a
    minima recua `mult` x ATR(14) semanal abaixo da maxima extrema (fundo, o
    espelho), e so fica CONFIRMADO nesse momento. True se os 2 ultimos topos e
    os 2 ultimos fundos confirmados sao ascendentes."""
    H, L, A = w.high.to_numpy(), w.low.to_numpy(), atr.to_numpy()
    out = np.zeros(len(w), bool)
    topos, fundos, dirc, ext = [], [], 0, 0
    for t in range(len(w)):
        if np.isnan(A[t]):
            continue
        thr = mult * A[t]
        if dirc == 0:
            dirc, ext = 1, t
        elif dirc == 1:
            if H[t] > H[ext]:
                ext = t
            elif L[t] <= H[ext] - thr:
                topos.append(H[ext]); dirc, ext = -1, t
        else:
            if L[t] < L[ext]:
                ext = t
            elif H[t] >= L[ext] + thr:
                fundos.append(L[ext]); dirc, ext = 1, t
        out[t] = len(topos) >= 2 and len(fundos) >= 2 and topos[-1] > topos[-2] and fundos[-1] > fundos[-2]
    return pd.Series(out, index=w.index)


def adx(w: pd.DataFrame, n: int = 14) -> pd.Series:
    up, dn = w.high.diff(), -w.low.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=w.index)
    ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=w.index)
    tr = setup.atr(w, n)
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / tr
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


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
        sig0 = setup.sinais(w)
        fin = (d.close * d.volume).rolling(63, min_periods=40).median().reindex(w.index, method="ffill")
        ibw = ib.reindex(w.index, method="ffill")
        ratio = w.close / ibw
        grande_rs = ((fin >= CORTE_FIN) & (ratio > e(ratio, 21))).to_numpy()
        ax, at = adx(w), setup.atr(w, 14)
        amp6 = w.high.rolling(6).max().shift() - w.low.rolling(6).min().shift()
        e2 = estrutura(w, 2)
        regra = {"base": True, "estrut2": e2, "estrut3": estrutura(w, 3), "adx>20": ax > 20, "adx>25": ax > 25,
                 "semlateral": amp6 >= 2.5 * at, "estrut2+adx20": e2 & (ax > 20),
                 "zz2": zigzag(w, at, 2), "zz3": zigzag(w, at, 3), "zz4": zigzag(w, at, 4)}
        ini, fim = base.janela(conjunto)
        for c in configs:
            ok = regra[c] if isinstance(regra[c], bool) else regra[c].fillna(False).to_numpy()
            for pop, extra in (("grandes", grande_rs), ("todos", True)):
                sig = sig0.copy()
                sig["recuo_media"] = sig0.recuo_media.to_numpy() & ok & extra
                for v in ("atr14x2", "atr21x3"):
                    for t in setup.simular(d, w, sig, "recuo_media", v):
                        if ini <= t.entrada_data <= fim:
                            out.append(t.__dict__ | {"ticker": tk, "cfg": c, "var": v, "pop": pop})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def rodar(conjunto: str, configs: list[str]) -> list[dict]:
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

    print(f"\n{conjunto.upper()} — UNIVERSO TODO, por operação (só direção; sem filtro de grandes e de força)", flush=True)
    Tt = T[T["pop"] == "todos"]
    n0 = len(Tt[Tt.cfg == "base"])
    for c in configs:
        g = Tt[Tt.cfg == c]
        anos = " ".join(f"{a[2:]}:{br(h.ret.mean(), 1)}" for a, h in g.groupby(g.entrada_data.str[:4]))
        print(f"  {c:14s} n={len(g):5d} ({len(g) / n0:4.0%})  por op. {br(g.ret.mean()):>7s} "
              f"±{br(1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)), sinal=False):6s} acerto {br((g.ret > 0).mean(), 1, sinal=False)}  | {anos}", flush=True)

    linhas = []
    G = [t for t in trades if t["pop"] == "grandes"]
    for c in configs:
        g = T[(T["pop"] == "grandes") & (T.cfg == c)]
        cart = []
        for v in ("atr14x2", "atr21x3"):
            tv = [t for t in G if t["cfg"] == c and t["var"] == v]
            for K in (3, 5):
                cart.append(carteira(tv, cl, K, ini, fim, "cdi", selic=selic) | {"rot": f"{v} K{K}"})
        anos = " ".join(f"{a[2:]}:{br(h.ret.mean(), 1)}({len(h)})" for a, h in g.groupby(g.entrada_data.str[:4]))
        linhas.append(dict(cfg=c, score=np.mean([x["final"] for x in cart]), dd=np.mean([x["dd"] for x in cart]),
                           n=len(g) / 2, exp=g.ret.mean() if len(g) else np.nan,
                           ic=1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan,
                           cel=" | ".join(f"{x['rot']} R${br(x['final'], 0, pct=False, sinal=False)} dd{br(x['dd'], 0)}" for x in cart),
                           anos=anos))
    return linhas


def main() -> None:
    if "--zigzag" in sys.argv:
        # Rodada 2, declarada antes de rodar: zz2/zz3/zz4 contra a base, IS e OOS
        # sem selecao intermediaria. Sucesso = carteira acima da base nos dois.
        zz = ["base", "zz2", "zz3", "zz4"]
        imprimir("IS — ZigZag: GRANDES + força relativa", rodar("is", zz), "is")
        imprimir("OOS — ZigZag: GRANDES + força relativa", rodar("oos", zz), "oos")
        return
    li = rodar("is", CONFIGS)
    imprimir("IS — GRANDES + força relativa: carteira", li, "is")
    top = [r["cfg"] for r in sorted(li, key=lambda x: -x["score"]) if r["cfg"] != "base"][:3]
    print(f"\n  3 melhores do IS (vão para o OOS): {top}", flush=True)
    imprimir("OOS — GRANDES + força relativa: carteira", rodar("oos", ["base"] + top), "oos")


if __name__ == "__main__":
    main()
