/** SysML spec reader v3 — HTML-first, session cites, FR chrome */

const $ = (id) => document.getElementById(id);

const TOC_WIDTH_KEY = "viewer.tocWidth";
const TOC_COLLAPSED_KEY = "viewer.tocCollapsed";
const PDF_TOC_KEY = "viewer.pdfTocOpen";
const TOC_MIN_W = 160;
const TOC_MAX_W = 480;
const PDFJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.6.82/pdf.min.mjs";
const PDFJS_WORKER = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.6.82/pdf.worker.min.mjs";

const state = {
  docs: [],
  version: "2.0",
  docId: "",
  clauseId: "",
  query: "",
  toc: [],
  tocFlat: [],
  session: [],
  sessionItems: [],
  sessionIndex: 0,
  searchHits: [],
  mode: "read", // read | cites | search
  pdfDoc: null,
  pdfDocId: "",
  pdfPage: 1,
  pdfTocOpen: true,
  pdfNavLock: false,
  tocCollapsed: false,
  activeQuote: "",
};

const els = {
  version: $("version"),
  doc: $("doc"),
  query: $("query"),
  status: $("status"),
  routeBadge: $("route-badge"),
  tocTree: $("toc-tree"),
  tocFilter: $("toc-filter"),
  breadcrumb: $("breadcrumb"),
  readerMeta: $("reader-meta"),
  clauseBody: $("clause-body"),
  readerLoading: $("reader-loading"),
  readerError: $("reader-error"),
  readerEmpty: $("reader-empty"),
  readerErrorText: $("reader-error-text"),
  citeRail: $("cite-rail"),
  citeCount: $("cite-count"),
  citeTitle: $("cite-title"),
  searchResults: $("search-results"),
  pdfOverlay: $("pdf-overlay"),
  pdfCanvas: $("pdf-canvas"),
  pdfCanvasWrap: $("pdf-canvas-wrap"),
  pdfHl: $("pdf-hl"),
  pdfPageLabel: $("pdf-page-label"),
  pdfMenuBtn: $("pdf-menu-btn"),
  pdfTocPanel: $("pdf-toc-panel"),
  pdfTocTree: $("pdf-toc-tree"),
  pdfTocFilter: $("pdf-toc-filter"),
  toast: $("toast"),
};

let pdfjsMod = null;
let pdfWheelAcc = 0;
let pdfWheelTimer = 0;

function showStatus(msg, isError = false) {
  if (!msg) {
    els.status.hidden = true;
    return;
  }
  els.status.hidden = false;
  els.status.textContent = msg;
  els.status.style.background = isError ? "rgba(255,107,107,0.15)" : "";
  els.status.style.color = isError ? "var(--danger)" : "";
}

function toast(msg) {
  els.toast.textContent = msg;
  els.toast.hidden = false;
  setTimeout(() => { els.toast.hidden = true; }, 2200);
}

function parseUrl() {
  const path = location.pathname;
  const params = new URLSearchParams(location.search);
  state.query = params.get("q") || "";
  state.activeQuote = params.get("quote") || "";
  els.query.value = state.query;

  if (path.startsWith("/r/")) {
    const parts = path.split("/").filter(Boolean);
    state.docId = decodeURIComponent(parts[1] || "");
    state.version = decodeURIComponent(parts[2] || "2.0");
    state.clauseId = decodeURIComponent(parts[3] || "");
    state.mode = "read";
    return;
  }

  if (path === "/cites" || path === "/pack") {
    state.mode = "cites";
    const ids = decodeURIComponent(params.get("ids") || params.get("refs") || "");
    state.session = ids.split(",").map((s) => s.trim()).filter((s) => {
      const parts = s.split(":");
      return parts.length >= 3 && parts[0].length > 1;
    });
    state.sessionIndex = parseInt(params.get("i") || "0", 10) || 0;
    if (state.session.length && state.session[state.sessionIndex]) {
      const parts = state.session[state.sessionIndex].split(":");
      if (parts.length >= 3) {
        state.docId = parts[0];
        state.version = parts[1];
        state.clauseId = parts.slice(2).join(":");
      }
    }
    return;
  }

  state.version = params.get("version") || state.version;
  state.docId = params.get("doc") || state.docId;
  state.clauseId = params.get("clause") || state.clauseId;
}

