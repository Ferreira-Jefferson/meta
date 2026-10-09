"""Leitura das bases M1 versionadas no git (data/win_sem_leiloes/, data/wdo-mt5/) montadas por PEDAÇOS.

Por que pedaços (2026-10-09): o git guarda toda versão de um arquivo. Regravar a base inteira a cada atualização
somava o arquivo inteiro ao histórico de novo — no WDO@D, pior, porque o ajuste por diferença muda TODOS os preços
a cada rolagem (todo mês), e o git não consegue guardar só a diferença. Então: o arquivo grande fica CONGELADO e
os pregões novos entram em arquivos mensais pequenos (scripts/daytrade/atualiza_bases_mt5.py). Quem lê usa estas
funções e recebe a série contínua de sempre.

WIN (WIN$N, sem ajuste): `<base>.parquet` + `<base>_AAAA-MM.parquet`. Concatena; o pedaço mais novo vence em
horário repetido.

WDO@D (ajuste por diferença): `bases.csv` lista cada arquivo e a data em que foi coletado (os preços dele estão
ajustados como o MT5 os mostrava nesse dia). `ajustes.csv` lista cada rolagem detectada depois e o deslocamento
dela. Preço de hoje = preço gravado + soma dos deslocamentos detectados DEPOIS da coleta do arquivo (toda linha
de um arquivo é anterior a uma rolagem que ele ainda não viu, então todas levam o deslocamento).

Camada feature: só pandas/numpy; os caminhos vêm do chamador ou do padrão abaixo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
WIN_DIR = RAIZ / "data" / "win_sem_leiloes"
WDO_DIR = RAIZ / "data" / "wdo-mt5"
_MES = re.compile(r"_\d{4}-\d{2}$")
PRECOS_WDO = ["<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>"]


# ------------------------------------------------------------------ WIN
def pedacos_win(base: str | Path) -> list[Path]:
    """O arquivo base e os pedaços mensais dele, em ordem (base primeiro)."""
    base = Path(base) if Path(base).is_absolute() else WIN_DIR / base
    meses = sorted(p for p in base.parent.glob(f"{base.stem}_*.parquet") if _MES.search(p.stem[len(base.stem):]))
    return [base] + meses


def le_win(base: str | Path) -> pd.DataFrame:
    """M1 do WIN sem leilões: base congelada + pedaços mensais (o mais novo vence em horário repetido)."""
    d = pd.concat([pd.read_parquet(p) for p in pedacos_win(base)])
    return d[~d.index.duplicated(keep="last")].sort_index()


# ------------------------------------------------------------------ WDO@D
def _le_csv_mt5(p: Path) -> pd.DataFrame:
    w = pd.read_csv(p, sep="\t")
    w.index = pd.to_datetime(w["<DATE>"] + " " + w["<TIME>"], format="%Y.%m.%d %H:%M:%S")
    return w


def tabelas_wdo(pasta: str | Path = WDO_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    pasta = Path(pasta)
    bases = pd.read_csv(pasta / "bases.csv", sep=";", parse_dates=["coletado_em"])
    aj = pasta / "ajustes.csv"
    ajustes = (pd.read_csv(aj, sep=";", parse_dates=["detectado_em"]) if aj.exists()
               else pd.DataFrame({"detectado_em": pd.to_datetime([]), "delta": []}))
    return bases, ajustes


def le_wdo(pasta: str | Path = WDO_DIR) -> pd.DataFrame:
    """M1 do WDO@D no ajuste de HOJE, no layout de exportação do MT5 (<DATE> <TIME> <OPEN> ... <SPREAD>)."""
    pasta = Path(pasta)
    bases, ajustes = tabelas_wdo(pasta)
    partes = []
    for r in bases.sort_values("coletado_em", kind="stable").itertuples():
        w = _le_csv_mt5(pasta / r.arquivo)
        delta = float(ajustes.loc[ajustes.detectado_em > r.coletado_em, "delta"].sum())
        if delta:
            w[PRECOS_WDO] = (w[PRECOS_WDO] + delta).round(3)
        partes.append(w)
    d = pd.concat(partes)
    return d[~d.index.duplicated(keep="last")].sort_index()
