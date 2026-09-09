from pathlib import Path

from sysml_spec_qa.boot import ensure_index, index_ready
from sysml_spec_qa.db import rebuild_empty


def _mini_db(path: Path, version: str = "2.0") -> Path:
    conn = rebuild_empty(path)
    conn.execute(
        """
        INSERT INTO documents
          (id, title, version, family, lang_version, pdf_path, metamodel_path, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("kerml-1.0", "KerML mini", version, "kerml", "1.0", None, None, "local"),
    )
    conn.commit()
    conn.close()
    return path


def test_index_ready_missing(tmp_path):
    assert index_ready(tmp_path / "missing.sqlite") is False


def test_index_ready_empty_file(tmp_path):
    empty = tmp_path / "spec.sqlite"
    empty.write_bytes(b"")
    assert index_ready(empty) is False


def test_index_ready_after_documents(tmp_path):
    db = _mini_db(tmp_path / "spec.sqlite")
    assert index_ready(db) is True
    assert index_ready(db, version="2.0") is True
    assert index_ready(db, version="2.1") is False


def test_ensure_index_skips_when_ready(tmp_path, monkeypatch):
    db = _mini_db(tmp_path / "spec.sqlite")
    called: list[str] = []
    monkeypatch.setattr(
        "sysml_spec_qa.ingest.build.ingest",
        lambda *args, **kwargs: called.append("ingest"),
    )
    ran = ensure_index(version="2.0", db_path=db)
    assert ran is False
    assert called == []


def test_ensure_index_runs_when_missing(tmp_path, monkeypatch):
    db = tmp_path / "spec.sqlite"
    calls: list[tuple] = []

    def fake_ingest(version, skip_download=False, db_path=None):
        calls.append((version, db_path))
        _mini_db(db_path, version=version)

    monkeypatch.setattr("sysml_spec_qa.ingest.build.ingest", fake_ingest)
    ran = ensure_index(version="2.0", db_path=db)
    assert ran is True
    assert calls == [("2.0", db)]
    assert index_ready(db, "2.0")


def test_ensure_index_skip_flag(tmp_path):
    db = tmp_path / "spec.sqlite"
    ran = ensure_index(version="2.0", skip=True, db_path=db)
    assert ran is False
    assert not db.exists()


def test_ensure_index_force_rebuilds(tmp_path, monkeypatch):
    db = _mini_db(tmp_path / "spec.sqlite")
    calls: list[str] = []

    def fake_ingest(version, skip_download=False, db_path=None):
        calls.append(version)
        _mini_db(db_path, version=version)

    monkeypatch.setattr("sysml_spec_qa.ingest.build.ingest", fake_ingest)
    ran = ensure_index(version="2.0", force=True, db_path=db)
    assert ran is True
    assert calls == ["2.0"]
