from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from .config import (
    DEFAULT_VERSION,
    EUR_PER_MTOK,
    MAX_EXCERPT_WORDS,
    MAX_HITS,
    VIEWER_URL,
)
from .markdown import clause_relpath
from .query import analyze_query
from .search import (
    PassageHit,
    _conn,
    find_exception_passage,
    get_clause,
    reader_link,
    search_passages,
    search_passages_ranked,
)
from .textutil import cite_sentence, estimate_tokens, fit_quote, fold, word_count


def _trim_quote(quote: str, max_words: int = MAX_EXCERPT_WORDS) -> str:
    return fit_quote(quote, max_words)


@dataclass
class CiteRef:
    doc_id: str
    version: str
    clause_id: str
    title: str
    kind: str
    normative: bool
    page_start: int
    quote_en: str
    passage_id: str = ""
    md_path: str = ""
    reader_url: str = ""
    viewer_url: str = ""
    markdown_url: str = ""


@dataclass
class ExampleRef:
    example_id: str
    doc_id: str
    version: str
    clause_id: str
    caption: str
    text: str
    page: int
    viewer_url: str = ""
    reader_url: str = ""


@dataclass
class RetrievalPack:
    question: str
    version: str
    question_language: str
    intents: list[str]
    canonical_terms: list[str]
    primary: CiteRef | None = None
    exception: CiteRef | None = None
    examples: list[ExampleRef] = field(default_factory=list)
    session_url: str = ""
    answer_contract: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.primary is None:
            data["primary"] = None
        if self.exception is None:
            data["exception"] = None
        return data


def pack_link(refs: list[tuple[str, str, str]], query: str = "") -> str:
    """Legacy alias → cites session."""
    return cites_link(refs, query)


def cites_link(refs: list[tuple[str, str, str]], query: str = "", index: int = 0) -> str:
    encoded = ",".join(f"{d}:{v}:{c}" for d, v, c in refs)
    url = f"{VIEWER_URL.rstrip('/')}/cites?ids={quote_plus(encoded)}"
    if query:
        url += f"&q={quote_plus(query)}"
    if index:
        url += f"&i={index}"
    return url


def parse_ref(ref: str) -> tuple[str, str, str] | None:
    parts = ref.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def _passage_to_cite(row: dict, quote: str, query: str = "") -> CiteRef:
    from .markdown import clause_md_url
    from .search import viewer_link

    doc_id = row["doc_id"]
    version = row["version"]
    clause_id = row["clause_id"]
    return CiteRef(
        passage_id=row.get("passage_id") or f"{doc_id}:{clause_id}",
        doc_id=doc_id,
        version=version,
        clause_id=clause_id,
        title=row["title"],
        kind=row.get("kind") or "other",
        normative=bool(row["normative"]),
        page_start=row["page_start"],
        quote_en=quote,
        md_path=clause_relpath(version, doc_id, clause_id, row["title"]),
        reader_url=reader_link(doc_id, version, clause_id, query, quote=quote),
        viewer_url=viewer_link(
            doc_id, version, row["page_start"], clause_id, query, quote=quote
        ),
        markdown_url=clause_md_url(doc_id, version, clause_id, query),
    )


def _hit_to_row(hit) -> dict:
    return {
        "passage_id": hit.passage_id,
        "doc_id": hit.doc_id,
        "version": hit.version,
        "clause_id": hit.clause_id,
        "title": hit.title,
        "kind": hit.kind,
        "normative": hit.normative,
        "page_start": hit.page_start,
    }


