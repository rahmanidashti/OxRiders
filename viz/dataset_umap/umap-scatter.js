// umap-scatter.js — dependency-free interactive UMAP scatter (canvas).
//
//   import { createUmapScatter } from "./umap-scatter.js";
//   const data = await fetch("points.json").then(r => r.json());
//   const chart = createUmapScatter(document.querySelector("#umap"), data, { colorBy: "domain" });
//   chart.setColorBy("origin"); chart.setQuery("enzyme"); chart.focus("physics"); chart.destroy();
//
// Data contract (points.json, written by build_question_umap.py):
//   { meta: {...},
//     fields: { <field>: { label, categories: [{ key, label, count }] } },   // order = color-slot order
//     points: [{ id, q, x, y, <field>: key, ... }] }
//
// Theme: follows <html data-theme="light|dark"> when set, else prefers-color-scheme.
// Pass { theme: "light" | "dark" } to pin it.

// Categorical slots, light / dark steps of the same hues. Order is the CVD-safety
// mechanism: slots 1-3 validate all-pairs on a scatter; slots 4+ rely on the
// legend focus and the small-multiples facets for identity (never color alone).
const SLOTS = {
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
};

const STYLE_ID = "uq-styles";
const CSS = `
.uq-root { --surface-1:#fcfcfb; --surface-2:#f4f4f2; --text-primary:#0b0b0b; --text-secondary:#52514e;
  --text-muted:#7a7974; --hairline:rgba(11,11,11,0.10); --muted-mark:rgba(11,11,11,0.10);
  color-scheme:light; font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--text-primary);
  background:var(--surface-1); display:flex; flex-direction:column; gap:12px; min-width:0; }
.uq-root[data-uq-theme="dark"] { --surface-1:#1a1a19; --surface-2:#242423; --text-primary:#ffffff;
  --text-secondary:#c3c2b7; --text-muted:#8f8e86; --hairline:rgba(255,255,255,0.10);
  --muted-mark:rgba(255,255,255,0.10); color-scheme:dark; }
.uq-controls { display:flex; flex-wrap:wrap; align-items:center; gap:12px; }
.uq-controls label { color:var(--text-secondary); font-size:13px; display:flex; align-items:center; gap:6px; }
.uq-controls select, .uq-controls input { font:inherit; color:var(--text-primary); background:var(--surface-1);
  border:1px solid var(--hairline); border-radius:6px; padding:5px 8px; }
.uq-controls input { width:240px; }
.uq-status { color:var(--text-muted); font-size:13px; margin-left:auto; font-variant-numeric:tabular-nums; }
.uq-legend { display:flex; flex-wrap:wrap; gap:4px 6px; margin:0; padding:0; list-style:none; }
.uq-legend button { font:inherit; font-size:13px; color:var(--text-primary); background:none; border:1px solid transparent;
  border-radius:6px; padding:3px 8px; display:flex; align-items:center; gap:6px; cursor:pointer; }
.uq-legend button:hover { background:var(--surface-2); }
.uq-legend button[aria-pressed="true"] { border-color:var(--hairline); background:var(--surface-2); font-weight:600; }
.uq-legend button.uq-dim { color:var(--text-muted); }
.uq-swatch { width:10px; height:10px; border-radius:50%; flex:none; }
.uq-count { color:var(--text-muted); font-variant-numeric:tabular-nums; }
.uq-main { position:relative; height:var(--uq-height,620px); border:1px solid var(--hairline); border-radius:8px;
  overflow:hidden; touch-action:none; }
.uq-main canvas { display:block; width:100%; height:100%; cursor:crosshair; }
.uq-main canvas.uq-grab { cursor:grabbing; }
.uq-hint { position:absolute; left:10px; bottom:8px; font-size:12px; color:var(--text-muted); pointer-events:none; }
.uq-tip { position:absolute; pointer-events:none; max-width:380px; background:var(--surface-1); color:var(--text-primary);
  border:1px solid var(--hairline); border-radius:8px; padding:8px 10px; box-shadow:0 4px 16px rgba(0,0,0,0.12);
  font-size:13px; display:none; z-index:2; }
.uq-tip-q { font-weight:600; margin-bottom:6px; overflow-wrap:anywhere; }
.uq-tip-row { display:flex; align-items:center; gap:6px; color:var(--text-secondary); }
.uq-tip-key { width:12px; height:2px; border-radius:1px; flex:none; }
.uq-tip-id { color:var(--text-muted); margin-top:4px; font-size:12px; }
.uq-facets { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; }
.uq-facet { font:inherit; font-size:12px; color:var(--text-secondary); background:none; text-align:left; padding:6px;
  border:1px solid var(--hairline); border-radius:8px; cursor:pointer; display:flex; flex-direction:column; gap:4px; }
.uq-facet:hover { background:var(--surface-2); }
.uq-facet[aria-pressed="true"] { border-color:var(--text-secondary); }
.uq-facet canvas { width:100%; aspect-ratio:4/3; display:block; }
.uq-facet span { display:flex; justify-content:space-between; gap:6px; }
`;

