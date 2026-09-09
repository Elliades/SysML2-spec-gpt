from pathlib import Path

import pymupdf

from sysml_spec_qa.ingest.build import ingest
from sysml_spec_qa.ingest.manifest import SpecDoc
from sysml_spec_qa.pack import answer_pack, cites_link, clause_pack
from sysml_spec_qa.query import analyze_query


def _mini_ingest(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "raw" / "kerml-1.0.pdf"
    pdf.parent.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "7.2.5 Namespaces")
    page.insert_text((72, 110), "Every owned name in a Namespace must be unique.")
    page2 = doc.new_page()
    page2.insert_text((72, 80), "8.3.2.4.5 Namespace")
    page2.insert_text((72, 110), "All memberships of a Namespace must be distinguishable from each other.")
    doc.set_toc([[1, "7.2.5 Namespaces", 1], [1, "8.3.2.4.5 Namespace", 2]])
    doc.save(pdf)
    doc.close()

    fake = SpecDoc(
        id="kerml-1.0",
        title="KerML mini",
        version="2.0",
        family="kerml",
        lang_version="1.0",
        pdf_urls=("http://example.invalid/kerml.pdf",),
        metamodel_urls=(),
    )
    monkeypatch.setattr("sysml_spec_qa.ingest.build.stack_docs", lambda version: (fake,))
    monkeypatch.setattr(
        "sysml_spec_qa.ingest.build.ensure_doc_files",
        lambda doc, skip_download=False: (pdf, None, "local"),
    )
    db = tmp_path / "spec.sqlite"
    ingest("2.0", skip_download=True, db_path=db)
    return db


def test_analyze_query_fr(tmp_path, monkeypatch):
    q = analyze_query("c'est quoi les règles d'unicité des noms ?")
    assert q["language"] == "fr"
    assert "name_resolution" in q["intents"]


def test_answer_pack_shape(tmp_path, monkeypatch):
    db = _mini_ingest(tmp_path, monkeypatch)
    pack = answer_pack("unicité des noms", version="2.0", db_path=db)
    assert pack.primary is not None
    assert pack.question_language == "fr"
    assert pack.session_url
    assert "/cites?" in pack.session_url
    assert pack.cost["pack_tokens"] > 0
    assert "retrieval_ms" in pack.cost
    assert "shape" in pack.answer_contract
    assert pack.answer_contract["shape"][0] == "verdict"
    assert len(pack.examples) == 0


def test_clause_pack_and_cites_link(tmp_path, monkeypatch):
    db = _mini_ingest(tmp_path, monkeypatch)
    result = clause_pack(["7.2.5", "8.3.2.4.5"], version="2.0", db_path=db)
    assert len(result["passages"]) == 2
    assert result["session_url"]
    link = cites_link([("kerml-1.0", "2.0", "7.2.5")], "unique")
    assert "/cites?ids=" in link
