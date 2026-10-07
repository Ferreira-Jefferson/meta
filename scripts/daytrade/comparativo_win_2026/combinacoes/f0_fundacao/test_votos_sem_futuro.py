"""Teste automatico sem-futuro da camada de votos: truncar o M1 num instante nao pode mudar nenhuma linha <= corte.
Cortes no meio de M5/M15/M30 (pega barra maior em formacao) e na hora da decisao do Deslocamento.
Rodar: ..\..\..\..\..\.venv\Scripts\python.exe -m pytest test_votos_sem_futuro.py -n0 -p no:cacheprovider
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import votos  # noqa: E402


def test_passado_nao_muda_ao_truncar():
    cortes = [pd.Timestamp("2026-03-17 10:29:00"), pd.Timestamp("2026-06-02 11:44:00"),
              pd.Timestamp("2026-09-15 16:58:00")]
    assert votos.teste_sem_futuro(cortes) == []
