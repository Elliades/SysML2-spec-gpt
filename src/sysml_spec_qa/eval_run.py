from __future__ import annotations

from pathlib import Path

import yaml

from .config import EVAL_QUESTIONS, MAX_TOTAL_EXCERPT_WORDS
from .pack import answer_pack
from .search import search_passages
from .textutil import fold, word_count


def main(questions_path: Path | None = None) -> int:
    path = questions_path or EVAL_QUESTIONS
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = data["questions"]
    failed = 0
    for item in questions:
        qid = item["id"]
        query = item["q"]
        version = item.get("version", "2.0")
        try:
            pack = answer_pack(
                query,
                version=version,
                include_examples=item.get("wants_examples", False),
            )
            passages = search_passages(query, version=version, k=3)
        except FileNotFoundError as exc:
            print(exc)
            return 2

        primary = pack.primary
        blob = ""
        blob = fold(query)
        if primary:
            blob += fold(primary.quote_en + " " + primary.title + " " + primary.doc_id)
        if pack.exception:
            blob += fold(pack.exception.quote_en + " " + pack.exception.title)
        blob += fold(" ".join(p.quote_en + " " + p.title for p in passages))

        def term_present(term: str) -> bool:
            ft = fold(term)
            if ft in blob:
                return True
            if ft.startswith("distinguish") and "distinguish" in blob:
                return True
            if ft == "unique" and ("unique" in blob or "uniqueness" in blob):
                return True
            return False

        missing = [t for t in item.get("expect_terms", []) if not term_present(t)]
        any_terms = item.get("expect_any_terms") or []
        if any_terms and not any(term_present(t) for t in any_terms):
            missing.append(f"any_of({','.join(any_terms)})")

        primary_doc_ok = True
        expect_doc = item.get("expect_primary_doc")
        if expect_doc and primary:
            primary_doc_ok = fold(expect_doc) in fold(primary.doc_id)

        exception_doc_ok = True
        expect_exc_doc = item.get("expect_exception_doc")
        if expect_exc_doc:
            exception_doc_ok = bool(
                pack.exception and fold(expect_exc_doc) in fold(pack.exception.doc_id)
            )

        primary_clause_ok = True
        expect_clauses = item.get("expect_primary_clauses") or item.get("expect_clauses") or []
        if expect_clauses and primary:
            primary_clause_ok = primary.clause_id in expect_clauses or any(
                primary.clause_id.startswith(c.rsplit(".", 1)[0] + ".")
                for c in expect_clauses
                if c.count(".") >= 3
            )

        pack_words = word_count(primary.quote_en) if primary else 0
        if pack.exception:
            pack_words += word_count(pack.exception.quote_en)
        budget_ok = pack_words <= MAX_TOTAL_EXCERPT_WORDS

        pack_ok = primary is not None and bool(pack.session_url)
        if expect_clauses:
            pack_ok = pack_ok and primary_clause_ok

        lang_ok = True
        if item.get("language"):
            lang_ok = pack.question_language == item["language"]

        examples_ok = True
        if item.get("wants_examples"):
            examples_ok = len(pack.examples) > 0
        elif not item.get("wants_examples"):
            examples_ok = len(pack.examples) == 0

        cost_ok = bool(pack.cost.get("retrieval_ms") is not None and pack.cost.get("pack_tokens"))

        ok = (
            bool(primary or passages)
            and not missing
            and primary_doc_ok
            and exception_doc_ok
            and primary_clause_ok
            and budget_ok
            and pack_ok
            and lang_ok
            and examples_ok
            and cost_ok
        )
        if not ok:
            failed += 1
        status = "PASS" if ok else "FAIL"
        pid = primary.clause_id if primary else "—"
        pdoc = primary.doc_id if primary else "—"
        print(
            f"{status} {qid}: primary={pdoc} {pid} "
            f"words={pack_words} missing={missing} "
            f"doc_ok={primary_doc_ok} clause_ok={primary_clause_ok} "
            f"examples={len(pack.examples)} cost={pack.cost.get('pack_tokens')}tok"
        )
        if pack.session_url:
            print(f"    session: {pack.session_url[:120]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
