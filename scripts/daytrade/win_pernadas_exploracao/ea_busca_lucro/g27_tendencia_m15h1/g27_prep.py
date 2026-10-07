# -*- coding: utf-8 -*-
"""Pre-computa (uma vez, offline) as 3 medidas de tendencia de TEMPO MAIOR
ja' validadas como causais na Fase 2 desta busca (`rodada5/tendencia/base.py`,
usadas em R43-R47 de `REGRAS.md`):

  - `i_m15`: sinal da inclinacao da EMA20 amostrada em M15 (sobe/desce/plana).
  - `i_h1` : idem em H1.
  - `i_leg`: direcao da PERNADA de 750 pts em curso (zigzag sobre o caminho
    intra-vela M1, estado conhecido so' com o passado).

Pedido do dono, 2026-10-05: "ver em M15/H1 se o retangulo de M1 e' um recuo
de tendencia num grafico maior" -- G26 usou so' um drift cru; G27 usa estas
3 medidas de tendencia de verdade (ja' testadas e documentadas em R43-R47).

Salva `tendencia_m15_h1_leg.pkl`: DataFrame indexado por Timestamp (M1, dez/
2025 a set/2026 -- dez/2025 e' so' AQUECIMENTO do indicador, nunca vira
resultado) com as 3 colunas int8 em {-1,0,1}.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rodada5" / "tendencia"))
import base as t5  # noqa: E402

OUT = Path(__file__).parent / "tendencia_m15_h1_leg.pkl"


def main() -> None:
    d = t5.carrega()
    print(f"{len(d)} barras M1 carregadas (dez/2025 aquecimento -> set/2026)", flush=True)
    F = {}
    F["i_m15"] = t5.sinal_ema_slope(d, 15)
    F["i_h1"] = t5.sinal_ema_slope(d, 60)
    F["i_leg"] = t5.zigzag(d)
    ts = pd.to_datetime(d.d.str.replace(".", "-", regex=False) + " " + d.t)
    out = pd.DataFrame(F, index=ts)
    out = out[~out.index.duplicated(keep="first")].sort_index()
    out.to_pickle(OUT)
    print(f"Salvo em {OUT} ({len(out)} linhas, {OUT.stat().st_size/1_048_576:.2f} MB)", flush=True)
    print(out.tail())


if __name__ == "__main__":
    main()
