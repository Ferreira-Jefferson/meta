"""Robo v4 (ciclo 4 do CICLO.md). CONGELADO antes do sorteio dos 20 dias novos (ver ciclo4/PREREGISTRO.md, secao "Congelamento do v4").
v4 = v3 + candidatas escolhidas pela selecao para frente em ciclo4/p_selecao.py (70 dias de dias_usados.json; metrica: R$/dia reponderado
ao calendario real; criterios (a)-(e), o (e) = leave-one-day-out).
Ordem em que entraram: D16, D13, D1, D9, D2. (A configuracao e montada em ordem fixa D1<D2<D9<D13<D16, a mesma da avaliacao.)
  D16 c3_grupo_2025_06_20 G1 (0,3/0,3/2,0): alvo x2 se a entrada e a favor da perna (desloc >= 0,3 ATRd e ef do dia >= 0,3)
  D13 c3_2022_04_13 N1 (G3n ef<0,10, 0,3): nao vender no terco inferior da faixa do dia em rotacao (ef < 0,10, apos 10:30)
  D1  c3_2024_04_26 A_F1 (prioritaria): retomada da abertura a favor do gap (ignora vetos e o conflito de 2 lados)
  D9  c3_2022_12_12 N1: nao comprar ate 10:00 se a 1a vela foi de queda forte e o fecho esta abaixo da abertura
  D2  c3_grupo_2024_04_26 G4: flip apos stop da gap_fade (entra a favor do gap, stop 1,5 ATR15, alvo 2R)
Fora (nao passaram nos criterios, ou foram desclassificadas por grupo/ordem): D3, D4 (conflito de lados), D5, D6, D7, D8, D10, D11, D12, D14, D15
(detalhe por passo em ciclo4/p_selecao.log). Sem candidata nenhuma, o motor de ciclo4/cfg4.py reproduz o v3 exatamente (ciclo4/p_confere.log).
"""
import sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI / "ciclo4"))
import cfg4

IDS = ["D16", "D13", "D1", "D9", "D2"]


def monta_v4():
    return cfg4.monta(IDS)


def roda_v4(dia):
    return cfg4.roda(dia, monta_v4())