function el(tag, attrs = {}, parent) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  if (parent) parent.appendChild(node);
  return node;
}

export function createUmapScatter(container, data, options = {}) {
  const opts = { colorBy: Object.keys(data.fields)[0], theme: "auto", height: 620, facets: true,
    fitQuantile: 0.01, injectStyles: true, onSelect: null, ...options };
  if (opts.injectStyles && !document.getElementById(STYLE_ID)) {
    el("style", { id: STYLE_ID, text: CSS }, document.head);
  }

  const points = data.points;
  const n = points.length;
  const xs = new Float32Array(n), ys = new Float32Array(n);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  points.forEach((p, i) => {
    xs[i] = p.x; ys[i] = p.y;
    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
  });
  const lowerQ = points.map((p) => (p.q || "").toLowerCase());

  // The default view fits the dense core (quantile bounds), not the outlying
  // islands, which would otherwise squeeze the bulk into a corner. Zooming out
  // goes far enough to show every point.
  const quantile = (arr, q) => { const a = Float32Array.from(arr).sort(); return a[Math.floor(q * (a.length - 1))]; };
  const fq = Math.max(0, Math.min(0.2, opts.fitQuantile));
  const full = { x0: minX, x1: maxX, y0: minY, y1: maxY };
  const core = { x0: quantile(xs, fq), x1: quantile(xs, 1 - fq), y0: quantile(ys, fq), y1: quantile(ys, 1 - fq) };
  const kMin = Math.min(1, 0.9 * Math.min((core.x1 - core.x0) / (maxX - minX || 1), (core.y1 - core.y0) / (maxY - minY || 1)));

  // Fixed pseudo-random draw order: no category is systematically painted on top,
  // so overlap reads as it is rather than as the last-drawn color.
  const drawOrder = Uint32Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1, seed = 42; i > 0; i--) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const j = seed % (i + 1); [drawOrder[i], drawOrder[j]] = [drawOrder[j], drawOrder[i]];
  }

  const state = { field: opts.colorBy, focus: null, query: "", hover: -1, view: { k: 1, tx: 0, ty: 0 } };
  let active = new Uint8Array(n).fill(1);
  let catIndex = new Uint8Array(n); // category slot per point for the current field
  let screenX = new Float32Array(n), screenY = new Float32Array(n);
  let grid = new Map();

  // ---- DOM ----
  const root = el("div", { class: "uq-root" });
  root.style.setProperty("--uq-height", `${opts.height}px`);
  container.appendChild(root);

  const controls = el("div", { class: "uq-controls" }, root);
  const colorLabel = el("label", { text: "Color by" }, controls);
  const select = el("select", { "aria-label": "Color by" }, colorLabel);
  for (const [key, f] of Object.entries(data.fields)) el("option", { value: key, text: f.label }, select);
  select.value = state.field;
  const searchLabel = el("label", { text: "Search" }, controls);
  const search = el("input", { type: "search", placeholder: "Filter questions…", "aria-label": "Search questions" }, searchLabel);
  const status = el("span", { class: "uq-status", "aria-live": "polite" }, controls);

  const legend = el("ul", { class: "uq-legend", "aria-label": "Legend — click to isolate a category" }, root);
  const main = el("div", { class: "uq-main" }, root);
  const canvas = el("canvas", { role: "img", "aria-label": data.meta?.title || "UMAP scatter" }, main);
  el("div", { class: "uq-hint", text: "Scroll to zoom (out for outlying clusters) · drag to pan · double-click to reset" }, main);
  const tip = el("div", { class: "uq-tip", role: "tooltip" }, main);
  const facetsBox = opts.facets ? el("div", { class: "uq-facets", "aria-label": "One panel per category" }, root) : null;
  const ctx = canvas.getContext("2d");

  // ---- theme ----
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  function resolvedTheme() {
    if (opts.theme === "light" || opts.theme === "dark") return opts.theme;
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "light" || attr === "dark") return attr;
    return mq.matches ? "dark" : "light";
  }
  let colors = {};
  function readTheme() {
    root.setAttribute("data-uq-theme", resolvedTheme());
    const cs = getComputedStyle(root);
    colors = {
      surface: cs.getPropertyValue("--surface-1").trim(),
      text: cs.getPropertyValue("--text-primary").trim(),
      muted: cs.getPropertyValue("--muted-mark").trim(),
      slots: SLOTS[resolvedTheme()],
    };
  }

  // ---- data state ----
  const categories = () => data.fields[state.field].categories;
  const slotColor = (i) => colors.slots[i % colors.slots.length];

  function recomputeCategories() {
    const index = new Map(categories().map((c, i) => [c.key, i]));
    for (let i = 0; i < n; i++) catIndex[i] = index.get(points[i][state.field]) ?? 0;
  }
  function recomputeActive() {
    const fi = state.focus == null ? -1 : categories().findIndex((c) => c.key === state.focus);
    const q = state.query.trim().toLowerCase();
    let count = 0;
    for (let i = 0; i < n; i++) {
      const on = (fi < 0 || catIndex[i] === fi) && (!q || lowerQ[i].includes(q));
      active[i] = on ? 1 : 0;
      count += active[i];
    }
    status.textContent = count === n ? `${n.toLocaleString()} questions`
      : `${count.toLocaleString()} of ${n.toLocaleString()} questions`;
  }

  // ---- geometry ----
  let W = 0, H = 0, dpr = 1;
  // Maps data to a w x h box so that bounds b fills it; returns s and the screen
  // position (ox, oy) of data origin (minX, minY) with y pointing up.
  function baseScale(w, h, pad, b = full) {
    const s = Math.min((w - 2 * pad) / (b.x1 - b.x0 || 1), (h - 2 * pad) / (b.y1 - b.y0 || 1));
    const ox = (w - s * (b.x1 - b.x0)) / 2 - (b.x0 - minX) * s;
    const oy = (h - s * (b.y1 - b.y0)) / 2 - (b.y0 - minY) * s;
    return { s, ox, oy };
  }
  function project() {
    const { s, ox, oy } = baseScale(W, H, 24, core);
    const { k, tx, ty } = state.view;
    for (let i = 0; i < n; i++) {
      screenX[i] = (ox + (xs[i] - minX) * s) * k + tx;
      screenY[i] = (H - oy - (ys[i] - minY) * s) * k + ty; // y up
    }
    grid = new Map();
    const cell = 24;
    for (let i = 0; i < n; i++) {
      if (screenX[i] < -cell || screenY[i] < -cell || screenX[i] > W + cell || screenY[i] > H + cell) continue;
      const key = ((screenX[i] / cell) | 0) * 100003 + ((screenY[i] / cell) | 0);
      let b = grid.get(key);
      if (!b) grid.set(key, (b = []));
      b.push(i);
    }
  }
  function nearest(mx, my, radius = 14) {
    const cell = 24, cx = (mx / cell) | 0, cy = (my / cell) | 0;
    let best = -1, bestD = radius * radius;
    for (let gx = cx - 1; gx <= cx + 1; gx++) for (let gy = cy - 1; gy <= cy + 1; gy++) {
      const b = grid.get(gx * 100003 + gy);
      if (!b) continue;
      for (const i of b) {
        if (!active[i]) continue;
        const d = (screenX[i] - mx) ** 2 + (screenY[i] - my) ** 2;
        if (d < bestD) { bestD = d; best = i; }
      }
    }
    return best;
  }

  // ---- drawing ----
  function drawPoints(c, px, py, r, filterFn, ring) {
    // Muted context first, then the active points in the shuffled draw order,
    // batched into runs of one category so fills stay cheap.
    c.fillStyle = colors.muted;
    c.beginPath();
    for (let i = 0; i < n; i++) if (!filterFn(i)) { c.moveTo(px[i] + r, py[i]); c.arc(px[i], py[i], r, 0, 6.2832); }
    c.fill();
    c.globalAlpha = ring ? 1 : 0.8;
    let run = -1;
    const flush = () => { if (run >= 0) c.fill(); };
    for (let k = 0; k < n; k++) {
      const i = drawOrder[k];
      if (!filterFn(i)) continue;
      if (ring) { // surface ring per point, only once points are big enough to separate
        flush(); run = -1;
        c.fillStyle = colors.surface;
        c.beginPath(); c.arc(px[i], py[i], r + 1, 0, 6.2832); c.fill();
      }
      if (catIndex[i] !== run) { flush(); run = catIndex[i]; c.fillStyle = slotColor(run); c.beginPath(); }
      c.moveTo(px[i] + r, py[i]); c.arc(px[i], py[i], r, 0, 6.2832);
    }
    flush();
    c.globalAlpha = 1;
  }
  function draw() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = colors.surface;
    ctx.fillRect(0, 0, W, H);
    const r = Math.max(1.5, Math.min(6, 1.8 * Math.sqrt(state.view.k)));
    drawPoints(ctx, screenX, screenY, r, (i) => active[i] === 1, r >= 3.5);
    if (state.hover >= 0) {
      const i = state.hover;
      ctx.lineWidth = 2;
      ctx.strokeStyle = colors.text;
      ctx.beginPath(); ctx.arc(screenX[i], screenY[i], r + 3, 0, 6.2832); ctx.stroke();
    }
  }
  function resize() {
    const rect = main.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    W = rect.width; H = rect.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    project(); draw();
  }

  function renderLegend() {
    legend.replaceChildren();
    categories().forEach((c, i) => {
      const li = el("li", {}, legend);
      const pressed = state.focus === c.key;
      const b = el("button", { type: "button", "aria-pressed": String(pressed) }, li);
      if (state.focus != null && !pressed) b.classList.add("uq-dim");
      const sw = el("span", { class: "uq-swatch" }, b);
      sw.style.background = slotColor(i);
      el("span", { text: c.label }, b);
      el("span", { class: "uq-count", text: c.count.toLocaleString() }, b);
      b.addEventListener("click", () => api.focus(pressed ? null : c.key));
    });
  }
  function renderFacets() {
    if (!facetsBox) return;
    facetsBox.replaceChildren();
    categories().forEach((c, ci) => {
      const b = el("button", { type: "button", class: "uq-facet", "aria-pressed": String(state.focus === c.key),
        "aria-label": `${c.label}: ${c.count} questions — click to isolate` }, facetsBox);
      const cv = el("canvas", {}, b);
      const cap = el("span", {}, b);
      el("span", { text: c.label }, cap);
      el("span", { class: "uq-count", text: c.count.toLocaleString() }, cap);
      b.addEventListener("click", () => api.focus(state.focus === c.key ? null : c.key));
      const fw = cv.clientWidth || 150, fh = fw * 0.75;
      cv.width = Math.round(fw * dpr); cv.height = Math.round(fh * dpr);
      const fc = cv.getContext("2d");
      fc.setTransform(dpr, 0, 0, dpr, 0, 0);
      fc.fillStyle = colors.surface; fc.fillRect(0, 0, fw, fh);
      const { s, ox, oy } = baseScale(fw, fh, 6);
      const px = new Float32Array(n), py = new Float32Array(n);
      for (let i = 0; i < n; i++) { px[i] = ox + (xs[i] - minX) * s; py[i] = fh - oy - (ys[i] - minY) * s; }
      drawPoints(fc, px, py, 1.3, (i) => catIndex[i] === ci, false);
    });
  }

  // ---- tooltip ----
  function showTip(i, mx, my) {
    const p = points[i];
    tip.replaceChildren();
    el("div", { class: "uq-tip-q", text: p.q }, tip);
    for (const [field, f] of Object.entries(data.fields)) {
      const ci = f.categories.findIndex((c) => c.key === p[field]);
      const row = el("div", { class: "uq-tip-row" }, tip);
      const key = el("span", { class: "uq-tip-key" }, row);
      key.style.background = field === state.field ? slotColor(ci) : "transparent";
      const suffix = field === "domain" && p.domain_source === "zero-shot" ? " (zero-shot)" : "";
      el("span", { text: `${f.label}: ${f.categories[ci]?.label ?? p[field]}${suffix}` }, row);
    }
    el("div", { class: "uq-tip-id", text: p.id }, tip);
    tip.style.display = "block";
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = `${Math.min(mx + 14, W - tw - 8)}px`;
    tip.style.top = `${my + 14 + th > H ? my - th - 14 : my + 14}px`;
  }
  function hideTip() { tip.style.display = "none"; }

  // ---- interaction ----
  let drag = null;
  const local = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  canvas.addEventListener("pointerdown", (e) => {
    const [mx, my] = local(e);
    drag = { mx, my, tx: state.view.tx, ty: state.view.ty, moved: false };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    const [mx, my] = local(e);
    if (drag) {
      if (Math.abs(mx - drag.mx) + Math.abs(my - drag.my) > 3) drag.moved = true;
      if (drag.moved) {
        canvas.classList.add("uq-grab");
        state.view.tx = drag.tx + mx - drag.mx; state.view.ty = drag.ty + my - drag.my;
        state.hover = -1; hideTip(); project(); draw();
        return;
      }
    }
    const i = nearest(mx, my);
    if (i !== state.hover) { state.hover = i; draw(); }
    if (i >= 0) showTip(i, mx, my); else hideTip();
  });
  canvas.addEventListener("pointerup", () => {
    if (drag && !drag.moved && state.hover >= 0 && opts.onSelect) opts.onSelect(points[state.hover]);
    drag = null; canvas.classList.remove("uq-grab");
  });
  canvas.addEventListener("pointerleave", () => { if (!drag) { state.hover = -1; hideTip(); draw(); } });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [mx, my] = local(e);
    const v = state.view, f = Math.exp(-e.deltaY * 0.0015);
    const k = Math.max(kMin, Math.min(40, v.k * f)), g = k / v.k;
    v.tx = mx - (mx - v.tx) * g; v.ty = my - (my - v.ty) * g; v.k = k;
    state.hover = -1; hideTip(); project(); draw();
  }, { passive: false });
  canvas.addEventListener("dblclick", () => { state.view = { k: 1, tx: 0, ty: 0 }; project(); draw(); });
  select.addEventListener("change", () => api.setColorBy(select.value));
  search.addEventListener("input", () => api.setQuery(search.value));

  const onTheme = () => { readTheme(); renderLegend(); renderFacets(); draw(); };
  mq.addEventListener("change", onTheme);
  const themeObserver = new MutationObserver(onTheme);
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const ro = new ResizeObserver(resize);
  ro.observe(main);

  const api = {
    setColorBy(field) {
      if (!data.fields[field]) return;
      state.field = field; state.focus = null; select.value = field;
      recomputeCategories(); recomputeActive(); renderLegend(); renderFacets(); draw();
    },
    setQuery(q) { state.query = q || ""; if (search.value !== state.query) search.value = state.query; recomputeActive(); draw(); },
    focus(key) {
      state.focus = key; recomputeActive(); renderLegend();
      facetsBox?.querySelectorAll(".uq-facet").forEach((b, i) =>
        b.setAttribute("aria-pressed", String(categories()[i].key === key)));
      draw();
    },
    resetView() { state.view = { k: 1, tx: 0, ty: 0 }; project(); draw(); },
    destroy() {
      ro.disconnect(); themeObserver.disconnect(); mq.removeEventListener("change", onTheme); root.remove();
    },
  };

  readTheme(); recomputeCategories(); recomputeActive(); renderLegend();
  resize(); renderFacets();
  return api;
}
