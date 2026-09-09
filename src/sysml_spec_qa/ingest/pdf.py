from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pymupdf

from ..config import MAX_CLAUSE_WORDS
from ..textutil import (
    FOOTER_Y_RATIO,
    HEADER_Y_RATIO,
    clause_kind,
    is_normative,
    parse_clause_title,
    split_long_text,
    word_count,
)

SKIP_TITLE_RE = re.compile(
    r"^(table of contents|contents|list of (figures|tables)|foreword|copyright)$",
    re.I,
)


@dataclass
class TextBlock:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass
class ClauseChunk:
    clause_id: str
    title: str
    kind: str
    normative: bool
    page_start: int
    page_end: int
    text: str
    part: int = 0
    bboxes: list[dict] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return word_count(self.text)

    def bboxes_json(self) -> str:
        return json.dumps(self.bboxes)


def _page_blocks(page: pymupdf.Page, page_number: int) -> list[TextBlock]:
    height = page.rect.height
    top = height * HEADER_Y_RATIO
    bottom = height * (1.0 - FOOTER_Y_RATIO)
    blocks: list[TextBlock] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        x0, y0, x1, y1 = block["bbox"]
        if y1 < top or y0 > bottom:
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", []))
            if line_text.strip():
                lines.append(line_text)
        text = "\n".join(lines).strip()
        if not text:
            continue
        blocks.append(TextBlock(page_number, x0, y0, x1, y1, text))
    return blocks


def _load_pages(doc: pymupdf.Document) -> list[list[TextBlock]]:
    pages: list[list[TextBlock]] = []
    for index in range(doc.page_count):
        pages.append(_page_blocks(doc[index], index + 1))
    return pages


def _toc_entries(doc: pymupdf.Document) -> list[tuple[int, str, int]]:
    entries: list[tuple[int, str, int]] = []
    for level, title, page in doc.get_toc(simple=True):
        title = " ".join(str(title).split())
        if not title or SKIP_TITLE_RE.match(title):
            continue
        clause_id, _ = parse_clause_title(title)
        if clause_id is None and level == 1 and not re.match(r"^\d+", title):
            # Keep unnumbered high-level bookmarks only if they look like clauses later.
            continue
        entries.append((level, title, int(page)))
    return entries


def _heading_index(blocks: list[TextBlock], title: str, clause_id: str | None) -> int | None:
    folded_title = re.sub(r"\s+", " ", title).lower()
    clause_prefix = None
    if clause_id:
        clause_prefix = re.compile(
            rf"^{re.escape(clause_id)}(?:\s|$|[A-Za-z])",
            re.I,
        )
    for i, block in enumerate(blocks):
        compact = re.sub(r"\s+", " ", block.text)
        if clause_prefix and clause_prefix.match(compact):
            return i
        if folded_title and folded_title in compact.lower():
            return i
    return None


def _slice_blocks(
    pages: list[list[TextBlock]],
    start_page: int,
    end_page: int,
    start_idx: int | None,
    end_idx: int | None,
) -> list[TextBlock]:
    out: list[TextBlock] = []
    for page_no in range(start_page, end_page + 1):
        blocks = pages[page_no - 1]
        start = start_idx if page_no == start_page and start_idx is not None else 0
        stop = end_idx if page_no == end_page and end_idx is not None else len(blocks)
        if page_no == start_page == end_page:
            out.extend(blocks[start:stop])
        elif page_no == start_page:
            out.extend(blocks[start:])
        elif page_no == end_page:
            out.extend(blocks[:stop])
        else:
            out.extend(blocks)
    return out


