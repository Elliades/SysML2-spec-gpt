from pathlib import Path

import pymupdf

from sysml_spec_qa.ingest.pdf import parse_pdf
from sysml_spec_qa.ingest.xmi import parse_metamodel
from sysml_spec_qa.ingest.build import ingest
from sysml_spec_qa.search import get_element, search, viewer_link
from sysml_spec_qa.textutil import word_count


def test_parse_pdf_toc(tmp_path: Path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "7.2.5 Namespaces")
    page.insert_text((72, 110), "Every name must be unique within a namespace.")
    page2 = doc.new_page()
    page2.insert_text((72, 80), "8.3.4 Connectors")
    page2.insert_text((72, 110), "A Connector is typed by an Association and binds related features.")
    doc.set_toc(
        [
            [1, "7.2.5 Namespaces", 1],
            [1, "8.3.4 Connectors", 2],
        ]
    )
    pdf = tmp_path / "mini.pdf"
    doc.save(pdf)
    doc.close()

    chunks = parse_pdf(pdf)
    ids = {c.clause_id for c in chunks}
    assert "7.2.5" in ids
    assert "8.3.4" in ids
    ns = next(c for c in chunks if c.clause_id == "7.2.5")
    assert "unique" in ns.text.lower()
    assert ns.page_start == 1
    assert ns.bboxes


def test_parse_xmi(tmp_path: Path):
    xml = """<?xml version="1.0"?>
    <XMI xmlns:xmi="http://www.omg.org/XMI">
      <packagedElement xmi:type="uml:Class" name="Connector"/>
      <packagedElement xmi:type="uml:Class" name="Namespace"/>
      <ownedRule xmi:type="uml:Constraint" name="checkNamespaceUniqueNames"/>
    </XMI>
    """
    path = tmp_path / "mini.xmi"
    path.write_text(xml, encoding="utf-8")
    items = parse_metamodel(path)
    names = {(i.name, i.kind) for i in items}
    assert ("Connector", "class") in names
    assert ("Namespace", "class") in names
    assert ("checkNamespaceUniqueNames", "constraint") in names


def test_ingest_and_search(tmp_path, monkeypatch):
    from sysml_spec_qa.ingest import download as download_mod
    from sysml_spec_qa.ingest import manifest as manifest_mod
    from sysml_spec_qa.ingest.manifest import SpecDoc

    pdf = tmp_path / "raw" / "kerml-1.0.pdf"
    pdf.parent.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "7.2.5 Namespaces")
    page.insert_text((72, 110), "Every owned name in a Namespace must be unique.")
    page2 = doc.new_page()
    page2.insert_text((72, 80), "8.3.4 Connectors")
    page2.insert_text((72, 110), "A Connector connects related features of its featuring type.")
    doc.set_toc([[1, "7.2.5 Namespaces", 1], [1, "8.3.4 Connectors", 2]])
    doc.save(pdf)
    doc.close()

    xmi = tmp_path / "raw" / "kerml-1.0.xmi"
    path_xml = """<?xml version="1.0"?>
    <XMI xmlns:xmi="http://www.omg.org/XMI">
      <packagedElement xmi:type="uml:Class" name="Connector"/>
      <packagedElement xmi:type="uml:Class" name="Namespace"/>
    </XMI>
    """
    xmi.write_text(path_xml, encoding="utf-8")

    fake = SpecDoc(
        id="kerml-1.0",
        title="KerML mini",
        version="2.0",
        family="kerml",
        lang_version="1.0",
        pdf_urls=("http://example.invalid/kerml.pdf",),
        metamodel_urls=(),
    )

    def fake_stack(version: str):
        return (fake,)

    def fake_ensure(doc, skip_download=False):
        return pdf, xmi, "local"

    monkeypatch.setattr(manifest_mod, "stack_docs", fake_stack)
    monkeypatch.setattr("sysml_spec_qa.ingest.build.stack_docs", fake_stack)
    monkeypatch.setattr("sysml_spec_qa.ingest.build.ensure_doc_files", fake_ensure)
    monkeypatch.setattr(download_mod, "ensure_doc_files", fake_ensure)

    db = tmp_path / "spec.sqlite"
    ingest("2.0", skip_download=True, db_path=db)

    hits = search("unicité des noms", version="2.0", k=3, db_path=db)
    assert hits
    assert any("namespace" in h.title.lower() or "unique" in h.excerpt.lower() for h in hits)
    assert sum(word_count(h.excerpt) for h in hits) <= 200

    hits2 = search("connector", version="2.0", k=3, db_path=db)
    assert any("connector" in (h.title + h.excerpt).lower() for h in hits2)

    card = get_element("Namespace", version="2.0", db_path=db)
    assert card is not None
    assert card["name"] == "Namespace"

    link = viewer_link("kerml-1.0", "2.0", 1, "7.2.5", "unique")
    assert "kerml-1.0" in link
    assert "clause=7.2.5" in link
