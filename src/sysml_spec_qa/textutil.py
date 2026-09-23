from __future__ import annotations

import re
import unicodedata

CLAUSE_ID_RE = re.compile(
    r"^(?P<id>(?:Annex\s+[A-Z]|Appendix\s+[A-Z]|[A-Z](?:\.\d+)+|\d+(?:\.\d+)*))\b",
    re.IGNORECASE,
)

CONSTRAINT_RE = re.compile(r"\b((?:check|validate|derive)[A-Z][A-Za-z0-9]+)\b")
CONSTRAINT_NAME_LINE_RE = re.compile(r"^(?:validate|check|derive)[A-Z]")
NORMATIVE_LINE_RE = re.compile(r"\b(must|shall)\b", re.I)

WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]+")
PDF_HEADER_RE = re.compile(
    r"^(?:Systems Modeling Language\b.*|Part\s+\d+\s*$|\d{1,4}\s*$)$",
    re.I,
)
CODEISH_RE = re.compile(
    r"^\s*(?:abstract\s+|ref\s+)?(?:state|part|item|action|attribute|package)\s+(?:def\s+)?"
    r"|^\s*(?:entry|do|exit|then)\s+action\b"
    r"|^\s*[{}]\s*$"
    r"|:=",
    re.I,
)

HEADER_Y_RATIO = 0.045
FOOTER_Y_RATIO = 0.045

NORMATIVE_MARKERS = (" must ", " shall ", " required ", " distinguishable", " unique", " uniqu")

DESCRIPTION_PENALTY = re.compile(
    r"^\d+(?:\.\d+)*\s+\S+\s+Description\s+A\s+Namespace\s+is",
    re.I,
)


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


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])")
LIST_NUM_RE = re.compile(r"^\d+\.$")
SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]*$')


def unwrap_pdf_lines(text: str) -> str:
    """Join PDF wrap lines so a sentence is not cut after 'being\\ndefined.'"""
    raw = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not PDF_HEADER_RE.match(ln.strip())
    ]
    if not raw:
        return ""
    buf: list[str] = [raw[0]]
    for ln in raw[1:]:
        prev = buf[-1]
        if CONSTRAINT_NAME_LINE_RE.match(prev) or CONSTRAINT_NAME_LINE_RE.match(ln):
            buf.append(ln)
            continue
        if LIST_NUM_RE.match(prev):
            buf[-1] = f"{prev} {ln}"
            continue
        if LIST_NUM_RE.match(ln):
            buf.append(ln)
            continue
        if SENTENCE_END_RE.search(prev):
            buf.append(ln)
            continue
        if CODEISH_RE.search(prev) or CODEISH_RE.search(ln):
            buf.append(ln)
            continue
        buf[-1] = f"{prev} {ln}"
    return "\n".join(buf)


def _sentences(text: str) -> list[str]:
    joined = unwrap_pdf_lines(text)
    prose = [
        ln.strip()
        for ln in joined.splitlines()
        if ln.strip() and not CODEISH_RE.search(ln)
    ]
    parts = SENTENCE_RE.split(" ".join(prose).strip())
    return [p.strip() for p in parts if p.strip()]


def fit_quote(quote: str, max_words: int) -> str:
    """Trim to max_words without cutting inside a sentence when possible."""
    quote = " ".join(quote.split())
    if not quote:
        return ""
    if word_count(quote) <= max_words:
        return quote
    words = quote.split()
    clipped = " ".join(words[:max_words])
    punct = list(re.finditer(r"[.!?]", clipped))
    if punct:
        end = punct[-1].end()
        if end >= 24:
            return clipped[:end].strip()
    return clipped.strip() + " …"


def _line_score(line: str, query_terms: list[str]) -> int:
    hay = fold(line)
    score = _sentence_score(line, query_terms)
    if NORMATIVE_LINE_RE.search(line) and word_count(line) <= 35:
        score += 12
    if "distinguishable from each other" in hay:
        score += 25
    if "owned name" in hay and "unique" in hay:
        score += 20
    return score