def _chunks_from_blocks(clause_id: str, title: str, blocks: list[TextBlock]) -> list[ClauseChunk]:
    if not blocks:
        return []
    text = "\n".join(block.text for block in blocks).strip()
    if not text:
        return []
    kind = clause_kind(clause_id, title)
    normative = is_normative(clause_id, title)
    page_start = blocks[0].page
    page_end = blocks[-1].page
    bboxes = [
        {
            "page": b.page,
            "x0": round(b.x0, 2),
            "y0": round(b.y0, 2),
            "x1": round(b.x1, 2),
            "y1": round(b.y1, 2),
            "text": b.text[:500],
            "origin": "fitz",
        }
        for b in blocks
    ]
    parts = split_long_text(text, MAX_CLAUSE_WORDS)
    chunks: list[ClauseChunk] = []
    for i, part in enumerate(parts):
        # Keep all bboxes on the first part; later parts still deep-link to the clause page.
        chunks.append(
            ClauseChunk(
                clause_id=clause_id,
                title=title,
                kind=kind,
                normative=normative,
                page_start=page_start,
                page_end=page_end,
                text=part,
                part=i,
                bboxes=bboxes if i == 0 else [bboxes[0]] if bboxes else [],
            )
        )
    return chunks


def parse_pdf(pdf_path) -> list[ClauseChunk]:
    doc = pymupdf.open(pdf_path)
    try:
        pages = _load_pages(doc)
        toc = _toc_entries(doc)
        if len(toc) >= 8:
            return _chunks_from_toc(pages, toc)
        return _chunks_from_headings(pages)
    finally:
        doc.close()


def _chunks_from_toc(pages: list[list[TextBlock]], toc: list[tuple[int, str, int]]) -> list[ClauseChunk]:
    chunks: list[ClauseChunk] = []
    last_page = len(pages)
    for i, (_level, title, page) in enumerate(toc):
        clause_id, rest = parse_clause_title(title)
        if clause_id is None:
            continue
        start_page = max(1, min(page, last_page))
        next_page = toc[i + 1][2] if i + 1 < len(toc) else last_page
        end_page = max(start_page, min(int(next_page), last_page))
        start_idx = _heading_index(pages[start_page - 1], title, clause_id)
        end_idx = None
        if i + 1 < len(toc):
            next_title = toc[i + 1][1]
            next_id, _ = parse_clause_title(next_title)
            if end_page == start_page:
                end_idx = _heading_index(pages[end_page - 1], next_title, next_id)
            elif next_page == end_page:
                end_idx = _heading_index(pages[end_page - 1], next_title, next_id)
        blocks = _slice_blocks(pages, start_page, end_page, start_idx, end_idx)
        display_title = rest or title
        chunks.extend(_chunks_from_blocks(clause_id, f"{clause_id} {display_title}".strip(), blocks))
    return chunks


HEADING_LINE_RE = re.compile(
    r"^(?P<id>\d+(?:\.\d+){0,6})\s+(?P<title>[A-Z][^\n]{2,120})$"
)


def _chunks_from_headings(pages: list[list[TextBlock]]) -> list[ClauseChunk]:
    headings: list[tuple[int, int, str, str]] = []
    for page_idx, blocks in enumerate(pages):
        for block_idx, block in enumerate(blocks):
            first = block.text.split("\n", 1)[0].strip()
            match = HEADING_LINE_RE.match(first)
            if not match:
                continue
            headings.append((page_idx + 1, block_idx, match.group("id"), match.group("title").strip()))
    if not headings:
        # Fallback: one chunk per page so the index is still searchable.
        chunks: list[ClauseChunk] = []
        for page_no, blocks in enumerate(pages, start=1):
            chunks.extend(
                _chunks_from_blocks(f"p.{page_no}", f"Page {page_no}", blocks)
            )
        return chunks

    chunks: list[ClauseChunk] = []
    for i, (page, idx, clause_id, heading) in enumerate(headings):
        if i + 1 < len(headings):
            n_page, n_idx, _, _ = headings[i + 1]
            end_page, end_idx = n_page, n_idx
        else:
            end_page, end_idx = len(pages), None
        blocks = _slice_blocks(pages, page, end_page, idx, end_idx)
        title = f"{clause_id} {heading}"
        chunks.extend(_chunks_from_blocks(clause_id, title, blocks))
    return chunks
