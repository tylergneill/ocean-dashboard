/* Ocean registration progress: the page.

   Reads data/progress.json (written by build_progress.py) and draws, for the
   chosen tab:

     * two heaps of grains on a canvas. The left heap is the collection as it
       stands outside SETI; the right heap is everything with a SETI record.
       On load and on every tab or unit change, the registered grains are
       lifted off the top of the full heap and arc across to the right, so the
       picture is literally earth being moved.
     * a bar per measure (or per collection, on the All tab) with the same
       three parts: done, recorded-but-not-done, not in SETI.

   "Done" is the toggle. A text with any SETI record always moves right (the
   most permissive reading); the toggle decides which of those grains are
   solid (done at that level) and which are faint (a record, but missing the
   work or author ID the level asks for).

   No libraries, no build step. Open it through `make serve` (a browser will
   not fetch() a local file opened directly). */

"use strict";

const DATA_URL = "./data/progress.json";

/* Flag bits per item, matching build_progress.py: RECORD, WORK, AUTHOR. */
const RECORD = 1, WORK = 2, AUTHOR = 4;

/* What each toggle position requires of an item's flags. */
const LEVELS = {
  record: RECORD,
  work: RECORD | WORK,
  author: RECORD | AUTHOR,
  both: RECORD | WORK | AUTHOR,
};

/* At most this many grains on the canvas. Past it, one grain stands for
   several texts (or a larger slice of MB), and the note under the heaps says
   how many. Keeps the animation smooth on a phone. */
const MAX_GRAINS = 5000;

const state = { data: null, tab: "all", level: "record", unit: "texts" };
const dark = window.matchMedia("(prefers-color-scheme: dark)");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const nf = new Intl.NumberFormat("en-US");

/* ------------------------------------------------------------------ *
 * Tallies
 * ------------------------------------------------------------------ */

/* Split one collection's items into the three parts, for the current level,
   in both measures at once. Items are [bytes, flags] pairs. */
function tally(coll, level) {
  const need = LEVELS[level];
  const t = { done: [0, 0], partial: [0, 0], left: [0, 0] };   // [texts, bytes]
  for (const [b, f] of coll.items) {
    const part = (f & need) === need ? "done" : (f & RECORD) ? "partial" : "left";
    t[part][0] += 1;
    t[part][1] += b;
  }
  return t;
}

function colourOf(coll) {
  return dark.matches ? coll.dark : coll.light;
}

function shownCollections() {
  const all = state.data.collections;
  return state.tab === "all" ? all : all.filter((c) => c.code === state.tab);
}

/* ------------------------------------------------------------------ *
 * Heaps
 * ------------------------------------------------------------------ */

/* Grain positions for a mound of n grains, bottom row first, in grain units
   relative to the mound's centre-bottom. Rows narrow by two grains each level,
   so the outline is a triangle about twice as wide as it is tall. `base`
   fixes the bottom row's width; left out, it is chosen to suit n. */
function mound(n, base) {
  if (base == null) base = Math.max(1, Math.ceil(2 * Math.sqrt(n)));
  const pts = [];
  let row = 0, width = base;
  while (pts.length < n) {
    const w = Math.max(1, width);
    const inRow = Math.min(w, n - pts.length);
    // Centre the row; offset odd rows by half a grain so it reads as a pile
    // of stacked grains rather than a grid.
    const x0 = -inRow / 2 + (row % 2 ? 0.25 : -0.25);
    for (let i = 0; i < inRow; i++) pts.push([x0 + i + 0.5, row]);
    row += 1;
    width -= 2;
  }
  return pts;
}

/* The grain counts for the current tab and measure.

   Returns { left, right: [{colour, solid, n}], unit } where unit is how much
   one grain stands for (texts or bytes). Right-hand segments come in drawing
   order, bottom first: done grains settle at the bottom of the new heap, the
   not-yet-done ones lie loose on top. */