function buildUrl({ push = false } = {}) {
  let path = "/";
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);

  if (state.mode === "cites" && state.session.length) {
    path = "/cites";
    params.set("ids", state.session.join(","));
    if (state.sessionIndex) params.set("i", String(state.sessionIndex));
  } else if (state.docId && state.clauseId) {
    path = `/r/${encodeURIComponent(state.docId)}/${encodeURIComponent(state.version)}/${encodeURIComponent(state.clauseId)}`;
  } else {
    if (state.version) params.set("version", state.version);
    if (state.docId) params.set("doc", state.docId);
    if (state.clauseId) params.set("clause", state.clauseId);
  }

  const url = params.toString() ? `${path}?${params}` : path;
  if (push) history.pushState(null, "", url);
  else history.replaceState(null, "", url);
  return url;
}

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function docFamily(id) {
  if (id.startsWith("sysml")) return "sysml";
  if (id.startsWith("kerml")) return "kerml";
  return "other";
}

function renderDocSelectors() {
  const versions = [...new Set(state.docs.map((d) => d.version))].sort();
  els.version.innerHTML = versions.map((v) => `<option value="${v}">${v}</option>`).join("");
  els.version.value = state.version;
  const docs = state.docs.filter((d) => d.version === state.version);
  els.doc.innerHTML = docs.map((d) => `<option value="${d.id}">${d.title || d.id}</option>`).join("");
  if (state.docId && docs.some((d) => d.id === state.docId)) {
    els.doc.value = state.docId;
  } else if (docs.length) {
    state.docId = docs.find((d) => d.family === "sysml")?.id || docs[0].id;
    els.doc.value = state.docId;
  }
}

async function loadDocs() {
  state.docs = await api("/api/docs");
  renderDocSelectors();
}

async function loadToc() {
  if (!state.docId) return;
  state.toc = await api(`/api/toc?doc=${encodeURIComponent(state.docId)}&version=${encodeURIComponent(state.version)}`);
  state.tocFlat = state.toc.map((t) => t.clause_id);
  renderToc();
}

function sessionClauseSet() {
  return new Set(state.session.map((ref) => {
    const parts = ref.split(":");
    return parts.length >= 3 ? parts[2] : "";
  }));
}

function scrollTocToActive(tree) {
  requestAnimationFrame(() => {
    const active = tree.querySelector(".toc-item.active");
    if (!active) return;
    active.scrollIntoView({ block: "center", behavior: "instant" });
  });
}

function fillTocTree(tree, filterValue, { onPick, scrollToActive = false } = {}) {
  const filter = (filterValue || "").toLowerCase();
  const inSession = sessionClauseSet();
  const frag = document.createDocumentFragment();
  for (const item of state.toc) {
    const label = `${item.clause_id} ${item.title || ""}`.toLowerCase();
    if (filter && !label.includes(filter)) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toc-item";
    btn.style.paddingLeft = `${0.75 + (item.depth - 1) * 0.65}rem`;
    if (item.clause_id === state.clauseId) btn.classList.add("active");
    if (inSession.has(item.clause_id)) btn.classList.add("in-session");
    btn.innerHTML = `<span class="cid">${item.clause_id}</span>${escapeHtml(item.title || "")}`;
    btn.addEventListener("click", () => onPick(item));
    frag.appendChild(btn);
  }
  tree.replaceChildren(frag);
  if (scrollToActive) scrollTocToActive(tree);
}

function renderToc({ scrollToActive = false } = {}) {
  fillTocTree(els.tocTree, els.tocFilter.value, {
    onPick: (item) => openClause(item.clause_id, { push: true }),
    scrollToActive,
  });
  if (els.pdfTocTree && els.pdfOverlay && !els.pdfOverlay.hidden) {
    renderPdfToc({ scrollToActive });
  }
}

function renderPdfToc({ scrollToActive = false } = {}) {
  if (!els.pdfTocTree) return;
  fillTocTree(els.pdfTocTree, els.pdfTocFilter?.value || "", {
    onPick: (item) => openPdfClause(item),
    scrollToActive,
  });
}