def search_examples(
    query: str,
    version: str | None = None,
    k: int = 3,
    db_path: Path | None = None,
) -> list[ExampleRef]:
    from .textutil import fts_query

    version = version or DEFAULT_VERSION
    analysis = analyze_query(query)
    match = fts_query(analysis["terms"])
    if not match:
        return []
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT e.example_id, e.doc_id, e.version, e.clause_id, e.caption, e.page, e.text,
                   bm25(examples_fts) AS rank
            FROM examples_fts
            JOIN examples e ON e.id = examples_fts.rowid
            WHERE examples_fts MATCH ? AND e.version = ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, version, k * 3),
        ).fetchall()
    finally:
        conn.close()
    out: list[ExampleRef] = []
    for row in rows[:k]:
        from .search import viewer_link

        out.append(
            ExampleRef(
                example_id=row["example_id"],
                doc_id=row["doc_id"],
                version=row["version"],
                clause_id=row["clause_id"],
                caption=row["caption"] or "",
                text=row["text"],
                page=row["page"] or 1,
                viewer_url=viewer_link(row["doc_id"], version, row["page"] or 1, row["clause_id"], query),
                reader_url=reader_link(row["doc_id"], version, row["clause_id"], query),
            )
        )
    return out


def _refine_quote(hit, analysis: dict, db_path):
    if not hit:
        return hit
    row = get_clause(hit.clause_id, doc_id=hit.doc_id, version=hit.version, db_path=db_path)
    if not row:
        return hit
    from .search import get_clause_text

    body = row.get("full_text") or get_clause_text(
        hit.clause_id, hit.doc_id, hit.version, db_path
    )
    terms = list(analysis.get("terms") or [])
    if "name_resolution" in analysis.get("intents", []):
        terms.extend(["unique", "distinguishable", "membership", "namespace"])
    if "constraint" in analysis.get("intents", []):
        terms.extend(["distinguishable", "distinguish", "validate", "check", "membership"])
    hit.quote_en = _trim_quote(cite_sentence(body, terms, max_words=MAX_EXCERPT_WORDS))
    return hit


