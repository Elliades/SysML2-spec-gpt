from __future__ import annotations

import json
import re
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
    MIN_EXCERPT_WORDS,
    SYSML_SCORE_THRESHOLD,
    VIEWER_URL,
)
from .db import connect
from .query import analyze_query
from .synonyms import expand_query
from .textutil import cite_sentence, excerpt, fold, fts_query, word_count

EXCEPTION_HINT = re.compile(
    r"\b(except|exception|unless|however|provided that|not required)\b",
    re.I,
)


@dataclass
class PassageHit:
    passage_id: str
    doc_id: str
    version: str
    clause_id: str
    title: str
    kind: str
    normative: bool
    page_start: int
    page_end: int
    quote_en: str
    score: float
    bboxes: list[dict]
    md_path: str = ""
    overlap_score: int = 0

    def viewer_url(self, query: str = "") -> str:
        return viewer_link(
            self.doc_id,
            self.version,
            self.page_start,
            self.clause_id,
            query,
            quote=self.quote_en,
        )

    def reader_url(self, query: str = "") -> str:
        return reader_link(
            self.doc_id, self.version, self.clause_id, query, quote=self.quote_en
        )


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
    md_path: str = ""

    def viewer_url(self, query: str = "") -> str:
        return viewer_link(
            self.doc_id,
            self.version,
            self.page_start,
            self.clause_id,
            query,
            quote=self.excerpt,
        )

    def reader_url(self, query: str = "") -> str:
        return reader_link(
            self.doc_id, self.version, self.clause_id, query, quote=self.excerpt
        )

    def markdown_url(self, query: str = "") -> str:
        from .markdown import clause_md_url

        return clause_md_url(self.doc_id, self.version, self.clause_id, query)


def reader_link(
    doc_id: str,
    version: str,
    clause_id: str,
    query: str = "",
    quote: str = "",
) -> str:
    url = f"{VIEWER_URL.rstrip('/')}/r/{doc_id}/{version}/{quote_plus(clause_id)}"
    params: list[str] = []
    if query:
        params.append(f"q={quote_plus(query)}")
    if quote.strip():
        params.append(f"quote={quote_plus(quote.strip())}")
    if params:
        url += "?" + "&".join(params)
    return url


def viewer_link(
    doc_id: str,
    version: str,
    page: int,
    clause_id: str,
    query: str = "",
    quote: str = "",
) -> str:
    url = (
        f"{VIEWER_URL.rstrip('/')}/v/{doc_id}/{version}"
        f"?page={page}&clause={quote_plus(clause_id)}"
    )
    if query:
        url += f"&q={quote_plus(query)}"
    if quote.strip():
        url += f"&quote={quote_plus(quote.strip())}"
    return url


def _conn(path: Path | None = None):
    db = path or DB_PATH
    if not db.exists():
        raise FileNotFoundError(
            f"Index not found at {db}. Run: python -m sysml_spec_qa ingest"
        )
    return connect(db)


def _has_passages(conn) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='passages'"
        ).fetchone()
        if not row:
            return False
        return conn.execute("SELECT COUNT(*) FROM passages").fetchone()[0] > 0
    except Exception:
        return False


def _score_row(row, terms: list[str], routed_clauses: set[tuple[str, str]], analysis: dict) -> int:
    key = (row["doc_id"], row["clause_id"])
    blob = fold(row["title"] + "\n" + row["text"][:3000])
    overlap = sum(1 for t in terms if len(t) > 2 and fold(t) in blob)
    title_bonus = 3 if any(fold(t) in fold(row["title"]) for t in terms if len(t) > 2) else 0
    route_bonus = 8 if key in routed_clauses else 0
    title_penalty = 0
    if "name_resolution" in analysis.get("intents", []) and "abstract syntax" in fold(row["title"]):
        title_penalty = 4
    norm_bonus = 3 if analysis["wants_normative"] and row["normative"] else 0
    doc_id = row["doc_id"]
    if analysis.get("wants_kerml") and doc_id.startswith("kerml-"):
        doc_bonus = 5
    elif analysis.get("prefer_sysml", True) and doc_id.startswith("sysml-"):
        doc_bonus = 5
    else:
        doc_bonus = 0
    return overlap + title_bonus + route_bonus + norm_bonus + doc_bonus - title_penalty


