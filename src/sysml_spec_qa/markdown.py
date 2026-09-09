from __future__ import annotations

import html
import re
import shutil
from pathlib import Path
from typing import Any

import mistune

from .config import DB_PATH, MD_DIR
from .db import connect
from .search import reader_link, viewer_link
from .textutil import fold, parse_clause_title

_md = mistune.create_markdown(escape=False, plugins=["strikethrough", "table"])

PAGE_HEADER_RE = re.compile(
    r"^(?:Systems Modeling Language v2\.0, Part \d+|Kernel Modeling Language v[\d.]+)$",
    re.I,
)
PAGE_NUM_ONLY = re.compile(r"^\d{1,4}$")
CLAUSE_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\s+\S")
CODE_BLOCK_START = re.compile(
    r"^(?:(?:abstract\s+)?(?:(?:flow|part|action|attribute|item|connection|interface|port|enum|metadata|view|occurrence)\s+def\b)|"
    r"(?:succession\s+flow|message|flow)\b|"
    r"package\s+\w|"
    r"(?:derive|validate|check)[A-Z]\w*|"
    r"membership->|"
    r"//)",
    re.I,
)
CODE_BLOCK_INNER = re.compile(
    r"^(?:end\b|in\b|out\b|ref\b|item\b|part\b|action\b|attribute\b|event occurrence|abstract flow|flow f|flow subsets|"
    r"//|\{|\}|redefines|:>>|::>|references|subsets|\w+\s*:\s*\w+\s+subsets)",
    re.I,
)
PROSE_WRAP_CONT = re.compile(r"[^.!?;:}\]]\s*$")
PROSE_WRAP_NEXT = re.compile(r"^[a-z(]")


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :].lstrip("\n")
    return text


def _is_page_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if PAGE_HEADER_RE.match(stripped):
        return True
    if PAGE_NUM_ONLY.match(stripped):
        return True
    return False


def _reflow_wrapped_lines(lines: list[str]) -> list[str]:
    """Join PDF line wraps inside prose paragraphs."""
    out: list[str] = []
    buf = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            if buf:
                out.append(buf)
                buf = ""
            out.append("")
            continue
        if not buf:
            buf = line
            continue
        if PROSE_WRAP_CONT.search(buf) and PROSE_WRAP_NEXT.match(line):
            buf = f"{buf} {line}"
        else:
            out.append(buf)
            buf = line
    if buf:
        out.append(buf)
    return out


def _fence_code_blocks(lines: list[str]) -> list[str]:
    out: list[str] = []
    code_buf: list[str] = []
    depth = 0

    def flush_code() -> None:
        nonlocal code_buf, depth
        if not code_buf:
            return
        if out and out[-1] != "":
            out.append("")
        out.append("```sysml")
        out.extend(code_buf)
        out.append("```")
        out.append("")
        code_buf = []
        depth = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if depth > 0:
                code_buf.append(stripped)
            else:
                flush_code()
                out.append("")
            continue
        if stripped.startswith("▪"):
            flush_code()
            out.append(f"- {stripped[1:].strip()}")
            continue
        is_start = bool(CODE_BLOCK_START.match(stripped))
        is_inner = depth > 0 and bool(CODE_BLOCK_INNER.match(stripped))
        has_brace = "{" in stripped or "}" in stripped
        if is_start or is_inner or (depth > 0 and has_brace):
            depth += stripped.count("{") - stripped.count("}")
            code_buf.append(stripped)
            if depth <= 0 and code_buf:
                flush_code()
            continue
        flush_code()
        out.append(stripped)
    flush_code()
    return out


