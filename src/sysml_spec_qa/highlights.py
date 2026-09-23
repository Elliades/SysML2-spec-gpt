from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .query import analyze_query
from .textutil import cite_sentence, fold, word_count

TITLE_BLOCK_RE = re.compile(r"^\d+(?:\.\d+)*\s+\S")
NORMATIVE_HINT = re.compile(r"\b(must|shall|is a kind of|is syntactically|is semantically)\b", re.I)


def _rect_to_box(page: int, rect: Any) -> dict:
    return {
        "page": page,
        "x0": round(float(rect.x0), 2),
        "y0": round(float(rect.y0), 2),
        "x1": round(float(rect.x1), 2),
        "y1": round(float(rect.y1), 2),
        "origin": "search",
    }


def _quote_needles(quote: str, limit: int = 4) -> list[str]:
    quote = " ".join(quote.split())
    if not quote:
        return []
    words = quote.split()
    needles: list[str] = []
    if len(quote) <= 400:
        needles.append(quote)
    if len(words) > 24:
        step = max(12, len(words) // 3)
        for start in range(0, min(len(words), 60), step):
            chunk = " ".join(words[start : start + 24])
            if len(chunk) >= 20:
                needles.append(chunk)
    elif len(words) > 10 and quote not in needles:
        needles.append(quote)
    seen: set[str] = set()
    out: list[str] = []
    for needle in needles:
        key = fold(needle)
        if key in seen:
            continue
        seen.add(key)
        out.append(needle[:400])
        if len(out) >= limit:
            break
    return out


def focus_quote(
    row: dict[str, Any],
    quote: str = "",
    query: str = "",
) -> str:
    body = row.get("full_text") or row.get("text") or ""
    if quote.strip():
        return quote.strip()
    if query.strip():
        analysis = analyze_query(query)
        terms = list(analysis.get("terms") or [])
        if "constraint" in analysis.get("intents", []):
            terms.extend(["must", "shall", "distinguishable", "validate"])
        return cite_sentence(body, terms, max_words=80, min_words=12)
    # Default: opening definition sentence(s), not the whole clause.
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])", body.strip())
    picked: list[str] = []
    for sent in sentences:
        s = sent.strip()
        if not s or TITLE_BLOCK_RE.match(s):
            continue
        if NORMATIVE_HINT.search(s) or not picked:
            picked.append(s)
        if word_count(" ".join(picked)) >= 35 or len(picked) >= 2:
            break
    return " ".join(picked) if picked else body[:400]


def search_pdf_boxes(
    pdf_path: Path,
    quote: str,
    page: int | None = None,
    limit: int = 6,
) -> list[dict]:
    if not pdf_path.exists() or not quote.strip():
        return []
    try:
        import pymupdf
    except ImportError:
        return []
    doc = pymupdf.open(pdf_path)
    try:
        pages = [page] if page else list(range(1, doc.page_count + 1))
        boxes: list[dict] = []
        seen: set[tuple] = set()
        for needle in _quote_needles(quote):
            for pno in pages:
                if pno < 1 or pno > doc.page_count:
                    continue
                for rect in doc[pno - 1].search_for(needle):
                    box = _rect_to_box(pno, rect)
                    key = (box["page"], box["x0"], box["y0"], box["x1"], box["y1"])
                    if key in seen:
                        continue
                    seen.add(key)
                    boxes.append(box)
                    if len(boxes) >= limit:
                        return boxes
        return boxes
    finally:
        doc.close()