function grains() {
  const m = state.unit === "texts" ? 0 : 1;
  const colls = shownCollections();
  const parts = colls.map((c) => ({ c, t: tally(c, state.level) }));
  const total = parts.reduce((s, p) => s + p.t.done[m] + p.t.partial[m] + p.t.left[m], 0);
  const unit = Math.max(1, total / MAX_GRAINS);

  // A part with something in it gets at least one grain, so the first text
  // registered in a big collection is visible. Slightly flatters tiny
  // fractions; the bars below are exact.
  const g = (v) => (v > 0 ? Math.max(1, Math.round(v / unit)) : 0);

  const right = [];
  for (const { c, t } of parts) right.push({ colour: colourOf(c), solid: true, n: g(t.done[m]) });
  for (const { c, t } of parts) right.push({ colour: colourOf(c), solid: false, n: g(t.partial[m]) });
  const left = g(parts.reduce((s, p) => s + p.t.left[m], 0));
  return { left, right, unit };
}

let anim = null;   // the running animation's frame id, so a new one can cancel it

function drawHeaps(animate) {
  const canvas = document.getElementById("heaps");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const { left, right, unit } = grains();
  const nRight = right.reduce((s, r) => s + r.n, 0);
  const nAll = left + nRight;

  // One grain size for both heaps, so mass looks conserved as it moves:
  // the full collection's mound must fit in half the width.
  const base = Math.max(1, Math.ceil(2 * Math.sqrt(nAll)));
  const s = Math.max(1.2, Math.min((W / 2) * 0.9 / base, (H * 0.9) / (base / 2 + 1)));
  const ground = H - 4;
  const lx = W * 0.25, rx = W * 0.75;

  // The full heap at the left, at its original base. The left heap keeps
  // that base (it is being dug from the top); the grains that move right are
  // the ones at the top of it.
  const full = mound(nAll, base);
  const leftPts = full.slice(0, left);
  const liftPts = full.slice(left);
  const rightPts = mound(nRight);

  const soil = getComputedStyle(document.documentElement).getPropertyValue("--soil").trim();
  const rightStyle = [];
  for (const seg of right) for (let i = 0; i < seg.n; i++) rightStyle.push(seg);

  const toXY = (cx, [gx, gy]) => [cx + gx * s, ground - (gy + 1) * s];

  function frame(t) {
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = soil;
    ctx.globalAlpha = 1;
    for (const p of leftPts) {
      const [x, y] = toXY(lx, p);
      ctx.fillRect(x, y, s * 0.9, s * 0.9);
    }
    for (let i = 0; i < nRight; i++) {
      // Each grain starts a little after the one below it, so the right heap
      // builds from the bottom up while the left one is dug from the top down.
      const delay = nRight > 1 ? (i / (nRight - 1)) * 0.6 : 0;
      const k = Math.min(1, Math.max(0, (t - delay) / 0.4));
      const e = k * k * (3 - 2 * k);   // smoothstep
      const [x0, y0] = toXY(lx, liftPts[liftPts.length - 1 - i] || [0, 0]);
      const [x1, y1] = toXY(rx, rightPts[i]);
      const x = x0 + (x1 - x0) * e;
      const y = y0 + (y1 - y0) * e - Math.sin(Math.PI * e) * H * 0.25;
      const st = rightStyle[i];
      ctx.fillStyle = k === 0 ? soil : st.colour;
      ctx.globalAlpha = k === 0 || st.solid ? 1 : 0.35;
      ctx.fillRect(x, y, s * 0.9, s * 0.9);
    }
    ctx.globalAlpha = 1;
  }

  if (anim) cancelAnimationFrame(anim);
  if (!animate || reduceMotion || nRight === 0) {
    frame(1);
  } else {
    const start = performance.now(), dur = 1800;
    const step = (now) => {
      const t = Math.min(1, (now - start) / dur);
      frame(t);
      anim = t < 1 ? requestAnimationFrame(step) : null;
    };
    anim = requestAnimationFrame(step);
  }

  const what = state.unit === "texts"
    ? (unit > 1 ? `one grain ≈ ${nf.format(Math.round(unit))} texts` : "one grain = one text")
    : `one grain ≈ ${fmtMB(unit)}`;
  document.getElementById("grain-note").textContent =
    `${what}. Solid: done at this level. Faint: in SETI, not yet done. Click to replay.`;
}

/* ------------------------------------------------------------------ *
 * Bars
 * ------------------------------------------------------------------ */

function fmtMB(bytes) {
  const mb = bytes / 1e6;
  return mb >= 100 ? `${nf.format(Math.round(mb))} MB` : `${mb.toFixed(mb >= 1 ? 1 : 2)} MB`;
}

function pct(a, b) {
  return b ? `${(100 * a / b).toFixed(a && a < b / 1000 ? 2 : 1)}%` : "–";
}

