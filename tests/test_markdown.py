from sysml_spec_qa.markdown import clause_slug, export_markdown, md_dir_for_db, render_clause_md


def test_clause_slug():
    assert clause_slug("7.2.5", "7.2.5 Namespaces").startswith("7-2-5")
    assert "namespace" in clause_slug("7.2.5", "7.2.5 Namespaces")


def test_render_and_export(tmp_path, monkeypatch):
    from sysml_spec_qa.ingest.build import ingest
    from sysml_spec_qa.ingest.manifest import SpecDoc
    import pymupdf

    pdf = tmp_path / "raw" / "kerml-1.0.pdf"
    pdf.parent.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "7.2.5 Namespaces")
    page.insert_text((72, 110), "Every owned name in a Namespace must be unique.")
    doc.set_toc([[1, "7.2.5 Namespaces", 1]])
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
    md_dir = md_dir_for_db(db)
    stats = export_markdown(db_path=db, md_dir=md_dir, versions=["2.0"], force=True)
    assert stats["documents"] == 1
    assert stats["clauses"] >= 1
    assert (md_dir / "index.md").exists()
    files = list(md_dir.rglob("*.md"))
    assert any(path.name.endswith(".md") and "namespace" in path.name for path in files)
    body = next(path.read_text(encoding="utf-8") for path in files if "namespace" in path.name)
    assert "unique" in body.lower()

    rendered = render_clause_md(
        {
            "doc_id": "kerml-1.0",
            "version": "2.0",
            "clause_id": "7.2.5",
            "title": "7.2.5 Namespaces",
            "kind": "kernel",
            "normative": False,
            "page_start": 1,
            "page_end": 1,
        },
        "Every owned name in a Namespace must be unique.",
        [],
        ["espace de noms"],
    )
    assert rendered.startswith("---")
    assert "7.2.5" in rendered
