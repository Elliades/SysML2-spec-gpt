from __future__ import annotations

from .textutil import WORD_RE, fold

# Phrase replacements applied before tokenization (folded keys).
PHRASES: list[tuple[str, list[str]]] = [
    ("espace de noms", ["namespace", "namespaces"]),
    ("unicite des noms", ["unique", "uniqueness", "name", "namespace"]),
    ("regle d unicite", ["unique", "uniqueness", "namespace"]),
    ("regles d unicite", ["unique", "uniqueness", "namespace"]),
    ("qualified name", ["qualified", "name", "qualifiedname"]),
    ("nom unique", ["unique", "name", "namespace"]),
    ("binding connector", ["bindingconnector", "connector"]),
    ("connection usage", ["connectionusage", "connector"]),
]

STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "with", "what",
    "is", "are", "can", "i", "je", "les", "des", "une", "un", "du", "de", "la",
    "le", "quoi", "cest", "c", "est", "dans", "un", "une", "comment", "quoi",
    "ca", "peux", "peut", "puis", "mon", "ma", "mes", "how", "does", "do",
}

WORD_MAP: dict[str, list[str]] = {
    "unicite": ["unique", "uniqueness", "uniquely"],
    "unicité": ["unique", "uniqueness"],
    "unique": ["unique", "uniqueness"],
    "uniqueness": ["unique", "uniqueness", "namespace"],
    "nom": ["name", "names", "named", "namespace"],
    "noms": ["name", "names", "named"],
    "name": ["name", "names", "named"],
    "namespace": ["namespace", "namespaces"],
    "namespaces": ["namespace", "namespaces"],
    "connecter": ["connector", "connection", "connectionusage"],
    "connecteur": ["connector", "connectors", "connection", "connectionusage"],
    "connecteurs": ["connector", "connectors", "connection"],
    "connector": ["connector", "connectors", "connection", "bindingconnector"],
    "connexion": ["connection", "connector", "connectionusage"],
    "connection": ["connection", "connector", "connectionusage"],
    "extremite": ["end", "ends", "relatedfeature"],
    "extrémité": ["end", "ends", "relatedfeature"],
    "end": ["end", "ends", "relatedfeature"],
    "port": ["port", "portusage", "portdefinition"],
    "feature": ["feature", "usage"],
    "import": ["import", "imports", "visibility"],
    "importation": ["import", "importing"],
    "visibilite": ["visibility", "public", "private"],
    "visibilité": ["visibility", "public", "private"],
    "redefinition": ["redefinition", "redefine"],
    "redefinir": ["redefinition", "redefine"],
    "specialisation": ["specialization", "subsetting"],
    "specialization": ["specialization", "subsetting"],
    "contrainte": ["constraint", "check", "validate"],
    "constraint": ["constraint", "check"],
    "exigence": ["requirement", "requirementusage"],
    "requirement": ["requirement", "requirementusage"],
    "partie": ["part", "partusage", "partdefinition"],
    "attribut": ["attribute", "attributeusage"],
    "action": ["action", "actionusage"],
    "etat": ["state", "stateusage"],
    "état": ["state", "stateusage"],
    "succession": ["succession"],
    "binding": ["binding", "bindingconnector"],
    "flow": ["flow", "flowconnection"],
    "multiplicite": ["multiplicity"],
    "multiplicité": ["multiplicity"],
    "heritage": ["subclassification", "specialization"],
    "héritage": ["subclassification", "specialization"],
    "package": ["package", "namespace"],
    "definition": ["definition"],
    "usage": ["usage"],
    "membership": ["membership", "namespace"],
    "distinguishability": ["distinguishable", "distinguish", "membership"],
    "distinguishibility": ["distinguishable", "distinguish", "membership"],
    "visibility": ["visibility"],
}


def expand_query(question: str) -> list[str]:
    folded = fold(question)
    extras: list[str] = []
    for phrase, syns in PHRASES:
        if phrase in folded:
            extras.extend(syns)
    tokens = WORD_RE.findall(question)
    out: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        key = fold(token)
        if len(key) < 2 or key in seen:
            return
        seen.add(key)
        out.append(token)

    for extra in extras:
        add(extra)
    for tok in tokens:
        if fold(tok) in STOPWORDS:
            continue
        add(tok)
        for syn in WORD_MAP.get(fold(tok), []):
            add(syn)
    return out
