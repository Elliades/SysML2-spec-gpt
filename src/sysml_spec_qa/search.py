from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from .config import (
    DB_PATH,
    DEFAULT_VERSION,
    MAX_EXCERPT_WORDS,
    MAX_GET_WORDS,
    MAX_HITS,
    MAX_TOTAL_EXCERPT_WORDS,
    VIEWER_URL,
)
from .db import connect
from .synonyms import expand_query
from .textutil import excerpt, fold, fts_query, word_count


@dataclass
class Hit:
    doc_id: str
    version: str
    clause_id: str
    title: str
    kind: str
    normative: bool
    page_start: int
    page_end: int
    excerpt: str
    score: float
    bboxes: list[dict]

    def viewer_url(self, query: str = "") -> str:
        return viewer_link(
            self.doc_id, self.version, self.page_start, self.clause_id, query
        )


def viewer_link(
    doc_id: str,
    version: str,
    page: int,
    clause_id: str,
    query: str = "",
) -> str:
    url = f"{VIEWER_URL.rstrip('/')}/v/{doc_id}/{version}?page={page}&clause={quote_plus(clause_id)}"
    if query:
        url += f"&q={quote_plus(query)}"
    return url


def _conn(path: Path | None = None):
    db = path or DB_PATH
    if not db.exists():
        raise FileNotFoundError(
            f"Index not found at {db}. Run: python -m sysml_spec_qa ingest"
        )
    return connect(db)


def route(question: str, version: str | None = None, db_path: Path | None = None) -> list[dict]:
    version = version or DEFAULT_VERSION
    terms = expand_query(question)
    conn = _conn(db_path)
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()
    try:
        for term in terms:
            rows = conn.execute(
                """
                SELECT term, kind, doc_id, clause_id
                FROM catalog
                WHERE version = ? AND term_norm = ?
                LIMIT 12
                """,
                (version, fold(term)),
            ).fetchall()
            for row in rows:
                if not row["clause_id"]:
                    continue
                key = (row["doc_id"], row["clause_id"])
                if key in seen:
                    continue
                seen.add(key)
                hits.append(
                    {
                        "term": row["term"],
                        "kind": row["kind"],
                        "doc_id": row["doc_id"],
                        "clause_id": row["clause_id"],
                        "version": version,
                    }
                )
            if len(hits) >= 8:
                break
    finally:
        conn.close()
    return hits[:8]


def search(
    query: str,
    version: str | None = None,
    k: int = MAX_HITS,
    db_path: Path | None = None,
) -> list[Hit]:
    version = version or DEFAULT_VERSION
    k = max(1, min(int(k), 5))
    terms = expand_query(query)
    match = fts_query(terms)
    if not match:
        return []
    conn = _conn(db_path)
    routed = route(query, version, db_path)
    routed_clauses = {(r["doc_id"], r["clause_id"]) for r in routed}
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.doc_id, c.version, c.clause_id, c.title, c.kind, c.normative,
                   c.page_start, c.page_end, c.text, c.bboxes,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ? AND c.version = ?
            ORDER BY rank
            LIMIT 40
            """,
            (match, version),
        ).fetchall()
    except Exception:
        conn.close()
        raise
    scored: list[tuple[int, float, Any]] = []
    for row in rows:
        key = (row["doc_id"], row["clause_id"])
        blob = fold(row["title"] + "\n" + row["text"][:3000])
        overlap = sum(1 for t in terms if len(t) > 3 and fold(t) in blob)
        title_bonus = 2 if any(fold(t) in fold(row["title"]) for t in terms if len(t) > 3) else 0
        route_bonus = 3 if key in routed_clauses else 0
        scored.append((overlap + title_bonus + route_bonus, float(row["rank"]), row))
    scored.sort(key=lambda item: (-item[0], item[1]))

    hits: list[Hit] = []
    remaining = MAX_TOTAL_EXCERPT_WORDS
    for overlap, rank, row in scored:
        if len(hits) >= k:
            break
        budget = min(MAX_EXCERPT_WORDS, remaining)
        if budget < 40:
            break
        snip = excerpt(row["text"], terms, budget)
        remaining -= word_count(snip)
        try:
            bboxes = json.loads(row["bboxes"] or "[]")
        except json.JSONDecodeError:
            bboxes = []
        hits.append(
            Hit(
                doc_id=row["doc_id"],
                version=row["version"],
                clause_id=row["clause_id"],
                title=row["title"],
                kind=row["kind"] or "other",
                normative=bool(row["normative"]),
                page_start=row["page_start"],
                page_end=row["page_end"],
                excerpt=snip,
                score=float(-overlap) + rank,
                bboxes=bboxes,
            )
        )
    conn.close()
    return hits[:k]


def get_clause(
    clause_id: str,
    doc_id: str | None = None,
    version: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    version = version or DEFAULT_VERSION
    conn = _conn(db_path)
    sql = """
        SELECT doc_id, version, clause_id, title, kind, normative,
               page_start, page_end, text, bboxes
        FROM chunks
        WHERE version = ? AND clause_id = ?
    """
    params: list[Any] = [version, clause_id]
    if doc_id:
        sql += " AND doc_id = ?"
        params.append(doc_id)
    sql += " ORDER BY part ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return None
    text = "\n\n".join(row["text"] for row in rows)
    words = text.split()
    truncated = False
    if len(words) > MAX_GET_WORDS:
        text = " ".join(words[:MAX_GET_WORDS]) + " …"
        truncated = True
    first = rows[0]
    try:
        bboxes = json.loads(first["bboxes"] or "[]")
    except json.JSONDecodeError:
        bboxes = []
    return {
        "doc_id": first["doc_id"],
        "version": first["version"],
        "clause_id": first["clause_id"],
        "title": first["title"],
        "kind": first["kind"],
        "normative": bool(first["normative"]),
        "page_start": first["page_start"],
        "page_end": rows[-1]["page_end"],
        "text": text,
        "truncated": truncated,
        "bboxes": bboxes,
        "viewer_url": viewer_link(
            first["doc_id"], version, first["page_start"], first["clause_id"], clause_id
        ),
    }


def get_element(name: str, version: str | None = None, db_path: Path | None = None) -> dict | None:
    version = version or DEFAULT_VERSION
    conn = _conn(db_path)
    needle = fold(name)
    row = conn.execute(
        """
        SELECT name, card_json FROM element_cards
        WHERE version = ? AND name_norm = ?
        """,
        (version, needle),
    ).fetchone()
    if row is None:
        row = conn.execute(
            """
            SELECT name, card_json FROM element_cards
            WHERE version = ? AND name_norm LIKE ?
            ORDER BY length(name_norm) ASC
            LIMIT 1
            """,
            (version, f"%{needle}%"),
        ).fetchone()
    conn.close()
    if row is None:
        return None
    card = json.loads(row["card_json"])
    card["viewer_links"] = []
    for section in ("description_clauses", "syntax_clauses", "other_clauses"):
        for ref in card.get(section, []):
            ref["viewer_url"] = viewer_link(
                ref["doc_id"], version, ref["page"], ref["clause_id"], name
            )
    return card


def list_documents(db_path: Path | None = None) -> list[dict]:
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT id, title, version, family, lang_version, pdf_path FROM documents ORDER BY version, family"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
