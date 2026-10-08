"""Candidatas de saida sobre a v4 da estrategia semanal, nas tres fontes.

v4 (ver VERSOES_SEMANAL.md): recuo a MME9 com as MMEs semanais 9/21/50
subindo + grandes (financeiro >= R$100 mi/dia no sinal) + razao papel/IBOV
acima da MME21 + ZigZag de 3 ATR com topos e fundos ascendentes; stop inicial
+ linha ATR (14x2 e 21x3).

DECLARADO ANTES DE RODAR:
  v4           como esta
  v4+empate1R  depois de a maxima andar 1 risco a favor, o stop sobe para a entrada
  v4+prazo8    se no fechamento da 8a semana o papel nao esta acima da entrada, sai
  Fontes: MT5 IS, MT5 OOS (out/22-set/25) e yfinance (entradas 2011-01 a 2021-09).
  Nivel 1 (fica?): carteira melhor que a v4 em >= 2 das 3 fontes, sem queda
  maxima pior em nenhuma (tolerancia de 1 ponto).
  Nivel 2: carteira contra CDI e BOVA11; taxa anual posicionada contra o CDI
  dos mesmos dias.
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
import semanal_historico_yf_2026_10_08 as hist  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
from semanal_estacionamento_2026_10_08 import carteira, selic_dia  # noqa: E402
from semanal_estrutura_2026_10_08 import zigzag  # noqa: E402
from semanal_grandes_refino_2026_10_08 import ibov_semanal as ibov_mt5  # noqa: E402
from semanal_linha_de_base_2026_10_08 import CAP0, br, bh  # noqa: E402

# "v4+ordem" (pedido do dono, 2026-10-08, depois de ver que a carteira pula metade dos
# sinais da v4): exige MME9 > MME21 > MME50 semanais na semana do sinal.
CANDIDATAS = {"v4": {}, "v4+empate1R": dict(breakeven_r=1.0), "v4+prazo8": dict(prazo_semanas=8),
              "v4+ordem": dict(_ordem=(9, 21, 50))}
# As 6 ordens possiveis das tres MMEs na semana do sinal (pedido do dono: "teste se alguma ordem melhora")
for _o in ((9, 21, 50), (9, 50, 21), (21, 9, 50), (21, 50, 9), (50, 9, 21), (50, 21, 9)):
    CANDIDATAS["ordem " + ">".join(map(str, _o))] = dict(_ordem=_o)
FONTES = [("MT5 IS", "mt5", "is"), ("MT5 OOS", "mt5", "oos"), ("yfinance 2011–21", "yf", None)]


def medir(tk: str, fonte: str, conjunto: str | None, ib: pd.Series, cands: list[str] | None = None):
    out = []
    with redirect_stdout(io.StringIO()):
        try:
            if fonte == "mt5":
                d = base.carregar(tk, conjunto)
                fin_d = d.close * d.volume
                ini, fim = base.janela(conjunto)
            else:
                d = hist.diario_yf(f"{tk}.SA")
                fin_d = d.fin
                ini, fim = hist.INI_ENTRADA, hist.FIM
        except Exception:
            return tk, out, {}, pd.Series(dtype=float)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        e = setup.ema
        sig = setup.sinais(w)
        fin = fin_d.rolling(63, min_periods=40).median().reindex(w.index, method="ffill")
        ratio = w.close / ib.reindex(w.index, method="ffill")
        v4 = (fin >= 100e6) & (ratio > e(ratio, 21)) & zigzag(w, setup.atr(w, 14), 3)
        sig["recuo_media"] = sig.recuo_media & v4
        for c in cands or list(CANDIDATAS):
            kw = dict(CANDIDATAS[c])
            s = sig
            ordem = kw.pop("_ordem", None)
            if ordem:
                a, b_, c_ = (sig[f"e{n}"] for n in ordem)
                s = sig.copy()
                s["recuo_media"] = sig.recuo_media & (a > b_) & (b_ > c_)
            for v in ("atr14x2", "atr21x3"):
                for t in setup.simular(d, w, s, "recuo_media", v, **kw):
                    if ini <= t.entrada_data <= fim:
                        out.append(t.__dict__ | {"ticker": tk, "cfg": c, "var": v})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def avaliar(nome: str, fonte: str, conjunto: str | None, cands: list[str]) -> dict:
    selic, fcdi = selic_dia(), (1 + selic_dia()).cumprod()
    if fonte == "mt5":
        ib, tks = ibov_mt5(), base.papeis(conjunto)
        ini, fim = base.janela(conjunto)
        bova = pd.read_parquet(base.PASTA / "BOVA11.parquet")["close"].loc[: base.PESQUISA[1]]
    else:
        ib, tks = hist.ibov_semanal(), [t for t, _ in base.universo()]
        ini, fim = hist.INI_ENTRADA, hist.FIM
        bova = hist.diario_yf("BOVA11.SA")["close"]
    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(medir, tk, fonte, conjunto, ib, cands) for tk in tks]):
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
    cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]
    b = bh(bova, ini, fim)
    cdi = CAP0 * float(np.prod(1 + selic.loc[ini:fim]))
    print(f"\n== {nome} — BOVA11 R${br(b['final'], 0, pct=False, sinal=False)} (dd {br(b['dd'], 0)}) · só CDI R${br(cdi, 0, pct=False, sinal=False)}", flush=True)
    res = {}
    for c in cands:
        g = T[T.cfg == c]
        finais, dds, cel = [], [], []
        for v in ("atr14x2", "atr21x3"):
            tv = [t for t in trades if t["cfg"] == c and t["var"] == v]
            for K in (3, 5):
                r = carteira(tv, cl, K, ini, fim, "cdi", selic=selic)
                finais.append(r["final"]); dds.append(r["dd"])
                cel.append(f"{v[3:]} K{K} R${br(r['final'], 0, pct=False, sinal=False)} ({r['n']}/{len(tv)})")
        fe = fcdi.asof(pd.to_datetime(g.entrada_data)).to_numpy()
        fs = fcdi.asof(pd.to_datetime(g.saida_data)).to_numpy()
        dias = np.maximum(g.dias.to_numpy(), 1).sum()
        taxa = np.exp(np.log1p(g.ret.to_numpy()).sum() / dias * 365) - 1
        taxa_cdi = np.exp(np.log1p(fs / fe - 1).sum() / dias * 365) - 1
        res[c] = dict(final=np.mean(finais), dd=np.mean(dds))
        print(f"  {c:12s} carteira R${br(np.mean(finais), 0, pct=False, sinal=False):>6s} dd {br(np.mean(dds), 0):>5s}  n={len(g) / 2:4.0f}"
              f"  posicionada {br(taxa, 1)}/ano × CDI {br(taxa_cdi, 1)}  | {' · '.join(cel)}", flush=True)
    return res


def main() -> None:
    cands = ["v4"] + [c for c in sys.argv[1:] if c in CANDIDATAS] if len(sys.argv) > 1 else list(CANDIDATAS)
    todas = {nome: avaliar(nome, fonte, conj, cands) for nome, fonte, conj in FONTES}
    print("\nNÍVEL 1 — fica se melhorar a carteira em >= 2 de 3 fontes sem piorar a queda máxima (tolerância 1 ponto)", flush=True)
    for c in cands[1:]:
        melhor = [todas[f][c]["final"] > todas[f]["v4"]["final"] for f in todas]
        dd_ok = [todas[f][c]["dd"] >= todas[f]["v4"]["dd"] - 0.01 for f in todas]
        fica = sum(melhor) >= 2 and all(dd_ok)
        margem = sum(todas[f][c]["final"] >= todas[f]["v4"]["final"] + 20 for f in todas) >= 2 and all(dd_ok)
        det = "  ".join(f"{f}: {'melhor' if m else 'pior'}{'' if d else ' (queda pior)'}" for f, m, d in zip(todas, melhor, dd_ok))
        print(f"  {c:16s} sem margem: {'FICA' if fica else 'não fica':8s} com margem R$20: {'FICA' if margem else 'não fica':8s} |  {det}", flush=True)


if __name__ == "__main__":
    main()
