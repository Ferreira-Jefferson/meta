"""Varredura de paridades (ativo x timeframe x setup x parametros x saida) com IS/OOS.

Uso:  .\\.venv\\Scripts\\python.exe -m scripts.raschke.varredura [--workers 6] [--acoes 60]

Cada UNIDADE = (ativo, timeframe). Termina -> imprime a linha dela na hora e
grava `scripts/raschke/saida/unidade_<ativo>_<tf>.csv`. Resumo ordenado:
`python -m scripts.raschke.analise`.
"""
from __future__ import annotations

import argparse
import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from . import dados, nucleo
from .nucleo import Custo, Saida

SAIDA_DIR = Path(__file__).resolve().parent / "saida"

# (nome, funcao, grade de parametros do SETUP, intraday_only, daily_ok)
GRADES = {
    "HG":   (nucleo.ordens_holy_grail,
             [dict(adx_min=a, modo=m) for a in (25.0, 30.0) for m in ("toque", "inicial")], False),
    "TS":   (nucleo.ordens_turtle_soup,
             [dict(folga_atr=f, validade=v) for f in (0.0, 0.1) for v in (1, 3)], False),
    "TS1":  (lambda b, tick, **k: nucleo.ordens_turtle_soup(b, tick, plus_one=True, **k),
             [dict(idade=3), dict(idade=4)], False),
    "ANTI": (nucleo.ordens_anti,
             [dict(modo=m, recuo=r) for m in ("stoch", "310") for r in (1, 2)], False),
    "PIN":  (nucleo.ordens_pinball,
             [dict(rsi_lo=30.0, rsi_hi=70.0), dict(rsi_lo=20.0, rsi_hi=80.0)], False),
    "8020": (nucleo.ordens_80_20,
             [dict(pen_atr=p, razao_range_min=r) for p in (0.05, 0.15) for r in (0.0, 1.0)], True),
}


def grade_saidas(intraday: bool, setup: str) -> list[tuple[str, Saida]]:
    out: list[tuple[str, Saida]] = []
    if intraday and setup in ("PIN",):
        for ar in (None, 2.0, 3.0):
            out.append((f"pin alvo={ar}", Saida(alvo_r=ar, pinball=True)))
            out.append((f"eod alvo={ar}", Saida(alvo_r=ar, eod=True)))
        return out
    if intraday:
        for ar, tr in itertools.product((None, 1.0, 2.0, 3.0), (0, 6)):
            out.append((f"eod alvo={ar} trail={tr}", Saida(alvo_r=ar, trail_n=tr, eod=True)))
        if setup == "HG":
            out.append(("eod alvo=swing", Saida(alvo_swing=True, eod=True)))
        return out
    for ar, tr, mb in itertools.product((None, 1.0, 2.0, 3.0), (0, 3), (3, 10)):
        out.append((f"alvo={ar} trail={tr} max={mb}", Saida(alvo_r=ar, trail_n=tr, max_barras=mb)))
    if setup == "HG":
        out.append(("alvo=swing max=10", Saida(alvo_swing=True, max_barras=10)))
        out.append(("alvo=swing max=3", Saida(alvo_swing=True, max_barras=3)))
    return out


def _carregar(ativo: str, tf: str):
    """-> (Barras, idx, Custo, classe) ou None."""
    if ativo in ("WIN", "WDO"):
        if tf == "D1":
            b, idx = dados.diario_futuro(ativo)
        else:
            b, idx = dados.intraday_futuro(ativo, tf)
        return b, idx, dados.custo_futuro(ativo, tf), "futuro_indice" if ativo == "WIN" else "futuro_dolar"
    if ativo.endswith("_SA"):
        r = dados.diario_acao(ativo)
        if r is None:
            return None
        b, idx = r
        return b, idx, dados.custo_acao(float(b.c[-1])), "acao"
    r = dados.diario_mt5(ativo)
    if r is None:
        return None
    b, idx = r
    if ativo == "IND@D":
        return b, idx, Custo(tick=5.0, valor_ponto=1.0, qty=1, fee_brl=2.5), "indice_fut"
    if ativo == "DOL@D":
        return b, idx, Custo(tick=0.5, valor_ponto=50.0, qty=1, fee_brl=2.5), "indice_fut"
    if ativo == "BIT@D":
        return b, idx, Custo(tick=20.0, valor_ponto=0.01, qty=1, fee_brl=0.5), "bitcoin"
    if ativo in ("BITH11", "QBTC11", "BITI11", "BITC11"):
        return b, idx, dados.custo_acao(float(b.c[-1])), "bitcoin"
    if ativo == "IBOV":
        return b, idx, Custo(tick=1.0, valor_ponto=1.0, qty=1, pct_lado=0.00035), "indice_cash"
    return b, idx, dados.custo_acao(float(b.c[-1])), "etf_indice"


