"""Historico longo (yfinance, entradas 2011-01 a 2021-09) das regras congeladas no MT5.

Ordem do dono (2026-10-08): validar tudo no MT5 primeiro e usar o yfinance so
depois, para periodos longos, conferindo os gaps. As regras abaixo foram
escolhidas no IS/OOS do MT5 (entradas out/2022-set/2025); 2011-2021 nao se
sobrepoe a esse periodo e nenhuma delas foi medida aqui.

GAPS DO YFINANCE (auditoria em 2026-10-08, 187 papeis, 2010-2021):
  * pregoes faltando: mediana 0% (so NATU3 com 16%);
  * linhas com VOLUME ZERO: ~20-35 por papel (feriados inseridos) e trechos
    longos de preco CONGELADO em que o codigo nao negociava (SUZB3 1.942 dias
    -- era SUZB5 ate 2017 --, PCAR3, TEND3, AZEV3...);
  * saltos > +80% num dia em 8 papeis (erro de dado).
  Tratamento: descarta todo dia com volume zero e corta o historico depois do
  ultimo salto > +80%. O filtro de financeiro >= R$100 mi/dia tambem nunca
  deixaria passar um trecho congelado.

DECLARADO ANTES DE RODAR (configuracoes congeladas, stop inicial + ATR):
  todos          sinal-base (recuo a MME9), universo todo        [referencia]
  grandes        + financeiro >= R$100 mi/dia no sinal          [referencia]
  grandes+rs     + razao papel/IBOV acima da MME21 da razao
  grandes+rs+zz3 + ZigZag de 3 ATR semanais com topos e fundos ascendentes
  Carteira R$1.000 (caixa a CDI, R$1,90/ordem, K=3 e K=5, 14x2 e 21x3) no
  periodo inteiro e em 3 janelas que recomecam do zero: 2011-14, 2015-18,
  2019-21; contra BOVA11 comprar e segurar e so CDI.
  Sucesso do ZigZag: grandes+rs+zz3 acima de grandes+rs no periodo inteiro E
  em pelo menos 2 das 3 janelas.
VIES: o universo e o de hoje (sobreviventes); em 12 anos isso pesa mais que
nos 3 anos do MT5. R$100 mi/dia e nominal: em 2011 poucos papeis passam.
"""
from __future__ import annotations

import io
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
import base_mt5 as base  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
from market_data.loader import load_one  # noqa: E402
from semanal_estacionamento_2026_10_08 import carteira, selic_dia  # noqa: E402
from semanal_estrutura_2026_10_08 import zigzag  # noqa: E402
from semanal_linha_de_base_2026_10_08 import CAP0, br, bh  # noqa: E402

FIM = "2021-09-30"
INI_ENTRADA = "2011-01-01"
CONFIGS = ["todos", "grandes", "grandes+rs", "grandes+rs+zz3"]
JANELAS = [("2011-2021", "2011-01-01", FIM), ("2011-14", "2011-01-01", "2014-12-31"),
           ("2015-18", "2015-01-01", "2018-12-31"), ("2019-21", "2019-01-01", FIM)]


def diario_yf(sym: str) -> pd.DataFrame:
    b = load_one(sym)[["open", "high", "low", "close", "adj_close", "volume"]].dropna()
    b = b[(b.close > 0) & (b.volume > 0)].loc[:FIM]
    saltos = b.index[b.adj_close.pct_change() > 0.8]
    if len(saltos):
        b = b.loc[saltos[-1]:]
    f = b.adj_close / b.close
    d = b[["open", "high", "low", "close"]].mul(f, axis=0)
    d["volume"], d["fin"] = b.volume, b.close * b.volume
    return d


def ibov_semanal() -> pd.Series:
    w = setup.semanal(load_one("^BVSP").loc[:FIM])
    return w.close


