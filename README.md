# SysML v2 Spec QA

Local, token-efficient search over the **KerML** and **SysML v2** language specifications, wired into Cursor via MCP. Answers come back as short excerpts plus **clickable links** that open a localhost PDF viewer on the cited page, with the passage highlighted.

This repository does **not** contain the OMG PDFs. The OMG license forbids republishing the specifications on a network. Ingest downloads them into `data/` (gitignored) for personal informational use.

## Why KerML is in the corpus

Typical questions are not all in the SysML Language PDF:

- Name uniqueness lives in KerML `Namespace`
- Connector / BindingConnector are KerML Kernel concepts; SysML adds ConnectionUsage, ports, etc.

## Setup

Python 3.11+. From this directory:

```powershell
cd C:\workspace\sysml-spec-qa
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m sysml_spec_qa ingest --version 2.0
```

`ingest --version 2.1` adds the current SysML-v2-Release beta PDFs (KerML 1.1 / SysML 2.1).

Rebuild the index from already-downloaded files:

```powershell
python -m sysml_spec_qa ingest --skip-download
```

Ingest also writes searchable markdown under `data/md/` (gitignored, same as the PDFs). Rebuild markdown only:

```powershell
python -m sysml_spec_qa export-md
```

Open `data/md/index.md` or a clause file such as `data/md/2.0/kerml-1.0/7-2-5-namespaces.md` and use Cursor search.

## Run

Default viewer port is **8797** (`SYSML_VIEWER_PORT`) — avoids collision with Covas Trade Intel on 8787.

**One-shot viewer**:

```powershell
python -m sysml_spec_qa serve
```

**Worker autostart** (like `quatermaster-backup` — scheduled task + Startup shortcut):

```powershell
cd C:\workspace\sysml-spec-qa
.\scripts\install-worker.ps1
# elevated optional; re-run to update task/shortcut
.\scripts\uninstall-worker.ps1   # remove
```

Registers **`SysmlSpecQa-Worker`** (AtStartup +45s, AtLogOn). Logs: `data/logs/worker.log`.

Opens `http://127.0.0.1:8797`. Example deep links:

`http://127.0.0.1:8797/r/sysml-2.0-language/2.0/7.5.1?q=connection` (HTML clause reader + highlight)

`http://127.0.0.1:8797/cites?ids=kerml-1.0:2.0:8.3.2.4.5,sysml-2.0-language:2.0:7.5.1&q=connector` (multi-cite session)

Health: `GET http://127.0.0.1:8797/api/health`

Legacy `/v/…`, `/m/…`, `/pack?refs=…` redirect to the new routes.

**Cursor MCP** — copy `.cursor/mcp.json` into your Cursor user or project MCP config (`SYSML_VIEWER_URL` must match the worker port). Restart Cursor, then ask:

- « c’est quoi les règles d’unicité des noms ? »
- « à quoi je peux connecter un connector ? »

The MCP tools are `spec_element`, `spec_answer_pack`, `spec_clause_pack`, `spec_examples`, plus `spec_route`, `spec_search`, `spec_get`. Prefer `spec_answer_pack` for questions: it returns one primary cite (+ optional exception), `session_url`, exact English `quote_en`, and `cost` (tokens, ms, €). Token budget stays around 160 words of source text.

**Eval** (needs a built index):

```powershell
python -m sysml_spec_qa eval
python -m pytest
```

## Layout

- `src/sysml_spec_qa/ingest/` — download, clause-split PDFs, parse XMI, SQLite FTS5
- `src/sysml_spec_qa/mcp_server.py` — Cursor tools
- `scripts/worker.ps1` — restart loop for the viewer (used by the scheduled task)
- `scripts/install-worker.ps1` — register autostart on this PC
- `viewer/static/` — clause reader UI
- `eval/questions.yaml` — gold questions
- `data/` — PDFs + `index/spec.sqlite` + `md/` clause files (local only)

## Corpus

| Stack | Documents | Source |
| --- | --- | --- |
| 2.0 formal | KerML 1.0 + SysML 2.0 Language + XMI | OMG (`KerML/1.0/PDF`, `SysML/2.0/Language/PDF`, `*/20250201/*.xmi`) |
| 2.1 beta | KerML + SysML Language PDFs | [SysML-v2-Release `doc/`](https://github.com/Systems-Modeling/SysML-v2-Release/tree/master/doc) |

Transformation v1→v2 and the API spec are out of scope for v1.

## GitHub

This project is a dedicated repo (not Q-home). To publish:

```powershell
gh repo create Elliades/sysml-spec-qa --private --source . --remote origin --push
```

Keep `data/` untracked so specification text is never pushed.
