-- Banco PROPRIO (db/social_arbitrage.sqlite), separado de journal.sqlite/
-- live.sqlite pelo mesmo motivo dos dois: este e' um registro de decisao
-- DISCRICIONARIA, escrito por um humano num ritmo de dias/semanas, e nao
-- deve competer por lock de arquivo com o diario sistematico (escrita a
-- cada barra) nem com a operacao ao vivo (escrita a cada segundo).

CREATE TABLE IF NOT EXISTS theses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    marca               TEXT NOT NULL,
    ticker              TEXT NOT NULL,
    fase                TEXT NOT NULL,
    lente               TEXT NOT NULL,
    fonte_deteccao      TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    criterio_saida      TEXT NOT NULL,
    tamanho_alvo_pct    REAL NOT NULL,
    criado_em           TEXT NOT NULL,
    atualizado_em       TEXT,
    motivo_rejeicao     TEXT,
    preco_entrada       REAL,
    quantidade          REAL,
    preco_saida         REAL,
    resultado_brl       REAL,
    prob_acerto_estimada REAL,
    payoff_estimado     REAL
);

CREATE TABLE IF NOT EXISTS evidencias (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id           INTEGER NOT NULL REFERENCES theses(id),
    texto               TEXT NOT NULL,
    fonte               TEXT NOT NULL,
    registrado_em       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidencias_thesis_id ON evidencias(thesis_id);
CREATE INDEX IF NOT EXISTS idx_theses_fase ON theses(fase);
CREATE INDEX IF NOT EXISTS idx_theses_ticker ON theses(ticker);
