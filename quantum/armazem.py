"""Armazém SQLite do Quantum. Um arquivo só (`dados/quantum.sqlite`).

Regra de ouro dos dados de fundamento: cada linha de `demonstracoes` carrega
`dt_receb`, a data em que o documento chegou na CVM. Nenhum cálculo pode usar
uma linha antes dessa data — é isso que separa um backtest de uma fantasia.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    cnpj TEXT PRIMARY KEY,
    nome TEXT, nome_comercial TEXT, cd_cvm TEXT, setor TEXT,
    situacao TEXT, site_ri TEXT, financeira INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tickers (
    ticker TEXT PRIMARY KEY,
    cnpj TEXT, classe TEXT, segmento TEXT,
    inicio_negociacao TEXT, fim_negociacao TEXT, acoes_por_unit REAL DEFAULT 1
);
-- Uma linha por (empresa, data de referência). Fluxos já em LTM (12 meses),
-- estoques no fim do período, tudo em R$. dt_receb = disponibilidade.
CREATE TABLE IF NOT EXISTS demonstracoes (
    cnpj TEXT, dt_refer TEXT, tipo TEXT, versao INTEGER, dt_receb TEXT,
    consolidado INTEGER,
    receita REAL, lucro_bruto REAL, ebit REAL, lucro REAL, lucro_contr REAL, fco REAL,
    ativo REAL, caixa REAL, divida REAL, pl REAL, pl_contr REAL,
    acoes REAL,
    PRIMARY KEY (cnpj, dt_refer)
);
CREATE TABLE IF NOT EXISTS precos (
    ticker TEXT, data TEXT,
    close REAL, adj_close REAL, volume REAL, dividendo REAL, split REAL,
    PRIMARY KEY (ticker, data)
);
CREATE TABLE IF NOT EXISTS indices (
    serie TEXT, data TEXT, valor REAL,
    PRIMARY KEY (serie, data)
);
CREATE TABLE IF NOT EXISTS documentos (
    protocolo TEXT PRIMARY KEY,
    cnpj TEXT, data_entrega TEXT, data_ref TEXT,
    categoria TEXT, tipo TEXT, especie TEXT, assunto TEXT, link TEXT
);
CREATE INDEX IF NOT EXISTS ix_doc_cnpj ON documentos(cnpj, data_entrega);
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    etapa TEXT, inicio TEXT, fim TEXT, status TEXT, mensagem TEXT
);
CREATE TABLE IF NOT EXISTS estudos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rodada TEXT, tipo TEXT, estrategia TEXT, params TEXT, criado_em TEXT,
    resultado TEXT
);
CREATE TABLE IF NOT EXISTS revelacoes (
    periodo TEXT PRIMARY KEY, revelado_em TEXT, motivo TEXT
);
"""


def conectar(caminho: Path | None = None) -> sqlite3.Connection:
    config.garantir_pastas()
    con = sqlite3.connect(caminho or config.BANCO, timeout=60, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    # migração leve: colunas acrescentadas depois da primeira versão do banco
    cols = {r[1] for r in con.execute("PRAGMA table_info(tickers)")}
    if "acoes_por_unit" not in cols:
        con.execute("ALTER TABLE tickers ADD COLUMN acoes_por_unit REAL DEFAULT 1")
    return con


@contextmanager
def conexao(caminho: Path | None = None):
    con = conectar(caminho)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert(con: sqlite3.Connection, tabela: str, df: pd.DataFrame) -> int:
    """INSERT OR REPLACE do DataFrame inteiro (colunas = colunas da tabela)."""
    if df is None or df.empty:
        return 0
    df = df.astype(object).where(pd.notna(df), None)
    cols = list(df.columns)
    sql = f"INSERT OR REPLACE INTO {tabela} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    con.executemany(sql, df.itertuples(index=False, name=None))
    return len(df)


def ler(con: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params)


# ── Log de execuções (o painel mostra) ──────────────────────────────────────
def log_inicio(con, etapa: str) -> int:
    cur = con.execute(
        "INSERT INTO execucoes (etapa, inicio, status) VALUES (?, ?, 'rodando')",
        (etapa, datetime.now().isoformat(timespec="seconds")),
    )
    con.commit()
    return cur.lastrowid


def log_fim(con, id_: int, status: str, mensagem: str = "") -> None:
    con.execute(
        "UPDATE execucoes SET fim=?, status=?, mensagem=? WHERE id=?",
        (datetime.now().isoformat(timespec="seconds"), status, mensagem[:2000], id_),
    )
    con.commit()


# ── Estudos ────────────────────────────────────────────────────────────────
def salvar_estudo(con, rodada: str, tipo: str, estrategia: str, params: dict, resultado: dict) -> int:
    cur = con.execute(
        "INSERT INTO estudos (rodada, tipo, estrategia, params, criado_em, resultado) VALUES (?,?,?,?,?,?)",
        (rodada, tipo, estrategia, json.dumps(params, default=str),
         datetime.now().isoformat(timespec="seconds"), json.dumps(resultado, default=str)),
    )
    con.commit()
    return cur.lastrowid


def periodo_revelado(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM revelacoes WHERE periodo=?", (nome,)).fetchone() is not None


def revelar_periodo(con, nome: str, motivo: str) -> None:
    con.execute(
        "INSERT OR IGNORE INTO revelacoes (periodo, revelado_em, motivo) VALUES (?,?,?)",
        (nome, datetime.now().isoformat(timespec="seconds"), motivo),
    )
    con.commit()
