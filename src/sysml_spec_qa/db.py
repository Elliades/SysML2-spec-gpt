from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import DB_PATH, INDEX_DIR

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  version TEXT NOT NULL,
  family TEXT NOT NULL,
  lang_version TEXT,
  pdf_path TEXT,
  metamodel_path TEXT,
  source_url TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  doc_id TEXT NOT NULL,
  version TEXT NOT NULL,
  clause_id TEXT NOT NULL,
  title TEXT NOT NULL,
  part INTEGER NOT NULL DEFAULT 0,
  kind TEXT,
  normative INTEGER NOT NULL DEFAULT 0,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  text TEXT NOT NULL,
  word_count INTEGER NOT NULL,
  bboxes TEXT,
  FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_clause ON chunks(version, clause_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, version);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  clause_id,
  title,
  text,
  doc_id,
  tokenize = 'unicode61 remove_diacritics 1'
);

CREATE TABLE IF NOT EXISTS catalog (
  id INTEGER PRIMARY KEY,
  term TEXT NOT NULL,
  term_norm TEXT NOT NULL,
  kind TEXT NOT NULL,
  doc_id TEXT,
  version TEXT NOT NULL,
  clause_id TEXT,
  extra TEXT
);

CREATE INDEX IF NOT EXISTS idx_catalog_term ON catalog(version, term_norm);

CREATE TABLE IF NOT EXISTS constraints (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  version TEXT NOT NULL,
  clause_id TEXT,
  page INTEGER,
  text TEXT
);

CREATE INDEX IF NOT EXISTS idx_constraints_name ON constraints(version, name);

CREATE TABLE IF NOT EXISTS element_cards (
  name TEXT NOT NULL,
  name_norm TEXT NOT NULL,
  version TEXT NOT NULL,
  card_json TEXT NOT NULL,
  PRIMARY KEY (name_norm, version)
);

CREATE TABLE IF NOT EXISTS passages (
  id INTEGER PRIMARY KEY,
  passage_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  version TEXT NOT NULL,
  clause_id TEXT NOT NULL,
  title TEXT NOT NULL,
  heading_path TEXT,
  kind TEXT,
  normative INTEGER NOT NULL DEFAULT 0,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  part INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL,
  word_count INTEGER NOT NULL,
  token_estimate INTEGER NOT NULL,
  bboxes TEXT,
  FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_passages_clause ON passages(version, clause_id);
CREATE INDEX IF NOT EXISTS idx_passages_doc ON passages(doc_id, version);

CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
  clause_id,
  heading_path,
  text,
  doc_id,
  tokenize = 'unicode61 remove_diacritics 1'
);

CREATE TABLE IF NOT EXISTS examples (
  id INTEGER PRIMARY KEY,
  example_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  version TEXT NOT NULL,
  clause_id TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT 'sysml',
  caption TEXT,
  page INTEGER,
  text TEXT NOT NULL,
  bboxes TEXT,
  FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_examples_clause ON examples(version, clause_id);

CREATE VIRTUAL TABLE IF NOT EXISTS examples_fts USING fts5(
  clause_id,
  caption,
  text,
  doc_id,
  tokenize = 'unicode61 remove_diacritics 1'
);

CREATE TABLE IF NOT EXISTS cross_refs (
  id INTEGER PRIMARY KEY,
  source_doc_id TEXT NOT NULL,
  source_clause_id TEXT NOT NULL,
  target_clause_id TEXT NOT NULL,
  version TEXT NOT NULL,
  context TEXT
);

CREATE INDEX IF NOT EXISTS idx_cross_refs_source ON cross_refs(version, source_doc_id, source_clause_id);
CREATE INDEX IF NOT EXISTS idx_cross_refs_target ON cross_refs(version, target_clause_id);

CREATE TABLE IF NOT EXISTS toc (
  id INTEGER PRIMARY KEY,
  doc_id TEXT NOT NULL,
  version TEXT NOT NULL,
  clause_id TEXT NOT NULL,
  parent_id TEXT,
  title TEXT NOT NULL,
  depth INTEGER NOT NULL DEFAULT 1,
  page_start INTEGER NOT NULL DEFAULT 1,
  normative INTEGER NOT NULL DEFAULT 0,
  sort_key TEXT NOT NULL,
  FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_toc_doc ON toc(doc_id, version, sort_key);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def rebuild_empty(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or DB_PATH
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        sibling = Path(str(db_path) + suffix)
        if sibling.exists():
            sibling.unlink()
    conn = connect(db_path)
    init_db(conn)
    return conn