def medir(tk: str, ib: pd.Series):
    out = []
    with redirect_stdout(io.StringIO()):
        try:
            d = diario_yf(f"{tk}.SA")
        except Exception:
            return tk, out, {}, pd.Series(dtype=float)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        e = setup.ema
        sig0 = setup.sinais(w)
        fin = d.fin.rolling(63, min_periods=40).median().reindex(w.index, method="ffill")
        ibw = ib.reindex(w.index, method="ffill")
        ratio = w.close / ibw
        grande = (fin >= 100e6).to_numpy()
        rs = (ratio > e(ratio, 21)).to_numpy()
        zz = zigzag(w, setup.atr(w, 14), 3).to_numpy()
        mascaras = {"todos": True, "grandes": grande, "grandes+rs": grande & rs, "grandes+rs+zz3": grande & rs & zz}
        for c, m in mascaras.items():
            sig = sig0.copy()
            sig["recuo_media"] = sig0.recuo_media.to_numpy() & m
            for v in ("atr14x2", "atr21x3"):
                for t in setup.simular(d, w, sig, "recuo_media", v):
                    if INI_ENTRADA <= t.entrada_data <= FIM:
                        out.append(t.__dict__ | {"ticker": tk, "cfg": c, "var": v})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def main() -> None:
    ib = ibov_semanal()
    selic = selic_dia()
    bova = diario_yf("BOVA11.SA")
    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(medir, tk, ib) for tk, _ in base.universo()]):
            tk, tr, r, c = f.result()
            trades += tr
            if len(c):
                closes[tk] = c
            if r:
                r52[tk] = pd.Series(r)
    pct = pd.DataFrame(r52).rank(axis=1, pct=True)
    for t in trades:
        s = t["semana_sinal"]
        v = pct.at[s, t["ticker"]] if s in pct.index else np.nan
        t["pct12m"] = None if pd.isna(v) else float(v)
    T = pd.DataFrame(trades)
    T["ano"] = T.entrada_data.str[:4]
    cl = pd.DataFrame(closes).sort_index().ffill()

    print("== yfinance, entradas 2011-01 a 2021-09 — papéis grandes com sinal por ano:", flush=True)
    G = T[(T.cfg == "grandes") & (T["var"] == "atr21x3")]
    print("  " + "  ".join(f"{a}:{h.ticker.nunique()}" for a, h in G.groupby("ano")), flush=True)

    print("\nPOR OPERAÇÃO (14×2 e 21×3 juntas)", flush=True)
    for c in CONFIGS:
        g = T[T.cfg == c]
        anos = " ".join(f"{a[2:]}:{br(h.ret.mean(), 0)}" for a, h in g.groupby("ano"))
        print(f"  {c:15s} n={len(g):5d} por op. {br(g.ret.mean()):>7s} ±{br(1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)), sinal=False):6s}"
              f" acerto {br((g.ret > 0).mean(), 1, sinal=False)} | {anos}", flush=True)

    for nome, ini, fim in JANELAS:
        b = bh(bova["close"], ini, fim)
        cdi = CAP0 * float(np.prod(1 + selic.loc[ini:fim]))
        print(f"\nCARTEIRA R$1.000 {nome} — BOVA11 R${br(b['final'], 0, pct=False, sinal=False)} (dd {br(b['dd'], 0)}) · "
              f"só CDI R${br(cdi, 0, pct=False, sinal=False)}", flush=True)
        for c in CONFIGS[1:]:
            cel, finais = [], []
            for v in ("atr14x2", "atr21x3"):
                tv = [t for t in trades if t["cfg"] == c and t["var"] == v and ini <= t["entrada_data"] <= fim]
                for K in (3, 5):
                    r = carteira(tv, cl, K, ini, fim, "cdi", selic=selic)
                    finais.append(r["final"])
                    cel.append(f"{v[3:]} K{K} R${br(r['final'], 0, pct=False, sinal=False):>6s} dd{br(r['dd'], 0):>5s} n={r['n']:3d}")
            print(f"  {c:15s} média R${br(np.mean(finais), 0, pct=False, sinal=False):>6s} | " + " | ".join(cel), flush=True)


if __name__ == "__main__":
    main()
