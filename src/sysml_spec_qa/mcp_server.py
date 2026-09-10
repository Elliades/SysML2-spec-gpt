from __future__ import annotations

import json
from typing import Any

from . import search as spec
from .config import DEFAULT_VERSION, MAX_HITS
from .pack import answer_pack, clause_pack, search_examples


def _heading(hit_or_row: Any, doc_id: str, clause_id: str, title: str) -> str:
    label = title if title.startswith(clause_id) else f"{clause_id} — {title}"
    return f"### {doc_id} {label}"


def _format_hit(hit: spec.Hit, query: str) -> str:
    status = "normative" if hit.normative else "informative"
    pages = f"p.{hit.page_start}" if hit.page_start == hit.page_end else f"p.{hit.page_start}–{hit.page_end}"
    return (
        f"{_heading(hit, hit.doc_id, hit.clause_id, hit.title)}\n"
        f"_{status}_ · {pages} · {hit.kind}\n"
        f"[open highlighted]({hit.viewer_url(query)}) · "
        f"[open markdown]({hit.markdown_url(query)})\n"
        f"`{hit.md_path}`\n\n"
        f"{hit.excerpt}"
    )


def spec_route(question: str, version: str = DEFAULT_VERSION) -> str:
    """Map a natural-language SysML/KerML question to clause ids (no excerpt text)."""
    try:
        hits = spec.route(question, version=version)
    except FileNotFoundError as exc:
        return str(exc)
    if not hits:
        return json.dumps({"version": version, "clauses": []})
    return json.dumps({"version": version, "clauses": hits}, indent=2)


def spec_search(query: str, version: str = DEFAULT_VERSION, k: int = MAX_HITS) -> str:
    """Search KerML/SysML clauses. Returns at most k short excerpts plus highlighted viewer links."""
    try:
        hits = spec.search(query, version=version, k=k)
    except FileNotFoundError as exc:
        return str(exc)
    if not hits:
        return f"No hits for {query!r} in version {version}."
    parts = [
        f"{len(hits)} hit(s) for {query!r} (version {version}; excerpts truncated)."
    ]
    for hit in hits:
        parts.append(_format_hit(hit, query))
    return "\n\n".join(parts)


def spec_get(clause_id: str, doc_id: str = "", version: str = DEFAULT_VERSION) -> str:
    """Fetch one clause by id (e.g. 7.2.5). Truncated to keep token use low."""
    try:
        row = spec.get_clause(clause_id, doc_id=doc_id or None, version=version)
    except FileNotFoundError as exc:
        return str(exc)
    if not row:
        return f"Clause {clause_id} not found in version {version}."
    status = "normative" if row["normative"] else "informative"
    note = " (truncated)" if row.get("truncated") else ""
    return (
        f"{_heading(row, row['doc_id'], row['clause_id'], row['title'])}\n"
        f"_{status}_ · p.{row['page_start']}–{row['page_end']}{note}\n"
        f"[open highlighted]({row['viewer_url']}) · "
        f"[open markdown]({row.get('markdown_url')})\n"
        f"`{row.get('md_path')}`\n\n"
        f"{row['text']}"
    )


def spec_element(name: str, version: str = DEFAULT_VERSION) -> str:
    """Precomputed element card (Connector, Namespace, Feature, …) with clause links."""
    try:
        card = spec.get_element(name, version=version)
    except FileNotFoundError as exc:
        return str(exc)
    if not card:
        return f"No element card for {name!r} in version {version}."
    lines = [f"## {card['name']} (version {version})"]
    if card.get("excerpt"):
        lines.append(card["excerpt"])
    for label, key in (
        ("Description (typically informative cl. 7)", "description_clauses"),
        ("Abstract syntax (typically normative cl. 8)", "syntax_clauses"),
        ("Other", "other_clauses"),
    ):
        refs = card.get(key) or []
        if not refs:
            continue
        lines.append(f"### {label}")
        for ref in refs:
            status = "normative" if ref.get("normative") else "informative"
            lines.append(
                f"- {ref['doc_id']} {ref['clause_id']} — {ref['title']} "
                f"({status}, p.{ref['page']}) [open]({ref.get('viewer_url')})"
            )
    if card.get("constraints"):
        lines.append("### Constraints")
        for row in card["constraints"][:8]:
            lines.append(
                f"- `{row['name']}` in {row.get('doc_id')} {row.get('clause_id')} p.{row.get('page')}"
            )
    if card.get("related"):
        lines.append("Related: " + ", ".join(card["related"]))
    return "\n".join(lines)


def spec_answer_pack(
    question: str,
    version: str = DEFAULT_VERSION,
    k: int = MAX_HITS,
    include_examples: bool = False,
) -> str:
    """Compact JSON answer pack: primary cite, optional exception, session link, cost."""
    try:
        pack = answer_pack(question, version=version, k=k, include_examples=include_examples)
    except FileNotFoundError as exc:
        return str(exc)
    return json.dumps(pack.to_dict(), indent=2, ensure_ascii=False)


def spec_clause_pack(
    clause_ids: str,
    doc_id: str = "",
    version: str = DEFAULT_VERSION,
    query: str = "",
) -> str:
    """Open multiple cited clauses together. clause_ids is comma-separated (e.g. 7.2.5,8.3.2.4.5)."""
    ids = [c.strip() for c in clause_ids.split(",") if c.strip()]
    try:
        result = clause_pack(ids, doc_id=doc_id or None, version=version, query=query)
    except FileNotFoundError as exc:
        return str(exc)
    return json.dumps(result, indent=2, ensure_ascii=False)


def spec_examples(query: str, version: str = DEFAULT_VERSION, k: int = 3) -> str:
    """Search SysML/KerML language examples in the spec."""
    try:
        examples = search_examples(query, version=version, k=k)
    except FileNotFoundError as exc:
        return str(exc)
    if not examples:
        return f"No examples for {query!r} in version {version}."
    return json.dumps([ex.__dict__ for ex in examples], indent=2, ensure_ascii=False)


def _attach_tools(mcp: Any) -> None:
    mcp.tool()(spec_route)
    mcp.tool()(spec_search)
    mcp.tool()(spec_get)
    mcp.tool()(spec_element)
    mcp.tool()(spec_answer_pack)
    mcp.tool()(spec_clause_pack)
    mcp.tool()(spec_examples)


def main() -> None:
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer(
        "sysml-spec",
        instructions=(
            "Search KerML and SysML v2 language specs. Default doc preference: cite "
            "sysml-2.x-language first; use kerml-* only when the user explicitly mentions "
            "KerML or SysML has no applicable passage. Prefer spec_element for named "
            "metaclasses, spec_answer_pack for questions, spec_clause_pack when clause ids "
            "are known. Always include session_url / reader_url links. Keep answers short. "
            "Follow answer_contract.shape (verdict, rule, exception?, conclusion, cost). "
            "In chat, cite only marked passage excerpts (quote_en), not whole clauses. "
            "Citations are always verbatim English quote_en inside guillemets — never French. "
            "For French answers, add *Traduction :* on the next line, outside guillemets."
        ),
    )
    _attach_tools(mcp)
    mcp.run()


if __name__ == "__main__":
    main()
