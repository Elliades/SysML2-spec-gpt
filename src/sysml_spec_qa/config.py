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
DB_PATH = Path(os.environ.get("SYSML_SPEC_DB", INDEX_DIR / "spec.sqlite"))
VIEWER_STATIC = ROOT / "viewer" / "static"
EVAL_QUESTIONS = ROOT / "eval" / "questions.yaml"

VIEWER_HOST = os.environ.get("SYSML_VIEWER_HOST", "127.0.0.1")
VIEWER_PORT = int(os.environ.get("SYSML_VIEWER_PORT", "8787"))
VIEWER_URL = os.environ.get("SYSML_VIEWER_URL", f"http://{VIEWER_HOST}:{VIEWER_PORT}")

DEFAULT_VERSION = os.environ.get("SYSML_SPEC_VERSION", "2.0")

MAX_HITS = 3
MAX_EXCERPT_WORDS = 220
MAX_TOTAL_EXCERPT_WORDS = 800
MAX_CLAUSE_WORDS = 800
MAX_GET_WORDS = 600
