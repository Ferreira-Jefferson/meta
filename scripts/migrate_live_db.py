"""Migra as tabelas `live_*` de um banco de origem para o banco dedicado.

Por que este script existe
---------------------------
Até FEAT-000, o diário da operação real (`live_*`) e o diário de backtest
(`runs`/`trades`/...) viviam no MESMO arquivo `db/journal.sqlite`.
`journal.live_store` agora usa `core.config.LIVE_DB_PATH` (`db/live.sqlite`)
como default — mas o dado que já existia em produção (conta `principal`,
posições, histórico de intents/ordens) continua em `journal.sqlite` até
alguém rodar este script.

Marcador de conclusão de migração (correção pós-code-review, hipótese-agente
A1/A2/A4/B2)
-----------------------------------------------------------------------------
Um `db/live.sqlite` recém-criado (vazio) é, sem mais nada, indistinguível de
um banco já migrado — e reintroduzir uma cópia sobre um destino que já
recebeu escrita real do robô (por fora desta migração) produz linhas com
`id` colidindo mas conteúdo divergente (`INSERT OR IGNORE` silenciosamente
mantém a linha do destino, "perdendo" a diferença sem avisar ninguém). Por
isso o destino carrega `PRAGMA user_version`: 0 = nunca migrado por este
script, 1 = já migrado (ao menos uma vez). Se o destino tem `user_version ==
0` mas já contém linhas em `live_accounts` (sinal de que o robô real ou outro
processo já escreveu ali sem passar por este script), a migração é
RECUSADA — a menos que `--force` seja passado explicitamente. `user_version`
é escrito na MESMA transação que copia os dados (antes do `COMMIT`), então um
crash entre a criação do schema e o commit da cópia deixa o destino com
schema criado mas `user_version` ainda em 0 (a marcação nunca chega a
existir sem o commit) — o que é o comportamento certo: um destino
"schema criado mas vazio" continua sendo tratado como "nunca migrado".

Limite residual conhecido: `journal.live_store.ensure_tables`/`_connect` já
dão um `commit()` implícito ao criar as tabelas `live_*` no destino — esse
commit acontece ANTES da transação de cópia deste script começar e está fora
do controle daqui (não faz parte do escopo desta correção mexer em
`journal/live_store.py`). Na prática isso não abre brecha: criar tabelas
vazias via `CREATE TABLE IF NOT EXISTS` não grava nenhuma linha nem toca
`user_version`, então o pior cenário de crash nesse meio-tempo ainda deixa o
destino elegível para uma nova tentativa de migração normal (schema presente,
sem dado, sem marcador).

Relatório de divergência (correção pós-code-review, hipótese-agente F1/A5/A6)
-----------------------------------------------------------------------------
Depois de copiar cada tabela, o número de linhas na ORIGEM (lido antes da
cópia, via conexão somente-leitura) é comparado com o número de linhas no
DESTINO logo após a cópia. Se o destino ficou com MENOS linhas do que a
origem tinha — sinal de que `INSERT OR IGNORE` descartou alguma linha por
violar CHECK/UNIQUE/NOT NULL —, o script imprime um `AVISO` por tabela
afetada e o processo termina com código de saída 1 (o que já foi copiado
com sucesso permanece commitado — isto NÃO é um rollback, é um relatório
loud: silêncio sobre dinheiro perdido/duplicado é exatamente o que esta run
existe para evitar).

Arquivo de origem ausente vs. origem sem tabelas `live_*` (hipótese-agente A7)
-----------------------------------------------------------------------------
Um `--source` que aponta para um caminho que NÃO EXISTE no disco é, com
grande probabilidade, um erro de digitação do operador — e não deve terminar
como "migração completa" (`{}`, exit 0). Por isso `source` inexistente
levanta `FileNotFoundError` e o CLI sai com código != 0. Já um `source` que
EXISTE mas não tem nenhuma tabela `live_*` (instalação nova, banco de
backtest puro) é o caso legítimo original: devolve `{}` e sai com código 0.

Reversibilidade
----------------
Este script NUNCA escreve na origem (`source` é aberta em modo somente-
leitura via URI `mode=ro` — garantia MECÂNICA, não só disciplina de código).
Desfazer a migração é, na maioria dos casos, apagar `db/live.sqlite` — mas
desde que este lote ligou `PRAGMA journal_mode=WAL` no destino
(`journal.live_store._connect`), pode sobrar `db/live.sqlite-wal` e
`db/live.sqlite-shm` no disco (o WAL ainda não foi consolidado no arquivo
principal). Apagar só `live.sqlite` e deixar os sidecars para trás pode
fazer o SQLite recriar o banco a partir de um WAL órfão na próxima conexão.
Para desfazer com segurança: rode `PRAGMA wal_checkpoint(TRUNCATE);` contra
`db/live.sqlite` ANTES de apagar (consolida e zera o WAL), ou apague os três
arquivos juntos (`live.sqlite`, `live.sqlite-wal`, `live.sqlite-shm`).

Idempotência
------------
`INSERT OR IGNORE ... SELECT * FROM ...` preserva as chaves originais (sem
listar colunas, sem deixar o AUTOINCREMENT do destino reatribuir `id`) — é
por isso que a 2ª execução não duplica nenhuma linha. Um destino com
`user_version >= 1` (já migrado antes) segue copiando normalmente, sem
exigir `--force` — o `--force` só existe para ignorar a checagem específica
de "destino povoado sem marcador" (`user_version == 0` com `live_accounts`
não vazia).

Uso:
    .venv/Scripts/python.exe scripts/migrate_live_db.py
    .venv/Scripts/python.exe scripts/migrate_live_db.py --source db/journal.sqlite --dest db/live.sqlite
    .venv/Scripts/python.exe scripts/migrate_live_db.py --force   # só se tiver certeza
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


class MigrationRefused(RuntimeError):
    """Destino tem `user_version == 0` mas já contém linhas em `live_accounts`
    — provável escrita real por fora desta migração. Recusa é o default;
    `--force`/`force=True` ignora só esta checagem."""


class MigrationIncomplete(RuntimeError):
    """Levantada DEPOIS do commit quando alguma tabela terminou com menos
    linhas no destino do que existiam na origem (perda silenciosa via
    `INSERT OR IGNORE`). `.result` guarda o que foi de fato commitado;
    `.mismatches` guarda `(tabela, linhas_na_origem, linhas_no_destino)` por
    tabela afetada. Não é rollback — o dado copiado com sucesso permanece."""

    def __init__(self, result: dict[str, int], mismatches: list[tuple[str, int, int]]) -> None:
        self.result = result
        self.mismatches = mismatches
        resumo = "; ".join(
            f"{table} (origem={source_count}, destino={dest_count})"
            for table, source_count, dest_count in mismatches
        )
        super().__init__(f"migração incompleta — divergência de contagem em: {resumo}")


def migrate(source: Path = DB_PATH, dest: Path = LIVE_DB_PATH, force: bool = False) -> dict[str, int]:
    """Copia as linhas das tabelas `live_*` de `source` para `dest`.

    Nunca escreve em `source`. Retorna `{tabela: linhas_inseridas}` — só para
    as tabelas `live_*` que de fato existem em `source` (banco existente sem
    nenhuma tabela `live_*` devolve `{}` sem levantar exceção).

    Levanta `FileNotFoundError` se `source` não existir no disco (ver
    docstring do módulo — A7). Levanta `MigrationRefused` se `dest` tiver
    `user_version == 0` e já contiver linhas em `live_accounts` e `force`
    for `False`. Levanta `MigrationIncomplete` (depois de já ter commitado o
    que copiou) se alguma tabela ficou com menos linhas no destino do que na
    origem.
    """
    source = Path(source)
    dest = Path(dest)

    if not source.exists():
        raise FileNotFoundError(f"origem não existe: {source}")

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

        # Marcador de conclusão de migração — ler ANTES de copiar (ver
        # docstring do módulo).
        user_version = dest_conn.execute("PRAGMA user_version").fetchone()[0]
        if user_version == 0 and not force:
            existing_accounts = dest_conn.execute(
                "SELECT COUNT(*) FROM live_accounts"
            ).fetchone()[0]
            if existing_accounts > 0:
                raise MigrationRefused(
                    f"destino '{dest}' já contém {existing_accounts} conta(s) em "
                    "live_accounts sem marcador de migração (PRAGMA user_version = 0) "
                    "— provavelmente o robô real (ou outro processo) já escreveu neste "
                    "banco por fora desta migração. Rode com --force só se tiver "
                    "certeza de que é seguro sobrescrever."
                )

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
            mismatches: list[tuple[str, int, int]] = []
            dest_conn.execute("BEGIN")
            try:
                for table in existing:
                    source_count = dest_conn.execute(
                        f"SELECT COUNT(*) FROM src_ro.{table}"
                    ).fetchone()[0]
                    before = dest_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    dest_conn.execute(
                        f"INSERT OR IGNORE INTO {table} SELECT * FROM src_ro.{table}"
                    )
                    after = dest_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    result[table] = after - before
                    if after < source_count:
                        mismatches.append((table, source_count, after))

                if user_version == 0:
                    dest_conn.execute("PRAGMA user_version = 1")
                dest_conn.execute("COMMIT")
            except Exception:
                dest_conn.execute("ROLLBACK")
                raise

            if mismatches:
                for table, source_count, dest_count in mismatches:
                    missing = source_count - dest_count
                    print(
                        f"AVISO: {table} tem {source_count} linhas na origem mas só "
                        f"{dest_count} no destino — {missing} linha(s) não copiada(s), "
                        "possivelmente por violação de CHECK/UNIQUE/NOT NULL"
                    )
                raise MigrationIncomplete(result, mismatches)

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
    parser.add_argument(
        "--force", action="store_true",
        help="ignora a recusa de destino já povoado sem marcador de migração "
             "(user_version == 0 com live_accounts não vazia) — use só se "
             "tiver certeza de que é seguro sobrescrever",
    )
    args = parser.parse_args()
    try:
        result = migrate(source=args.source, dest=args.dest, force=args.force)
    except FileNotFoundError as exc:
        print(f"[migrate] ERRO: {exc}", file=sys.stderr)
        sys.exit(1)
    except MigrationRefused as exc:
        print(f"[migrate] RECUSADO: {exc}", file=sys.stderr)
        sys.exit(1)
    except MigrationIncomplete as exc:
        print(f"[migrate] {exc.result}")
        print(f"[migrate] ERRO: {exc}", file=sys.stderr)
        sys.exit(1)
    else:
        print(result)


if __name__ == "__main__":
    main()
