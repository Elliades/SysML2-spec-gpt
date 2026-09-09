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

## Run

**Viewer** (bind to localhost only):

```powershell
python -m sysml_spec_qa serve
```

Opens `http://127.0.0.1:8787`. Example deep link:

`http://127.0.0.1:8787/v/kerml-1.0/2.0?page=21&clause=7.2.5&q=unique`

**Cursor MCP** — copy `.cursor/mcp.json` into your Cursor user or project MCP config (paths already point at this workspace). Restart Cursor, start the viewer, then ask:

- « c’est quoi les règles d’unicité des noms ? »
- « à quoi je peux connecter un connector ? »

The MCP tools are `spec_route`, `spec_search`, `spec_get`, `spec_element`. They never load the whole spec into context (max ~800 tokens of excerpts).

**Eval** (needs a built index):

```powershell
python -m sysml_spec_qa eval
python -m pytest
```

## Layout

- `src/sysml_spec_qa/ingest/` — download, clause-split PDFs, parse XMI, SQLite FTS5
- `src/sysml_spec_qa/mcp_server.py` — Cursor tools
- `viewer/static/` — PDF.js viewer + bbox overlay
- `eval/questions.yaml` — gold questions
- `data/` — PDFs + `index/spec.sqlite` (local only)

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
