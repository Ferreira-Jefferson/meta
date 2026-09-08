"""Pergunta do dono 2026-09-04, depois de ver o resultado de T25/S5: quantos
trades saem por STOP, quantos por ALVO, e quantos sao fechados a mercado no
FECHAMENTO do pregao (`IntradayExitReason.FORCED_FLATTEN` -- posicao ainda
aberta quando a sessao acaba, nem bateu stop nem alvo). Generaliza para
qualquer combo (alvo, stop), mesmo motor tick e janela IS dos scripts
irmaos desta rodada (`wdof1_alvo_stop_combo_2026_09_04.py`).

Uso: python wdof1_contagem_saidas_2026_09_04.py <alvo> <stop>
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wdo_grid_reload_f1_lab import montar_config, rodar  # noqa: E402


def main() -> None:
    alvo, stop = int(sys.argv[1]), int(sys.argv[2])
    df = pd.read_parquet(CACHE)
    is_df = df[df["janela"] == "IS"][["open", "high", "low", "close", "volume"]]

    cfg = montar_config()
    resultado = rodar(is_df, cfg, profit_ticks=alvo, stop_ticks=stop, level_spacing_ticks=1)

    contagem = Counter(t.exit_reason.value for t in resultado.trades)
    total = sum(contagem.values())

    print(f"T{alvo} S{stop} -- {total} trades no IS (72 pregoes)\n")
    for motivo in ("target", "stop", "forced_flatten", "manual", "signal"):
        n = contagem.get(motivo, 0)
        if n or motivo in ("target", "stop", "forced_flatten"):
            pct = 100.0 * n / total if total else 0.0
            print(f"  {motivo:16s} {n:6d}  ({pct:5.1f}%)")

    outros = set(contagem) - {"target", "stop", "forced_flatten", "manual", "signal"}
    for motivo in outros:
        print(f"  {motivo:16s} {contagem[motivo]:6d}")


if __name__ == "__main__":
    main()
