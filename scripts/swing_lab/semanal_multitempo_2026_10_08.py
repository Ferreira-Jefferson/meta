"""Confirmacao em outros tempos graficos sobre a v5 (regua pura de nivel 1).

Pedido do dono (2026-10-08): "olhar confirmacoes em outros tempos graficos".

O sinal continua semanal (v5). Cada candidata exige UMA confirmacao a mais,
lida sem olhar o futuro:
  MENSAL (ultimo mes JA FECHADO no fim da semana do sinal)
    m_acima9   fechamento mensal acima da MME9 mensal
    m_sobe9    MME9 mensal subindo
    m_6m       fechamento mensal acima do de 6 meses antes
    m_candle   ultimo mes fechado positivo (fechamento > abertura)
  DIARIO (no fechamento do ultimo pregao da semana do sinal)
    d_9>21     MME9 diaria acima da MME21 diaria
    d_acima21  fechamento diario acima da MME21 diaria
    d_sobe21   MME21 diaria subindo (contra 5 pregoes antes)
    d_acima200 fechamento diario acima da MME200 diaria

Lista fechada ANTES de rodar: 8 candidatas. Com 8, uma passar por acaso e
plausivel; por isso a regra e a mesma de sempre (melhora por operacao E
posicionada no MT5 IS E no MT5 OOS, >= 10 operacoes em cada; yf = contexto).

Limite do MT5: o historico comeca em out/21, entao no inicio do IS (out/22)
ha so ~12 meses para as medias mensais. Por isso nada de MME21 mensal nem
momento de 12 meses; a MME9 mensal ainda aquece pouco no inicio do IS.
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
import semanal_versoes_puro_2026_10_08 as vp  # noqa: E402
from semanal_estrutura_2026_10_08 import zigzag  # noqa: E402
from semanal_grandes_refino_2026_10_08 import ibov_semanal as ibov_mt5  # noqa: E402
from semanal_linha_de_base_2026_10_08 import br  # noqa: E402

CANDIDATAS = ["m_acima9", "m_sobe9", "m_6m", "m_candle", "d_9>21", "d_acima21", "d_sobe21", "d_acima200"]
CFGS = ["v5"] + [f"v5+{c}" for c in CANDIDATAS]
MIN_N = 10


def confirmacoes(d: pd.DataFrame, w: pd.DataFrame) -> dict[str, pd.Series]:
    e = setup.ema
    m = d.resample("ME").agg({"open": "first", "close": "last"}).dropna()
    m = m[m.index <= d.index[-1]]  # mes corrente incompleto fica de fora
    e9m = e(m.close, 9)
    mens = {"m_acima9": m.close > e9m, "m_sobe9": e9m > e9m.shift(),
            "m_6m": m.close > m.close.shift(6), "m_candle": m.close > m.open}
    c = d.close
    e9d, e21d, e200d = e(c, 9), e(c, 21), e(c, 200)
    diar = {"d_9>21": e9d > e21d, "d_acima21": c > e21d, "d_sobe21": e21d > e21d.shift(5),
            "d_acima200": (c > e200d) & (np.arange(len(c)) >= 200)}
    out = {}
    for k, s in mens.items():  # rotulo = fim do mes; so vale depois que o mes fechou
        out[k] = s.reindex(w.index, method="ffill").fillna(False).astype(bool)
    for k, s in diar.items():
        out[k] = pd.Series(s, index=c.index).reindex(w.index, method="ffill").fillna(False).astype(bool)
    return out


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
            return out
        if len(d) < 300:
            return out
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        sig0 = setup.sinais(w)
        ratio = w.close / ib.reindex(w.index, method="ffill")
        v5 = (sig0.recuo_media
              & (fin_d.rolling(63, min_periods=40).median().reindex(w.index, method="ffill") >= 100e6)
              & (ratio > setup.ema(ratio, 21)) & zigzag(w, setup.atr(w, 14), 3))
        conf = confirmacoes(d, w)
        for nome in CFGS:
            ok = v5.copy() if nome == "v5" else v5 & conf[nome[3:]]
            sig = sig0.copy()
            sig["recuo_media"] = ok
            for v in ("atr14x2", "atr21x3"):
                for t in setup.simular(d, w, sig, "recuo_media", v, prazo_semanas=8):
                    if ini <= t.entrada_data <= fim:
                        out.append(t.__dict__ | {"ticker": tk, "cfg": nome, "var": v})
    return out


def resumo(g: pd.DataFrame) -> dict:
    if not len(g):
        return dict(n=0, exp=np.nan, ic=np.nan, taxa=np.nan)
    dias = np.maximum(g.dias.to_numpy(), 1).sum()
    return dict(n=len(g) / 2, exp=g.ret.mean(),
                ic=1.96 * g.ret.std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan,
                taxa=np.exp(np.log1p(g.ret.to_numpy()).sum() / dias * 365) - 1)


def main() -> None:
    res: dict = {}
    for nome, fonte, conj in vp.FONTES:
        if fonte == "mt5":
            ib, tks = ibov_mt5(), base.papeis(conj)
        else:
            ib, tks = hist.ibov_semanal(), [t for t, _ in base.universo()]
        trades = []
        with ProcessPoolExecutor(max_workers=2) as ex:
            for f in as_completed([ex.submit(medir, tk, fonte, conj, ib) for tk in tks]):
                trades += f.result()
        T = pd.DataFrame(trades)
        print(f"\n== {nome} (todos os sinais, caixa fora)", flush=True)
        for cfg in CFGS:
            r = res[(nome, cfg)] = resumo(T[T.cfg == cfg])
            print(f"  {cfg:15s} n={r['n']:4.0f}  por op. {br(r['exp']):>7s} ±{br(r['ic'], sinal=False):6s}"
                  f"  posicionada {br(r['taxa'], 1)}/ano", flush=True)

    print("\nNÍVEL 1 — fica se por operação E posicionada melhorarem no MT5 IS E no MT5 OOS (>= 10 em cada); yfinance = contexto", flush=True)
    fontes = [n for n, _, _ in vp.FONTES]
    mt5 = [n for n, f, _ in vp.FONTES if f == "mt5"]
    for cfg in CFGS[1:]:
        ok = {f: res[(f, cfg)]["exp"] > res[(f, "v5")]["exp"] and res[(f, cfg)]["taxa"] > res[(f, "v5")]["taxa"] for f in fontes}
        fica = all(ok[f] for f in mt5) and all(res[(f, cfg)]["n"] >= MIN_N for f in mt5)
        det = "  ".join(f"{f}: n={res[(f, cfg)]['n']:.0f} op {br(res[(f, 'v5')]['exp'], 2)} -> {br(res[(f, cfg)]['exp'], 2)}, "
                        f"pos {br(res[(f, 'v5')]['taxa'], 1)} -> {br(res[(f, cfg)]['taxa'], 1)}{' [melhora]' if ok[f] else ''}" for f in fontes)
        print(f"  {cfg:15s} {'FICA' if fica else 'nao fica':9s} | {det}", flush=True)


if __name__ == "__main__":
    main()
