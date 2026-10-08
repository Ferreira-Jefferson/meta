"""Confirmacao por VOLUME sobre a v5 (regua pura de nivel 1).

Pedido do dono (2026-10-08): "acho que so falta medir volume".

Mesma maquina de semanal_multitempo_2026_10_08.py (sinal v5 + uma
confirmacao, regra de nivel 1); so troca a lista de confirmacoes. Tudo lido
no fechamento da semana do sinal (o volume do dia da entrada so e conhecido
no fechamento daquele dia, por isso fica de fora):
  v_sinal_baixo  volume da semana do sinal abaixo da media de 20 semanas
  v_sinal_alto   volume da semana do sinal acima da media de 20 semanas
  v_recuo_seco   media das 3 ultimas semanas abaixo da media das 10 anteriores
  v_interesse    media de 10 semanas acima da media de 50 semanas
  v_pressao      nas ultimas 10 semanas, volume das semanas de alta maior que
                 o das semanas de queda
  v_obv          OBV semanal acima da MME21 do OBV
Lista fechada ANTES de rodar: 6 candidatas (as duas primeiras sao lados
opostos da mesma pergunta).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
import semanal_multitempo_2026_10_08 as mt  # noqa: E402

CANDIDATAS = ["v_sinal_baixo", "v_sinal_alto", "v_recuo_seco", "v_interesse", "v_pressao", "v_obv"]


def confirmacoes(d: pd.DataFrame, w: pd.DataFrame) -> dict[str, pd.Series]:
    v = w.volume.astype(float)
    m20 = v.rolling(20, min_periods=15).mean()
    sobe = w.close > w.close.shift()
    desce = w.close < w.close.shift()
    obv = (np.sign(w.close.diff()).fillna(0) * v).cumsum()
    return {
        "v_sinal_baixo": v < m20,
        "v_sinal_alto": v > m20,
        "v_recuo_seco": v.rolling(3).mean() < v.shift(3).rolling(10, min_periods=8).mean(),
        "v_interesse": v.rolling(10).mean() > v.rolling(50, min_periods=30).mean(),
        "v_pressao": v.where(sobe, 0).rolling(10).sum() > v.where(desce, 0).rolling(10).sum(),
        "v_obv": obv > setup.ema(obv, 21),
    }


# roda tambem nos processos filhos (spawn reimporta este modulo)
mt.confirmacoes = confirmacoes
mt.CFGS = ["v5"] + [f"v5+{c}" for c in CANDIDATAS]

if __name__ == "__main__":
    mt.main()
