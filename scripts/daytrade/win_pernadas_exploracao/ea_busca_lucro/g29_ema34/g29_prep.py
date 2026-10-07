# -*- coding: utf-8 -*-
"""Pre-computa (uma vez, offline) a EMA de M1 do WIN@ em 3 periodos --
21/34/55 (34 = pedido literal do dono; 21/55 = vizinhos, para ver
sensibilidade ao periodo, pratica padrao do projeto). Causal: `ewm` so'
usa o passado.

Salva `ema_m1.pkl`: DataFrame indexado por Timestamp M1 (jan/2026 a set/2026
-- nao precisa de aquecimento alem do proprio ano corrente porque o EMA de
periodo curto esquece o passado rapido; os primeiros ~200 bars de jan/26 sao
so' aquecimento do proprio indicador, descartados na pratica porque a
janela IS comeca em 2026-01-01 00:00 e o aquecimento eh interno ao calculo).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g05_regime_vol"))
import g05_base as g05b  # noqa: E402

OUT = Path(__file__).parent / "ema_m1.pkl"
PERIODOS = (21, 34, 55)


def main() -> None:
    win = g05b.carrega_win()
    out = {}
    for p in PERIODOS:
        out[f"ema{p}"] = win["close"].ewm(span=p, adjust=False).mean()
    df = __import__("pandas").DataFrame(out)
    df.to_pickle(OUT)
    print(f"Salvo em {OUT} ({len(df)} linhas, {OUT.stat().st_size/1_048_576:.2f} MB)")
    print(df.tail())


if __name__ == "__main__":
    main()
