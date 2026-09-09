from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..textutil import estimate_tokens, word_count

PASSAGE_MIN = 40
PASSAGE_MAX = 400

CROSS_REF_RE = re.compile(
    r"\b(?:see|See|clause|Clause|section|Section)\s+(\d+(?:\.\d+)*)",
    re.I,
)

SYSML_KW = (
    "part def",
    "part usage",
    "package",
    "connector",
    "port def",
    "port usage",
    "item def",
    "item usage",
    "action def",
    "action usage",
    "requirement def",
    "requirement usage",
    "attribute def",
    "attribute usage",
    "connection def",
    "connection usage",
    "flow def",
    "flow usage",
    "interface def",
    "interface usage",
    "state def",
    "state usage",
    "namespace",
    "import",
    "feature",
    "binding",
    "succession",
    "allocation",
    "metadata def",
    "enum def",
)

EXAMPLE_START_RE = re.compile(
    r"^(?:Example|EXAMPLE|Listing|LISTING)\s*(?:\d+(?:\.\d+)*)?\s*[:\.]?\s*$",
    re.I,
)


@dataclass
class Passage:
    passage_id: str
    doc_id: str
    version: str
    clause_id: str
    title: str
    heading_path: str
    kind: str
    normative: bool
    page_start: int
    page_end: int
    text: str
    part: int
    bboxes: list[dict] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return word_count(self.text)

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.text)

    def bboxes_json(self) -> str:
        return json.dumps(self.bboxes)


@dataclass
class ExampleBlock:
    example_id: str
    doc_id: str
    version: str
    clause_id: str
    language: str
    text: str
    caption: str
    page: int
    bboxes: list[dict] = field(default_factory=list)

    def bboxes_json(self) -> str:
        return json.dumps(self.bboxes)


def split_passages(
    doc_id: str,
    version: str,
    clause_id: str,
    title: str,
    kind: str,
    normative: bool,
    page_start: int,
    page_end: int,
    text: str,
    bboxes: list[dict],
) -> list[Passage]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []
    passages: list[Passage] = []
    part = 0

    def append_passage(body: str) -> None:
        nonlocal part
        if not body.strip():
            return
        pid = f"{doc_id}:{clause_id}:{part}"
        passages.append(
            Passage(
                passage_id=pid,
                doc_id=doc_id,
                version=version,
                clause_id=clause_id,
                title=title,
                heading_path=title,
                kind=kind,
                normative=normative,
                page_start=page_start,
                page_end=page_end,
                text=body.strip(),
                part=part,
                bboxes=bboxes if part == 0 else (bboxes[:1] if bboxes else []),
            )
        )
        part += 1

    buf: list[str] = []
    count = 0
    for para in paragraphs:
        n = word_count(para)
        if n > PASSAGE_MAX:
            if buf:
                append_passage("\n\n".join(buf))
                buf, count = [], 0
            from ..textutil import split_long_text

            for chunk in split_long_text(para, PASSAGE_MAX):
                append_passage(chunk)
            continue
        if buf and count + n > PASSAGE_MAX:
            append_passage("\n\n".join(buf))
            buf, count = [para], n
            continue
        buf.append(para)
        count += n
        if count >= PASSAGE_MIN:
            append_passage("\n\n".join(buf))
            buf, count = [], 0
    if buf:
        append_passage("\n\n".join(buf))
    if not passages and text.strip():
        passages.append(
            Passage(
                passage_id=f"{doc_id}:{clause_id}:0",
                doc_id=doc_id,
                version=version,
                clause_id=clause_id,
                title=title,
                heading_path=title,
                kind=kind,
                normative=normative,
                page_start=page_start,
                page_end=page_end,
                text=text.strip(),
                part=0,
                bboxes=bboxes,
            )
        )
    return passages


def extract_cross_refs(text: str, source_doc: str, source_clause: str, version: str) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()
    for match in CROSS_REF_RE.finditer(text):
        target = match.group(1)
        if target == source_clause or target in seen:
            continue
        seen.add(target)
        refs.append(
            {
                "source_doc_id": source_doc,
                "source_clause_id": source_clause,
                "target_clause_id": target,
                "version": version,
                "context": text[max(0, match.start() - 40) : match.end() + 40].strip(),
            }
        )
    return refs


def _looks_like_sysml(line: str) -> bool:
    low = line.lower().strip()
    if not low or len(low) < 4:
        return False
    if low.endswith(";") or low.endswith("{") or low.endswith("}"):
        return True
    return any(kw in low for kw in SYSML_KW)


def extract_examples(
    doc_id: str,
    version: str,
    clause_id: str,
    text: str,
    page_start: int,
    bboxes: list[dict],
) -> list[ExampleBlock]:
    lines = text.splitlines()
    examples: list[ExampleBlock] = []
    i = 0
    ex_num = 0
    while i < len(lines):
        line = lines[i].strip()
        if EXAMPLE_START_RE.match(line) or (
            line.lower().startswith("example") and i + 1 < len(lines)
        ):
            caption = line
            block: list[str] = []
            i += 1
            while i < len(lines):
                cur = lines[i]
                if EXAMPLE_START_RE.match(cur.strip()) and block:
                    break
                if re.match(r"^\d+(?:\.\d+)+\s+[A-Z]", cur.strip()) and block:
                    break
                block.append(cur)
                i += 1
            body = "\n".join(block).strip()
            if body and (_looks_like_sysml(body) or word_count(body) >= 8):
                examples.append(
                    ExampleBlock(
                        example_id=f"{doc_id}:{clause_id}:ex{ex_num}",
                        doc_id=doc_id,
                        version=version,
                        clause_id=clause_id,
                        language="sysml",
                        text=body,
                        caption=caption,
                        page=page_start,
                        bboxes=bboxes[:1] if bboxes else [],
                    )
                )
                ex_num += 1
            continue
        i += 1
    return examples