function renderBreadcrumb() {
  if (!state.clauseId) {
    els.breadcrumb.textContent = "";
    return;
  }
  const parts = state.clauseId.split(".");
  const crumbs = [];
  for (let i = 0; i < parts.length; i++) {
    const cid = parts.slice(0, i + 1).join(".");
    crumbs.push(`<a data-clause="${cid}">${cid}</a>`);
  }
  const fam = docFamily(state.docId).toUpperCase();
  els.breadcrumb.innerHTML = `${fam} › ${crumbs.join(" › ")}`;
  els.breadcrumb.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", () => openClause(a.dataset.clause, { push: true }));
  });
}

function renderReaderMeta(meta) {
  const fam = docFamily(state.docId);
  els.readerMeta.innerHTML = `
    <span class="chip ${fam}">${state.docId}</span>
    <span class="chip ${meta.normative ? "norm" : "info"}">${meta.normative ? "normative" : "informative"}</span>
    <span class="chip">p.${meta.page_start}${meta.page_end !== meta.page_start ? "–" + meta.page_end : ""}</span>
    <strong>${escapeHtml(meta.title || state.clauseId)}</strong>
  `;
}

function setReaderState(which) {
  els.readerLoading.hidden = which !== "loading";
  els.readerError.hidden = which !== "error";
  els.readerEmpty.hidden = which !== "empty";
  els.clauseBody.hidden = which !== "content";
}

async function openClause(clauseId, { push = false, addToSession = false } = {}) {
  state.clauseId = clauseId;
  state.mode = state.session.length ? "cites" : "read";
  if (addToSession) {
    const ref = `${state.docId}:${state.version}:${clauseId}`;
    if (!state.session.includes(ref)) state.session.push(ref);
  }
  setReaderState("loading");
  showStatus("");
  try {
    const params = new URLSearchParams({
      doc: state.docId,
      version: state.version,
      clause: clauseId,
    });
    if (state.mode === "search" && state.query) {
      params.set("highlight", state.query);
    }
    const data = await api(`/api/clause_html?${params}`);
    els.clauseBody.innerHTML = data.html;
    renderReaderMeta(data);
    renderBreadcrumb();
    renderToc({ scrollToActive: true });
    setReaderState("content");
    els.routeBadge.hidden = false;
    els.routeBadge.textContent = state.mode === "cites" ? "Session" : "Lecture";
    buildUrl({ push });
  } catch (err) {
    els.readerErrorText.textContent = err.message;
    setReaderState("error");
  }
}

function renderCiteRail() {
  if (state.mode === "search" && state.searchHits.length) {
    els.citeTitle.textContent = "Résultats";
    els.searchResults.hidden = false;
    els.citeRail.hidden = true;
    els.searchResults.innerHTML = state.searchHits.map((h, i) => cardHtml(h, i, false)).join("");
    bindCards(els.searchResults);
    els.citeCount.textContent = `${state.searchHits.length}`;
    return;
  }

  els.searchResults.hidden = true;
  els.citeRail.hidden = false;
  els.citeTitle.textContent = state.session.length ? "Session citations" : "Citations";

  if (!state.session.length) {
    els.citeRail.innerHTML = `<p class="muted" style="padding:0.5rem">Aucune citation. Recherchez ou ouvrez un lien MCP.</p>`;
    els.citeCount.textContent = "";
    return;
  }

  els.citeCount.textContent = `${state.sessionIndex + 1}/${state.session.length}`;
  els.citeRail.innerHTML = state.session.map((ref, i) => {
    const [doc, ver, clause] = ref.split(":");
    const active = i === state.sessionIndex;
    return `<div class="card${active ? " active" : ""}" data-idx="${i}" data-doc="${doc}" data-ver="${ver}" data-clause="${clause}">
      <div class="card-head">
        <span class="chip ${docFamily(doc)}">${doc}</span>
        <span class="card-title">${clause}</span>
      </div>
    </div>`;
  }).join("");
  bindSessionCards();
}

