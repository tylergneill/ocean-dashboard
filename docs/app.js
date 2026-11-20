/* Ocean registration progress: the page.

   Reads data/progress.json (written by build_progress.py) and draws, for the
   chosen tab:

     * a pool and a vessel on a canvas. The pool on the left is the collection
       as it stands outside SETI; the vessel on the right holds everything with
       a SETI record. On load and on every tab or unit change, the registered
       share is drawn up out of the pool as drops that arc across and fall into
       the vessel, filling it in a layer per collection.
     * a bar per measure (or per collection, on the All tab) with the same
       three parts: done, recorded-but-not-done, not in SETI.

   "Done" is the toggle. A text with any SETI record always moves right (the
   most permissive reading); the toggle decides which of that water is solid
   colour (done at that level) and which is faint (a record, but missing the
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

/* At most this many drops for a whole collection. Past it, one drop stands
   for several texts (or a larger slice of MB), and the note under the canvas
   says how many. Keeps the stream legible and the animation smooth. */
const MAX_DROPS = 400;

const state = { data: null, tab: "all", level: "record", unit: "texts" };
const dark = window.matchMedia("(prefers-color-scheme: dark)");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const nf = new Intl.NumberFormat("en-US");

/* ------------------------------------------------------------------ *
 * Tallies
 * ------------------------------------------------------------------ */

/* Split one collection's items into the three parts, for the current level,
   in both measures at once. Items are [bytes, parts] pairs, parts being the
   flags of each part of the text (one part for most; a GRETIL text split over
   several files has one per file). A text counts in shares: 12 of 18 parts in
   SETI puts 12/18 of it, and of its bytes, on the right. So the text totals
   can be fractional; they are rounded for display. */
