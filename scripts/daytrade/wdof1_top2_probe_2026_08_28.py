"""Sonda RAPIDA (3 combos, nao a grade completa de 400) no WdoGridReloadMaker,
pedido do dono 2026-08-28 apos ver a grade alvo_vol/stop_vol do CopaWin: "vamos
fazer o mesmo" -> escala pedida (400 combos) provou ser cara demais no motor
tick (custo real medido, nao extrapolado: ver o log desta sessao), e o dono
reduziu para so' os 2 primeiros pares do TOP-10 do CopaWin, aplicados aqui
como profit_ticks/stop_ticks.

RESSALVA que fica registrada: no CopaWin "Alvo"/"Stop" sao `alvo_vol`/
`stop_vol` (multiplos de volatilidade, recalibracao 2026-08-28). Aqui sao
`profit_ticks`/`stop_ticks` (ticks FIXOS) -- parametrizacao diferente. Usar os
MESMOS numeros (19,14)/(19,12) e' sonda heuristica barata, nao transferencia
validada entre familias.

Roda so' no IS (72 pregoes, `frozen_split_scope_2026_08_21`: varredura de
parametro e' "melhorar estrategia", respeita o corte -- OOS fica intocado
para este angulo, mesmo tendo sido usado para confirmar T1S16 ontem).
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

# (rotulo, profit_ticks, stop_ticks) -- baseline + top-2 do CopaWin emprestados
COMBOS = [
    ("baseline T1 S16 (atual)", 1, 16),
    ("top1 CopaWin-borrowed T19 S14", 19, 14),
    ("top2 CopaWin-borrowed T19 S12", 19, 12),
]


def _roda(args):
    rotulo, alvo, stop = args
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from wdo_grid_reload_f1_lab import montar_config, rodar

    df = pd.read_parquet(CACHE)
    is_df = df[df["janela"] == "IS"][["open", "high", "low", "close", "volume"]]
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
    return dict(rotulo=rotulo, alvo=alvo, stop=stop, dt=dt, pregoes=npreg,
                trades=len(trades), liquido=liq,
                por_pregao=liq / npreg if npreg else float("nan"),
                por_trade=liq / len(trades) if trades else float("nan"),
                maxdd=dd, calmar=liq / dd if dd > 0 else float("inf"))


def br(v, dec=2):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    print(f"{len(COMBOS)} combos, ate' {len(COMBOS)} processos em paralelo\n", flush=True)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=len(COMBOS)) as ex:
        for r in ex.map(_roda, COMBOS):
            print(f"  [{r['dt']:6.1f}s] {r['rotulo']:32s} alvo={r['alvo']:2d} stop={r['stop']:2d} "
                  f"-> {r['trades']:4d} trades  R$ {br(r['liquido']):>10s}  "
                  f"maxdd R$ {br(r['maxdd']):>9s}  calmar {br(r['calmar'],2):>5s}  "
                  f"R$/trade {br(r['por_trade'],2):>6s}", flush=True)
    print(f"\ntotal: {time.perf_counter()-t0:.1f}s")


if __name__ == "__main__":
    main()
