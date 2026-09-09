from __future__ import annotations

import json
import sqlite3

from ..config import DB_PATH
from ..db import connect, init_db, rebuild_empty
from ..textutil import fold
from .catalog import build_cards, clause_terms_from_title, extract_constraints
from .download import ensure_doc_files
from .manifest import SpecDoc, stack_docs
from .pdf import parse_pdf
from .xmi import MetaItem, parse_metamodel


def ingest(version: str = "2.0", skip_download: bool = False, db_path=None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    if path.exists():
        conn = connect(path)
        init_db(conn)
        _delete_version(conn, version)
    else:
        conn = rebuild_empty(path)
    _ingest_stack(conn, stack_docs(version), skip_download)
    conn.commit()
    return conn


def ingest_all(versions: list[str], skip_download: bool = False, db_path=None) -> sqlite3.Connection:
    conn = rebuild_empty(db_path or DB_PATH)
    for version in versions:
        print(f"== ingest {version} ==")
        _ingest_stack(conn, stack_docs(version), skip_download)
    conn.commit()
    return conn


def _delete_version(conn: sqlite3.Connection, version: str) -> None:
    ids = [row[0] for row in conn.execute("SELECT id FROM chunks WHERE version = ?", (version,))]
    for row_id in ids:
        conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (row_id,))
    conn.execute("DELETE FROM chunks WHERE version = ?", (version,))
    conn.execute("DELETE FROM catalog WHERE version = ?", (version,))
    conn.execute("DELETE FROM constraints WHERE version = ?", (version,))
    conn.execute("DELETE FROM element_cards WHERE version = ?", (version,))
    conn.execute("DELETE FROM documents WHERE version = ?", (version,))
    conn.commit()


def ingest_all(versions: list[str], skip_download: bool = False, db_path=None) -> sqlite3.Connection:
    conn = rebuild_empty(db_path or DB_PATH)
    for version in versions:
        print(f"== ingest {version} ==")
        _ingest_stack(conn, stack_docs(version), skip_download)
    conn.commit()
    return conn


def _ingest_stack(conn: sqlite3.Connection, docs: tuple[SpecDoc, ...], skip_download: bool) -> None:
    version = docs[0].version
    chunk_rows: list[dict] = []
    meta_items: list[MetaItem] = []
    constraint_rows: list[dict] = []

    for doc in docs:
        print(f"  {doc.id}: download")
        pdf_path, meta_path, source_url = ensure_doc_files(doc, skip_download=skip_download)
        conn.execute(
            """
            INSERT OR REPLACE INTO documents
              (id, title, version, family, lang_version, pdf_path, metamodel_path, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.id,
                doc.title,
                doc.version,
                doc.family,
                doc.lang_version,
                str(pdf_path),
                str(meta_path) if meta_path else None,
                source_url,
            ),
        )
        print(f"  {doc.id}: parse PDF {pdf_path.name}")
        chunks = parse_pdf(pdf_path)
        print(f"  {doc.id}: {len(chunks)} chunks")
        for chunk in chunks:
            cur = conn.execute(
                """
                INSERT INTO chunks (
                  doc_id, version, clause_id, title, part, kind, normative,
                  page_start, page_end, text, word_count, bboxes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.id,
                    doc.version,
                    chunk.clause_id,
                    chunk.title,
                    chunk.part,
                    chunk.kind,
                    1 if chunk.normative else 0,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.text,
                    chunk.word_count,
                    chunk.bboxes_json(),
                ),
            )
            row_id = cur.lastrowid
            conn.execute(
                "INSERT INTO chunks_fts(rowid, clause_id, title, text, doc_id) VALUES (?, ?, ?, ?, ?)",
                (row_id, chunk.clause_id, chunk.title, chunk.text, doc.id),
            )
            row = {
                "id": row_id,
                "doc_id": doc.id,
                "version": doc.version,
                "clause_id": chunk.clause_id,
                "title": chunk.title,
                "kind": chunk.kind,
                "normative": chunk.normative,
                "page_start": chunk.page_start,
                "text": chunk.text,
            }
            chunk_rows.append(row)
            for term, kind in clause_terms_from_title(chunk.title):
                conn.execute(
                    """
                    INSERT INTO catalog (term, term_norm, kind, doc_id, version, clause_id, extra)
                    VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (term, fold(term), kind, doc.id, doc.version, chunk.clause_id),
                )
            for name, snippet in extract_constraints(chunk.text):
                constraint_rows.append(
                    {
                        "name": name,
                        "doc_id": doc.id,
                        "version": doc.version,
                        "clause_id": chunk.clause_id,
                        "page": chunk.page_start,
                        "text": snippet,
                    }
                )
                conn.execute(
                    """
                    INSERT INTO constraints (name, doc_id, version, clause_id, page, text)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (name, doc.id, doc.version, chunk.clause_id, chunk.page_start, snippet),
                )
                conn.execute(
                    """
                    INSERT INTO catalog (term, term_norm, kind, doc_id, version, clause_id, extra)
                    VALUES (?, ?, 'constraint', ?, ?, ?, NULL)
                    """,
                    (name, fold(name), doc.id, doc.version, chunk.clause_id),
                )

        if meta_path and meta_path.exists():
            print(f"  {doc.id}: parse metamodel {meta_path.name}")
            items = parse_metamodel(meta_path)
            print(f"  {doc.id}: {len(items)} metamodel terms")
            meta_items.extend(items)
            for item in items:
                conn.execute(
                    """
                    INSERT INTO catalog (term, term_norm, kind, doc_id, version, clause_id, extra)
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        item.name,
                        fold(item.name),
                        item.kind,
                        doc.id,
                        doc.version,
                        None if not item.extra else str(item.extra)[:200],
                    ),
                )

    print(f"  building element cards for {version}")
    cards = build_cards(version, chunk_rows, meta_items, constraint_rows)
    for card in cards:
        conn.execute(
            """
            INSERT OR REPLACE INTO element_cards (name, name_norm, version, card_json)
            VALUES (?, ?, ?, ?)
            """,
            (card["name"], card["name_norm"], version, json.dumps(card)),
        )
    print(f"  {len(cards)} element cards")
