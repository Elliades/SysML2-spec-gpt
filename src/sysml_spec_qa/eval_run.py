from __future__ import annotations

import sys
from pathlib import Path

import yaml

from .config import EVAL_QUESTIONS, MAX_TOTAL_EXCERPT_WORDS
from .search import search
from .textutil import fold, word_count


def main(questions_path: Path | None = None) -> int:
    path = questions_path or EVAL_QUESTIONS
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = data["questions"]
    failed = 0
    for item in questions:
        qid = item["id"]
        query = item["q"]
        try:
            hits = search(query, version=item.get("version", "2.0"), k=3)
        except FileNotFoundError as exc:
            print(exc)
            return 2
        blob = fold(" ".join(h.excerpt + " " + h.title + " " + h.doc_id for h in hits))
        missing = [t for t in item.get("expect_terms", []) if fold(t) not in blob]
        docs_ok = True
        expect_docs = item.get("expect_docs") or []
        if expect_docs:
            docs_ok = any(any(fold(d) in fold(h.doc_id) for d in expect_docs) for h in hits)
        words = sum(word_count(h.excerpt) for h in hits)
        budget_ok = words <= MAX_TOTAL_EXCERPT_WORDS
        ok = bool(hits) and not missing and docs_ok and budget_ok
        if not ok:
            failed += 1
        status = "PASS" if ok else "FAIL"
        print(f"{status} {qid}: hits={len(hits)} words={words} missing={missing} docs_ok={docs_ok}")
        for hit in hits:
            print(f"    {hit.doc_id} {hit.clause_id} p.{hit.page_start} {hit.title[:80]}")
    print(f"{len(questions) - failed}/{len(questions)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
