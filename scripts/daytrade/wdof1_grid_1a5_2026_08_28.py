"""Varredura pedida pelo dono 2026-08-28: alvo (profit_ticks) e stop
(stop_ticks) em 1..5 cada, 25 combinacoes, no WdoGridReloadMaker.

Depois de ver que emprestar (alvo,stop) do CopaWin (19/14, 19/12) perdeu de
longe para o baseline 1/16 -- ver `wdof1_top2_probe_2026_08_28.py` e a
ressalva sobre parametrizacoes incompativeis -- o dono pediu para calibrar
dentro do proprio espaco do maker (ticks fixos, level_spacing_ticks=1), numa
faixa pequena e barata (1..5 x 1..5) em vez da grade de 400 celulas que foi
interrompida.

Roda so' no IS (72 pregoes, `frozen_split_scope_2026_08_21`: varredura de
parametro e' "melhorar estrategia", respeita o corte).

Paralelismo: ProcessPoolExecutor com submit()/as_completed() (nao ex.map,
que bloqueia na ordem de submissao) -- `feedback_parallelize_sweeps` e
`feedback_stream_results_as_ready`: usa os 12 nucleos, imprime cada combo
assim que termina, nao em ordem de tamanho.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

COMBOS = [(alvo, stop) for alvo in range(1, 6) for stop in range(1, 6)]

# referencia ja medida (nao re-roda: mesma config, ver wdof1_top2_probe_2026_08_28)
BASELINE = dict(rotulo="baseline T1 S16 (atual, referencia)", alvo=1, stop=16,
                trades=2773, liquido=11233.50, maxdd=121.50, calmar=92.46,
                por_trade=4.05, pregoes=None, dt=0.0)

_IS_DF_PROC = None  # cache por processo: o pool reusa processos entre tarefas


def _is_df_do_processo():
    global _IS_DF_PROC
    if _IS_DF_PROC is None:
        df = pd.read_parquet(CACHE)
        _IS_DF_PROC = df[df["janela"] == "IS"][["open", "high", "low", "close", "volume"]]
    return _IS_DF_PROC


def _roda(args):
    alvo, stop = args
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from wdo_grid_reload_f1_lab import montar_config, rodar

    is_df = _is_df_do_processo()
    cfg = montar_config()
    t0 = time.perf_counter()
    res = rodar(is_df, cfg, profit_ticks=alvo, stop_ticks=stop, level_spacing_ticks=1)
    dt = time.perf_counter() - t0

    trades = res.trades
    liq = sum(t.pnl_brl for t in trades)
    eq = pico = dd = 0.0
    for t in trades:
        eq += t.pnl_brl
        pico = max(pico, eq)
        dd = max(dd, pico - eq)
    npreg = len({t.exit_ts.date() for t in trades}) if trades else 0
    return dict(rotulo=f"T{alvo} S{stop}", alvo=alvo, stop=stop, dt=dt, pregoes=npreg,
                trades=len(trades), liquido=liq,
                por_pregao=liq / npreg if npreg else float("nan"),
                por_trade=liq / len(trades) if trades else float("nan"),
                maxdd=dd, calmar=liq / dd if dd > 0 else float("inf"))


def br(v, dec=2):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    n_workers = min(12, os.cpu_count() or 4)
    print(f"{len(COMBOS)} combos, {n_workers} processos em paralelo\n", flush=True)
    print(f"  [ref.  ] {BASELINE['rotulo']:32s} alvo= 1 stop=16 "
          f"-> {BASELINE['trades']:4d} trades  R$ {br(BASELINE['liquido']):>10s}  "
          f"maxdd R$ {br(BASELINE['maxdd']):>9s}  calmar {br(BASELINE['calmar'],2):>5s}  "
          f"R$/trade {br(BASELINE['por_trade'],2):>6s}", flush=True)

    t0 = time.perf_counter()
    resultados = []
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, combo): combo for combo in COMBOS}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            resultados.append(r)
            feitos += 1
            print(f"  [{feitos:2d}/{len(COMBOS)} {r['dt']:6.1f}s] {r['rotulo']:32s} "
                  f"alvo={r['alvo']:2d} stop={r['stop']:2d} "
                  f"-> {r['trades']:4d} trades  R$ {br(r['liquido']):>10s}  "
                  f"maxdd R$ {br(r['maxdd']):>9s}  calmar {br(r['calmar'],2):>5s}  "
                  f"R$/trade {br(r['por_trade'],2):>6s}", flush=True)

    print(f"\ntotal: {time.perf_counter()-t0:.1f}s", flush=True)

    print("\n--- top 5 por MaxDD (menor risco) ---", flush=True)
    for r in sorted(resultados, key=lambda r: r["maxdd"])[:5]:
        print(f"  T{r['alvo']} S{r['stop']}: maxdd R$ {br(r['maxdd'])}  "
              f"liquido R$ {br(r['liquido'])}  calmar {br(r['calmar'])}  "
              f"trades {r['trades']}", flush=True)

    print("\n--- top 5 por lucro/dia ---", flush=True)
    for r in sorted(resultados, key=lambda r: r["por_pregao"], reverse=True)[:5]:
        print(f"  T{r['alvo']} S{r['stop']}: R$/pregao {br(r['por_pregao'])}  "
              f"liquido R$ {br(r['liquido'])}  maxdd R$ {br(r['maxdd'])}  "
              f"trades {r['trades']}", flush=True)


if __name__ == "__main__":
    main()
