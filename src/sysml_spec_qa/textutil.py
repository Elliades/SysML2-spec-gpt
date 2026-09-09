from __future__ import annotations

import re
import unicodedata

CLAUSE_ID_RE = re.compile(
    r"^(?P<id>(?:Annex\s+[A-Z]|Appendix\s+[A-Z]|[A-Z](?:\.\d+)+|\d+(?:\.\d+)*))\b",
    re.IGNORECASE,
)

CONSTRAINT_RE = re.compile(r"\b((?:check|validate|derive)[A-Z][A-Za-z0-9]+)\b")

WORD_RE = re.compile(r"[A-Za-z0-9_]+")

HEADER_Y_RATIO = 0.045
FOOTER_Y_RATIO = 0.045


def fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in norm if not unicodedata.combining(ch)).lower()


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def estimate_tokens(text: str) -> int:
    # Conservative proxy: ~0.75 words/token for spec English.
    return max(1, int(word_count(text) / 0.75)) if text.strip() else 0


def parse_clause_title(title: str) -> tuple[str | None, str]:
    raw = " ".join(title.split())
    match = CLAUSE_ID_RE.match(raw)
    if not match:
        return None, raw
    clause_id = re.sub(r"\s+", " ", match.group("id")).replace("Annex ", "A").replace("Appendix ", "A")
    rest = raw[match.end() :].strip(" .-–—")
    return clause_id, rest or raw


def major_clause(clause_id: str | None) -> str | None:
    if not clause_id:
        return None
    if clause_id.upper().startswith("A"):
        return "A"
    return clause_id.split(".", 1)[0]


def clause_kind(clause_id: str | None, title: str) -> str:
    lowered = title.lower()
    if CONSTRAINT_RE.search(title):
        return "constraint"
    if "annex" in lowered or (clause_id or "").upper().startswith("A"):
        return "annex"
    major = major_clause(clause_id)
    if major == "7":
        return "description"
    if major == "8":
        return "syntax"
    if major in {"9", "10"}:
        return "semantics"
    return "other"


def is_normative(clause_id: str | None, title: str) -> bool:
    kind = clause_kind(clause_id, title)
    if kind in {"description", "annex"}:
        return False
    major = major_clause(clause_id)
    if major is None:
        return False
    if major == "A":
        return False
    try:
        return int(major) >= 8
    except ValueError:
        return False


def excerpt(text: str, query_terms: list[str], max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    hay = fold(text)
    pos = -1
    for term in query_terms:
        if len(term) < 3:
            continue
        pos = hay.find(fold(term))
        if pos >= 0:
            break
    if pos < 0:
        return " ".join(words[:max_words]).strip() + " …"
    prefix = text[:pos]
    start_word = max(0, len(prefix.split()) - max_words // 4)
    snippet = words[start_word : start_word + max_words]
    prefix_ellipsis = "… " if start_word else ""
    suffix_ellipsis = " …" if start_word + max_words < len(words) else ""
    return prefix_ellipsis + " ".join(snippet).strip() + suffix_ellipsis


def split_long_text(text: str, max_words: int) -> list[str]:
    if word_count(text) <= max_words:
        return [text.strip()] if text.strip() else []
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf: list[str] = []
    count = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        n = word_count(para)
        if buf and count + n > max_words:
            chunks.append("\n\n".join(buf).strip())
            buf = [para]
            count = n
        else:
            buf.append(para)
            count += n
    if buf:
        chunks.append("\n\n".join(buf).strip())
    return chunks or [text.strip()]


GENERIC_FTS = {
    "name",
    "names",
    "named",
    "usage",
    "definition",
    "element",
    "type",
    "types",
}


def fts_query(terms: list[str]) -> str:
    cleaned: list[str] = []
    generic: list[str] = []
    for term in terms:
        tok = re.sub(r"[^\w]", "", term, flags=re.UNICODE)
        if len(tok) < 2:
            continue
        if fold(tok) in GENERIC_FTS:
            generic.append(tok)
            continue
        cleaned.append(tok)
    pool = cleaned or generic
    seen: set[str] = set()
    parts: list[str] = []
    for tok in pool:
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        if tok[0].isupper() and len(tok) > 3:
            parts.append(f'"{tok}"')
        else:
            parts.append(f"{tok}*")
    return " OR ".join(parts[:24])
