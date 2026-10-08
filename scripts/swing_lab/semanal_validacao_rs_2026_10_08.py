"""VALIDACAO (conjunto travado) do filtro de forca relativa das small caps.

Autorizado pelo dono em 2026-10-08 ("siga"), depois de o filtro ter melhorado
a carteira e cortado o DD no IS e no OOS (ver semanal_small_caps_2026_10_08.py).

CONFIGURACAO CONGELADA ANTES DE OLHAR (nada aqui pode ser ajustado depois):
  sinal    recuo a MME9 com as tres MMEs semanais subindo (linha de base)
  filtro   razao SMLL/IBOV semanal acima da MME21 da razao, na semana do sinal
  saida    stop inicial na minima do candle-sinal + linha ATR 21x3
  carteira R$1.000, R$1,90/ordem + 0,21%/perna, K=3 e K=5, prioridade pelo
           ranking de 12 meses
  comparacao: a mesma estrategia SEM o filtro, e BOVA11 comprar e segurar
Entradas de 2025-10-01 ate o ultimo pregao da base. Operacao ainda aberta no
fim entra marcada no ultimo fechamento (e contada como "aberta").

A validacao responde UMA pergunta. Se a regra for mudada depois de ver este
resultado, este conjunto deixa de validar a regra nova.
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
from semanal_linha_de_base_2026_10_08 import br, bh, carteira  # noqa: E402

AUTORIZACAO = ("dono autorizou na conversa de 2026-10-08 ('siga'): validar filtro rs>m21 "
               "(SMLL/IBOV > MME21) + recuo MME9 + ATR 21x3 com stop, carteira K3/K5")


def razao_em_alta() -> pd.Series:
    def sem(tk):
        d = pd.read_parquet(base.PASTA / f"{tk}.parquet")
        w = setup.semanal(d)
        return (w.iloc[:-1] if w.index[-1] > d.index[-1] else w)["close"]
    rs = (sem("SMLL") / sem("IBOV")).dropna()
    return rs > setup.ema(rs, 21)


def medir(tk: str, rs_alta: pd.Series):
    out = []
    with redirect_stdout(io.StringIO()):
        d = base.carregar(tk, "validacao", autorizacao=AUTORIZACAO)
        if len(d) < 300:
            return tk, out, {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:
            w = w.iloc[:-1]
        sig0 = setup.sinais(w)
        ini = base.janela("validacao")[0]
        for nome, ok in (("sem filtro", np.ones(len(w), bool)),
                         ("com filtro", rs_alta.reindex(w.index).fillna(False).astype(bool).to_numpy())):
            sig = sig0.copy()
            sig["recuo_media"] = sig0.recuo_media & ok
            for t in setup.simular(d, w, sig, "recuo_media", "atr21x3"):
                if t.entrada_data >= ini:
                    out.append(t.__dict__ | {"ticker": tk, "cfg": nome})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def main() -> None:
    rs_alta = razao_em_alta()
    tks = [t for t, _ in base.universo()]
    ini = base.janela("validacao")[0]
    print(f"== VALIDAÇÃO — {len(tks)} papéis, entradas a partir de {ini}", flush=True)
    jan = rs_alta.loc[ini:]
    print(f"  semanas com small caps ganhando do IBOV: {jan.mean():.0%} de {len(jan)}", flush=True)
    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        for f in as_completed([ex.submit(medir, tk, rs_alta) for tk in tks]):
            tk, tr, r, c = f.result()
            trades += tr; closes[tk] = c
            if r:
                r52[tk] = pd.Series(r)
    T = pd.DataFrame(trades)
    fim = max(c.index[-1] for c in closes.values()).strftime("%Y-%m-%d")
    print(f"  último pregão: {fim}", flush=True)

    print("\nPOR OPERAÇÃO (ATR 21×3 com stop)", flush=True)
    for nome, g in T.groupby("cfg", sort=False):
        r = g.ret
        print(f"  {nome:10s} n={len(g):4d} (abertas no fim: {(g.motivo == 'aberto').sum():3d})  por op.={br(r.mean()):>7s} "
              f"±{br(1.96 * r.std(ddof=1) / np.sqrt(len(r)), sinal=False)}  acerto={br((r > 0).mean(), 1, sinal=False)}"
              f"  dias méd={g.dias.median():.0f}", flush=True)

    pct = pd.DataFrame(r52).rank(axis=1, pct=True)
    T["pct12m"] = [pct.at[s, t] if s in pct.index else np.nan for s, t in zip(T.semana_sinal, T.ticker)]
    cl = pd.DataFrame(closes).sort_index().ffill()
    print("\nCARTEIRA R$1.000", flush=True)
    b = bh(pd.read_parquet(base.PASTA / "BOVA11.parquet")["close"], ini, fim)
    print(f"  BOVA11 comprar e segurar  R${br(b['final'], 0, pct=False, sinal=False):>6s}  MaxDD {br(b['dd'], 1)}", flush=True)
    for nome in ("sem filtro", "com filtro"):
        tv = [dict(r._asdict()) for r in T[T.cfg == nome].itertuples(index=False)]
        for t in tv:
            t["pct12m"] = None if pd.isna(t["pct12m"]) else t["pct12m"]
        for K in (3, 5):
            r = carteira(tv, cl, K, ini, fim, False)
            print(f"  {nome:10s} K{K}             R${br(r['final'], 0, pct=False, sinal=False):>6s}  MaxDD {br(r['dd'], 1)}"
                  f"  operações {r['n']}  corretagem R${br(r['taxas'], 2, pct=False, sinal=False)}", flush=True)


if __name__ == "__main__":
    main()
