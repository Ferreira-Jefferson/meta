"""Migra as tabelas `live_*` de um banco de origem para o banco dedicado.

Por que este script existe
---------------------------
Até FEAT-000, o diário da operação real (`live_*`) e o diário de backtest
(`runs`/`trades`/...) viviam no MESMO arquivo `db/journal.sqlite`.
`journal.live_store` agora usa `core.config.LIVE_DB_PATH` (`db/live.sqlite`)
como default — mas o dado que já existia em produção (conta `principal`,
posições, histórico de intents/ordens) continua em `journal.sqlite` até
alguém rodar este script.

Reversibilidade
----------------
Este script NUNCA escreve na origem (`source` é aberta em modo somente-
leitura via URI `mode=ro` — garantia MECÂNICA, não só disciplina de código).
Desfazer a migração é, portanto, trivial: apagar `db/live.sqlite`. A origem
nunca é tocada, então nada se perde.

Idempotência
------------
`INSERT OR IGNORE ... SELECT * FROM ...` preserva as chaves originais (sem
listar colunas, sem deixar o AUTOINCREMENT do destino reatribuir `id`) — é
por isso que a 2ª execução não duplica nenhuma linha.

Uso:
    .venv/Scripts/python.exe scripts/migrate_live_db.py
    .venv/Scripts/python.exe scripts/migrate_live_db.py --source db/journal.sqlite --dest db/live.sqlite
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import DB_PATH, LIVE_DB_PATH
from journal.live_store import ensure_tables

# Ordem de cópia = ordem de dependência de FK (pai antes de filho).
# `live_accounts` é raiz; todas as outras só dependem dela, EXCETO
# `live_fills`, que depende de `live_orders`. `_connect` do store liga
# `PRAGMA foreign_keys = ON`, então copiar fora desta ordem faz o INSERT do
# filho falhar (é o comportamento certo: se a ordem estiver errada, queremos
# que quebre, não que grave FK inválida silenciosamente).
_TABLES_IN_FK_ORDER: tuple[str, ...] = (
    "live_accounts",
    "live_intents",
    "live_orders",
    "live_fills",
    "live_positions",
    "live_equity",
    "live_withdrawals",
    "live_deposits",
    "live_events",
)


def migrate(source: Path = DB_PATH, dest: Path = LIVE_DB_PATH) -> dict[str, int]:
    """Copia as linhas das tabelas `live_*` de `source` para `dest`.

    Nunca escreve em `source`. Retorna `{tabela: linhas_inseridas}` — só para
    as tabelas `live_*` que de fato existem em `source` (banco novo, sem
    nenhuma tabela `live_*`, devolve `{}` sem levantar exceção).
    """
    source = Path(source)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # autocommit (sem transação implícita do driver) — precisamos controlar
    # nós mesmos onde a transação começa, porque ATTACH não pode rodar
    # dentro de uma transação aberta (requisito 3.4.4 do ACTION-PLAN).
    dest_conn = sqlite3.connect(f"file:{dest.resolve().as_posix()}", uri=True, isolation_level=None)
    try:
        # 1. Cria o schema no destino ANTES de qualquer cópia — sem isso o
        #    INSERT bate em "no such table" num banco `dest` novo.
        ensure_tables(dest_conn)
        dest_conn.execute("PRAGMA foreign_keys = ON")

        if not source.exists():
            return {}

        source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
        dest_conn.execute(f"ATTACH DATABASE '{source_uri}' AS src_ro")
        try:
            existing: list[str] = []
            for table in _TABLES_IN_FK_ORDER:
                row = dest_conn.execute(
                    "SELECT name FROM src_ro.sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
                if row is not None:
                    existing.append(table)

            if not existing:
                return {}

            result: dict[str, int] = {}
            dest_conn.execute("BEGIN")
            try:
                for table in existing:
                    before = dest_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    dest_conn.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM src_ro.{table}")
                    after = dest_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    result[table] = after - before
                dest_conn.execute("COMMIT")
            except Exception:
                dest_conn.execute("ROLLBACK")
                raise
            return result
        finally:
            dest_conn.execute("DETACH DATABASE src_ro")
    finally:
        dest_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", type=Path, default=DB_PATH)
    parser.add_argument("--dest", type=Path, default=LIVE_DB_PATH)
    args = parser.parse_args()
    result = migrate(source=args.source, dest=args.dest)
    print(result)


if __name__ == "__main__":
    main()
