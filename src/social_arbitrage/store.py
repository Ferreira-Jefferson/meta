"""Persistencia das teses de arbitragem social. Unico caminho para gravar
`Thesis`/`Evidencia` -- mesma politica de `journal/writer.py` (AGENTS.md
regra 3: nao escrever SQL fora do modulo dono do dado).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from core.config import SOCIAL_ARBITRAGE_DB_PATH, SOCIAL_ARBITRAGE_SCHEMA_PATH
from social_arbitrage.thesis import Evidencia, Fase, Lente, Thesis


def _row_to_thesis(row: sqlite3.Row, evidencias: list[Evidencia]) -> Thesis:
    return Thesis(
        id=row["id"],
        marca=row["marca"],
        ticker=row["ticker"],
        fase=Fase(row["fase"]),
        lente=Lente(row["lente"]),
        fonte_deteccao=row["fonte_deteccao"],
        descricao=row["descricao"],
        criterio_saida=row["criterio_saida"],
        tamanho_alvo_pct=row["tamanho_alvo_pct"],
        criado_em=datetime.fromisoformat(row["criado_em"]),
        evidencias=evidencias,
        motivo_rejeicao=row["motivo_rejeicao"],
        preco_entrada=row["preco_entrada"],
        quantidade=row["quantidade"],
        preco_saida=row["preco_saida"],
        resultado_brl=row["resultado_brl"],
        atualizado_em=datetime.fromisoformat(row["atualizado_em"]) if row["atualizado_em"] else None,
        prob_acerto_estimada=row["prob_acerto_estimada"],
        payoff_estimado=row["payoff_estimado"],
    )


class SocialArbitrageStore:
    """CRUD do ciclo de vida da tese. Uma instancia por banco -- passe
    `db_path=tmp_path/...` em teste (AGENTS.md: nenhum caminho fixo
    compartilhado entre testes paralelos)."""

    def __init__(self, db_path: Path = SOCIAL_ARBITRAGE_DB_PATH, schema_path: Path = SOCIAL_ARBITRAGE_SCHEMA_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # `with conn:` so' comita/reverte a transacao -- NAO fecha a conexao
        # (comportamento documentado do sqlite3). Sem o `close()` explicito,
        # a conexao de migracao ficava aberta ate o GC coletar o objeto, e no
        # Windows isso trava a exclusao do arquivo (medido: `TemporaryDirectory.
        # cleanup()` do dry-run falhava com "arquivo em uso" logo apos criar
        # o `SocialArbitrageStore`, mesmo sem nenhuma tese ainda criada).
        conn = self._connect()
        try:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def criar_tese(
        self,
        *,
        marca: str,
        ticker: str,
        lente: Lente,
        fonte_deteccao: str,
        descricao: str,
        criterio_saida: str,
        tamanho_alvo_pct: float,
        quando: datetime,
        prob_acerto_estimada: float | None = None,
        payoff_estimado: float | None = None,
    ) -> Thesis:
        """Registra uma tese nova em `Fase.DETECTADA`. A validacao dos
        campos (nenhum vazio, `tamanho_alvo_pct` em (0, 1]) e' a de
        `Thesis.__post_init__` -- construir o objeto antes de gravar garante
        que nunca existe linha invalida no banco.

        `prob_acerto_estimada`/`payoff_estimado` so' fazem sentido quando
        `tamanho_alvo_pct` veio de `sizing.tamanho_meio_kelly` -- gravar aqui
        e' o que permite `calibragem.py` comparar depois a estimativa contra
        o resultado real."""
        tese = Thesis(
            id=None,
            marca=marca,
            ticker=ticker,
            fase=Fase.DETECTADA,
            lente=lente,
            fonte_deteccao=fonte_deteccao,
            descricao=descricao,
            criterio_saida=criterio_saida,
            tamanho_alvo_pct=tamanho_alvo_pct,
            criado_em=quando,
            prob_acerto_estimada=prob_acerto_estimada,
            payoff_estimado=payoff_estimado,
        )
        with self._tx() as conn:
            cursor = conn.execute(
                """INSERT INTO theses
                   (marca, ticker, fase, lente, fonte_deteccao, descricao, criterio_saida,
                    tamanho_alvo_pct, criado_em, prob_acerto_estimada, payoff_estimado)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tese.marca, tese.ticker, tese.fase.value, tese.lente.value, tese.fonte_deteccao,
                 tese.descricao, tese.criterio_saida, tese.tamanho_alvo_pct,
                 tese.criado_em.isoformat(), tese.prob_acerto_estimada, tese.payoff_estimado),
            )
            tese.id = cursor.lastrowid
        return tese

    def obter(self, thesis_id: int) -> Thesis:
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
            if row is None:
                raise KeyError(f"tese {thesis_id!r} nao encontrada.")
            evid_rows = conn.execute(
                "SELECT * FROM evidencias WHERE thesis_id = ? ORDER BY id", (thesis_id,)
            ).fetchall()
            evidencias = [
                Evidencia(texto=r["texto"], fonte=r["fonte"], registrado_em=datetime.fromisoformat(r["registrado_em"]))
                for r in evid_rows
            ]
            return _row_to_thesis(row, evidencias)

    def listar(self, fase: Fase | None = None) -> list[Thesis]:
        with self._tx() as conn:
            if fase is None:
                rows = conn.execute("SELECT id FROM theses ORDER BY criado_em DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM theses WHERE fase = ? ORDER BY criado_em DESC", (fase.value,)
                ).fetchall()
            ids = [r["id"] for r in rows]
        return [self.obter(i) for i in ids]

    def adicionar_evidencia(self, thesis_id: int, evidencia: Evidencia) -> Thesis:
        """Acumula evidencia numa tese em DETECTADA/EM_VERIFICACAO --
        `Thesis.adicionar_evidencia` recusa fase errada."""
        tese = self.obter(thesis_id)
        tese.adicionar_evidencia(evidencia)
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO evidencias (thesis_id, texto, fonte, registrado_em) VALUES (?, ?, ?, ?)",
                (thesis_id, evidencia.texto, evidencia.fonte, evidencia.registrado_em.isoformat()),
            )
        return tese

    def transicionar(self, thesis_id: int, nova_fase: Fase, *, quando: datetime, motivo_rejeicao: str | None = None) -> Thesis:
        """Move a fase da tese -- `Thesis.transicionar` recusa transicao
        fora de `_TRANSICOES_VALIDAS`. `motivo_rejeicao` so' e' gravado ao
        transicionar para `Fase.REJEITADA` (registro do porque, para nao
        repetir a mesma tese depois sem lembrar do motivo)."""
        tese = self.obter(thesis_id)
        tese.transicionar(nova_fase, quando=quando)
        if nova_fase == Fase.REJEITADA:
            if not motivo_rejeicao or not motivo_rejeicao.strip():
                raise ValueError("transicionar para REJEITADA exige `motivo_rejeicao` nao vazio.")
            tese.motivo_rejeicao = motivo_rejeicao
        with self._tx() as conn:
            conn.execute(
                "UPDATE theses SET fase = ?, atualizado_em = ?, motivo_rejeicao = COALESCE(?, motivo_rejeicao) WHERE id = ?",
                (nova_fase.value, quando.isoformat(), tese.motivo_rejeicao, thesis_id),
            )
        return tese

    def registrar_abertura(self, thesis_id: int, *, preco_entrada: float, quantidade: float, quando: datetime) -> Thesis:
        """Registra que o dono ABRIU a posicao pelo canal que ja usa
        (MT5/home broker) e move a tese para `Fase.ABERTA`. Isto e' um
        REGISTRO retroativo da ordem ja executada -- este modulo nao manda
        ordem (ver o faseamento em `social_arbitrage/__init__.py`)."""
        if preco_entrada <= 0:
            raise ValueError(f"registrar_abertura: `preco_entrada` tem de ser > 0, recebeu {preco_entrada!r}.")
        if quantidade <= 0:
            raise ValueError(f"registrar_abertura: `quantidade` tem de ser > 0, recebeu {quantidade!r}.")
        tese = self.obter(thesis_id)
        tese.transicionar(Fase.ABERTA, quando=quando)
        tese.preco_entrada = preco_entrada
        tese.quantidade = quantidade
        with self._tx() as conn:
            conn.execute(
                "UPDATE theses SET fase = ?, atualizado_em = ?, preco_entrada = ?, quantidade = ? WHERE id = ?",
                (Fase.ABERTA.value, quando.isoformat(), preco_entrada, quantidade, thesis_id),
            )
        return tese

    def registrar_fechamento(self, thesis_id: int, *, preco_saida: float, quando: datetime) -> Thesis:
        """Registra a saida (a paridade de informacao bateu, ou o dono
        decidiu sair) e calcula `resultado_brl` = (saida - entrada) *
        quantidade. Exige a tese em `Fase.ABERTA` -- `Thesis.transicionar`
        recusa qualquer outra origem."""
        if preco_saida <= 0:
            raise ValueError(f"registrar_fechamento: `preco_saida` tem de ser > 0, recebeu {preco_saida!r}.")
        tese = self.obter(thesis_id)
        tese.transicionar(Fase.FECHADA, quando=quando)
        tese.preco_saida = preco_saida
        tese.resultado_brl = (preco_saida - tese.preco_entrada) * tese.quantidade
        with self._tx() as conn:
            conn.execute(
                "UPDATE theses SET fase = ?, atualizado_em = ?, preco_saida = ?, resultado_brl = ? WHERE id = ?",
                (Fase.FECHADA.value, quando.isoformat(), preco_saida, tese.resultado_brl, thesis_id),
            )
        return tese
