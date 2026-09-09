from sysml_spec_qa.ingest.extract import (
    extract_cross_refs,
    extract_examples,
    split_passages,
)


def test_split_passages():
    paras = [" ".join(["word"] * 90) for _ in range(3)]
    text = "\n\n".join(paras)
    passages = split_passages(
        "kerml-1.0",
        "2.0",
        "8.3.2.4.5",
        "8.3.2.4.5 Namespace",
        "syntax",
        True,
        10,
        11,
        text,
        [],
    )
    assert len(passages) >= 2
    assert all(40 <= p.word_count <= 400 for p in passages)


def test_extract_cross_refs():
    text = "See 7.2.5 for namespace rules and Clause 8.3.2.4 for syntax."
    refs = extract_cross_refs(text, "kerml-1.0", "8.3.2.4.5", "2.0")
    targets = {r["target_clause_id"] for r in refs}
    assert "7.2.5" in targets
    assert "8.3.2.4" in targets


def test_extract_examples_sysml():
    text = """Example:
part def Vehicle {
  part engine : Engine;
}
"""
    examples = extract_examples("sysml-2.0-language", "2.0", "7.1", text, 5, [])
    assert examples
    assert "part def" in examples[0].text.lower()
