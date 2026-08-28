"""Calibracao NULA da varredura de `candle_measure.py` (pedido explicito do
dono): roda o MESMO pipeline (deteccao de padrao + medicao de retorno/MFE-MAE
+ teste de permutacao) sobre uma serie SINTETICA sem estrutura direcional
(`candle_lab.mirror_signflip_synthetic`) e conta quantas das ~126 celulas
passariam pelos mesmos filtros de significancia SO' POR ACASO.

Isso responde a pergunta que a varredura real sozinha nao responde: com
~126 celulas testadas (21 padroes x 2 simbolos x 3 horizontes), quantos
"achados" com p<0,05 esperar so' de ruido (~5%, ~6 celulas) -- se o numero
real bater ou ficar PROXIMO do numero da serie sem estrutura, os achados da
varredura real nao sao evidencia de nada.

`N_SEEDS` (minimo 5, mesma disciplina de outras calibracoes nulas do
projeto -- ver `metodo_nulo_signflip_custo`): reporta a DISTRIBUICAO da
contagem entre sementes, nunca so' uma media sem dispersao (`metodo_numero_
sem_dispersao`).

Uso: `python scripts/daytrade/candle_null_calibration.py`.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from candle_lab import HORIZONS, SYMBOLS, evaluate_pattern, in_sample_bars, mirror_signflip_synthetic  # noqa: E402
from strategy.daytrade.lab.candle_patterns import PATTERNS  # noqa: E402

TIMEFRAME = "M15"
N_SEEDS = 5
N_PERM = 150  # reduzido frente aos 300 da varredura real -- 5 sementes x 126 celulas x 2 testes


def run_one_seed(seed: int) -> dict[str, int]:
    counts = {"p_ret<0.05": 0, "p_ret<0.01": 0, "p_asym<0.05": 0, "p_asym<0.01": 0}
    total = 0
    for symbol in SYMBOLS:
        real_df = in_sample_bars(symbol, TIMEFRAME)
        # `SYMBOLS.index`, NUNCA `hash(symbol)` -- hash de string e'
        # aleatorizado por PROCESSO em Python (PYTHONHASHSEED), o que
        # tornaria a serie sintetica DIFERENTE a cada execucao mesmo com
        # `seed` fixo, quebrando a reprodutibilidade que a rodada de
        # multiplas sementes existe para garantir.
        synth_df = mirror_signflip_synthetic(real_df, seed=seed * 1000 + SYMBOLS.index(symbol))
        for pattern_name, spec in PATTERNS.items():
            for horizon in HORIZONS:
                r = evaluate_pattern(
                    synth_df, symbol, TIMEFRAME, pattern_name, spec.detector, spec.direction,
                    horizon, n_perm=N_PERM, seed=seed,
                )
                total += 1
                if r.ret_p_value == r.ret_p_value:
                    if r.ret_p_value < 0.05:
                        counts["p_ret<0.05"] += 1
                    if r.ret_p_value < 0.01:
                        counts["p_ret<0.01"] += 1
                if r.asymmetry_p_value == r.asymmetry_p_value:
                    if r.asymmetry_p_value < 0.05:
                        counts["p_asym<0.05"] += 1
                    if r.asymmetry_p_value < 0.01:
                        counts["p_asym<0.01"] += 1
    counts["total_celulas"] = total
    return counts


def main() -> None:
    print(f"[candle_null_calibration] {N_SEEDS} sementes, n_perm={N_PERM}, "
          f"{len(PATTERNS)} padroes x {len(SYMBOLS)} simbolos x {len(HORIZONS)} horizontes "
          f"= {len(PATTERNS)*len(SYMBOLS)*len(HORIZONS)} celulas/semente", flush=True)
    all_counts: list[dict[str, int]] = []
    t0 = time.time()
    for seed in range(N_SEEDS):
        c = run_one_seed(seed)
        all_counts.append(c)
        print(f"  semente {seed}: {c}  ({time.time()-t0:.0f}s acumulado)", flush=True)

    total_celulas = all_counts[0]["total_celulas"]
    print(f"\n=== resumo ({N_SEEDS} sementes, {total_celulas} celulas cada) ===")
    for key in ("p_ret<0.05", "p_ret<0.01", "p_asym<0.05", "p_asym<0.01"):
        vals = [c[key] for c in all_counts]
        mean = sum(vals) / len(vals)
        esperado_pct = 5.0 if "0.05" in key else 1.0
        esperado_n = esperado_pct / 100.0 * total_celulas
        print(f"  {key}: sementes={vals}  media={mean:.1f}  "
              f"min={min(vals)}  max={max(vals)}  "
              f"esperado so' por acaso (~{esperado_pct:.0f}%): ~{esperado_n:.1f}")


if __name__ == "__main__":
    main()