def _hit_from_clause(clause_id: str, doc_id: str | None, version: str, question: str, analysis: dict, db_path):
    from .search import get_clause_text

    row = get_clause(clause_id, doc_id=doc_id, version=version, db_path=db_path)
    if not row:
        return None
    body = row.get("full_text") or get_clause_text(clause_id, doc_id or row["doc_id"], version, db_path)
    terms = list(analysis.get("terms") or [])
    if "name_resolution" in analysis.get("intents", []):
        terms.extend(["unique", "distinguishable", "membership", "namespace"])
    if "constraint" in analysis.get("intents", []):
        terms.extend(["distinguishable", "distinguish", "validate", "check", "membership"])
    quote = cite_sentence(body, terms, max_words=MAX_EXCERPT_WORDS)
    return PassageHit(
        passage_id=f"{row['doc_id']}:{row['clause_id']}:pinned",
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


def _pick_primary(ranked: list, analysis: dict) -> PassageHit | None:
    if not ranked:
        return None
    if analysis.get("wants_kerml"):
        for hit in ranked:
            if hit.doc_id.startswith("kerml-"):
                return hit
        return ranked[0]
    for hit in ranked:
        if hit.doc_id.startswith("sysml-"):
            return hit
    return ranked[0]


def _constraint_pinned_hit(question: str, version: str, analysis: dict, db_path):
    conn = _conn(db_path)
    try:
        folded_q = fold(question).replace(" ", "")
        rows = conn.execute(
            """
            SELECT name, doc_id, clause_id FROM constraints
            WHERE version = ? AND lower(name) LIKE ?
            ORDER BY length(name) ASC
            LIMIT 4
            """,
            (version, f"%{folded_q[:48]}%"),
        ).fetchall()
        for row in rows:
            if not row["clause_id"]:
                continue
            hit = _hit_from_clause(row["clause_id"], row["doc_id"], version, question, analysis, db_path)
            if hit:
                return hit
    finally:
        conn.close()
    return None


def _sysml_namespace_primary(version: str, analysis: dict, db_path) -> PassageHit | None:
    """Informative SysML namespace membership clause (SysML-first for name/constraint questions)."""
    for clause_id in ("7.5.2", "7.5.1", "7.5.3"):
        hit = _hit_from_clause(
            clause_id, "sysml-2.0-language", version, "", analysis, db_path
        )
        if hit and word_count(hit.quote_en) >= 25:
            return hit
    return None


def _upgrade_sysml_primary(primary_hit, analysis: dict, version: str, db_path):
    """Prefer a substantive SysML clause over empty notation headings."""
    if not primary_hit or analysis.get("wants_kerml"):
        return primary_hit
    intents = set(analysis.get("intents", []))
    if not intents & {"name_resolution", "constraint"}:
        return primary_hit
    row = get_clause(
        primary_hit.clause_id, doc_id=primary_hit.doc_id, version=version, db_path=db_path
    )
    body = (row or {}).get("full_text") or (row or {}).get("text") or ""
    if word_count(body) >= 40 and word_count(primary_hit.quote_en) >= 25:
        return primary_hit
    upgraded = _sysml_namespace_primary(version, analysis, db_path)
    return upgraded or primary_hit


def _maybe_sysml_constraint_primary(primary_hit, analysis: dict, question: str, version: str, db_path):
    """Keep SysML primary; never promote KerML constraint clauses to primary."""
    if not primary_hit or analysis.get("wants_kerml"):
        return primary_hit
    if "constraint" in analysis.get("intents", []):
        pinned = _constraint_pinned_hit(question, version, analysis, db_path)
        if pinned and pinned.doc_id.startswith("sysml-"):
            return pinned
        if pinned and pinned.doc_id.startswith("kerml-"):
            upgraded = _sysml_namespace_primary(version, analysis, db_path)
            if upgraded:
                return upgraded
    return primary_hit


def _build_answer_contract(analysis: dict, has_exception: bool) -> dict:
    kind = analysis.get("answer_kind") or "verdict"
    if kind == "list":
        shape = ["list", "rule", "conclusion", "cost"]
    else:
        shape = ["verdict", "rule", "conclusion", "cost"]
    if has_exception:
        shape.insert(2, "exception")
    lang = analysis["language"]
    if lang == "fr":
        citation_note = (
            "Dans le chat, cite uniquement les morceaux des points marqués (quote_en du pack), "
            "pas la clause entière. L'encadré markdown (blockquote) contient uniquement la spec "
            "dans sa langue d'origine : « quote_en anglais » + métadonnées (doc, clause, lien). "
            "Aucun français dans l'encadré — pas de « La spec : », pas de *Traduction :*. "
            "Prose française et *Traduction :* toujours hors encadré."
        )
        if kind == "list":
            citation_note += (
                " Question d'inventaire : ouvrir par une liste à puces dérivée du quote_en. "
                "Ne pas commencer par Oui/Non."
            )
            format_md = (
                "**[Éléments.]** [une phrase d'intro — hors encadré]\n"
                "\n"
                "- `item` — [rôle]\n"
                "- `item` — [rôle]\n"
                "\n"
                "> « [quote_en exact, anglais] »\n"
                "> (`[doc]` `[clause]`, informative|normative) — [session_url]\n"
                "\n"
                "*Traduction :* [traduction fidèle — hors encadré]\n"
                "\n"
                "**Conclusion :** [phrase opérationnelle.]\n"
                "\n"
                "---\n"
                "*{footer_fr}*"
            )
        else:
            format_md = (
                "**[Verdict.]** [règle en prose française — hors encadré]\n"
                "\n"
                "> « [quote_en exact, anglais] »\n"
                "> (`[doc]` `[clause]`, informative|normative) — [session_url]\n"
                "\n"
                "*Traduction :* [traduction fidèle — hors encadré]\n"
                "\n"
                "> **Exception** *(si fournie)*\n"
                ">\n"
                "> [explication française — hors encadré de citation]\n"
                ">\n"
                "> > « [exception quote_en, anglais] »\n"
                "> > (`[doc]` `[clause]`, informative|normative)\n"
                ">\n"
                "> *Traduction :* [traduction fidèle de l'exception]\n"
                "\n"
                "**Conclusion :** [phrase opérationnelle.]\n"
                "\n"
                "---\n"
                "*{footer_fr}*"
            )
    else:
        citation_note = (
            "In chat, cite only the marked passage excerpts (pack quote_en), not the whole "
            "clause. Markdown blockquote = original-language spec only (verbatim quote_en + "
            "doc/clause/link). Explanation prose outside the blockquote."
        )
        if kind == "list":
            citation_note += " Inventory question: lead with a bullet list. Do not start with Yes/No."
            format_md = (
                "**[Elements.]** [one intro sentence — outside blockquote]\n"
                "\n"
                "- `item` — [role]\n"
                "- `item` — [role]\n"
                "\n"
                "> « [exact quote_en] »\n"
                "> (`[doc]` `[clause]`, informative|normative) — [session_url]\n"
                "\n"
                "**Conclusion:** [one operational sentence.]\n"
                "\n"
                "---\n"
                "*{footer_en}*"
            )
        else:
            format_md = (
                "**[Verdict.]** [rule in one sentence — outside blockquote]\n"
                "\n"
                "> « [exact quote_en] »\n"
                "> (`[doc]` `[clause]`, informative|normative) — [session_url]\n"
                "\n"
                "> **Exception** *(if provided)*\n"
                ">\n"
                "> [condition explanation — outside citation blockquote]\n"
                ">\n"
                "> > « [exception quote_en] »\n"
                "> > (`[doc]` `[clause]`, informative|normative)\n"
                "\n"
                "**Conclusion:** [one operational sentence.]\n"
                "\n"
                "---\n"
                "*{footer_en}*"
            )
    return {
        "shape": shape,
        "kind": kind,
        "language": lang,
        "citation": citation_note,
        "format_markdown": format_md,
        "prefer_sysml_over_kerml": analysis.get("prefer_sysml", True),
        "cite_kerml_only_when": (
            "user explicitly mentions KerML, or SysML has no applicable passage"
        ),
        "include_examples_only_when_asked": True,
    }


def _pack_cost(token_est: int, retrieval_ms: int) -> dict:
    eur = round(token_est / 1_000_000 * EUR_PER_MTOK, 6)
    footer_fr = (
        f"recherche {retrieval_ms} ms · extraits spec ~{token_est} tok "
        f"(quote_en des points marqués uniquement) · index local gratuit "
        f"— hors tour Cursor/Composer"
    )
    footer_en = (
        f"retrieval {retrieval_ms} ms · spec excerpts ~{token_est} tok "
        f"(marked quote_en only) · local index free "
        f"— excludes Cursor/Composer turn"
    )
    return {
        "retrieval_ms": retrieval_ms,
        "pack_tokens": token_est,
        "excerpt_tokens": token_est,
        "estimated_eur": eur,
        "note": (
            "excerpt_tokens counts primary/exception quote_en only; "
            "not the full agent turn billed by Cursor"
        ),
        "footer_fr": footer_fr,
        "footer_en": footer_en,
    }


def answer_pack(
    question: str,
    version: str | None = None,
    k: int = MAX_HITS,
    include_examples: bool | None = None,
    db_path: Path | None = None,
) -> RetrievalPack:
    t0 = time.perf_counter()
    version = version or DEFAULT_VERSION
    analysis = analyze_query(question)
    if include_examples is None:
        include_examples = analysis["wants_examples"]

    ranked = search_passages_ranked(question, version=version, k=max(k, 8), db_path=db_path)
    primary_hit = _pick_primary(ranked, analysis)
    primary_hit = _maybe_sysml_constraint_primary(
        primary_hit, analysis, question, version, db_path
    )
    primary_hit = _upgrade_sysml_primary(primary_hit, analysis, version, db_path)
    primary_ref: CiteRef | None = None
    exception_ref: CiteRef | None = None

    if primary_hit:
        primary_hit = _refine_quote(primary_hit, analysis, db_path)
        primary_hit.quote_en = _trim_quote(primary_hit.quote_en)
        primary_ref = _passage_to_cite(_hit_to_row(primary_hit), primary_hit.quote_en, question)
        if analysis.get("answer_kind") != "list":
            exc_hit = find_exception_passage(
                primary_hit,
                ranked[1:],
                question,
                version=version,
                db_path=db_path,
            )
            if exc_hit:
                exc_hit = _refine_quote(exc_hit, analysis, db_path)
                exc_hit.quote_en = _trim_quote(exc_hit.quote_en)
                exception_ref = _passage_to_cite(_hit_to_row(exc_hit), exc_hit.quote_en, question)
            elif "constraint" in analysis.get("intents", []):
                pinned = _constraint_pinned_hit(question, version, analysis, db_path)
                if pinned and pinned.doc_id.startswith("kerml-"):
                    pinned = _refine_quote(pinned, analysis, db_path)
                    pinned.quote_en = _trim_quote(pinned.quote_en)
                    exception_ref = _passage_to_cite(_hit_to_row(pinned), pinned.quote_en, question)

    examples: list[ExampleRef] = []
    if include_examples:
        examples = search_examples(question, version=version, k=3, db_path=db_path)

    refs: list[tuple[str, str, str]] = []
    if primary_ref:
        refs.append((primary_ref.doc_id, primary_ref.version, primary_ref.clause_id))
    if exception_ref:
        refs.append((exception_ref.doc_id, exception_ref.version, exception_ref.clause_id))

    token_est = 0
    if primary_ref:
        token_est += estimate_tokens(primary_ref.quote_en)
    if exception_ref:
        token_est += estimate_tokens(exception_ref.quote_en)
    token_est += sum(estimate_tokens(e.text) for e in examples)

    retrieval_ms = int((time.perf_counter() - t0) * 1000)

    return RetrievalPack(
        question=question,
        version=version,
        question_language=analysis["language"],
        intents=analysis["intents"],
        canonical_terms=analysis["terms"],
        primary=primary_ref,
        exception=exception_ref,
        examples=examples,
        session_url=cites_link(refs, question) if refs else "",
        answer_contract=_build_answer_contract(analysis, exception_ref is not None),
        cost=_pack_cost(token_est, retrieval_ms),
    )


def clause_pack(
    clause_ids: list[str],
    doc_id: str | None = None,
    version: str | None = None,
    query: str = "",
    db_path: Path | None = None,
) -> dict[str, Any]:
    version = version or DEFAULT_VERSION
    refs: list[CiteRef] = []
    for clause_id in clause_ids:
        row = get_clause(clause_id, doc_id=doc_id, version=version, db_path=db_path)
        if not row:
            continue
        quote = row["text"]
        words = quote.split()
        if len(words) > MAX_EXCERPT_WORDS:
            quote = " ".join(words[:MAX_EXCERPT_WORDS]) + " …"
        refs.append(_passage_to_cite(row, quote, query))
    pack_refs = [(r.doc_id, r.version, r.clause_id) for r in refs]
    return {
        "version": version,
        "passages": [asdict(r) for r in refs],
        "session_url": cites_link(pack_refs, query) if pack_refs else "",
        "pack_url": cites_link(pack_refs, query) if pack_refs else "",
        "token_estimate": sum(estimate_tokens(r.quote_en) for r in refs),
    }


def resolve_cites(
    refs: list[str],
    query: str = "",
    db_path: Path | None = None,
) -> dict[str, Any]:
    items: list[dict] = []
    for ref in refs:
        parsed = parse_ref(ref.strip())
        if not parsed:
            continue
        doc_id, version, clause_id = parsed
        row = get_clause(clause_id, doc_id=doc_id, version=version, db_path=db_path)
        if not row:
            continue
        from .textutil import cite_sentence
        from .query import analyze_query

        from .search import get_clause_text

        terms = analyze_query(query)["terms"] if query else []
        body = row.get("full_text") or get_clause_text(
            clause_id, doc_id, version, db_path
        )
        quote = (
            cite_sentence(body, terms, max_words=MAX_EXCERPT_WORDS)
            if terms
            else body[:800]
        )
        pref = _passage_to_cite(row, quote, query)
        items.append(asdict(pref))
    return {
        "query": query,
        "refs": refs,
        "items": items,
        "count": len(items),
    }


def resolve_pack(refs: list[str], query: str = "", db_path: Path | None = None) -> dict[str, Any]:
    """Legacy alias for resolve_cites."""
    return resolve_cites(refs, query=query, db_path=db_path)
