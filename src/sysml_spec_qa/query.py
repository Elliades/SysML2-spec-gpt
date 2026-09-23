from __future__ import annotations

import re

from .synonyms import PHRASES, STOPWORDS, WORD_MAP, expand_query
from .textutil import WORD_RE, fold

FR_HINTS = {
    "comment", "quoi", "regle", "regles", "unicite", "connecter", "connecteur",
    "connexion", "nom", "noms", "import", "importation", "visibilite", "exemple",
    "exigence", "definition", "utilisation", "peut", "puis", "dans", "les", "des",
    "une", "est", "ce", "ca", "quoi", "pourquoi",
}

EN_HINTS = {
    "what", "how", "can", "does", "rule", "rules", "unique", "connect", "connector",
    "connection", "name", "names", "import", "visibility", "example", "requirement",
    "definition", "usage", "feature", "namespace", "binding", "redefinition",
}

KERML_EXPLICIT = re.compile(r"\b(kerml|kernel\s+modeling\s+language)\b", re.I)


def wants_kerml(question: str) -> bool:
    return bool(KERML_EXPLICIT.search(question))


INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("example", re.compile(r"\b(exemple|example|sample|listing)\b", re.I)),
    ("inventory", re.compile(
        r"\b(quels? sont|quelles? sont|what are|what can|elements?|éléments?|"
        r"membres?|contenu|contained|mis dans|put (?:in|into))\b",
        re.I,
    )),
    ("closed", re.compile(
        r"\b(est-ce que|puis-je|peux-je|can i|may i|is it|does a|does the)\b",
        re.I,
    )),
    ("can_connect", re.compile(r"\b(connect|connecter|connection|connexion|connecter)\b", re.I)),
    ("name_resolution", re.compile(r"\b(unique|unicit|unicit[eé]|name|nom|noms|namespace|qualified)\b", re.I)),
    ("constraint", re.compile(r"\b(constraint|contrainte|validate|check)\b", re.I)),
    ("syntax", re.compile(r"\b(syntax|grammar|concrete|notation)\b", re.I)),
    ("semantics", re.compile(r"\b(semantics|semantic|meaning|signification)\b", re.I)),
    ("metaclass", re.compile(r"\b([A-Z][a-z]+(?:Usage|Definition|Connector|Namespace))\b")),
]


def detect_language(question: str) -> str:
    tokens = {fold(t) for t in WORD_RE.findall(question)}
    fr = len(tokens & FR_HINTS)
    en = len(tokens & EN_HINTS)
    if fr > en and fr >= 2:
        return "fr"
    if en > fr and en >= 2:
        return "en"
    if any(ch in question for ch in "àâäéèêëïîôùûüç"):
        return "fr"
    return "en"


def detect_intents(question: str) -> list[str]:
    intents: list[str] = []
    for name, pattern in INTENT_PATTERNS:
        if pattern.search(question):
            intents.append(name)
    return intents or ["general"]


def camel_to_words(text: str) -> list[str]:
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).split()
    return [p for p in parts if len(p) > 2]


def analyze_query(question: str) -> dict:
    language = detect_language(question)
    intents = detect_intents(question)
    terms = expand_query(question)
    for match in re.finditer(r"\b((?:check|validate|derive)[A-Z][A-Za-z0-9]+)\b", question):
        name = match.group(1)
        intents = list(dict.fromkeys(intents + ["constraint"]))
        terms.append(name)
        terms.extend(camel_to_words(name))
    for match in re.finditer(r"\b[A-Z][a-z]+(?:Usage|Definition|Connector|Namespace)\b", question):
        terms.extend(camel_to_words(match.group(0)))
    seen: set[str] = set()
    canonical: list[str] = []
    for t in terms:
        key = fold(t)
        if key in seen or key in STOPWORDS or len(key) < 2:
            continue
        seen.add(key)
        canonical.append(t)
    explicit_kerml = wants_kerml(question)
    if "closed" in intents:
        answer_kind = "verdict"
    elif "inventory" in intents:
        answer_kind = "list"
    else:
        answer_kind = "verdict"
    return {
        "language": language,
        "intents": intents,
        "terms": canonical,
        "answer_kind": answer_kind,
        "wants_examples": "example" in intents,
        "wants_normative": any(i in intents for i in ("constraint", "syntax", "can_connect", "name_resolution")),
        "wants_kerml": explicit_kerml,
        "prefer_sysml": not explicit_kerml,
    }