def format_clause_body(text: str) -> str:
    """Normalize raw spec text: drop PDF noise, reflow prose, fence SysML examples."""
    raw_lines = text.splitlines()
    cleaned: list[str] = []
    for line in raw_lines:
        if _is_page_noise(line):
            continue
        cleaned.append(line.rstrip())
    reflowed = _reflow_wrapped_lines(cleaned)
    fenced = _fence_code_blocks(reflowed)
    paragraphs: list[str] = []
    buf: list[str] = []
    for line in fenced:
        if line == "":
            if buf:
                paragraphs.append("\n".join(buf))
                buf = []
            continue
        if line.startswith("```") or line.startswith("- "):
            if buf:
                paragraphs.append("\n".join(buf))
                buf = []
            paragraphs.append(line)
            continue
        buf.append(line)
    if buf:
        paragraphs.append("\n".join(buf))
    return "\n\n".join(paragraphs)


def highlight_html(body_html: str, query: str) -> str:
    if not query or not query.strip():
        return body_html
    terms = [t for t in re.split(r"\s+", query.strip()) if len(t) >= 3]
    if not terms:
        return body_html
    out = body_html
    for term in terms[:6]:
        pattern = re.compile(re.escape(term), re.IGNORECASE)

        def repl(m: re.Match[str]) -> str:
            return f"<mark>{m.group(0)}</mark>"

        out = pattern.sub(repl, out)
    return out


def render_clause_html(
    text: str,
    query: str = "",
    title: str = "",
    clause_id: str = "",
) -> str:
    body = strip_frontmatter(text)
    # Skip duplicate nav/header lines already shown in reader chrome.
    body_lines = body.splitlines()
    removed_md_title = False
    while body_lines:
        s = body_lines[0].strip()
        if not s:
            body_lines.pop(0)
            continue
        if body_lines[0].startswith("#"):
            body_lines.pop(0)
            removed_md_title = True
            continue
        if s.startswith("[Open ") or s.startswith("_informative") or s.startswith("_normative"):
            body_lines.pop(0)
            continue
        if removed_md_title and CLAUSE_HEADING_RE.match(s):
            body_lines.pop(0)
            continue
        break
    body = format_clause_body("\n".join(body_lines).strip())
    rendered = _md(body)
    if title and clause_id:
        anchor = f'<a id="clause-{html.escape(clause_id)}"></a>'
        rendered = anchor + rendered
    return highlight_html(rendered, query)

SAFE_RE = re.compile(r"[^a-z0-9]+")

CLAUSE_ALIASES: dict[str, list[str]] = {
    "namespace": ["espace de noms", "namespaces"],
    "connector": ["connecteur", "connecteurs"],
    "import": ["importation"],
    "feature": ["caracteristique"],
    "connection": ["connexion"],
    "binding": ["liaison"],
    "unique": ["unicite", "unicité"],
    "name": ["nom", "noms"],
}


def md_dir_for_db(db_path) -> Path:
    path = Path(db_path)
    if path.parent.name == "index":
        return path.parent.parent / "md"
    return path.parent / "md"


def clause_slug(clause_id: str, title: str = "") -> str:
    _, rest = parse_clause_title(title or clause_id)
    rest = SAFE_RE.sub("-", fold(rest)).strip("-")[:72]
    cid = SAFE_RE.sub("-", fold(clause_id)).strip("-") or "clause"
    return f"{cid}-{rest}" if rest and rest != cid else cid


def clause_relpath(version: str, doc_id: str, clause_id: str, title: str = "") -> str:
    return f"data/md/{version}/{doc_id}/{clause_slug(clause_id, title)}.md"


def example_relpath(version: str, example_id: str) -> str:
    safe = SAFE_RE.sub("-", example_id.replace(":", "-")).strip("-")
    return f"data/md/{version}/_examples/{safe}.md"


def clause_md_url(doc_id: str, version: str, clause_id: str, query: str = "") -> str:
    from urllib.parse import quote_plus

    from .config import VIEWER_URL

    url = f"{VIEWER_URL.rstrip('/')}/m/{doc_id}/{version}"
    params = []
    if clause_id:
        params.append(f"clause={quote_plus(clause_id)}")
    if query:
        params.append(f"q={quote_plus(query)}")
    if params:
        url += "?" + "&".join(params)
    return url


