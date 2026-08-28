"""Continuacao da varredura de alvo (profit_ticks) x stop (stop_ticks) no
WdoGridReloadMaker, pedida pelo dono 2026-08-28: apos a faixa 1..5 (ver
`wdof1_grid_1a5_2026_08_28.py`) mostrar um padrao claro -- alvo=1 e' o unico
regime saudavel, alvo>=2 destroi o resultado na faixa testada -- o dono
pediu inicialmente 6..40 (1.225 combos, ~20h+ de CPU estimado) e, avisado do
custo e do padrao ja visto, reduziu para 6..20 (225 combos).

Roda so' no IS (72 pregoes, `frozen_split_scope_2026_08_21`: varredura de
parametro e' "melhorar estrategia", respeita o corte).

Paralelismo: ProcessPoolExecutor com submit()/as_completed() (nao ex.map) --
`feedback_parallelize_sweeps` e `feedback_stream_results_as_ready`: usa os
12 nucleos, imprime cada combo assim que termina. Cache de DataFrame por
processo (`_is_df_do_processo`) evita reler o parquet em cada uma das 225
chamadas -- so' paga o custo de leitura uma vez por processo do pool.
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

COMBOS = [(alvo, stop) for alvo in range(6, 21) for stop in range(6, 21)]

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

    def _tabela_top10(rs):
        print(f"\n--- top 10 por liquido (de {len(rs)} concluidos) ---", flush=True)
        print(f"  {'combo':8s} {'trades':>7s} {'liquido':>12s} {'maxdd':>10s} "
              f"{'calmar':>8s} {'R$/trade':>9s}", flush=True)
        for r in sorted(rs, key=lambda r: r["liquido"], reverse=True)[:10]:
            print(f"  T{r['alvo']} S{r['stop']:<5d} {r['trades']:7d} "
                  f"R$ {br(r['liquido']):>9s} R$ {br(r['maxdd']):>7s} "
                  f"{br(r['calmar']):>8s} R$ {br(r['por_trade']):>6s}", flush=True)
        print("", flush=True)

    t0 = time.perf_counter()
    resultados = []
    ultimo_checkpoint = 0
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, combo): combo for combo in COMBOS}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            resultados.append(r)
            feitos += 1
            print(f"  [{feitos:3d}/{len(COMBOS)} {r['dt']:6.1f}s] {r['rotulo']:32s} "
                  f"alvo={r['alvo']:2d} stop={r['stop']:2d} "
                  f"-> {r['trades']:4d} trades  R$ {br(r['liquido']):>10s}  "
                  f"maxdd R$ {br(r['maxdd']):>9s}  calmar {br(r['calmar'],2):>5s}  "
                  f"R$/trade {br(r['por_trade'],2):>6s}", flush=True)
            if feitos - ultimo_checkpoint >= 50:
                ultimo_checkpoint = feitos
                _tabela_top10(resultados)

    print(f"\ntotal: {time.perf_counter()-t0:.1f}s", flush=True)
    _tabela_top10(resultados)

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

    print("\n--- top 5 por Calmar ---", flush=True)
    for r in sorted(resultados, key=lambda r: r["calmar"], reverse=True)[:5]:
        print(f"  T{r['alvo']} S{r['stop']}: calmar {br(r['calmar'])}  "
              f"liquido R$ {br(r['liquido'])}  maxdd R$ {br(r['maxdd'])}  "
              f"trades {r['trades']}", flush=True)


if __name__ == "__main__":
    main()