def _apply_sysml_first(
    scored: list[tuple[int, float, Any]],
    analysis: dict,
) -> list[tuple[int, float, Any]]:
    """SysML-only ranking unless the user explicitly asked for KerML or there is no SysML hit."""
    if analysis.get("wants_kerml"):
        return scored
    sysml = [item for item in scored if item[2]["doc_id"].startswith("sysml-")]
    if sysml:
        return sysml
    return scored


def _fetch_passage_rows(conn, match: str, version: str, use_passages: bool) -> list[Any]:
    if use_passages:
        return conn.execute(
            """
            SELECT p.id, p.passage_id, p.doc_id, p.version, p.clause_id, p.title, p.kind,
                   p.normative, p.page_start, p.page_end, p.text, p.bboxes,
                   bm25(passages_fts) AS rank
            FROM passages_fts
            JOIN passages p ON p.id = passages_fts.rowid
            WHERE passages_fts MATCH ? AND p.version = ?
            ORDER BY rank
            LIMIT 50
            """,
            (match, version),
        ).fetchall()
    return conn.execute(
        """
        SELECT c.id, c.doc_id || ':' || c.clause_id || ':' || c.part AS passage_id,
               c.doc_id, c.version, c.clause_id, c.title, c.kind, c.normative,
               c.page_start, c.page_end, c.text, c.bboxes,
               bm25(chunks_fts) AS rank
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        WHERE chunks_fts MATCH ? AND c.version = ?
        ORDER BY rank
        LIMIT 50
        """,
        (match, version),
    ).fetchall()