def normative_line_quote(
    text: str, query_terms: list[str], max_words: int = 80
) -> str | None:
    """Pick a short normative line (constraint English sentence) when present."""
    lines = [ln.strip() for ln in unwrap_pdf_lines(text).splitlines() if ln.strip()]
    best_line: str | None = None
    best_score = 0
    for idx, line in enumerate(lines):
        if CONSTRAINT_NAME_LINE_RE.match(line):
            for nxt in lines[idx + 1 : idx + 4]:
                if not NORMATIVE_LINE_RE.search(nxt):
                    continue
                if not SENTENCE_END_RE.search(nxt):
                    continue
                if word_count(nxt) > max_words:
                    continue
                score = _line_score(nxt, query_terms) + 18
                if score > best_score:
                    best_score = score
                    best_line = nxt
        if not NORMATIVE_LINE_RE.search(line) or word_count(line) > max_words:
            continue
        if not SENTENCE_END_RE.search(line):
            continue
        score = _line_score(line, query_terms)
        if score > best_score:
            best_score = score
            best_line = line
    if best_line and best_score >= 10:
        return best_line
    return None


def _sentence_score(sent: str, query_terms: list[str]) -> int:
    hay = fold(sent)
    score = 0
    for term in query_terms:
        if len(term) < 3:
            continue
        ft = fold(term)
        if ft in hay:
            score += 3 if len(term) > 5 else 2
    for marker in NORMATIVE_MARKERS:
        if marker in hay:
            score += 8
    for key in ("distinguishable", "unique", "uniqueness", "membership", "validate", "check"):
        if key in hay:
            score += 6
    qfold = " ".join(fold(t) for t in query_terms)
    if "subset" in qfold and any(k in hay for k in ("subsetting", "subsets", "subsetted")):
        score += 14
    if "subset" in qfold and any(k in hay for k in ("subclassification", "specializes")):
        score += 8
    if any(k in hay for k in ("can be declared", "may hierarchically contain", "in the body")):
        score += 10
    if PDF_HEADER_RE.match(sent.strip()) or "systems modeling language" in hay:
        score -= 40
    if CODEISH_RE.search(sent) and "can be declared" not in hay:
        score -= 18
    if DESCRIPTION_PENALTY.search(sent):
        score -= 20
    if "abstract syntax" in hay and "must" not in hay:
        score -= 8
    if hay.startswith("operations") or hay.startswith("constraints"):
        score -= 4
    return score


def cite_sentence(text: str, query_terms: list[str], max_words: int = 80, min_words: int = 12) -> str:
    """Extract 1–2 complete sentences around the best matching term."""
    pinned = normative_line_quote(text, query_terms, max_words=max_words)
    if pinned:
        return fit_quote(pinned, max_words)
    sentences = _sentences(text)
    if not sentences:
        return excerpt(text, query_terms, max_words)
    if len(sentences) == 1:
        return fit_quote(sentences[0], max_words)

    best_idx = 0
    best_score = -999
    for idx, sent in enumerate(sentences):
        score = _sentence_score(sent, query_terms)
        if score > best_score:
            best_score = score
            best_idx = idx

    picked: list[str] = [sentences[best_idx]]
    total = word_count(picked[0])
    if total < min_words and best_idx + 1 < len(sentences):
        nxt = sentences[best_idx + 1]
        if SENTENCE_END_RE.search(nxt) and total + word_count(nxt) <= max_words:
            picked.append(nxt)
            total += word_count(nxt)
    if total < min_words and best_idx > 0:
        prev = sentences[best_idx - 1]
        if SENTENCE_END_RE.search(prev) and total + word_count(prev) <= max_words:
            picked.insert(0, prev)

    return fit_quote(" ".join(picked).strip(), max_words)


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
    return " OR ".join(parts[:12])
