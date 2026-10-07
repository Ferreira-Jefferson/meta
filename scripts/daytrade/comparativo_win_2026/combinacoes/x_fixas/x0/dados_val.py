"""Shim de dados da X0 -- MESMA interface de ../../../dados.py, para o periodo 2022-01-03 -> 2023-12-29.

Uso: `sys.modules['dados'] = dados_val` ANTES de importar qualquer port (nenhum port e' editado).

Fonte: data/comparativo_win_2026/m1_WIN$N_2022_2025.parquet (WIN$N cru, 2021-12-01..2025-09-30; tem real_volume e
tick_volume; real_volume > 0 em todas as barras). Ticks SEMPRE sinteticos, 4 por M1, pela mesma funcao
`dados._sinteticos` (aqui importada do dados.py real, nao copiada).

Modo prova (variavel de ambiente DADOS_VAL_MODO=2026): o shim delega m1()/ticks() ao dados.py real de 2026 (ticks
reais desde 20/02), dias() = pregoes de 2026 entre PROVA_INI e PROVA_FIM (env, default 2026-09-01..2026-09-30) e
salvar() grava em v0/prova_2026/. Serve so' para provar que o shim nao muda a logica dos ports.
"""
import importlib.util
import os
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
ORIG_DIR = AQUI.parents[2]                      # .../comparativo_win_2026
spec = importlib.util.spec_from_file_location("dados_orig", ORIG_DIR / "dados.py")
_O = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_O)

_sinteticos, ms, ts, trade = _O._sinteticos, _O.ms, _O.ts, _O.trade
TICK, RS_PONTO, CAPITAL, COLUNAS = _O.TICK, _O.RS_PONTO, _O.CAPITAL, _O.COLUNAS
ROOT, DADOS = _O.ROOT, _O.DADOS

MODO = os.environ.get("DADOS_VAL_MODO", "val")
if MODO == "2026":
    INICIO = date.fromisoformat(os.environ.get("PROVA_INI", "2026-09-01"))
    FIM = date.fromisoformat(os.environ.get("PROVA_FIM", "2026-09-30"))
    SAIDA = AQUI / "prova_2026"
elif MODO == "continuo":     # verificacao da emenda: 2022-01-03 -> 2025-09-30 numa rodada so'
    INICIO, FIM = date(2022, 1, 3), date(2025, 9, 30)
    SAIDA = AQUI / "continuo"
else:
    INICIO, FIM = date(2022, 1, 3), date(2023, 12, 29)
    SAIDA = AQUI / "resultados"


@lru_cache(maxsize=1)
def m1() -> pd.DataFrame:
    if MODO == "2026":
        return _O.m1()
    return pd.read_parquet(DADOS / "m1_WIN$N_2022_2025.parquet")


def dias() -> list:
    return sorted(d for d in set(m1().index.date) if INICIO <= d <= FIM)


@lru_cache(maxsize=None)
def _por_dia():
    b = m1()
    return {d: g for d, g in b.groupby(b.index.date)}


def ticks(dia: date):
    if MODO == "2026":
        return _O.ticks(dia)
    t, p, v = _sinteticos(_por_dia()[dia])
    return t, p, v, False


def salvar(estrategia: str, trades: list) -> Path:
    SAIDA.mkdir(exist_ok=True)
    out = SAIDA / f"{estrategia}.csv"
    pd.DataFrame(trades, columns=COLUNAS).to_csv(out, index=False)
    return out