function cardHtml(h, i, active) {
  return `<div class="card${active ? " active" : ""}" data-i="${i}" data-doc="${h.doc_id}" data-ver="${h.version}" data-clause="${h.clause_id}">
    <div class="card-head">
      <span class="chip ${docFamily(h.doc_id)}">${h.doc_id}</span>
      <span class="card-title">${h.clause_id}</span>
      <span class="chip ${h.normative ? "norm" : "info"}">${h.normative ? "norm." : "info."}</span>
    </div>
    <div class="card-quote">${escapeHtml((h.quote_en || "").slice(0, 200))}</div>
  </div>`;
}

function bindCards(container) {
  container.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", async () => {
      state.docId = card.dataset.doc;
      state.version = card.dataset.ver;
      state.clauseId = card.dataset.clause;
      const ref = `${state.docId}:${state.version}:${state.clauseId}`;
      if (!state.session.includes(ref)) state.session.push(ref);
      state.sessionIndex = state.session.indexOf(ref);
      state.mode = "cites";
      await openClause(state.clauseId);
      renderCiteRail();
    });
  });
}

function bindSessionCards() {
  els.citeRail.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", async () => {
      state.sessionIndex = parseInt(card.dataset.idx, 10);
      state.docId = card.dataset.doc;
      state.version = card.dataset.ver;
      await openClause(card.dataset.clause, { push: true });
      renderCiteRail();
    });
  });
}

async function runSearch() {
  state.query = els.query.value.trim();
  state.mode = "search";
  showStatus("Recherche…");
  try {
    const hits = await api(
      `/api/search?q=${encodeURIComponent(state.query)}&version=${encodeURIComponent(state.version)}&k=12`
    );
    state.searchHits = hits;
    renderCiteRail();
    showStatus(`${hits.length} résultat(s)`);
    if (hits.length) {
      const h = hits[0];
      state.docId = h.doc_id;
      state.version = h.version;
      renderDocSelectors();
      await loadToc();
      await openClause(h.clause_id, { addToSession: true });
      renderCiteRail();
    }
    buildUrl({ push: true });
  } catch (err) {
    showStatus(err.message, true);
  }
}

async function loadSessionFromApi() {
  if (!state.session.length) {
    showStatus("Lien de session invalide (paramètre ids manquant ou tronqué).", true);
    setReaderState("error");
    els.readerErrorText.textContent =
      "Ouvrez un lien complet du type /cites?ids=sysml-2.0-language:2.0:7.5.3,kerml-1.0:2.0:8.3.2.4.5";
    return;
  }
  setReaderState("loading");
  try {
    const data = await api(
      `/api/cites?refs=${encodeURIComponent(state.session.join(","))}&q=${encodeURIComponent(state.query)}`
    );
    const items = data.items || [];
    state.sessionItems = items;
    if (items.length) {
      const idx = Math.min(state.sessionIndex, items.length - 1);
      const item = items[idx];
      state.docId = item.doc_id;
      state.version = item.version;
      state.clauseId = item.clause_id;
      renderDocSelectors();
      await loadToc();
      await openClause(state.clauseId);
      els.citeRail.innerHTML = items.map((it, i) => {
        const active = i === idx;
        return `<div class="card${active ? " active" : ""}" data-idx="${i}" data-doc="${it.doc_id}" data-ver="${it.version}" data-clause="${it.clause_id}">
          <div class="card-head">
            <span class="chip ${docFamily(it.doc_id)}">${it.doc_id}</span>
            <span class="card-title">${it.clause_id}</span>
          </div>
          <div class="card-quote">${escapeHtml((it.quote_en || "").slice(0, 220))}</div>
        </div>`;
      }).join("");
      bindSessionCards();
      els.citeCount.textContent = `${idx + 1}/${items.length}`;
    }
  } catch (err) {
    showStatus(err.message, true);
    setReaderState("error");
  }
}

function navigateClause(delta) {
  if (!state.tocFlat.length || !state.clauseId) return;
  const i = state.tocFlat.indexOf(state.clauseId);
  const next = state.tocFlat[i + delta];
  if (next) openClause(next, { push: true });
}

function parseRef(ref) {
  const parts = ref.split(":");
  if (parts.length < 3) return null;
  return { doc: parts[0], ver: parts[1], clause: parts.slice(2).join(":") };
}

