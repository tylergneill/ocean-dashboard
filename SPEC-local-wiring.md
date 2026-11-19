# Spec: wire up the dashboard locally

For an agent working on Tyler's own machine, where the sibling repos are
checked out. The code on branch `v0` was written in the cloud against public
copies only; this pass connects it to the real local data and checks it.

## Goal

`make data && make serve` on Tyler's machine shows all five Sāgarasaṅgama
collections, with SETI's registered texts correctly on the right-hand heap,
and the page looks right in a browser.

## Ground rules

- Work on branch `v0` (or a branch off it). **Never open or merge a pull
  request without Tyler's explicit permission.** Commit and push are fine.
- The sibling repos are **read-only** from here. Do not edit sagara-sangama,
  the Atlases, SETI or Pāṇḍitya. If a figure this dashboard needs is missing
  from what a sibling publishes, note it (see "Report back"); the fix belongs
  upstream, per sagara-sangama's `CONTRACT.md`.
- Read only what siblings publish: `docs/data/*` in sagara-sangama and the
  Atlases, `data/seti-master.csv` in SETI. Not their working `data/`, caches
  or scripts.
- Python, standard library only (3.11+ for `tomllib`). Keep code documented;
  Tyler wants to understand what it does.
- Keep it small. This is a motivational tool, not a product.

## What v0 already does

- `build_progress.py` reads Sāgarasaṅgama's `docs/data/search.json` (all
  Atlas items), the SETI master, and optionally the GRETIL Atlas
  `tree.json`. It matches items to SETI rows **by link only** and writes
  `docs/data/progress.json` (gitignored). Each item is `[bytes, flags]`,
  flags being RECORD=1, WORK=2, AUTHOR=4.
- `docs/` is a static page: tabs (All + one per collection), two heaps of
  grains (left: not in SETI, right: in SETI) with a lift-and-arc animation,
  a "Done means" toggle (Record / + Work / + Author / + Work & author), a
  Texts / MB switch, and bars with exact numbers.
- Tested only in node with a stubbed DOM. **Never seen in a real browser.**
- Run against the public sagara-sangama index (three Atlases) plus GRETIL
  and Jain Quantum items taken from SETI's
  `reports/2026-10-13-atlas-works-items.csv`: GRETIL matched 290 of 1,123
  items; the other four collections have no SETI rows yet, so zero.

## Tasks

### 1. Paths

Fix `config.toml` so the three inputs resolve. The defaults are guesses
based on how SETI's `scripts/atlas_works.py` finds its siblings
(`<git>/sagara-sangama/sagara-sangama/`, `<git>/sagara-sangama/atlases/…`).
Find where the repos actually are, set relative paths, and confirm
`make data` runs. Use the SETI repo's master, not Pāṇḍitya's dated copy.

### 2. Five collections in the index

The public sagara-sangama `search.json` has only Wikisource, Sanskrit
Documents and E-bhāratīsampat. Tyler's local one should also have GRETIL
(`a: "g"`) and Jain Quantum (`a: "j"`). Confirm `make data` prints all five.
If the local index still has three, stop and report: don't build the other
two from the Atlases' own trees without asking.

### 3. GRETIL matching

SETI's 1,037 GRETIL rows link legacy `1_sanskr/…/*.htm` files. The search
index's GRETIL ids are mostly `corpustei/…xml` paths. The GRETIL Atlas
`tree.json` (`works[].files`) lists every file of an item and bridges the
two; `load_gretil_files()` uses it. With it in place:

- Report how many of the 1,037 rows still match nothing (the build prints
  this, and the page footer shows it).
- Look at a sample of the unmatched ones and say why: a link-rule gap here,
  or a row pointing at a file the Atlas doesn't have. Fix rule gaps in
  `site_keys()` / `item_keys()`. Leave data problems for Tyler.
- Spot-check about ten matched items by hand: SETI row ↔ Atlas item really
  are the same text.

The cross-check: `atlas_works.py` does the same GRETIL join for its
calibration. Its count of GRETIL items with a SETI Pandit ID should be close
to the dashboard's GRETIL "+work" figure.

### 4. Link rules for the other collections

None of these has SETI rows yet, so nothing can be tested by matching. Read
each Atlas's `docs/app.js` (or wherever it builds item links) and confirm
the rules in `item_keys()` / `site_keys()` agree:

- **Sanskrit Documents:** item key is the doc id (`doc_x/name`); SETI links
  with `.html`, `.itx` or any `-xx.pdf` suffix reduce to the same key.
- **Wikisource:** the item's stored URL, percent-decoded, spaces → `_`.
- **E-bhāratīsampat:** `readSearch.php?id=<i>` or reader `bookid=` (the
  five-round base64 of the serial `s`; `ebs_reader_id()` mirrors
  `ebReaderId()` in sagara-sangama's `search.js`). Check the encoding against
  one real book.
- **Jain Quantum (jainqq.org):** no rule yet. Find how the Atlas links an
  item to jainqq.org and add the rule, so that the first SETI row Tyler adds
  for it will match.

For each, add a tiny test: one known item and two or three link spellings
that must give the same key. A `tests/` file run with
`python3 -m unittest` is enough.

### 5. Colours

Wikisource, Sanskrit Documents and E-bhāratīsampat use sagara-sangama's
hex values. GRETIL and Jain Quantum have placeholders in `COLLECTIONS`
(`placeholder_colour: True`). If Tyler's local sagara-sangama
(`docs/growth.js` / `docs/search.js`) has colours for them, copy those and
drop the placeholder flag. If not, leave the placeholders.

### 6. Look at it in a browser

`make serve`, open http://localhost:8765, and check, light and dark mode,
desktop and a narrow (phone-width) window:

- tabs switch; the active tab is underlined in its colour
- heaps animate on load, tab change and Texts/MB change; clicking replays
- the Done-means toggle recolours without re-animating; solid vs faint
  grains are distinguishable
- bars match the build's printed numbers
- footer shows dates and the unmatched-row count

Fix what's broken. Screenshots of All and GRETIL go in the report.

## Report back to Tyler

Short: what paths were set, the five collections' numbers (texts in SETI,
+work, +author, MB moved), GRETIL unmatched count and why, link rules
confirmed or changed, colour status, anything broken in the browser and
whether it was fixed, and anything that needs an upstream fix in a sibling
repo. Then stop; Tyler decides about any PR.

## Out of scope

- Publishing the page (GitHub Pages) or committing `progress.json`.
- An "author detail" level (established vs attributed author): not in the
  SETI master yet. The toggle button is there, disabled.
- Per-text titles or hover detail on grains.
- Anything in Pāṇḍitya. The dashboard will matter there once Sāgarasaṅgama
  texts flow into the SETI master Pāṇḍitya copies, but nothing here reads
  or changes it.
