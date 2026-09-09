from __future__ import annotations

import json
import re
from collections import defaultdict

from ..textutil import CONSTRAINT_RE, fold, parse_clause_title
from .xmi import MetaItem

SEED_ELEMENTS = (
    "Namespace",
    "Membership",
    "Import",
    "Element",
    "Relationship",
    "Feature",
    "Type",
    "Classifier",
    "Connector",
    "BindingConnector",
    "Succession",
    "Association",
    "ConnectionUsage",
    "ConnectionDefinition",
    "PortUsage",
    "PortDefinition",
    "PartUsage",
    "PartDefinition",
    "AttributeUsage",
    "ItemUsage",
    "ActionUsage",
    "StateUsage",
    "RequirementUsage",
    "FlowConnectionUsage",
    "InterfaceUsage",
    "AllocationUsage",
    "Multiplicity",
    "Redefinition",
    "Subsetting",
    "FeatureTyping",
    "FeatureMembership",
)


def clause_terms_from_title(title: str) -> list[tuple[str, str]]:
    clause_id, rest = parse_clause_title(title)
    heading = rest or title
    terms: list[tuple[str, str]] = []
    if clause_id:
        terms.append((clause_id, "clause"))
    for match in re.findall(r"\b[A-Z][A-Za-z0-9]+(?:Usage|Definition|Connector|Namespace)?\b", heading):
        if len(match) >= 4:
            terms.append((match, "heading"))
    for name in CONSTRAINT_RE.findall(title + " " + heading):
        terms.append((name, "constraint"))
    return terms


def extract_constraints(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in CONSTRAINT_RE.finditer(text):
        name = match.group(1)
        start = max(0, match.start() - 160)
        end = min(len(text), match.end() + 240)
        snippet = " ".join(text[start:end].split())
        found.append((name, snippet))
    return found


def build_cards(
    version: str,
    chunks: list[dict],
    meta_items: list[MetaItem],
    constraints: list[dict],
) -> list[dict]:
    names: set[str] = set(SEED_ELEMENTS)
    for item in meta_items:
        if item.kind == "class" and item.name[0].isupper():
            names.add(item.name)

    by_name: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        title = chunk["title"]
        text = chunk["text"]
        blob = f"{title}\n{text[:2000]}"
        for name in names:
            if re.search(rf"\b{re.escape(name)}\b", blob):
                by_name[name].append(chunk)

    constraint_by_elem: dict[str, list[dict]] = defaultdict(list)
    for row in constraints:
        for name in names:
            if name.lower() in row["name"].lower() or name.lower() in (row.get("text") or "").lower()[:200]:
                constraint_by_elem[name].append(row)

    cards: list[dict] = []
    for name in sorted(names):
        related_chunks = by_name.get(name, [])
        if not related_chunks and name not in SEED_ELEMENTS:
            continue
        description = []
        syntax = []
        other = []
        for chunk in related_chunks:
            ref = {
                "doc_id": chunk["doc_id"],
                "clause_id": chunk["clause_id"],
                "title": chunk["title"],
                "page": chunk["page_start"],
                "kind": chunk["kind"],
                "normative": bool(chunk["normative"]),
            }
            if chunk["kind"] == "description" or str(chunk["clause_id"]).startswith("7"):
                description.append(ref)
            elif chunk["kind"] == "syntax" or str(chunk["clause_id"]).startswith("8"):
                syntax.append(ref)
            else:
                other.append(ref)

        related: set[str] = set()
        for chunk in related_chunks[:12]:
            for other_name in names:
                if other_name == name:
                    continue
                if re.search(rf"\b{re.escape(other_name)}\b", chunk["title"]):
                    related.add(other_name)

        excerpt = ""
        for chunk in related_chunks:
            if name in chunk["title"]:
                excerpt = " ".join(chunk["text"].split()[:80])
                break
        if not excerpt and related_chunks:
            excerpt = " ".join(related_chunks[0]["text"].split()[:80])

        cards.append(
            {
                "name": name,
                "name_norm": fold(name),
                "version": version,
                "description_clauses": _uniq_refs(description)[:8],
                "syntax_clauses": _uniq_refs(syntax)[:8],
                "other_clauses": _uniq_refs(other)[:8],
                "constraints": [
                    {
                        "name": row["name"],
                        "clause_id": row.get("clause_id"),
                        "page": row.get("page"),
                        "doc_id": row.get("doc_id"),
                    }
                    for row in constraint_by_elem.get(name, [])[:12]
                ],
                "related": sorted(related)[:10],
                "excerpt": excerpt,
            }
        )
    return cards


def _uniq_refs(refs: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for ref in refs:
        key = (ref["doc_id"], ref["clause_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out