function navigateCite(delta) {
  if (state.mode !== "cites" || !state.session.length) return;
  state.sessionIndex = (state.sessionIndex + delta + state.session.length) % state.session.length;
  const parsed = parseRef(state.session[state.sessionIndex]);
  if (!parsed) return;
  state.docId = parsed.doc;
  state.version = parsed.ver;
  openClause(parsed.clause, { push: true }).then(renderCiteRail);
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function activeCiteQuote() {
  if (state.sessionItems.length) {
    const item = state.sessionItems[state.sessionIndex];
    if (item?.quote_en) return item.quote_en;
  }
  if (state.activeQuote) return state.activeQuote;
  if (state.mode === "search" && state.searchHits.length) {
    const hit = state.searchHits.find(
      (h) => h.doc_id === state.docId && h.clause_id === state.clauseId
    );
    if (hit?.quote_en) return hit.quote_en;
  }
  return "";
}

async function loadPdfjs() {
  if (!pdfjsMod) {
    pdfjsMod = await import(PDFJS_URL);
    pdfjsMod.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
  }
  return pdfjsMod;
}

async function ensurePdfDoc() {
  const pdfjs = await loadPdfjs();
  if (!state.pdfDoc || state.pdfDocId !== state.docId) {
    if (state.pdfDoc) {
      try { state.pdfDoc.destroy(); } catch { /* ignore */ }
    }
    state.pdfDoc = await pdfjs.getDocument(`/files/${state.docId}.pdf`).promise;
    state.pdfDocId = state.docId;
  }
  return pdfjs;
}

function setPdfTocOpen(open) {
  state.pdfTocOpen = open;
  if (els.pdfOverlay) els.pdfOverlay.classList.toggle("pdf-toc-collapsed", !open);
  if (els.pdfMenuBtn) {
    els.pdfMenuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    els.pdfMenuBtn.textContent = open ? "Masquer sommaire" : "Sommaire";
  }
  localStorage.setItem(PDF_TOC_KEY, open ? "1" : "0");
}

function isPdfOpen() {
  return Boolean(els.pdfOverlay && !els.pdfOverlay.hidden);
}

async function openPdf() {
  if (!state.docId || !state.clauseId) return;
  els.pdfOverlay.hidden = false;
  setPdfTocOpen(localStorage.getItem(PDF_TOC_KEY) !== "0");
  try {
    if (!state.toc.length) await loadToc();
    renderPdfToc({ scrollToActive: true });
    const pdfjs = await ensurePdfDoc();
    const fromToc = state.toc.find((t) => t.clause_id === state.clauseId);
    state.pdfPage = fromToc?.page_start || state.pdfPage || 1;
    try {
      const row = await api(
        `/api/clause?clause=${encodeURIComponent(state.clauseId)}&doc=${encodeURIComponent(state.docId)}&version=${encodeURIComponent(state.version)}`
      );
      state.pdfPage = row.page_start || state.pdfPage;
    } catch {
      /* keep TOC page if clause metadata is unavailable */
    }
    await renderPdfPage(pdfjs);
    if (els.pdfCanvasWrap) els.pdfCanvasWrap.scrollTop = 0;
  } catch (err) {
    toast("PDF indisponible: " + err.message);
    els.pdfOverlay.hidden = true;
  }
}

async function openPdfClause(item) {
  const clauseId = item.clause_id;
  state.clauseId = clauseId;
  state.pdfPage = item.page_start || 1;
  if (!item.page_start) {
    try {
      const row = await api(
        `/api/clause?clause=${encodeURIComponent(clauseId)}&doc=${encodeURIComponent(state.docId)}&version=${encodeURIComponent(state.version)}`
      );
      state.pdfPage = row.page_start || 1;
    } catch { /* keep current page */ }
  }
  const pdfjs = await ensurePdfDoc();
  await renderPdfPage(pdfjs);
  if (els.pdfCanvasWrap) els.pdfCanvasWrap.scrollTop = 0;
  renderPdfToc({ scrollToActive: true });
  openClause(clauseId, { push: true });
}

async function stepPdfPage(delta) {
  if (!state.pdfDoc || state.pdfNavLock || !isPdfOpen()) return;
  const next = state.pdfPage + delta;
  if (next < 1 || next > state.pdfDoc.numPages) return;
  state.pdfNavLock = true;
  state.pdfPage = next;
  try {
    const pdfjs = await loadPdfjs();
    await renderPdfPage(pdfjs);
    if (els.pdfCanvasWrap) {
      els.pdfCanvasWrap.scrollTop = delta > 0 ? 0 : els.pdfCanvasWrap.scrollHeight;
    }
  } finally {
    state.pdfNavLock = false;
  }
}

function onPdfWheel(e) {
  if (!isPdfOpen()) return;
  const wrap = els.pdfCanvasWrap;
  if (!wrap) return;
  const atTop = wrap.scrollTop <= 2;
  const atBottom = wrap.scrollTop + wrap.clientHeight >= wrap.scrollHeight - 2;
  const down = e.deltaY > 0;
  const up = e.deltaY < 0;
  if ((down && atBottom) || (up && atTop)) {
    e.preventDefault();
    pdfWheelAcc += e.deltaY;
    clearTimeout(pdfWheelTimer);
    if (Math.abs(pdfWheelAcc) >= 48) {
      stepPdfPage(pdfWheelAcc > 0 ? 1 : -1);
      pdfWheelAcc = 0;
    } else {
      pdfWheelTimer = setTimeout(() => { pdfWheelAcc = 0; }, 280);
    }
  } else {
    pdfWheelAcc = 0;
  }
}

async function renderPdfPage(pdfjs) {
  const page = await state.pdfDoc.getPage(state.pdfPage);
  const scale = 1.4;
  const viewport = page.getViewport({ scale });
  const canvas = els.pdfCanvas;
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  els.pdfPageLabel.textContent = `Page ${state.pdfPage} / ${state.pdfDoc.numPages}`;
  const hlParams = new URLSearchParams({
    doc: state.docId,
    version: state.version,
    clause: state.clauseId,
    page: String(state.pdfPage),
  });
  const citeQuote = activeCiteQuote();
  if (citeQuote) hlParams.set("quote", citeQuote);
  else if (state.mode === "search" && state.query) hlParams.set("q", state.query);
  els.pdfHl.innerHTML = "";
  els.pdfHl.style.width = viewport.width + "px";
  els.pdfHl.style.height = viewport.height + "px";
  try {
    const hl = await api(`/api/highlights?${hlParams}`);
    if (hl.focus) {
      els.pdfPageLabel.textContent = `Page ${state.pdfPage} / ${state.pdfDoc.numPages} · citation`;
    }
    for (const box of hl.bboxes || []) {
      if (box.page !== state.pdfPage) continue;
      const div = document.createElement("div");
      div.className = "hl cite-focus";
      const x0 = box.x0 * scale;
      const y0 = viewport.height - box.y1 * scale;
      div.style.left = x0 + "px";
      div.style.top = y0 + "px";
      div.style.width = (box.x1 - box.x0) * scale + "px";
      div.style.height = (box.y1 - box.y0) * scale + "px";
      els.pdfHl.appendChild(div);
    }
  } catch {
    /* page still readable without highlights */
  }
}

function hidePdfOverlay() {
  if (els.pdfOverlay) els.pdfOverlay.hidden = true;
}

async function boot() {
  parseUrl();
  hidePdfOverlay();
  await loadDocs();
  renderDocSelectors();

  if (state.mode === "cites") {
    if (state.session.length) {
      await loadSessionFromApi();
    } else {
      showStatus("Lien de session invalide (paramètre ids manquant ou tronqué).", true);
      setReaderState("error");
      els.readerErrorText.textContent =
        "Ouvrez un lien complet du type /cites?ids=sysml-2.0-language:2.0:7.5.2,kerml-1.0:2.0:8.3.2.4.5&q=…";
    }
  } else if (state.docId && state.clauseId) {
    await loadToc();
    await openClause(state.clauseId);
  } else {
    setReaderState("empty");
  }

  renderCiteRail();
}

$("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  runSearch();
});

