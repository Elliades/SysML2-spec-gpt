from __future__ import annotations

from pathlib import Path

import httpx

from ..config import RAW_DIR
from .manifest import SpecDoc

USER_AGENT = "sysml-spec-qa/0.1 (local research tool; +https://github.com/Elliades/sysml-spec-qa)"


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        follow_redirects=True,
        timeout=httpx.Timeout(120.0, connect=30.0),
    )


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def _looks_like_xml_or_json(data: bytes) -> bool:
    head = data.lstrip()[:80]
    return head.startswith(b"<") or head.startswith(b"{") or head.startswith(b"[")


def download_first(urls: tuple[str, ...], dest: Path, kind: str) -> tuple[Path, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with _client() as client:
        for url in urls:
            try:
                response = client.get(url)
                response.raise_for_status()
                data = response.content
            except httpx.HTTPError as exc:
                errors.append(f"{url}: {exc}")
                continue
            if kind == "pdf" and not _looks_like_pdf(data):
                errors.append(f"{url}: not a PDF ({response.headers.get('content-type')})")
                continue
            if kind == "meta" and not _looks_like_xml_or_json(data):
                errors.append(f"{url}: not XML/JSON")
                continue
            dest.write_bytes(data)
            return dest, url
    raise RuntimeError(f"Failed to download {dest.name}: " + " | ".join(errors[:4]))


def ensure_doc_files(doc: SpecDoc, skip_download: bool = False) -> tuple[Path, Path | None, str]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = RAW_DIR / f"{doc.id}.pdf"
    meta_path: Path | None = None
    source_url = ""

    if skip_download and pdf_path.exists():
        source_url = "local"
    else:
        _, source_url = download_first(doc.pdf_urls, pdf_path, "pdf")

    if doc.metamodel_urls:
        # Prefer XMI when the URL says so, else keep the extension of the URL that worked.
        xmi_path = RAW_DIR / f"{doc.id}.xmi"
        json_path = RAW_DIR / f"{doc.id}.json"
        if skip_download and (xmi_path.exists() or json_path.exists()):
            meta_path = xmi_path if xmi_path.exists() else json_path
        else:
            last_error = None
            for url in doc.metamodel_urls:
                suffix = ".json" if url.lower().endswith(".json") else ".xmi"
                candidate = RAW_DIR / f"{doc.id}{suffix}"
                try:
                    path, _ = download_first((url,), candidate, "meta")
                    meta_path = path
                    break
                except RuntimeError as exc:
                    last_error = exc
            if meta_path is None and not skip_download:
                print(f"  warning: metamodel skipped for {doc.id}: {last_error}")

    return pdf_path, meta_path, source_url
