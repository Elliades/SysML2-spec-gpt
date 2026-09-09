from __future__ import annotations

import os
from pathlib import Path

def repo_root() -> Path:
    env = os.environ.get("SYSML_SPEC_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


ROOT = repo_root()
DATA_DIR = Path(os.environ.get("SYSML_SPEC_DATA", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
INDEX_DIR = DATA_DIR / "index"
MD_DIR = Path(os.environ.get("SYSML_SPEC_MD", DATA_DIR / "md"))
DB_PATH = Path(os.environ.get("SYSML_SPEC_DB", INDEX_DIR / "spec.sqlite"))
VIEWER_STATIC = ROOT / "viewer" / "static"
EVAL_QUESTIONS = ROOT / "eval" / "questions.yaml"

VIEWER_HOST = os.environ.get("SYSML_VIEWER_HOST", "127.0.0.1")
VIEWER_PORT = int(os.environ.get("SYSML_VIEWER_PORT", "8797"))
VIEWER_URL = os.environ.get("SYSML_VIEWER_URL", f"http://{VIEWER_HOST}:{VIEWER_PORT}")

DEFAULT_VERSION = os.environ.get("SYSML_SPEC_VERSION", "2.0")

MAX_HITS = 1
MAX_EXCERPT_WORDS = 80
MAX_TOTAL_EXCERPT_WORDS = 160
MIN_EXCERPT_WORDS = 40
SYSML_SCORE_THRESHOLD = 4
EUR_PER_MTOK = float(os.environ.get("SYSML_EUR_PER_MTOK", "2.50"))
MAX_CLAUSE_WORDS = 800
MAX_GET_WORDS = 600


def resolve_pdf_path(doc_id: str, stored: str | None = None) -> Path | None:
    """Prefer a live file: stored path first, then data/raw/<doc_id>.pdf."""
    candidates: list[Path] = []
    if stored:
        candidates.append(Path(stored))
    candidates.append(RAW_DIR / f"{doc_id}.pdf")
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None