/* One labelled bar. `t` is a tally, `m` 0 for texts or 1 for bytes. */
function barRow(title, colour, t, m) {
  const total = t.done[m] + t.partial[m] + t.left[m];
  const fmt = m ? fmtMB : (n) => nf.format(n);
  const row = document.createElement("div");
  row.className = "bar-row";
  row.style.setProperty("--c", colour);
  const moved = t.done[m] + t.partial[m];
  row.innerHTML = `
    <h3>${title} <span class="nums">${fmt(moved)} of ${fmt(total)} in SETI (${pct(moved, total)})</span></h3>
    <div class="bar">
      <div class="done" style="width:${100 * t.done[m] / (total || 1)}%"></div>
      <div class="partial" style="width:${100 * t.partial[m] / (total || 1)}%"></div>
    </div>
    <div class="bar-label">done at this level: ${fmt(t.done[m])} (${pct(t.done[m], total)})
      · recorded, not done: ${fmt(t.partial[m])}</div>`;
  return row;
}

function drawBars() {
  const box = document.getElementById("bars");
  box.replaceChildren();
  const m = state.unit === "texts" ? 0 : 1;
  if (state.tab === "all") {
    // One row per collection in the chosen measure.
    for (const c of state.data.collections) {
      box.append(barRow(c.name, colourOf(c), tally(c, state.level), m));
    }
  } else {
    // One collection, both measures: texts and volume side by side.
    const c = shownCollections()[0];
    const t = tally(c, state.level);
    box.append(barRow("Texts", colourOf(c), t, 0));
    box.append(barRow("Volume", colourOf(c), t, 1));
  }
}

/* ------------------------------------------------------------------ *
 * Wiring
 * ------------------------------------------------------------------ */

function render(animate) {
  for (const b of document.querySelectorAll("#tabs button")) {
    b.setAttribute("aria-selected", String(b.dataset.tab === state.tab));
  }
  for (const b of document.querySelectorAll("#level button[data-level]")) {
    b.setAttribute("aria-pressed", String(b.dataset.level === state.level));
  }
  for (const b of document.querySelectorAll("#unit button")) {
    b.setAttribute("aria-pressed", String(b.dataset.unit === state.unit));
  }
  drawHeaps(animate);
  drawBars();
}

function buildTabs() {
  const nav = document.getElementById("tabs");
  const tab = (code, label, colour) => {
    const b = document.createElement("button");
    b.dataset.tab = code;
    b.setAttribute("role", "tab");
    if (colour) {
      b.style.setProperty("--c", colour);
      const dot = document.createElement("span");
      dot.className = "dot";
      b.append(dot);
    }
    b.append(label);
    b.addEventListener("click", () => { state.tab = code; render(true); });
    nav.append(b);
  };
  tab("all", "All");
  for (const c of state.data.collections) tab(c.code, c.name, colourOf(c));
}

function footer() {
  const d = state.data;
  const unmatched = Object.entries(d.seti_rows_unmatched || {})
    .filter(([, n]) => n > 0)
    .map(([name, n]) => `${nf.format(n)} SETI ${name} rows match no Atlas item.`)
    .join(" ");
  document.getElementById("footer").innerHTML =
    `Built ${d.generated.slice(0, 10)} from the search index of ` +
    `${(d.inputs.search_json.generated || "?").slice(0, 10)} and ` +
    `${nf.format(d.inputs.seti_master.rows)} SETI rows. ${unmatched}`;
}

async function main() {
  const res = await fetch(DATA_URL);
  if (!res.ok) {
    document.querySelector(".field").textContent =
      "No data/progress.json yet. Run `make data`, then reload.";
    return;
  }
  state.data = await res.json();
  buildTabs();
  footer();

  document.getElementById("level").addEventListener("click", (e) => {
    const lv = e.target.dataset && e.target.dataset.level;
    if (lv) { state.level = lv; render(false); }   // recolour only: nothing moves
  });
  document.getElementById("unit").addEventListener("click", (e) => {
    const u = e.target.dataset && e.target.dataset.unit;
    if (u) { state.unit = u; render(true); }
  });
  document.getElementById("heaps").addEventListener("click", () => drawHeaps(true));
  window.addEventListener("resize", () => drawHeaps(false));
  dark.addEventListener("change", () => render(false));

  render(true);
}

main();