def unidade(ativo: str, tf: str) -> tuple[str, str, list[dict], str]:
    t0 = time.time()
    car = _carregar(ativo, tf)
    if car is None:
        return ativo, tf, [], "sem dado"
    b, idx, custo, classe = car
    intraday = b.intraday
    rows: list[dict] = []
    for setup, (fn, grade, so_intraday) in GRADES.items():
        if so_intraday and not intraday:
            continue
        for params in grade:
            try:
                ordens = fn(b, custo.tick, **params)
            except Exception as e:  # noqa: BLE001
                print(f"[{ativo} {tf}] {setup} {params} falhou: {e}", file=sys.stderr, flush=True)
                continue
            um_dia = setup in ("PIN", "8020")
            for nome_saida, saida in grade_saidas(intraday, setup):
                tr = nucleo.simular(b, ordens, saida, custo, um_por_dia=um_dia)
                ts = np.array([idx[t.i_entrada] for t in tr], dtype="datetime64[ns]")
                is_tr = [t for t, d in zip(tr, ts) if d < np.datetime64(dados.CORTE_OOS)]
                oos_tr = [t for t, d in zip(tr, ts) if d >= np.datetime64(dados.CORTE_OOS)]
                mi, mo = nucleo.metricas(is_tr), nucleo.metricas(oos_tr)
                row = dict(ativo=ativo, classe=classe, tf=tf, setup=setup,
                           params=";".join(f"{k}={v}" for k, v in params.items()), saida=nome_saida)
                for pref, m in (("is", mi), ("oos", mo)):
                    for k, v in m.items():
                        row[f"{pref}_{k}"] = v
                rows.append(row)
    SAIDA_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(SAIDA_DIR / f"unidade_{ativo}_{tf}.csv", index=False)
    return ativo, tf, rows, f"{time.time() - t0:.0f}s"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)  # RAM: ver feedback_paralelismo_limitado_por_ram
    ap.add_argument("--acoes", type=int, default=60)
    a = ap.parse_args()
    unidades = [(s, tf) for s in ("WIN", "WDO") for tf in ("M5", "M15", "H1", "D1")]
    unidades += [(s, "D1") for s in ("IND@D", "DOL@D", "IBOV", "BOVA11", "SMAL11", "IVVB11",
                                     "BIT@D", "BITH11", "QBTC11", "BITI11")]
    unidades += [(t, "D1") for t in dados.liquidas(a.acoes)]
    print(f"{len(unidades)} unidades, {a.workers} workers", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(unidade, *u): u for u in unidades}
        for f in as_completed(futs):
            try:
                ativo, tf, rows, info = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"{futs[f]} ERRO {e}", flush=True)
                continue
            if not rows:
                print(f"{ativo:10s} {tf:4s} {info}", flush=True)
                continue
            df = pd.DataFrame(rows)
            ok = df[df["is_n"] >= 30]
            melhor = ok.sort_values("is_exp_r", ascending=False).head(1)
            if len(melhor):
                m = melhor.iloc[0]
                print(f"{ativo:10s} {tf:4s} {len(df):4d} cfg {info:>5s} | melhor IS {m['setup']:5s} "
                      f"expR IS {m['is_exp_r']:+.3f} (n={int(m['is_n'])}) -> OOS {m['oos_exp_r']:+.3f} "
                      f"(n={int(m['oos_n'])})", flush=True)
            else:
                print(f"{ativo:10s} {tf:4s} {len(df):4d} cfg {info:>5s} | nenhuma com n_IS>=30", flush=True)


if __name__ == "__main__":
    main()
