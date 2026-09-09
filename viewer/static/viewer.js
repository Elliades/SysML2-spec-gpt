import * as pdfjsLib from "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.6.82/pdf.min.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.6.82/pdf.worker.min.mjs";

const params = new URLSearchParams(location.search);
const pathParts = location.pathname.split("/").filter(Boolean);

const els = {
  doc: document.getElementById("doc"),
  version: document.getElementById("version"),
  clause: document.getElementById("clause"),
  query: document.getElementById("query"),
  go: document.getElementById("go"),
  prev: document.getElementById("prev"),
  next: document.getElementById("next"),
  pageLabel: document.getElementById("page-label"),
  canvas: document.getElementById("pdf-canvas"),
  overlay: document.getElementById("overlay"),
  hits: document.getElementById("hits"),
};

let pdfDoc = null;
let currentPage = 1;
let pageCount = 1;
let pageHeightPt = 0;

function stateFromUrl() {
  return {
    doc: pathParts[1] || params.get("doc") || "",
    version: pathParts[2] || params.get("version") || "2.0",
    page: Number(params.get("page") || 1),
    clause: params.get("clause") || "",
    q: params.get("q") || "",
  };
}

function pushUrl() {
  const doc = els.doc.value;
  const version = els.version.value;
  const page = currentPage;
  const clause = els.clause.value.trim();
  const q = els.query.value.trim();
  const search = new URLSearchParams();
  search.set("page", String(page));
  if (clause) search.set("clause", clause);
  if (q) search.set("q", q);
  history.replaceState(null, "", `/v/${doc}/${version}?${search.toString()}`);
}

async function loadDocs() {
  const docs = await fetch("/api/docs").then((r) => r.json());
  const versions = [...new Set(docs.map((d) => d.version))];
  els.version.innerHTML = versions
    .map((v) => `<option value="${v}">${v}</option>`)
    .join("");
  const initial = stateFromUrl();
  if (initial.version && versions.includes(initial.version)) {
    els.version.value = initial.version;
  }
  fillDocOptions(docs, els.version.value, initial.doc);
  els.clause.value = initial.clause;
  els.query.value = initial.q;
  els.version.addEventListener("change", () => {
    fillDocOptions(docs, els.version.value, els.doc.value);
  });
}

function fillDocOptions(docs, version, selected) {
  const filtered = docs.filter((d) => d.version === version);
  els.doc.innerHTML = filtered
    .map((d) => `<option value="${d.id}">${d.id}</option>`)
    .join("");
  if (selected && filtered.some((d) => d.id === selected)) {
    els.doc.value = selected;
  }
}

async function openPdf(page) {
  const docId = els.doc.value;
  if (!docId) return;
  const url = `/files/${docIdSafe(docId)}.pdf`;
  pdfDoc = await pdfjsLib.getDocument(url).promise;
  pageCount = pdfDoc.numPages;
  currentPage = Math.min(Math.max(1, page || 1), pageCount);
  await renderPage();
  await loadHits();
}

function docIdSafe(id) {
  return encodeURIComponent(id);
}

async function renderPage() {
  const page = await pdfDoc.getPage(currentPage);
  const viewport = page.getViewport({ scale: 1.35 });
  const canvas = els.canvas;
  const ctx = canvas.getContext("2d");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  els.overlay.style.width = `${viewport.width}px`;
  els.overlay.style.height = `${viewport.height}px`;
  await page.render({ canvasContext: ctx, viewport }).promise;
  pageHeightPt = page.view[3] - page.view[1];
  els.pageLabel.textContent = `p. ${currentPage} / ${pageCount}`;
  await drawHighlights(viewport);
}

function fitzToViewport(box, viewport) {
  const pdfY0 = pageHeightPt - box.y1;
  const pdfY1 = pageHeightPt - box.y0;
  const converted = viewport.convertToViewportRectangle([
    box.x0,
    pdfY0,
    box.x1,
    pdfY1,
  ]);
  const x = Math.min(converted[0], converted[2]);
  const y = Math.min(converted[1], converted[3]);
  const w = Math.abs(converted[2] - converted[0]);
  const h = Math.abs(converted[3] - converted[1]);
  return { x, y, w, h };
}

async function drawHighlights(viewport) {
  els.overlay.innerHTML = "";
  const doc = els.doc.value;
  const version = els.version.value;
  const clause = els.clause.value.trim();
  const q = els.query.value.trim();
  const url = new URL("/api/highlights", location.origin);
  url.searchParams.set("doc", doc);
  url.searchParams.set("version", version);
  url.searchParams.set("page", String(currentPage));
  if (clause) url.searchParams.set("clause", clause);
  if (q) url.searchParams.set("q", q);
  const data = await fetch(url).then((r) => r.json());
  for (const box of data.bboxes || []) {
    if (Number(box.page) !== currentPage) continue;
    const rect = fitzToViewport(box, viewport);
    const div = document.createElement("div");
    div.className = "hl";
    div.style.left = `${rect.x}px`;
    div.style.top = `${rect.y}px`;
    div.style.width = `${rect.w}px`;
    div.style.height = `${rect.h}px`;
    els.overlay.appendChild(div);
  }
}

async function loadHits() {
  const q = els.query.value.trim() || els.clause.value.trim();
  if (!q) {
    els.hits.innerHTML = "<p>No query. Other occurrences will appear here.</p>";
    return;
  }
  const version = els.version.value;
  const url = new URL("/api/search", location.origin);
  url.searchParams.set("q", q);
  url.searchParams.set("version", version);
  url.searchParams.set("k", "8");
  const hits = await fetch(url).then((r) => r.json());
  if (!hits.length) {
    els.hits.innerHTML = "<p>No other occurrences.</p>";
    return;
  }
  els.hits.innerHTML = hits
    .map(
      (h) => `
      <article>
        <a href="${h.viewer_url}">${h.doc_id} ${h.clause_id}</a>
        <div>${h.title}</div>
        <small>p.${h.page}${h.normative ? " · normative" : " · informative"}</small>
        <p>${escapeHtml(h.excerpt.slice(0, 280))}</p>
      </article>`
    )
    .join("");
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

els.go.addEventListener("click", async () => {
  const clause = els.clause.value.trim();
  let page = currentPage;
  if (clause) {
    const version = els.version.value;
    const doc = els.doc.value;
    const url = new URL("/api/clause", location.origin);
    url.searchParams.set("clause", clause);
    url.searchParams.set("doc", doc);
    url.searchParams.set("version", version);
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      page = data.page_start;
    }
  }
  pushUrl();
  await openPdf(page);
});

els.prev.addEventListener("click", async () => {
  if (currentPage > 1) {
    currentPage -= 1;
    pushUrl();
    await renderPage();
  }
});

els.next.addEventListener("click", async () => {
  if (currentPage < pageCount) {
    currentPage += 1;
    pushUrl();
    await renderPage();
  }
});

await loadDocs();
const initial = stateFromUrl();
await openPdf(initial.page || 1);
