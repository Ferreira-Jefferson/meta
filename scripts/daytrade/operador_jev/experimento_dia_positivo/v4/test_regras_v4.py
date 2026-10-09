"""Testes das regras deterministicas da v4 (puras, sem rede, sem arquivos). Rodar: pytest scripts/daytrade/operador_jev/experimento_dia_positivo/v4/test_regras_v4.py"""
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import regras_v4 as rg  # noqa: E402


def dia_fake(ohlc):
    return SimpleNamespace(m15=np.array([[o, h, l, c, 1.0] for o, h, l, c in ohlc], float))


def test_er_dia():
    d = dia_fake([(100, 110, 90, 105), (105, 125, 100, 120)])
    er, desl = rg.er_dia(d, 1)
    assert desl == 20 and abs(er - 20 / 45) < 1e-9
    er0, _ = rg.er_dia(d, 0)
    assert abs(er0 - 5 / 20) < 1e-9


def test_portao_limiar_e_lado():
    assert rg.portao(0.19, 50, 1)[0] is False
    assert rg.portao(0.20, 50, 1)[0] is True
    assert rg.portao(0.50, 50, -1)[0] is False       # venda contra o lado do dia
    assert rg.portao(0.50, -50, -1)[0] is True
    assert rg.portao(0.50, 0, 1)[0] is False
    assert rg.portao(0.17, 50, 1, limiar=0.15)[0] is True


def test_risco_reduz_ou_bloqueia():
    # caixa 2000 -> 6% = R$120 = 600 pts por contrato
    assert rg.risco(100000, 99500, 2, 2000)[0] == 1        # 500 pts x 0,20 x 2 = 200 > 120 -> nao cabe com 2; com 1 = 100 cabe
    assert rg.risco(100000, 99700, 2, 2000)[0] == 2        # 300 pts x 0,2 x 2 = 120 -> cabe (<= limite)
    assert rg.risco(100000, 99400, 2, 2000)[0] == 1        # 2: 240 > 120; 1: 120 <= 120
    assert rg.risco(100000, 99000, 2, 2000)[0] == 0        # 1 contrato: 200 > 120 -> nao entra
    assert rg.risco(100000, 99000, 1, 2000)[0] == 0


def test_reentrada():
    t = lambda brl, k: dict(brl=brl, k_sai=k, motivo="x")
    assert rg.reentrada([], 5)[0] is True
    assert rg.reentrada([t(-10, 4)], 5)[0] is False        # perdeu e so 1 vela
    assert rg.reentrada([t(-10, 4)], 6)[0] is True         # 2 velas
    assert rg.reentrada([t(+10, 4)], 5)[0] is True         # ganhou: sem espera
    assert rg.reentrada([t(1, 1), t(1, 2), t(1, 3)], 20)[0] is False   # maximo 3 por dia