els.version.addEventListener("change", async () => {
  state.version = els.version.value;
  renderDocSelectors();
  await loadToc();
});

els.doc.addEventListener("change", async () => {
  state.docId = els.doc.value;
  await loadToc();
});

function readTocWidth() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--toc-w").trim();
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? n : 280;
}

function setTocWidth(px) {
  const w = Math.min(TOC_MAX_W, Math.max(TOC_MIN_W, px));
  document.documentElement.style.setProperty("--toc-w", `${w}px`);
  localStorage.setItem(TOC_WIDTH_KEY, `${w}px`);
}

function setTocCollapsed(collapsed) {
  state.tocCollapsed = collapsed;
  document.body.classList.toggle("toc-collapsed", collapsed);
  localStorage.setItem(TOC_COLLAPSED_KEY, collapsed ? "1" : "0");

  const toggleBtn = $("toc-toggle");
  toggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  const label = collapsed ? "Afficher le sommaire" : "Masquer le sommaire";
  toggleBtn.title = label;
  toggleBtn.setAttribute("aria-label", label);
}

function initTocPanel() {
  const savedWidth = localStorage.getItem(TOC_WIDTH_KEY);
  if (savedWidth) document.documentElement.style.setProperty("--toc-w", savedWidth);
  setTocCollapsed(localStorage.getItem(TOC_COLLAPSED_KEY) === "1");

  $("toc-toggle").addEventListener("click", () => setTocCollapsed(!state.tocCollapsed));

  const resizer = $("toc-resizer");
  let startX = 0;
  let startW = 0;

  const stopResize = () => {
    document.body.classList.remove("toc-resizing");
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", stopResize);
    localStorage.setItem(TOC_WIDTH_KEY, `${readTocWidth()}px`);
  };

  const onMove = (e) => setTocWidth(startW + e.clientX - startX);

  const startResize = (clientX) => {
    if (state.tocCollapsed) return;
    startX = clientX;
    startW = readTocWidth();
    document.body.classList.add("toc-resizing");
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", stopResize);
  };

  resizer.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startResize(e.clientX);
  });

  resizer.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); setTocWidth(readTocWidth() - 16); }
    if (e.key === "ArrowRight") { e.preventDefault(); setTocWidth(readTocWidth() + 16); }
    if (e.key === "Home") { e.preventDefault(); setTocWidth(TOC_MIN_W); }
    if (e.key === "End") { e.preventDefault(); setTocWidth(TOC_MAX_W); }
  });
}