function tally(coll, level) {
  const need = LEVELS[level];
  const t = { done: [0, 0], partial: [0, 0], left: [0, 0] };   // [texts, bytes]
  for (const [b, parts] of coll.items) {
    let done = 0, rec = 0;
    for (const f of parts) {
      if ((f & need) === need) done += 1;
      if (f & RECORD) rec += 1;
    }
    const n = parts.length;
    const shares = { done: done / n, partial: (rec - done) / n, left: 1 - rec / n };
    for (const k in shares) {
      t[k][0] += shares[k];
      t[k][1] += shares[k] * b;
    }
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
 * Water
 * ------------------------------------------------------------------ */

/* The drop counts for the current tab and measure.

   Returns { left, right: [{colour, solid, n}], unit } where unit is how much
   one drop stands for (texts or bytes). Right-hand segments come in filling
   order, bottom first: done water settles at the bottom of the vessel, the
   not-yet-done layers float faint on top. */
function drops() {
  const m = state.unit === "texts" ? 0 : 1;
  const colls = shownCollections();
  const parts = colls.map((c) => ({ c, t: tally(c, state.level) }));
  const total = parts.reduce((s, p) => s + p.t.done[m] + p.t.partial[m] + p.t.left[m], 0);
  const unit = Math.max(1, total / MAX_DROPS);

  // A part with something in it gets at least one drop, so the first text
  // registered in a big collection is visible. Slightly flatters tiny
  // fractions; the bars below are exact.
  const g = (v) => (v > 0 ? Math.max(1, Math.round(v / unit)) : 0);

  const right = [];
  for (const { c, t } of parts) right.push({ colour: colourOf(c), solid: true, n: g(t.done[m]) });
  for (const { c, t } of parts) right.push({ colour: colourOf(c), solid: false, n: g(t.partial[m]) });
  const left = g(parts.reduce((s, p) => s + p.t.left[m], 0));
  return { left, right, unit };
}

/* A basin's outline: open at the top, rounded at the bottom corners. */
function basinPath(ctx, b) {
  const r = Math.min(14, b.w / 4, b.h / 4);
  ctx.beginPath();
  ctx.moveTo(b.x, b.y);
  ctx.lineTo(b.x, b.y + b.h - r);
  ctx.quadraticCurveTo(b.x, b.y + b.h, b.x + r, b.y + b.h);
  ctx.lineTo(b.x + b.w - r, b.y + b.h);
  ctx.quadraticCurveTo(b.x + b.w, b.y + b.h, b.x + b.w, b.y + b.h - r);
  ctx.lineTo(b.x + b.w, b.y);
}

/* A fixed scatter in [0, 1) per drop, so every replay looks the same. */
function scatter(i, salt) {
  const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

let anim = null;   // the running animation's frame id, so a new one can cancel it

function drawWater(animate) {
  const canvas = document.getElementById("water");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const { left, right, unit } = drops();
  const nRight = right.reduce((s, r) => s + r.n, 0);
  const nAll = left + nRight;

  const css = getComputedStyle(document.documentElement);
  const water = css.getPropertyValue("--water").trim();
  const rim = css.getPropertyValue("--rim").trim();
  const shine = css.getPropertyValue("--shine").trim();

  // Two identical basins, centred under their labels (a quarter and three
  // quarters across), with headroom above for the drops' arcs. Being the same
  // shape, the water leaving one visibly matches what lands in the other.
  const bottom = H - 6;
  const bw = W * 0.36, bh = H * 0.68;
  const pool = { x: W * 0.25 - bw / 2, y: bottom - bh, w: bw, h: bh };
  const ves = { x: W * 0.75 - bw / 2, y: bottom - bh, w: bw, h: bh };

  // Area per drop: either basin can hold the whole collection.
  const a = nAll ? 0.92 * bw * bh / nAll : 0;
  // A layer with anything in it is at least 2px deep, so it can be seen.
  const depth = (n, box) => (n > 0 ? Math.max(2, n * a / box.w) : 0);
  const r = Math.max(1.6, Math.min(4.5, Math.sqrt(a) * 0.5));

  const rightStyle = [];
  for (const seg of right) for (let i = 0; i < seg.n; i++) rightStyle.push(seg);

  // Timeline, in t-units (one is 2.2s): drop i leaves the pool at launch(i),
  // the bottom layer's drops first, so the vessel fills from below. How long
  // each is in the air comes from the physics below; a landing's ring lasts
  // SPLASH.
  const SPREAD = 0.62, SPLASH = 0.07;
  const launch = (i) => (nRight > 1 ? (i / (nRight - 1)) * SPREAD : 0);

  /* The vessel's surface once `landed` drops are in, layer by layer. */
  function vesselTop(landed) {
    let y = ves.y + ves.h, start = 0;
    for (const seg of right) {
      y -= depth(Math.max(0, Math.min(seg.n, landed - start)), ves);
      start += seg.n;
    }
    return y;
  }

  /* Each drop's flight is a plain parabola, like a thrown stone: steady speed
     across, rising and falling under one gravity G shared by every drop (px
     per t-unit², scaled to the canvas). Its apex is the lowest that clears
     both inner rims. Drops leave from the outer part of the pool and land at
     the mirror-image spot in the vessel, as far from its inner wall as they
     started from the pool's. A lopsided pairing (or a spot next to an inner
     wall) could leave no arc that clears both rims and stays on the canvas
     when the water is low. */
  const G = 34 * H;
  const rimClear = pool.y - r - 3;
  const posAt = (p, tau) => [p.x0 + p.vx * tau, p.apex + (G / 2) * (tau - p.up) ** 2];
  const heightAt = (p, x) => posAt(p, (x - p.x0) / p.vx)[1];
  const paths = [];
  for (let i = 0; i < nRight; i++) {
    const x0 = pool.x + pool.w * (0.08 + 0.52 * scatter(i, 1));
    const x1 = W - x0;
    const y0 = pool.y + pool.h - depth(left + nRight - i, pool);
    const y1 = vesselTop(i + 1);
    let p;
    for (let apex = rimClear; ; apex -= 2) {
      const up = Math.sqrt((2 * (y0 - apex)) / G);
      const T = up + Math.sqrt((2 * (y1 - apex)) / G);
      p = { x0, x1, apex, up, T, vx: (x1 - x0) / T, t0: launch(i) };
      const clear = heightAt(p, pool.x + pool.w) <= rimClear && heightAt(p, ves.x) <= rimClear;
      if (clear || apex <= r + 2) break;
    }
    paths.push(p);
  }
  const lastLanding = paths.reduce((m, p) => Math.max(m, p.t0 + p.T), 0);

  /* Fill a basin with layers [{n, colour, alpha}], bottom first. Returns the
     water surface's y. */
  function fill(box, layers) {
    ctx.save();
    basinPath(ctx, box);
    ctx.closePath();
    ctx.clip();
    let y = box.y + box.h;
    for (const L of layers) {
      const d = depth(L.n, box);
      if (!d) continue;
      ctx.globalAlpha = L.alpha;
      ctx.fillStyle = L.colour;
      ctx.fillRect(box.x, y - d, box.w, d);
      y -= d;
    }
    ctx.restore();
    if (y < box.y + box.h) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = shine;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(box.x + 1, y + 0.75);
      ctx.lineTo(box.x + box.w - 1, y + 0.75);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.strokeStyle = rim;
    ctx.lineWidth = 1.5;
    basinPath(ctx, box);
    ctx.stroke();
    return y;
  }

  function frame(t) {
    ctx.clearRect(0, 0, W, H);

    let departed = 0, landed = 0;
    for (const p of paths) {
      if (t > p.t0) departed += 1;
      if (t >= p.t0 + p.T) landed += 1;
    }

    fill(pool, [{ n: left + nRight - departed, colour: water, alpha: 1 }]);
    const layers = [];
    let start = 0;
    for (const seg of right) {
      const n = Math.max(0, Math.min(seg.n, landed - start));
      layers.push({ n, colour: seg.colour, alpha: seg.solid ? 1 : 0.4 });
      start += seg.n;
    }
    const vesTop = fill(ves, layers);

    // Drops in the air, each on its parabola. Splashes: a ring spreading on
    // the vessel's surface just after a drop lands.
    for (let i = 0; i < nRight; i++) {
      const p = paths[i];
      const tau = t - p.t0;
      const st = rightStyle[i];
      const x1 = p.x1;
      if (tau > 0 && tau < p.T) {
        const [x, y] = posAt(p, tau);
        ctx.globalAlpha = st.solid ? 1 : 0.5;
        ctx.fillStyle = st.colour;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      } else if (tau >= p.T && tau < p.T + SPLASH) {
        const q = (tau - p.T) / SPLASH;
        ctx.globalAlpha = (1 - q) * (st.solid ? 0.9 : 0.45);
        ctx.strokeStyle = st.colour;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.ellipse(x1, vesTop, r * (1 + 3 * q), r * (0.35 + 0.8 * q), 0, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }

  if (anim) cancelAnimationFrame(anim);
  if (!animate || reduceMotion || nRight === 0) {
    frame(lastLanding + 1);
  } else {
    const start = performance.now(), dur = 2200;
    const end = lastLanding + SPLASH;
    const step = (now) => {
      const t = Math.min(end, (now - start) / dur);
      frame(t);
      anim = t < end ? requestAnimationFrame(step) : null;
    };
    anim = requestAnimationFrame(step);
  }

  const what = state.unit === "texts"
    ? (unit > 1 ? `one drop ≈ ${nf.format(Math.round(unit))} texts` : "one drop = one text")
    : `one drop ≈ ${fmtMB(unit)}`;
  document.getElementById("drop-note").textContent =
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
  const fmt = m ? fmtMB : (n) => nf.format(Math.round(n));
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
  drawWater(animate);
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
  const versionOnly = Object.entries(d.seti_rows_version_only || {})
    .filter(([, n]) => n > 0)
    .map(([name, n]) => `${nf.format(n)} more link only a ${name} version file, which doesn't count.`)
    .join(" ");
  document.getElementById("footer").innerHTML =
    `Built ${d.generated.slice(0, 10)} from the search index of ` +
    `${(d.inputs.search_json.generated || "?").slice(0, 10)} and ` +
    `${nf.format(d.inputs.seti_master.rows)} SETI rows. ${unmatched} ${versionOnly}`;
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
  document.getElementById("water").addEventListener("click", () => drawWater(true));
  window.addEventListener("resize", () => drawWater(false));
  dark.addEventListener("change", () => render(false));

  render(true);
}

main();
