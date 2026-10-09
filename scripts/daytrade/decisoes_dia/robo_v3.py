"""Robo v3 (ciclo 3 do CICLO.md). CONGELADO antes do sorteio dos 20 dias novos (ver ciclo3/PREREGISTRO.md).
v3 = v2 + candidatas escolhidas pela selecao para frente em ciclo3/p3_selecao.py (metrica: R$/dia reponderado ao calendario real).
Ordem em que entraram: C8, C7, C6, C4.
  C8  c2_2022_05_24 A1+A2+F2: afrouxa 2 vetos de compra (rompimento sem volume c/ corpo forte; suporte de ontem so abaixo da VWAP)
      + FAZER expansao apos compressao (sem alvo, gestao adaptativa)
  C7  c2_2024_04_22 N5: nao vender minima nova com range e volume encolhendo
  C6  c2_2025_04_07 N4+N1+F1: nao vender perto do VWAP em rotacao apos 11:30; nao operar com ATR15 >= 1,5x teto; pullback com alvo 1R se amplitude >= 2 ATRd
  C4  c2_2023_09_04 P2: rompimento da faixa da 1a hora com volume >= 1,5x, alvo 1R; os 2 vetos de rompimento so valem sem esse volume
Fora (nao passaram nos criterios pre-registrados): C1, C2/C2b2/C2c/C2d/C3 (gestao sem alvo), C5, C5m, C9, C10a/b, C11-C15.
"""
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI / "ciclo3"))
import cfg3

IDS = ["C8", "C7", "C6", "C4"]


def monta_v3():
    return cfg3.monta(IDS)


def roda_v3(dia):
    return cfg3.roda(dia, monta_v3())
