"""Pergunta do dono 2026-09-04: "se ao stop fosse os ganhos e o alvo as
perdas, quanto teria no final?" -- inverte o SINAL do resultado BRUTO
apenas dos trades que saíram por STOP ou por ALVO (quem perdia nesses dois
motivos passa a ganhar o mesmo tanto, e vice-versa), mantendo a MESMA
corretagem real cobrada em cada trade (nunca invertida -- ver a memoria
`metodo-nulo-signflip-custo-2026-08-26`: inverter o liquido inteiro faria a
corretagem "virar lucro", o que nao existe na corretora de verdade).
Trades fechados por `forced_flatten` (fim de pregao, nem stop nem alvo)
ficam INTACTOS -- a pergunta e' especificamente sobre os dois motivos
citados, essa saida nao e' nem um nem outro.

Uso: python wdof1_swap_stop_alvo_2026_09_04.py <alvo> <stop>
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wdo_grid_reload_f1_lab import montar_config, rodar  # noqa: E402
from backtest.intraday.report import num_br  # noqa: E402


def _gross(t) -> float:
    pontos = (t.exit_price - t.entry_price) if t.side == "long" else (t.entry_price - t.exit_price)
    return pontos * t.point_value_brl * t.quantity


def main() -> None:
    alvo, stop = int(sys.argv[1]), int(sys.argv[2])
    df = pd.read_parquet(CACHE)
    is_df = df[df["janela"] == "IS"][["open", "high", "low", "close", "volume"]]

    cfg = montar_config()
    resultado = rodar(is_df, cfg, profit_ticks=alvo, stop_ticks=stop, level_spacing_ticks=1)
    trades = resultado.trades

    liquido_real = sum(t.pnl_brl for t in trades)
    fees_total = sum(t.fees_total for t in trades)

    liquido_invertido = 0.0
    n_stop = n_alvo = n_flatten = n_outro = 0
    for t in trades:
        motivo = t.exit_reason.value
        gross = _gross(t)
        if motivo in ("stop", "target"):
            liquido_invertido += -gross - t.fees_total
            if motivo == "stop":
                n_stop += 1
            else:
                n_alvo += 1
        else:
            liquido_invertido += t.pnl_brl  # forced_flatten (e outros) intactos
            if motivo == "forced_flatten":
                n_flatten += 1
            else:
                n_outro += 1

    print(f"T{alvo} S{stop} -- {len(trades)} trades no IS (72 pregoes)")
    print(f"  stop invertido (agora ganha): {n_stop}  |  alvo invertido (agora perde): {n_alvo}  "
          f"|  forced_flatten intacto: {n_flatten}" + (f"  |  outro intacto: {n_outro}" if n_outro else ""))
    print()
    print(f"liquido REAL (medido)                    = R${num_br(liquido_real)}")
    print(f"liquido com stop<->alvo INVERTIDO         = R${num_br(liquido_invertido)}")
    print(f"corretagem total paga nos dois cenarios   = R${num_br(fees_total)}  (nao invertida em nenhum dos dois)")


if __name__ == "__main__":
    main()
