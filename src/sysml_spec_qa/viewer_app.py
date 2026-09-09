from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import DEFAULT_VERSION, VIEWER_HOST, VIEWER_PORT, VIEWER_STATIC
from .search import get_clause, list_documents, search

INDEX_HTML = VIEWER_STATIC / "index.html"


def create_app() -> FastAPI:
    app = FastAPI(title="SysML spec viewer", docs_url=None, redoc_url=None)
    if VIEWER_STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(VIEWER_STATIC)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def root() -> HTMLResponse:
        if not INDEX_HTML.exists():
            raise HTTPException(500, "viewer/static/index.html missing")
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))

    @app.get("/v/{doc_id}/{version}", response_class=HTMLResponse)
    def view(doc_id: str, version: str) -> HTMLResponse:
        return root()

    @app.get("/api/docs")
    def api_docs() -> list[dict]:
        try:
            return list_documents()
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

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

    @app.get("/api/search")
    def api_search(
        q: str,
        version: str = DEFAULT_VERSION,
        k: int = 5,
        doc: str | None = None,
    ) -> list[dict]:
        hits = search(q, version=version, k=k)
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
                    "page_end": hit.page_end,
                    "kind": hit.kind,
                    "normative": hit.normative,
                    "excerpt": hit.excerpt,
                    "bboxes": hit.bboxes,
                    "viewer_url": hit.viewer_url(q),
                }
            )
        return out

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
            for hit in search(q, version=version, k=5):
                if hit.doc_id != doc:
                    continue
                bboxes.extend(hit.bboxes)
        if page is not None:
            bboxes = [b for b in bboxes if int(b.get("page", 0)) == page]
        # De-dupe rectangles.
        uniq = []
        seen = set()
        for box in bboxes:
            key = (box.get("page"), box.get("x0"), box.get("y0"), box.get("x1"), box.get("y1"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(box)
        return {"doc": doc, "version": version, "bboxes": uniq[:40]}

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
