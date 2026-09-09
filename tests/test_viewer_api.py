from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from sysml_spec_qa.ingest.build import ingest
from sysml_spec_qa.ingest.manifest import SpecDoc
from sysml_spec_qa.viewer_app import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "raw" / "kerml-1.0.pdf"
    pdf.parent.mkdir()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "7.2.5 Namespaces")
    page.insert_text((72, 110), "Every owned name in a Namespace must be unique.")
    page2 = doc.new_page()
    page2.insert_text((72, 80), "8.3.2.4.5 Namespace")
    page2.insert_text((72, 110), "All memberships of a Namespace must be distinguishable.")
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
    monkeypatch.setattr("sysml_spec_qa.config.DB_PATH", db)
    monkeypatch.setattr("sysml_spec_qa.search.DB_PATH", db)
    return db


APP_SHELL_MARKERS = (
    'id="viewer-app"',
    'data-viewer-app="3"',
    'lang="fr"',
    'id="toc-panel"',
    'id="cite-panel"',
    'id="pdf-toc-panel"',
    'id="pdf-menu-btn"',
    "Lecteur spec",
)


def _assert_app_shell(page):
    assert page.status_code == 200
    for marker in APP_SHELL_MARKERS:
        assert marker in page.text, f"missing shell marker: {marker}"


def test_viewer_root_serves_app_shell(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    _assert_app_shell(client.get("/"))


def test_viewer_reader_route(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    _assert_app_shell(client.get("/r/kerml-1.0/2.0/7.2.5"))


def test_pack_redirects_to_cites(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(create_app(), follow_redirects=False)
    resp = client.get("/pack", params={"refs": "kerml-1.0:2.0:7.2.5", "q": "unique"})
    assert resp.status_code == 302
    assert "/cites?" in resp.headers["location"]


def test_api_health(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "sysml-spec-qa"
    assert body["status"] == "ok"
    assert body["uptime"] >= 0
    assert body["checks"]["frontend"]["status"] == "ok"
    assert body["checks"]["backend"]["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["database"]["documents"] >= 1


def test_api_toc_and_clause_html(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    toc = client.get("/api/toc", params={"doc": "kerml-1.0", "version": "2.0"})
    assert toc.status_code == 200
    assert any(row["clause_id"] == "7.2.5" for row in toc.json())

    html = client.get(
        "/api/clause_html",
        params={"doc": "kerml-1.0", "version": "2.0", "clause": "7.2.5", "q": "Namespaces"},
    )
    assert html.status_code == 200
    body = html.json()["html"]
    assert 'id="clause-7.2.5"' in body
    assert "unique" in body.lower() or "<mark>" in body


def test_api_cites(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    pack = client.get(
        "/api/cites",
        params={"refs": "kerml-1.0:2.0:7.2.5", "q": "unique"},
    )
    assert pack.status_code == 200
    data = pack.json()
    assert data["count"] == 1
    assert data["items"][0]["quote_en"]


def test_resolve_pdf_path_falls_back_to_raw(tmp_path, monkeypatch):
    from sysml_spec_qa.config import resolve_pdf_path

    raw = tmp_path / "raw"
    raw.mkdir()
    pdf = raw / "kerml-1.0.pdf"
    pdf.write_bytes(b"%PDF-1.4 mini\n")
    monkeypatch.setattr("sysml_spec_qa.config.RAW_DIR", raw)
    found = resolve_pdf_path("kerml-1.0", r"C:\missing\kerml-1.0.pdf")
    assert found == pdf
    assert resolve_pdf_path("missing-doc", r"C:\missing\no.pdf") is None


def test_pdf_file_serves_from_raw_fallback(tmp_path, monkeypatch):
    import sqlite3

    db = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr("sysml_spec_qa.config.RAW_DIR", tmp_path / "raw")
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE documents SET pdf_path = ? WHERE id = ?",
        (r"C:\old-host\kerml-1.0.pdf", "kerml-1.0"),
    )
    conn.commit()
    conn.close()
    client = TestClient(create_app())
    resp = client.get("/files/kerml-1.0.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content[:5] == b"%PDF-"


def test_api_highlights_returns_focus(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    resp = client.get(
        "/api/highlights",
        params={"doc": "kerml-1.0", "version": "2.0", "clause": "7.2.5", "q": "unique"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc"] == "kerml-1.0"
    assert isinstance(body["bboxes"], list)
    assert "unique" in body["focus"].lower() or body["focus"]