def _bbox_text_map(pdf_path: Path, bboxes: list[dict]) -> dict[tuple, str]:
    """Attach PDF block text to stored bboxes by geometry overlap."""
    if not pdf_path.exists() or not bboxes:
        return {}
    try:
        import pymupdf
    except ImportError:
        return {}
    doc = pymupdf.open(pdf_path)
    out: dict[tuple, str] = {}
    try:
        by_page: dict[int, list[dict]] = {}
        for box in bboxes:
            by_page.setdefault(int(box.get("page", 0)), []).append(box)
        for pno, page_boxes in by_page.items():
            if pno < 1 or pno > doc.page_count:
                continue
            blocks = doc[pno - 1].get_text("blocks")
            for box in page_boxes:
                key = (
                    int(box.get("page", 0)),
                    float(box.get("x0", 0)),
                    float(box.get("y0", 0)),
                    float(box.get("x1", 0)),
                    float(box.get("y1", 0)),
                )
                best = ""
                best_area = 0.0
                bx0, by0, bx1, by1 = key[1], key[2], key[3], key[4]
                for block in blocks:
                    if block[6] != 0:
                        continue
                    x0, y0, x1, y1 = block[:4]
                    ix0, iy0 = max(bx0, x0), max(by0, y0)
                    ix1, iy1 = min(bx1, x1), min(by1, y1)
                    if ix1 <= ix0 or iy1 <= iy0:
                        continue
                    area = (ix1 - ix0) * (iy1 - iy0)
                    if area > best_area:
                        best_area = area
                        best = str(block[4] or "").strip()
                if best:
                    out[key] = best
        return out
    finally:
        doc.close()


def _score_block_text(text: str, quote: str, query: str) -> int:
    hay = fold(text)
    score = 0
    qfold = fold(quote)
    for token in qfold.split():
        if len(token) >= 4 and token in hay:
            score += 4
    if len(qfold) >= 12 and qfold[:40] in hay:
        score += 12
    if query:
        for term in analyze_query(query).get("terms", []):
            if len(term) >= 4 and fold(term) in hay:
                score += 2
    if TITLE_BLOCK_RE.match(text.strip()) and score < 8:
        score -= 6
    if NORMATIVE_HINT.search(text):
        score += 3
    return score


def focus_bboxes(
    bboxes: list[dict],
    quote: str,
    query: str = "",
    pdf_path: Path | None = None,
    page: int | None = None,
    limit: int = 6,
) -> list[dict]:
    """Return only bboxes that match the focused citation, not the whole clause."""
    if not bboxes:
        return []
    if page is not None:
        bboxes = [b for b in bboxes if int(b.get("page", 0)) == page]
    if pdf_path:
        searched = search_pdf_boxes(pdf_path, quote, page=page, limit=limit)
        if searched:
            return searched
    text_map: dict[tuple, str] = {}
    if pdf_path:
        text_map = _bbox_text_map(pdf_path, bboxes)
    scored: list[tuple[int, dict]] = []
    for box in bboxes:
        key = (
            int(box.get("page", 0)),
            float(box.get("x0", 0)),
            float(box.get("y0", 0)),
            float(box.get("x1", 0)),
            float(box.get("y1", 0)),
        )
        text = box.get("text") or text_map.get(key, "")
        score = _score_block_text(text, quote, query) if text else 0
        if score > 0:
            scored.append((score, box))
    if not scored:
        # Last resort: first non-title block on page, not the full clause.
        for box in bboxes[:3]:
            key_text = box.get("text") or text_map.get(
                (
                    int(box.get("page", 0)),
                    float(box.get("x0", 0)),
                    float(box.get("y0", 0)),
                    float(box.get("x1", 0)),
                    float(box.get("y1", 0)),
                ),
                "",
            )
            if key_text and not TITLE_BLOCK_RE.match(key_text.strip()):
                return [box]
        return bboxes[:1]
    scored.sort(key=lambda item: -item[0])
    top = scored[0][0]
    picked = [box for score, box in scored if score >= max(top - 2, 4)][:limit]
    return picked or [scored[0][1]]


def focused_highlights(
    row: dict[str, Any],
    *,
    quote: str = "",
    query: str = "",
    pdf_path: Path | None = None,
    page: int | None = None,
) -> list[dict]:
    focus = focus_quote(row, quote=quote, query=query)
    raw = row.get("bboxes") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    return focus_bboxes(raw, focus, query=query, pdf_path=pdf_path, page=page)