def _aliases_for_clause(title: str, text: str) -> list[str]:
    blob = fold(title + " " + text[:500])
    found: list[str] = []
    for key, aliases in CLAUSE_ALIASES.items():
        if key in blob:
            found.extend(aliases)
    return sorted(set(found))


def _related_clauses(conn, doc_id: str, clause_id: str, version: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT target_clause_id FROM cross_refs
        WHERE version = ? AND source_doc_id = ? AND source_clause_id = ?
        LIMIT 12
        """,
        (version, doc_id, clause_id),
    ).fetchall()
    return [r["target_clause_id"] for r in rows]


def render_clause_md(row: dict[str, Any], text: str, related: list[str], aliases: list[str]) -> str:
    status = "normative" if row["normative"] else "informative"
    pages = (
        f"{row['page_start']}"
        if row["page_start"] == row["page_end"]
        else f"{row['page_start']}-{row['page_end']}"
    )
    pdf = viewer_link(row["doc_id"], row["version"], row["page_start"], row["clause_id"])
    md_view = clause_md_url(row["doc_id"], row["version"], row["clause_id"])
    title = row["title"]
    alias_line = f"aliases: {', '.join(aliases)}\n" if aliases else ""
    related_line = f"related_clauses: {', '.join(related)}\n" if related else ""
    return (
        f"---\n"
        f"doc_id: {row['doc_id']}\n"
        f"version: {row['version']}\n"
        f"clause: {row['clause_id']}\n"
        f"pages: {pages}\n"
        f"kind: {row.get('kind') or 'other'}\n"
        f"status: {status}\n"
        f"viewer_url: {pdf}\n"
        f"markdown_url: {md_view}\n"
        f"{alias_line}"
        f"{related_line}"
        f"---\n\n"
        f"# {title}\n\n"
        f"_{status}_ · p.{pages} · {row.get('kind') or 'other'}\n\n"
        f"[Open highlighted PDF]({pdf}) · [Open in viewer]({md_view})\n\n"
        f"{text.strip()}\n"
    )


def render_example_md(row: dict[str, Any]) -> str:
    pdf = viewer_link(row["doc_id"], row["version"], row["page"] or 1, row["clause_id"])
    return (
        f"---\n"
        f"example_id: {row['example_id']}\n"
        f"doc_id: {row['doc_id']}\n"
        f"version: {row['version']}\n"
        f"clause: {row['clause_id']}\n"
        f"language: {row.get('language') or 'sysml'}\n"
        f"viewer_url: {pdf}\n"
        f"---\n\n"
        f"# {row.get('caption') or row['example_id']}\n\n"
        f"Clause `{row['clause_id']}` · [Open PDF]({pdf})\n\n"
        f"```sysml\n{row['text'].strip()}\n```\n"
    )


def export_markdown(
    db_path=None,
    md_dir: Path | None = None,
    versions: list[str] | None = None,
    include_examples: bool = True,
    force: bool = False,
) -> dict[str, int]:
    db = Path(db_path or DB_PATH)
    if not db.exists():
        raise FileNotFoundError(f"Index not found at {db}. Run: python -m sysml_spec_qa ingest")
    out = md_dir or MD_DIR
    conn = connect(db)
    try:
        all_docs = conn.execute(
            "SELECT id, title, version, family, source_url FROM documents ORDER BY version, family"
        ).fetchall()
        docs = [d for d in all_docs if not versions or d["version"] in versions]
        if not docs:
            return {"documents": 0, "clauses": 0, "examples": 0}

        wanted = {d["version"] for d in docs}
        if force:
            for version in wanted:
                target = out / version
                if target.exists():
                    shutil.rmtree(target)

        clause_count = 0
        example_count = 0
        for doc in docs:
            rows = conn.execute(
                """
                SELECT doc_id, version, clause_id, title, kind, normative,
                       page_start, page_end, part, text
                FROM chunks
                WHERE version = ? AND doc_id = ?
                ORDER BY page_start, clause_id, part
                """,
                (doc["version"], doc["id"]),
            ).fetchall()
            grouped: dict[str, list[Any]] = {}
            order: list[str] = []
            for row in rows:
                key = row["clause_id"]
                if key not in grouped:
                    grouped[key] = []
                    order.append(key)
                grouped[key].append(row)

            doc_dir = out / doc["version"] / doc["id"]
            doc_dir.mkdir(parents=True, exist_ok=True)
            toc: list[str] = []
            body: list[str] = []
            for clause_id in order:
                parts = grouped[clause_id]
                first = dict(parts[0])
                first["page_end"] = parts[-1]["page_end"]
                text = "\n\n".join(p["text"] for p in parts)
                related = _related_clauses(conn, doc["id"], clause_id, doc["version"])
                aliases = _aliases_for_clause(first["title"], text)
                slug = clause_slug(clause_id, first["title"])
                clause_path = doc_dir / f"{slug}.md"
                clause_path.write_text(
                    render_clause_md(first, text, related, aliases), encoding="utf-8"
                )
                clause_count += 1
                status = "normative" if first["normative"] else "informative"
                toc.append(
                    f"- [{first['title']}]({doc['id']}/{slug}.md) "
                    f"(p.{first['page_start']}, {status})"
                )
                body.append(f'<a id="{clause_id}"></a>\n\n## {first["title"]}\n\n{text.strip()}\n')

            full = (
                f"# {doc['title']}\n\n"
                f"Local excerpt for personal search. Do not republish.\n\n"
                f"Version `{doc['version']}` · `{doc['id']}`\n\n"
                f"## Contents\n\n"
                + "\n".join(toc)
                + "\n\n"
                + "\n".join(body)
            )
            (out / doc["version"] / f"{doc['id']}.md").write_text(full, encoding="utf-8")

            if include_examples:
                ex_dir = out / doc["version"] / "_examples"
                ex_dir.mkdir(parents=True, exist_ok=True)
                examples = conn.execute(
                    """
                    SELECT example_id, doc_id, version, clause_id, language, caption, page, text
                    FROM examples WHERE version = ? AND doc_id = ?
                    ORDER BY clause_id, example_id
                    """,
                    (doc["version"], doc["id"]),
                ).fetchall()
                for ex in examples:
                    ex_path = ex_dir / f"{ex['example_id'].replace(':', '-')}.md"
                    ex_path.write_text(render_example_md(dict(ex)), encoding="utf-8")
                    example_count += 1

        index_lines = [
            "# SysML / KerML spec markdown",
            "",
            "Local text for personal search. Do not republish OMG specification text.",
            "",
            "Search tips: use Cursor search on `data/md`, or open clause files directly.",
            "",
        ]
        for doc in all_docs:
            full_path = out / doc["version"] / f"{doc['id']}.md"
            if not full_path.exists():
                continue
            n_clauses = len(list((out / doc["version"] / doc["id"]).glob("*.md")))
            ex_n = len(list((out / doc["version"] / "_examples").glob("*.md"))) if include_examples else 0
            index_lines.append(
                f"- [{doc['title']}]({doc['version']}/{doc['id']}.md) "
                f"(`{doc['version']}`, {n_clauses} clauses, {ex_n} examples)"
            )
        (out / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        return {"documents": len(docs), "clauses": clause_count, "examples": example_count}
    finally:
        conn.close()


def resolve_clause_file(
    version: str,
    doc_id: str,
    clause_id: str,
    title: str = "",
    md_dir: Path | None = None,
) -> Path:
    root = md_dir or MD_DIR
    path = root / version / doc_id / f"{clause_slug(clause_id, title)}.md"
    if path.exists():
        return path
    folder = root / version / doc_id
    if folder.is_dir():
        prefix = clause_slug(clause_id, clause_id)
        for candidate in folder.glob(f"{prefix}*.md"):
            return candidate
    return path
