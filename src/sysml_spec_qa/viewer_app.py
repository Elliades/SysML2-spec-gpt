from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import DB_PATH, DEFAULT_VERSION, MD_DIR, ROOT, VIEWER_HOST, VIEWER_PORT, VIEWER_STATIC
from .markdown import clause_relpath, render_clause_html, resolve_clause_file
from .pack import resolve_cites, search_examples
from .search import get_clause, get_toc, list_documents, search_passages

INDEX_HTML = VIEWER_STATIC / "index.html"


def create_app() -> FastAPI:
    app = FastAPI(title="SysML spec viewer", docs_url=None, redoc_url=None)
    if VIEWER_STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(VIEWER_STATIC)), name="static")

    def shell() -> HTMLResponse:
        if not INDEX_HTML.exists():
            raise HTTPException(500, "viewer/static/index.html missing")
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))

    @app.get("/", response_class=HTMLResponse)
    def root() -> HTMLResponse:
        return shell()

    @app.get("/r/{doc_id}/{version}/{clause_id}", response_class=HTMLResponse)
    def view_reader(doc_id: str, version: str, clause_id: str) -> HTMLResponse:
        return shell()

    @app.get("/cites", response_class=HTMLResponse)
    def view_cites() -> HTMLResponse:
        return shell()

    @app.get("/v/{doc_id}/{version}", response_class=HTMLResponse)
    def view_legacy_pdf(doc_id: str, version: str, clause: str = "", page: int = 1, q: str = "") -> HTMLResponse:
        if clause:
            target = f"/r/{doc_id}/{version}/{quote_plus(clause)}"
            if q:
                target += f"?q={quote_plus(q)}"
            return RedirectResponse(target, status_code=302)
        return shell()

    @app.get("/m/{doc_id}/{version}", response_class=HTMLResponse)
    def view_legacy_md(doc_id: str, version: str, clause: str = "", q: str = "") -> HTMLResponse:
        if clause:
            target = f"/r/{doc_id}/{version}/{quote_plus(clause)}"
            if q:
                target += f"?q={quote_plus(q)}"
            return RedirectResponse(target, status_code=302)
        return shell()

    @app.get("/pack", response_class=HTMLResponse)
    def view_legacy_pack(refs: str = "", q: str = "") -> HTMLResponse:
        if refs:
            target = f"/cites?ids={quote_plus(refs)}"
            if q:
                target += f"&q={quote_plus(q)}"
            return RedirectResponse(target, status_code=302)
        return shell()

    @app.get("/api/docs")
    def api_docs() -> list[dict]:
        try:
            return list_documents()
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/health")
    @app.get("/health")
    def api_health() -> JSONResponse:
        checks: dict[str, dict] = {
            "viewer": {"status": "ok", "host": VIEWER_HOST, "port": VIEWER_PORT},
            "static": {
                "status": "ok" if INDEX_HTML.exists() else "down",
                "detail": str(INDEX_HTML),
            },
        }
        docs: list[dict] = []
        index_status = "down"
        try:
            docs = list_documents()
            index_status = "ok" if docs else "degraded"
            checks["index"] = {
                "status": index_status,
                "documents": len(docs),
                "path": str(DB_PATH),
            }
        except FileNotFoundError as exc:
            checks["index"] = {"status": "down", "detail": str(exc), "path": str(DB_PATH)}

        md_status = "ok" if MD_DIR.exists() else "degraded"
        checks["markdown"] = {"status": md_status, "path": str(MD_DIR)}

        required = ["viewer", "static", "index"]
        down = [name for name in required if checks.get(name, {}).get("status") == "down"]
        status = "ok"
        if down:
            status = "degraded"
        elif any(checks[name].get("status") == "degraded" for name in checks):
            status = "degraded"

        body = {
            "status": status,
            "service": "sysml-spec-qa",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "root": str(ROOT),
            "viewer_url": f"http://{VIEWER_HOST}:{VIEWER_PORT}",
            "checks": checks,
            "documents": docs,
        }
        code = 200 if status == "ok" else 503
        return JSONResponse(content=body, status_code=code)

    @app.get("/api/toc")
    def api_toc(doc: str, version: str = DEFAULT_VERSION) -> list[dict]:
        try:
            return get_toc(doc, version=version)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/clause")
    def api_clause(
        clause: str,
        doc: str | None = None,
        version: str = DEFAULT_VERSION,
    ) -> dict:
        row = get_clause(clause, doc_id=doc, version=version)
        if not row:
            raise HTTPException(404, f"Clause {clause} not found")
        return row

    @app.get("/api/clause_html")
    def api_clause_html(
        doc: str,
        clause: str,
        version: str = DEFAULT_VERSION,
        q: str = "",
    ) -> dict:
        row = get_clause(clause, doc_id=doc, version=version)
        if not row:
            raise HTTPException(404, f"Clause {clause} not found")
        path = resolve_clause_file(version, doc, clause, row["title"])
        if path.exists():
            markdown = path.read_text(encoding="utf-8")
        else:
            markdown = f"# {row['title']}\n\n{row['text']}"
        from .markdown import strip_frontmatter
        from .textutil import word_count

        if word_count(strip_frontmatter(markdown)) < word_count(row["text"]) // 2:
            markdown = f"# {row['title']}\n\n{row['text']}"
        html_body = render_clause_html(
            markdown,
            query=q,
            title=row["title"],
            clause_id=clause,
        )
        return {
            "doc_id": doc,
            "version": version,
            "clause_id": clause,
            "title": row["title"],
            "normative": row["normative"],
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "html": html_body,
            "reader_url": row.get("reader_url"),
            "md_path": clause_relpath(version, doc, clause, row["title"]),
        }

    @app.get("/api/search")
    def api_search(
        q: str,
        version: str = DEFAULT_VERSION,
        k: int = 12,
        doc: str | None = None,
    ) -> list[dict]:
        hits = search_passages(q, version=version, k=k)
        out = []
        for hit in hits:
            if doc and hit.doc_id != doc:
                continue
            out.append(
                {
                    "doc_id": hit.doc_id,
                    "version": hit.version,
                    "clause_id": hit.clause_id,
                    "title": hit.title,
                    "page": hit.page_start,
                    "kind": hit.kind,
                    "normative": hit.normative,
                    "quote_en": hit.quote_en,
                    "reader_url": hit.reader_url(q),
                    "viewer_url": hit.viewer_url(q),
                    "md_path": hit.md_path,
                }
            )
        sysml = [h for h in out if h["doc_id"].startswith("sysml-")]
        kerml = [h for h in out if h["doc_id"].startswith("kerml-")]
        other = [h for h in out if h not in sysml and h not in kerml]
        return sysml + kerml + other

    @app.get("/api/highlights")
    def api_highlights(
        doc: str,
        version: str = DEFAULT_VERSION,
        clause: str | None = None,
        q: str | None = Query(default=None),
        page: int | None = None,
    ) -> dict:
        bboxes: list[dict] = []
        if clause:
            row = get_clause(clause, doc_id=doc, version=version)
            if row:
                bboxes.extend(row.get("bboxes") or [])
        if q:
            for hit in search_passages(q, version=version, k=5):
                if hit.doc_id != doc:
                    continue
                bboxes.extend(hit.bboxes)
        if page is not None:
            bboxes = [b for b in bboxes if int(b.get("page", 0)) == page]
        uniq = []
        seen = set()
        for box in bboxes:
            key = (box.get("page"), box.get("x0"), box.get("y0"), box.get("x1"), box.get("y1"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(box)
        return {"doc": doc, "version": version, "bboxes": uniq[:40]}

    @app.get("/api/md")
    def api_md(
        doc: str,
        version: str = DEFAULT_VERSION,
        clause: str | None = None,
    ) -> dict:
        if clause:
            row = get_clause(clause, doc_id=doc, version=version)
            if not row:
                raise HTTPException(404, f"Clause {clause} not found")
            path = resolve_clause_file(version, doc, clause, row["title"])
            markdown = path.read_text(encoding="utf-8") if path.exists() else row["text"]
            return {
                "doc_id": doc,
                "version": version,
                "clause_id": clause,
                "title": row["title"],
                "markdown": markdown,
                "md_path": clause_relpath(version, doc, clause, row["title"]),
                "reader_url": row.get("reader_url"),
            }
        full = MD_DIR / version / f"{doc}.md"
        if not full.exists():
            raise HTTPException(404, f"Markdown not exported for {doc} {version}")
        return {
            "doc_id": doc,
            "version": version,
            "clause_id": None,
            "title": doc,
            "markdown": full.read_text(encoding="utf-8"),
            "md_path": f"data/md/{version}/{doc}.md",
        }

    @app.get("/files/{doc_id}.pdf")
    def pdf_file(doc_id: str) -> FileResponse:
        try:
            docs = {row["id"]: row for row in list_documents()}
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        row = docs.get(doc_id)
        if not row or not row.get("pdf_path"):
            raise HTTPException(404, f"Unknown document {doc_id}")
        path = Path(row["pdf_path"])
        if not path.exists():
            raise HTTPException(404, f"PDF missing: {path}")
        return FileResponse(path, media_type="application/pdf", filename=f"{doc_id}.pdf")

    @app.get("/api/cites")
    def api_cites(refs: str, q: str = "") -> dict:
        ref_list = [r.strip() for r in refs.split(",") if r.strip()]
        if not ref_list:
            raise HTTPException(400, "refs required: doc:version:clause,...")
        return resolve_cites(ref_list, query=q)

    @app.get("/api/pack")
    def api_pack(refs: str, q: str = "") -> dict:
        return api_cites(refs=refs, q=q)

    @app.get("/api/passages")
    def api_passages(
        q: str,
        version: str = DEFAULT_VERSION,
        k: int = 5,
    ) -> list[dict]:
        hits = search_passages(q, version=version, k=k)
        return [
            {
                "passage_id": h.passage_id,
                "doc_id": h.doc_id,
                "version": h.version,
                "clause_id": h.clause_id,
                "title": h.title,
                "kind": h.kind,
                "normative": h.normative,
                "page": h.page_start,
                "quote_en": h.quote_en,
                "reader_url": h.reader_url(q),
                "viewer_url": h.viewer_url(q),
                "md_path": h.md_path,
            }
            for h in hits
        ]

    @app.get("/api/examples")
    def api_examples(
        q: str,
        version: str = DEFAULT_VERSION,
        k: int = 5,
    ) -> list[dict]:
        examples = search_examples(q, version=version, k=k)
        return [ex.__dict__ for ex in examples]

    return app


def main() -> None:
    import uvicorn

    print(f"SysML viewer on http://{VIEWER_HOST}:{VIEWER_PORT} (localhost only)")
    uvicorn.run(
        create_app(),
        host=VIEWER_HOST,
        port=VIEWER_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
