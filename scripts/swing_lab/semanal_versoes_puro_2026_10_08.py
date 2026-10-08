"""Versoes da estrategia semanal medidas PURAS: caixa parado a 0%, sem CDI nem IBOV.

Ordem do dono (2026-10-08): "so quero medir a estrategia, nada de CDI ou IBOV".
Com o caixa rendendo CDI, versoes que operavam menos pareciam melhores so por
deixar mais dinheiro parado rendendo (ate candidatas com 1 operacao "passavam").

Versoes (cada uma = a anterior + uma regra; sinal-base = recuo a MME9 com as
MMEs semanais 9/21/50 subindo; stop inicial + linha ATR 14x2 e 21x3):
  v2  grandes: mediana do financeiro dos 63 pregoes >= R$100 mi no sinal
  v3  v2 + forca: razao papel/IBOV semanal acima da MME21 da razao
  v4  v3 + estrutura: ZigZag de 3 ATR semanais, 2 ultimos topos e fundos ascendentes
Candidatas sobre a v4: ordem 9>21>50, ordem 21>9>50, empate depois de 1 risco,
prazo de 8 semanas.
  v6  v5 (v4+prazo8) + volume da semana do sinal abaixo da media de 20 semanas

Fontes: MT5 IS, MT5 OOS (entradas out/22-set/25) e yfinance (2011-01 a 2021-09).

NIVEL 1 (a mudanca fica?) -- regra aprovada pelo dono em 2026-10-08, depois do
teste de sorteio (semanal_sorteio_2026_10_08.py) mostrar que a carteira de
R$1.000 com 3-5 vagas varia de R$777 a R$2.300 so pelo acaso de quais sinais
cabem: a decisao usa TODOS os sinais da regra.
  fica se o resultado medio por operacao E o rendimento anual enquanto
  posicionada (14x2 e 21x3 juntas, caixa nao entra) melhorarem no MT5 IS E no
  MT5 OOS, com >= 10 operacoes em cada um. O yfinance (2011-21) e CONTEXTO
  (dono, 2026-10-08): o mercado mudou muito desde entao, e uma divergencia dele
  pode ser so reflexo disso -- aparece ao lado, nao veta nem decide.
  A carteira de R$1.000 (caixa a 0%) aparece so como checagem de viabilidade.
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
from semanal_estacionamento_2026_10_08 import carteira  # noqa: E402
from semanal_estrutura_2026_10_08 import zigzag  # noqa: E402
from semanal_grandes_refino_2026_10_08 import ibov_semanal as ibov_mt5  # noqa: E402
from semanal_linha_de_base_2026_10_08 import br  # noqa: E402

# nome: (mascaras exigidas, ordem das MMEs ou None, kwargs da simulacao, contra quem compara)
VERSOES = {
    "v2": (("grande",), None, {}, None),
    "v3": (("grande", "forca"), None, {}, "v2"),
    "v4": (("grande", "forca", "estrutura"), None, {}, "v3"),
    "v4+ordem 9>21>50": (("grande", "forca", "estrutura"), (9, 21, 50), {}, "v4"),
    "v4+ordem 21>9>50": (("grande", "forca", "estrutura"), (21, 9, 50), {}, "v4"),
    "v4+empate1R": (("grande", "forca", "estrutura"), None, dict(breakeven_r=1.0), "v4"),
    "v4+prazo8": (("grande", "forca", "estrutura"), None, dict(prazo_semanas=8), "v4"),
    # v6 = v5 (v4+prazo8) + volume da semana do sinal abaixo da media de 20 semanas
    "v6 volume baixo": (("grande", "forca", "estrutura", "volume"), None, dict(prazo_semanas=8), "v4+prazo8"),
}
FONTES = [("MT5 IS", "mt5", "is"), ("MT5 OOS", "mt5", "oos"), ("yfinance 2011–21", "yf", None)]


def medir(tk: str, fonte: str, conjunto: str | None, ib: pd.Series):
    out = []
    with redirect_stdout(io.StringIO()):
        try:
            if fonte == "mt5":
                d = base.carregar(tk, conjunto)
                fin_d, (ini, fim) = d.close * d.volume, base.janela(conjunto)
            else:
                d = hist.diario_yf(f"{tk}.SA")
                fin_d, ini, fim = d.fin, hist.INI_ENTRADA, hist.FIM
        except Exception:
            return tk, out, {}, pd.Series(dtype=float)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        e = setup.ema
        sig0 = setup.sinais(w)
        ratio = w.close / ib.reindex(w.index, method="ffill")
        m = {"grande": fin_d.rolling(63, min_periods=40).median().reindex(w.index, method="ffill") >= 100e6,
             "forca": ratio > e(ratio, 21), "estrutura": zigzag(w, setup.atr(w, 14), 3),
             "volume": w.volume < w.volume.rolling(20, min_periods=15).mean()}
        for nome, (masc, ordem, kw, _) in VERSOES.items():
            ok = sig0.recuo_media.copy()
            for k in masc:
                ok &= m[k]
            if ordem:
                a, b, c = (sig0[f"e{n}"] for n in ordem)
                ok &= (a > b) & (b > c)
            sig = sig0.copy()
            sig["recuo_media"] = ok
            for v in ("atr14x2", "atr21x3"):
                for t in setup.simular(d, w, sig, "recuo_media", v, **kw):
                    if ini <= t.entrada_data <= fim:
                        out.append(t.__dict__ | {"ticker": tk, "cfg": nome, "var": v})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def avaliar(nome_fonte: str, fonte: str, conjunto: str | None) -> dict:
    if fonte == "mt5":
        ib, tks = ibov_mt5(), base.papeis(conjunto)
        ini, fim = base.janela(conjunto)
    else:
        ib, tks = hist.ibov_semanal(), [t for t, _ in base.universo()]
        ini, fim = hist.INI_ENTRADA, hist.FIM
    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(medir, tk, fonte, conjunto, ib) for tk in tks]):
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
    print(f"\n== {nome_fonte} (caixa a 0%)", flush=True)
    res = {}
    for nome in VERSOES:
        g = T[T.cfg == nome]
        finais, dds, exe, disp = [], [], 0, 0
        for v in ("atr14x2", "atr21x3"):
            tv = [t for t in trades if t["cfg"] == nome and t["var"] == v]
            for K in (3, 5):
                r = carteira(tv, cl, K, ini, fim, "zero")
                finais.append(r["final"]); dds.append(r["dd"]); exe += r["n"]; disp += len(tv)
        n = len(g) / 2
        dias = np.maximum(g.dias.to_numpy(), 1).sum() if len(g) else 1
        taxa = np.exp(np.log1p(g.ret.to_numpy()).sum() / dias * 365) - 1 if len(g) else np.nan
        ic = 1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan
        res[nome] = dict(final=np.mean(finais), dd=np.mean(dds), n=n,
                         exp=g.ret.mean() if len(g) else np.nan, taxa=taxa)
        print(f"  {nome:17s} carteira R${br(np.mean(finais), 0, pct=False, sinal=False):>6s}  queda {br(np.mean(dds), 0):>5s}"
              f"  operações {n:4.0f} (carteira executa {exe / max(disp, 1):4.0%})"
              f"  por op. {br(g.ret.mean() if len(g) else np.nan):>7s} ±{br(ic, sinal=False):6s}  posicionada {br(taxa, 1)}/ano", flush=True)
    return res


def main() -> None:
    todas = {nome: avaliar(nome, fonte, conj) for nome, fonte, conj in FONTES}
    print("\nNÍVEL 1 — fica se por operação E posicionada melhorarem no MT5 IS E no MT5 OOS (>= 10 operações em cada); yfinance = contexto", flush=True)
    mt5 = [f for f in todas if f.startswith("MT5")]
    for nome, (_, _, _, ant) in VERSOES.items():
        if not ant:
            continue
        ok = {f: todas[f][nome]["exp"] > todas[f][ant]["exp"] and todas[f][nome]["taxa"] > todas[f][ant]["taxa"] for f in todas}
        fica = all(ok[f] for f in mt5) and all(todas[f][nome]["n"] >= 10 for f in mt5)
        det = "  ".join(f"{f}: n={todas[f][nome]['n']:.0f} op {br(todas[f][ant]['exp'], 2)} -> {br(todas[f][nome]['exp'], 2)}, "
                        f"pos {br(todas[f][ant]['taxa'], 1)} -> {br(todas[f][nome]['taxa'], 1)}{' [melhora]' if ok[f] else ''}" for f in todas)
        print(f"  {nome:17s} x {ant:3s} {'FICA' if fica else 'nao fica':9s} | {det}", flush=True)


if __name__ == "__main__":
    main()
