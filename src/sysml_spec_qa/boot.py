"""First-boot helper: build the spec index if missing, then serve the viewer."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import DB_PATH, DEFAULT_VERSION, VIEWER_HOST, VIEWER_PORT
from .search import list_documents


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def index_ready(db_path: Path | None = None, version: str | None = None) -> bool:
    """True when the SQLite index exists and contains the requested stack."""
    path = db_path or DB_PATH
    if not path.exists() or path.stat().st_size < 64:
        return False
    try:
        docs = list_documents(path)
    except (FileNotFoundError, sqlite3.Error, OSError):
        return False
    if not docs:
        return False
    if version and version != "all":
        return any(doc.get("version") == version for doc in docs)
    return True


def ensure_index(
    *,
    version: str | None = None,
    force: bool | None = None,
    skip: bool | None = None,
    db_path: Path | None = None,
) -> bool:
    """Download specs and build the index when needed. Returns True if ingest ran."""
    from .ingest.build import ingest as ingest_one
    from .ingest.build import ingest_all

    path = db_path or DB_PATH
    stack = version or os.environ.get("SYSML_SPEC_VERSION", DEFAULT_VERSION)
    do_force = _flag("SYSML_INGEST_FORCE") if force is None else force
    do_skip = _flag("SYSML_SKIP_INGEST") if skip is None else skip

    if do_skip and not do_force:
        print("boot: skip ingest (SYSML_SKIP_INGEST=1)")
        return False
    if not do_force and index_ready(path, stack):
        print(f"boot: index ready at {path}")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"boot: ingesting SysML/KerML {stack} into {path} (first start can take several minutes)")
    if stack == "all":
        ingest_all(["2.0", "2.1"], db_path=path)
    else:
        ingest_one(stack, db_path=path)
    if not index_ready(path, stack):
        raise SystemExit(f"boot: ingest finished but the index is still empty at {path}")
    print(f"boot: ingest complete ({path})")
    return True


def main() -> None:
    ensure_index()
    from .viewer_app import main as serve

    print(f"boot: starting viewer on {VIEWER_HOST}:{VIEWER_PORT}")
    serve()
