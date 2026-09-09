# SysML v2 Spec QA

Local, token-efficient search over the **KerML** and **SysML v2** language specifications, wired into Cursor via MCP. Answers come back as short excerpts plus **clickable links** that open a localhost PDF viewer on the cited page, with the passage highlighted.

This repository does **not** contain the OMG PDFs. The OMG license forbids republishing the specifications on a network. Ingest downloads them into `data/` (gitignored) for personal informational use. Keep the viewer on a **private** LAN or Tailscale — do not expose it on the public internet.

## Deploy with Docker

On any machine with Docker Compose v2:

```bash
git clone https://github.com/Elliades/SysML2-spec-gpt.git
cd SysML2-spec-gpt
cp .env.example .env
# optional: set SYSML_VIEWER_URL to the hostname people will actually open
docker compose up --build
```

First start downloads the KerML / SysML PDFs (personal use) and builds `data/index/spec.sqlite` — several minutes, needs outbound HTTPS. Later starts reuse `./data` and come up in seconds.

Then open `http://localhost:3112` · health: `GET /api/health`.

| Variable | Default | Role |
| --- | --- | --- |
| `SYSML_HOST_PORT` | `3112` | Host port published as `localhost:<port>` |
| `SYSML_VIEWER_URL` | `http://localhost:3112` | Links in MCP / cites (set this to your LAN or reverse-proxy URL) |
| `SYSML_SPEC_VERSION` | `2.0` | Stack to ingest: `2.0`, `2.1`, or `all` |
| `SYSML_SKIP_INGEST` | `0` | `1` = start even without an index (pre-copied `data/index`) |
| `SYSML_INGEST_FORCE` | `0` | `1` = rebuild the index on next start |
| `SYSML_DATA` | `./data` | Bind-mount for PDFs + sqlite + markdown |

Stop: `docker compose down`. Wipe the corpus: delete `./data` (or `docker compose down -v` if you switched to a named volume).

## Why KerML is in the corpus

Typical questions are not all in the SysML Language PDF:

- Name uniqueness lives in KerML `Namespace`
- Connector / BindingConnector are KerML Kernel concepts; SysML adds ConnectionUsage, ports, etc.

## Setup (local Python)

Python 3.11+. Prefer [Docker](#deploy-with-docker) on another host. From this directory:

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

**Viewer autostart** (local HTTP server on :8797 — **not** the Cursor Cloud Agent CLI):

```powershell
.\scripts\install-worker.ps1
```

**Cursor Cloud Agent worker** (My Machines — visible in **Cursor → Agents → environment**):

```powershell
.\scripts\install-agent-worker.ps1
```

Registers **`Quatermaster-sysml-spec-qa`** via `~\homelab\start-cursor-agent-worker.ps1` (Startup shortcut *Cursor Agent Worker*, same as Q-Home / Rec-it). Requires `agent login` once. Repo: `Elliades/SysML2-spec-gpt`.

Opens `http://127.0.0.1:8797`. Example deep links:

`http://127.0.0.1:8797/r/sysml-2.0-language/2.0/7.5.1?q=connection` (HTML clause reader + highlight)

`http://127.0.0.1:8797/cites?ids=kerml-1.0:2.0:8.3.2.4.5,sysml-2.0-language:2.0:7.5.1&q=connector` (multi-cite session)

Health: `GET http://127.0.0.1:8797/api/health`

**Apps (homelab, private LAN + Tailscale):** same Docker stack, port **3112**. Set `SYSML_VIEWER_URL=http://sysml.apps.chaos-art.fr` in `.env`. To copy a pre-built index instead of downloading PDFs on the server, rsync `data/index` + `data/md` and set `SYSML_SKIP_INGEST=1`. Never publish `data/raw` PDFs.

```powershell
cd C:\workspace\Apps-server
./provision/deploy-sysml-spec-qa.ps1
```

`http://apps:3112/` · `http://sysml.apps.chaos-art.fr/` · `GET /api/health`

Legacy `/v/…`, `/m/…`, `/pack?refs=…` redirect to the new routes.

**Cursor MCP** — une fois le viewer démarré :

```powershell
.\scripts\install-cursor-mcp.ps1
```

Puis **redémarrer Cursor**. Le serveur `sysml-spec` apparaît dans **Settings → MCP** (config globale `%USERPROFILE%\.cursor\mcp.json` + projet). Outils : `spec_answer_pack`, `spec_element`, `spec_search`, …

Copie manuelle possible depuis [`.cursor/mcp.json`](.cursor/mcp.json). Ensuite demander par exemple :

- « c’est quoi les règles d’unicité des noms ? »
- « à quoi je peux connecter un connector ? »

The MCP tools are `spec_element`, `spec_answer_pack`, `spec_clause_pack`, `spec_examples`, plus `spec_route`, `spec_search`, `spec_get`. Prefer `spec_answer_pack` for questions: it returns one primary cite (+ optional exception), `session_url`, exact English `quote_en`, and `cost` (tokens, ms, €). Token budget stays around 160 words of source text.

**Eval** (needs a built index):

```powershell
python -m sysml_spec_qa eval
python -m pytest
```

## Layout

- `Dockerfile` / `docker-compose.yml` — clone-and-run viewer (`python -m sysml_spec_qa boot`)
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