def search_passages_ranked(
    query: str,
    version: str | None = None,
    k: int = MAX_HITS,
    db_path: Path | None = None,
    family: str | None = None,
) -> list[PassageHit]:
    version = version or DEFAULT_VERSION
    k = max(1, min(int(k), 12))
    analysis = analyze_query(query)
    terms = analysis["terms"] or expand_query(query)
    match = fts_query(terms)
    if not match:
        return []
    conn = _conn(db_path)
    routed = route(query, version, db_path)
    routed_clauses = {(r["doc_id"], r["clause_id"]) for r in routed}
    use_passages = _has_passages(conn)
    try:
        rows = _fetch_passage_rows(conn, match, version, use_passages)
    except Exception:
        conn.close()
        raise
    scored: list[tuple[int, float, Any]] = []
    for row in rows:
        bonus = _score_row(row, terms, routed_clauses, analysis)
        scored.append((bonus, float(row["rank"]), row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if family == "kerml":
        scored = [item for item in scored if item[2]["doc_id"].startswith("kerml-")]
    elif family == "sysml":
        scored = [item for item in scored if item[2]["doc_id"].startswith("sysml-")]
    else:
        scored = _apply_sysml_first(scored, analysis)

    from .markdown import clause_relpath

    hits: list[PassageHit] = []
    remaining = MAX_TOTAL_EXCERPT_WORDS
    seen: set[str] = set()
    for overlap, rank, row in scored:
        if len(hits) >= k:
            break
        pid = row["passage_id"]
        if pid in seen:
            continue
        seen.add(pid)
        budget = min(MAX_EXCERPT_WORDS, remaining)
        if budget < MIN_EXCERPT_WORDS:
            break
        snip = cite_sentence(row["text"], terms, max_words=budget, min_words=MIN_EXCERPT_WORDS)
        remaining -= word_count(snip)
        try:
            bboxes = json.loads(row["bboxes"] or "[]")
        except json.JSONDecodeError:
            bboxes = []
        hits.append(
            PassageHit(
                passage_id=pid,
                doc_id=row["doc_id"],
                version=row["version"],
                clause_id=row["clause_id"],
                title=row["title"],
                kind=row["kind"] or "other",
                normative=bool(row["normative"]),
                page_start=row["page_start"],
                page_end=row["page_end"],
                quote_en=snip,
                score=float(-overlap) + rank,
                bboxes=bboxes,
                md_path=clause_relpath(row["version"], row["doc_id"], row["clause_id"], row["title"]),
                overlap_score=overlap,
            )
        )
    conn.close()
    return hits


def search_passages(
    query: str,
    version: str | None = None,
    k: int = MAX_HITS,
    db_path: Path | None = None,
) -> list[PassageHit]:
    return search_passages_ranked(query, version=version, k=k, db_path=db_path)


def _kerml_foundation_exception(
    primary: PassageHit,
    other_hits: list[PassageHit],
    analysis: dict,
    version: str,
    db_path: Path | None,
) -> PassageHit | None:
    """KerML normative foundation when SysML is primary but the rule is in KerML."""
    primary_key = (primary.doc_id, primary.clause_id)
    for hit in other_hits:
        if hit.doc_id.startswith("kerml-") and (hit.doc_id, hit.clause_id) != primary_key:
            return hit
    terms = list(analysis.get("terms") or []) + ["unique", "distinguishable", "membership"]
    for clause_id in ("8.3.2.4.5", "7.2.5"):
        row = get_clause(clause_id, version=version, db_path=db_path)
        if not row or not row["doc_id"].startswith("kerml-"):
            continue
        body = row.get("full_text") or get_clause_text(
            clause_id, row["doc_id"], version, db_path
        )
        quote = cite_sentence(body, terms, max_words=MAX_EXCERPT_WORDS)
        if any(t in fold(quote) for t in ("unique", "distinguishable", "membership", "must")):
            return PassageHit(
                passage_id=f"{row['doc_id']}:{row['clause_id']}:kerml_exc",
                doc_id=row["doc_id"],
                version=row["version"],
                clause_id=row["clause_id"],
                title=row["title"],
                kind=row.get("kind") or "other",
                normative=bool(row["normative"]),
                page_start=row["page_start"],
                page_end=row["page_end"],
                quote_en=quote,
                score=0.0,
                bboxes=row.get("bboxes") or [],
            )
    return None


def find_exception_passage(
    primary: PassageHit,
    other_hits: list[PassageHit],
    query: str,
    version: str | None = None,
    db_path: Path | None = None,
) -> PassageHit | None:
    version = version or DEFAULT_VERSION
    analysis = analyze_query(query)
    primary_key = (primary.doc_id, primary.clause_id)
    intents = set(analysis.get("intents", []))
    wants_kerml_foundation = (
        primary.doc_id.startswith("sysml-")
        and not analysis.get("wants_kerml")
        and bool(intents & {"name_resolution", "constraint"})
    )
    if wants_kerml_foundation:
        exc = _kerml_foundation_exception(
            primary, other_hits, analysis, version, db_path
        )
        if exc:
            return exc

    for hit in other_hits:
        if (hit.doc_id, hit.clause_id) == primary_key:
            continue
        if primary.doc_id.startswith("sysml-") and hit.doc_id.startswith("kerml-"):
            continue
        blob = f"{hit.title}\n{hit.quote_en}"
        if EXCEPTION_HINT.search(blob):
            return hit

    conn = _conn(db_path)
    try:
        xrefs = conn.execute(
            """
            SELECT target_clause_id, context FROM cross_refs
            WHERE version = ? AND source_doc_id = ? AND source_clause_id = ?
            LIMIT 8
            """,
            (version, primary.doc_id, primary.clause_id),
        ).fetchall()
        for xref in xrefs:
            blob = xref["context"] or ""
            if not EXCEPTION_HINT.search(blob):
                continue
            target = xref["target_clause_id"]
            for hit in other_hits:
                if hit.clause_id == target:
                    return hit
            row = get_clause(target, doc_id=primary.doc_id, version=version, db_path=db_path)
            if not row:
                row = get_clause(target, version=version, db_path=db_path)
            if row and (row["doc_id"], row["clause_id"]) != primary_key:
                terms = analyze_query(query)["terms"]
                quote = cite_sentence(row["text"], terms, max_words=MAX_EXCERPT_WORDS)
                return PassageHit(
                    passage_id=f"{row['doc_id']}:{row['clause_id']}:exc",
                    doc_id=row["doc_id"],
                    version=row["version"],
                    clause_id=row["clause_id"],
                    title=row["title"],
                    kind=row.get("kind") or "other",
                    normative=bool(row["normative"]),
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    quote_en=quote,
                    score=0.0,
                    bboxes=row.get("bboxes") or [],
                )

        if "constraint" not in intents:
            return None
        analysis = analyze_query(query)
        for term in analysis["terms"]:
            rows = conn.execute(
                """
                SELECT name, doc_id, clause_id, page, text FROM constraints
                WHERE version = ? AND name LIKE ?
                LIMIT 4
                """,
                (version, f"%{term}%"),
            ).fetchall()
            for row in rows:
                if not row["clause_id"]:
                    continue
                key = (row["doc_id"], row["clause_id"])
                if key == primary_key:
                    continue
                clause = get_clause(row["clause_id"], doc_id=row["doc_id"], version=version, db_path=db_path)
                if not clause:
                    continue
                terms = analysis["terms"]
                quote = cite_sentence(clause["text"], terms, max_words=MAX_EXCERPT_WORDS)
                return PassageHit(
                    passage_id=f"{clause['doc_id']}:{clause['clause_id']}:constraint",
                    doc_id=clause["doc_id"],
                    version=clause["version"],
                    clause_id=clause["clause_id"],
                    title=clause["title"],
                    kind=clause.get("kind") or "constraint",
                    normative=bool(clause["normative"]),
                    page_start=clause["page_start"],
                    page_end=clause["page_end"],
                    quote_en=quote,
                    score=0.0,
                    bboxes=clause.get("bboxes") or [],
                )
    finally:
        conn.close()
    return None


def route(question: str, version: str | None = None, db_path: Path | None = None) -> list[dict]:
    version = version or DEFAULT_VERSION
    terms = expand_query(question)
    conn = _conn(db_path)
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_hit(doc_id: str | None, clause_id: str | None, term: str, kind: str) -> None:
        if not doc_id or not clause_id:
            return
        key = (doc_id, clause_id)
        if key in seen:
            return
        seen.add(key)
        hits.append(
            {
                "term": term,
                "kind": kind,
                "doc_id": doc_id,
                "clause_id": clause_id,
                "version": version,
            }
        )

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
                add_hit(row["doc_id"], row["clause_id"], row["term"], row["kind"])
            if len(hits) >= 8:
                break

        folded_q = fold(question).replace(" ", "")
        if "validate" in folded_q or "check" in folded_q:
            rows = conn.execute(
                """
                SELECT name, doc_id, clause_id FROM constraints
                WHERE version = ? AND lower(name) LIKE ?
                LIMIT 6
                """,
                (version, f"%{folded_q[:48]}%"),
            ).fetchall()
            for row in rows:
                add_hit(row["doc_id"], row["clause_id"], row["name"], "constraint")

        for term in terms:
            if len(hits) >= 10:
                break
            rows = conn.execute(
                """
                SELECT name, doc_id, clause_id FROM constraints
                WHERE version = ? AND (name LIKE ? OR name LIKE ?)
                LIMIT 6
                """,
                (version, f"%{term}%", f"%{fold(term)}%"),
            ).fetchall()
            for row in rows:
                add_hit(row["doc_id"], row["clause_id"], row["name"], "constraint")

        for match in __import__("re").finditer(
            r"\b([A-Z][a-z]+(?:Usage|Definition|Connector|Namespace))\b", question
        ):
            name = match.group(1)
            card_row = conn.execute(
                """
                SELECT card_json FROM element_cards
                WHERE version = ? AND name_norm = ?
                """,
                (version, fold(name)),
            ).fetchone()
            if not card_row:
                continue
            card = json.loads(card_row["card_json"])
            for section in ("syntax_clauses", "description_clauses", "other_clauses"):
                for ref in card.get(section, [])[:2]:
                    add_hit(ref.get("doc_id"), ref.get("clause_id"), name, "element")
    finally:
        conn.close()
    return hits[:10]


def search(
    query: str,
    version: str | None = None,
    k: int = MAX_HITS,
    db_path: Path | None = None,
) -> list[Hit]:
    """Unified search via passages."""
    passages = search_passages(query, version=version, k=k, db_path=db_path)
    return [
        Hit(
            doc_id=p.doc_id,
            version=p.version,
            clause_id=p.clause_id,
            title=p.title,
            kind=p.kind,
            normative=p.normative,
            page_start=p.page_start,
            page_end=p.page_end,
            excerpt=p.quote_en,
            score=p.score,
            bboxes=p.bboxes,
            md_path=p.md_path,
        )
        for p in passages
    ]


def get_clause_text(
    clause_id: str,
    doc_id: str | None = None,
    version: str | None = None,
    db_path: Path | None = None,
) -> str:
    """Full clause text from all chunk parts (no truncation)."""
    version = version or DEFAULT_VERSION
    conn = _conn(db_path)
    sql = """
        SELECT text FROM chunks
        WHERE version = ? AND clause_id = ?
    """
    params: list[Any] = [version, clause_id]
    if doc_id:
        sql += " AND doc_id = ?"
        params.append(doc_id)
    sql += " ORDER BY part ASC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return "\n\n".join(row["text"] for row in rows)


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
    from .markdown import clause_md_url, clause_relpath

    full_text = "\n\n".join(row["text"] for row in rows)
    words = full_text.split()
    truncated = False
    text = full_text
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
        "full_text": full_text,
        "truncated": truncated,
        "bboxes": bboxes,
        "viewer_url": viewer_link(
            first["doc_id"], version, first["page_start"], first["clause_id"], clause_id
        ),
        "reader_url": reader_link(first["doc_id"], version, first["clause_id"], clause_id),
        "md_path": clause_relpath(
            version, first["doc_id"], first["clause_id"], first["title"]
        ),
        "markdown_url": clause_md_url(
            first["doc_id"], version, first["clause_id"], clause_id
        ),
    }


def get_toc(
    doc_id: str,
    version: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    version = version or DEFAULT_VERSION
    conn = _conn(db_path)
    try:
        has_toc = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='toc'"
        ).fetchone()
        if has_toc:
            rows = conn.execute(
                """
                SELECT clause_id, parent_id, title, depth, page_start, normative
                FROM toc
                WHERE doc_id = ? AND version = ?
                ORDER BY sort_key
                """,
                (doc_id, version),
            ).fetchall()
            return [dict(row) for row in rows]
        rows = conn.execute(
            """
            SELECT DISTINCT clause_id, title, page_start, normative
            FROM chunks
            WHERE doc_id = ? AND version = ?
            ORDER BY clause_id
            """,
            (doc_id, version),
        ).fetchall()
        out = []
        for row in rows:
            cid = row["clause_id"]
            parts = cid.split(".")
            parent = ".".join(parts[:-1]) if len(parts) > 1 else None
            out.append(
                {
                    "clause_id": cid,
                    "parent_id": parent,
                    "title": row["title"],
                    "depth": len(parts),
                    "page_start": row["page_start"],
                    "normative": bool(row["normative"]),
                }
            )
        return out
    finally:
        conn.close()


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
    for section in ("description_clauses", "syntax_clauses", "other_clauses"):
        for ref in card.get(section, []):
            ref["viewer_url"] = viewer_link(
                ref["doc_id"], version, ref["page"], ref["clause_id"], name
            )
            ref["reader_url"] = reader_link(
                ref["doc_id"], version, ref["clause_id"], name
            )
    return card


def list_documents(db_path: Path | None = None) -> list[dict]:
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT id, title, version, family, lang_version, pdf_path FROM documents ORDER BY version, family"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
