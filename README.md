# ocean-registration-progress-dashboard

A small local dashboard of how far the Sāgarasaṅgama collections have got
into SETI, one collection at a time.

It coordinates between two sibling projects and belongs to neither:
Sāgarasaṅgama says what each collection holds, SETI says what has been
registered. This repo reads what they publish and draws the gap.

## Running it

```
make data    # read the sibling repos, write docs/data/progress.json
make serve   # http://localhost:8765
make test    # link-rule tests (python3 -m unittest)
```

Paths to the inputs are in `config.toml`, relative to this repo. Python 3.11+,
standard library only. The page is plain HTML, CSS and JavaScript with no
build step.

## What it reads

| Input | From | Used for |
|---|---|---|
| `docs/data/search.json` | sagara-sangama | every text-bearing item of every Atlas, with its size |
| `data/seti-master.csv` | seti | which texts are registered, and their Pandit IDs |
| `docs/data/tree.json` (optional) | gretil-atlas | every file of a GRETIL item |

Only published files, never working files, following Sāgarasaṅgama's
`CONTRACT.md`.

## What counts as registered

An Atlas item is **in SETI** when any link in any SETI row (Link 1, 2 or 3)
points at that item's page on its source site. Matching is by link only,
never by title. The per-site link rules are in `site_keys()` and
`item_keys()` in `build_progress.py`:

- **Sanskrit Documents:** the document id, whatever the stem (`.html`,
  `.itx`, `-sa.pdf` and the other downloads).
- **Sanskrit Wikisource:** the page URL, percent-decoded, spaces as
  underscores; the mobile host and `/w/index.php?title=` give the same key.
- **E-bhāratīsampat:** either the Atlas's `readSearch.php?id=` or the
  readers' `bookid=` (`readbook3`, `read_chapter`, `ebook_pdf`).
- **GRETIL:** the path after `/gretil/`, on Göttingen's site or the mirror.
  The search index carries one path per item (often the new `corpustei/`
  one) while SETI points at legacy
  `1_sanskr/….htm` files, so the GRETIL tree.json, which lists all of an
  item's files, is needed for a full match.
- **Jain Quantum:** the serial (`sr_no`), from jainqq.org's `/explore/<srno>/<page>`
  or `/booktext/<title>/<srno>`, leading zeros ignored.

Being in SETI moves a text to the right. The **Done means** toggle then
decides which of those are solid and which are faint:

| Toggle | Done when the SETI row has |
|---|---|
| Record | a row |
| + Work | a Pandit work ID (a partly filled cell like `... , 42078` counts) |
| + Author | a Pandit author ID, or `—` for no author |
| + Work & author | both |
| Author detail | not in the SETI master yet |

## The page

- One tab per collection, plus All. Collection colours are Sāgarasaṅgama's
  for Wikisource, Sanskrit Documents and E-bhāratīsampat. GRETIL and Jain
  Quantum use the colours from Sāgarasaṅgama's unmerged
  `add-gretil-and-jain-2` branch until its main carries them.
- Two heaps of grains: not yet in SETI on the left, in SETI on the right.
  On load the registered grains lift off the left heap and arc across.
  Click the heaps to replay.
- Bars underneath give exact counts and MB.