els.tocFilter.addEventListener("input", renderToc);
$("prev-clause").addEventListener("click", () => navigateClause(-1));
$("next-clause").addEventListener("click", () => navigateClause(1));
$("reader-retry").addEventListener("click", () => openClause(state.clauseId));
$("pdf-btn").addEventListener("click", openPdf);
$("pdf-close").addEventListener("click", hidePdfOverlay);
$("pdf-menu-btn").addEventListener("click", () => setPdfTocOpen(!state.pdfTocOpen));
$("pdf-toc-close").addEventListener("click", () => setPdfTocOpen(false));
if (els.pdfTocFilter) els.pdfTocFilter.addEventListener("input", () => renderPdfToc());
$("pdf-prev").addEventListener("click", () => stepPdfPage(-1));
$("pdf-next").addEventListener("click", () => stepPdfPage(1));
if (els.pdfCanvasWrap) {
  els.pdfCanvasWrap.addEventListener("wheel", onPdfWheel, { passive: false });
}

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea, select")) {
    if (e.key === "Escape") e.target.blur();
    return;
  }
  if (isPdfOpen()) {
    if (e.key === "Escape") {
      if (state.pdfTocOpen) setPdfTocOpen(false);
      else hidePdfOverlay();
      return;
    }
    if (e.key === "PageDown" || e.key === "ArrowRight") {
      e.preventDefault();
      stepPdfPage(1);
      return;
    }
    if (e.key === "PageUp" || e.key === "ArrowLeft") {
      e.preventDefault();
      stepPdfPage(-1);
      return;
    }
  }
  if (e.key === "/") { e.preventDefault(); els.query.focus(); }
  if (e.key === "j" && state.mode === "cites" && state.session.length) navigateCite(1);
  if (e.key === "k" && state.mode === "cites" && state.session.length) navigateCite(-1);
  if (e.key === "[") navigateClause(-1);
  if (e.key === "]") navigateClause(1);
  if (e.key === "Escape") els.pdfOverlay.hidden = true;
});

window.addEventListener("popstate", () => {
  parseUrl();
  boot();
});

initTocPanel();
boot();
