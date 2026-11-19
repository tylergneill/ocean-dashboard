"""Build docs/data/progress.json: how much of each Sāgarasaṅgama collection SETI covers.

What it reads (read-only, nothing else):

  * Sāgarasaṅgama's published search index, docs/data/search.json. One item per
    Atlas entry, with the Atlas code ('a'), its id ('i', or a whole URL 'u' for
    Wikisource), its size in bytes ('b'), and whether it bears text. This is the
    whole heap: every text-bearing item, per collection.
  * The SETI master, data/seti-master.csv. One row per registered e-text, with
    up to three links and the Pandit work and author IDs.
  * Optionally the GRETIL Atlas tree.json, which lists every file of a GRETIL
    item (see match_gretil below for why that matters).

It follows the same rule Sāgarasaṅgama's CONTRACT.md sets for itself: read only
what a sibling repo publishes, never its working files.

What it decides, per text-bearing item:

  * Does any SETI row link to it? Matching is by link only. Each Atlas item's
    page on its source site is turned into one or more normalised keys, every
    link in every SETI row is normalised the same way, and an item counts as
    registered when the two share a key. Titles are never used: two stotras
    called "Kavacham" are different texts, and a fuzzy title match would move
    things right that have not been registered.
  * If so, which of the stricter levels does the best matching row reach?
      RECORD  a SETI row exists (always set for a matched item)
      WORK    the Work ID cell holds at least one Pandit ID
      AUTHOR  the Author ID cell holds a Pandit ID, or "—" (no author)
    These are bit flags, not a ladder: a row can know its author but not its
    work. The page's toggle picks which flags count as done.

What it writes: one JSON file the page reads. Each collection carries its
items as compact [bytes, flags] pairs so the page can redraw the heaps for any
toggle setting without another build. No titles, to keep the file small.

Standard library only. Python 3.11+ (for tomllib).

    python3 build_progress.py              # paths from config.toml
    python3 build_progress.py --help
"""

import argparse
import base64
import csv
import datetime
import json
import re
import sys
import tomllib
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "data" / "progress.json"

# Flag bits for one item. See the module docstring.
RECORD, WORK, AUTHOR = 1, 2, 4

OPEN = "..."       # SETI: no Pandit ID identified yet
NO_AUTHOR = "—"    # SETI: the text has no author

# The five collections, in the order the tabs show them, with their colours.
# Wikisource, Sanskrit Documents and E-bhāratīsampat take the exact hex values
# of Sāgarasaṅgama's growth chart and search page (docs/growth.js,
# docs/search.js) so a collection keeps its colour across the projects.
# GRETIL and Jain Quantum have no colour there yet; the two below are
# placeholders in the same lightness band, to be replaced by whatever
# Sāgarasaṅgama settles on. `seti` is the Collection value SETI uses for it,
# where SETI has one.
COLLECTIONS = [
    {"code": "w", "name": "Sanskrit Wikisource", "site": "sa.wikisource.org",
     "light": "#2a78d6", "dark": "#3987e5", "seti": None},
    {"code": "d", "name": "Sanskrit Documents", "site": "sanskritdocuments.org",
     "light": "#1baf7a", "dark": "#199e70", "seti": None},
    {"code": "e", "name": "E-bhāratīsampat", "site": "ebharatisampat.in",
     "light": "#eb6834", "dark": "#d95926", "seti": None},
    {"code": "g", "name": "GRETIL", "site": "gretil.sub.uni-goettingen.de",
     "light": "#b5487f", "dark": "#cc5a93", "seti": "GRETIL", "placeholder_colour": True},
    {"code": "j", "name": "Jain Quantum", "site": "jainqq.org",
     "light": "#8a63c9", "dark": "#9a76d6", "seti": None, "placeholder_colour": True},
]

# Sanskrit Documents serves one document under several stems: the .html page
# and a download per script. Copied from Sāgarasaṅgama's search.js
# DOWNLOAD_SUFFIXES (itself copied from the Atlas's app.js), longest first so
# "-sa.pdf" is stripped before ".pdf".
SD_SUFFIXES = sorted(
    {".html", ".htm", ".itx", ".pdf", "-ta.pdf", "-te.pdf", "-kn.pdf", "-gu.pdf",
     "-bn.pdf", "-or.pdf", "-ml.pdf", "-pa.pdf", "-as.pdf", "-sa.pdf"},
    key=len, reverse=True)


# ---------------------------------------------------------------- link keys

def url_key(url):
    """One normalised key for a URL, or None if it is not a URL.

    Scheme, "www." and a trailing slash are dropped, the host is lowercased and
    the path percent-decoded, so the same page written two ways gives one key.
    Some sites need more than that; those are handled by site_keys()."""
    url = url.strip()
    if not url:
        return None
    if "://" not in url:
        url = "http://" + url
    parts = urllib.parse.urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    path = urllib.parse.unquote(parts.path).rstrip("/")
    return host, path, parts.query


def site_keys(url):
    """All match keys for one link. The per-site rules live here.

    Returns a set of strings; an unusable link gives an empty set."""
    k = url_key(url)
    if not k:
        return set()
    host, path, query = k

    if host.endswith("sanskritdocuments.org"):
        # One document, many stems: strip the download suffix to get the doc id.
        for suf in SD_SUFFIXES:
            if path.endswith(suf):
                path = path[: -len(suf)]
                break
        return {"sd:" + path.lstrip("/")}

    if host.endswith("wikisource.org"):
        # MediaWiki treats spaces and underscores in a title as the same.
        return {"ws:" + host + path.replace(" ", "_")}

    if host.endswith("ebharatisampat.in"):
        # Two kinds of id reach the same book: the Atlas's readSearch.php?id=
        # and the readers' bookid= (see ebs_reader_id).
        q = urllib.parse.parse_qs(query)
        keys = set()
        for v in q.get("id", []):
            keys.add("ebs-id:" + v)
        for v in q.get("bookid", []):
            keys.add("ebs-book:" + v)
        return keys

    if host.endswith("uni-goettingen.de") and "/gretil/" in path:
        # Everything after /gretil/ is the file's path in the corpus, which is
        # what the GRETIL Atlas's ids and tree files are.
        return {"gretil:" + path.split("/gretil/", 1)[1]}

    return {"url:" + host + path + ("?" + query if query else "")}


def ebs_reader_id(serial):
    """E-bhāratīsampat's reader bookid for a book's serial.

    The serial base64-encoded five times, the string reversed between rounds.
    Same as ebReaderId() in Sāgarasaṅgama's search.js and the Atlas's app.js."""
    if not serial:
        return None
    e = str(serial)
    for _ in range(4):
        e = base64.b64encode(e.encode()).decode()[::-1]
    return base64.b64encode(e.encode()).decode()


def item_keys(it, gretil_files):
    """Match keys for one search-index item, by its Atlas's own link rule.

    The rules mirror rehydrate() in Sāgarasaṅgama's search.js. If a link ever
    looks wrong, the Atlas is right and this has drifted."""
    a, i = it["a"], it.get("i", "")
    if a == "d":
        return {"sd:" + i}
    if a == "w":
        return site_keys(it.get("u", ""))
    if a == "e":
        keys = {"ebs-id:" + i}
        rid = ebs_reader_id(it.get("s"))
        if rid:
            keys.add("ebs-book:" + rid)
        return keys
    if a == "g":
        # The index carries one path per item; the tree lists all its files,
        # and SETI may point at any of them (often a legacy .htm).
        return {"gretil:" + f for f in gretil_files.get(i, [i])}
    # Jain Quantum: no link rule yet, and SETI has no rows for it. The key
    # below cannot match anything; it is here so the item still counts in the
    # heap. Add the rule when SETI starts registering Jain Quantum texts.
    return {f"{a}:{i}"}


# ---------------------------------------------------------------- SETI

def id_flags(row):
    """WORK and AUTHOR flags for one SETI row.

    A work cell like "... , 42078" (a parvan unidentified, its Mahābhārata
    identified) counts as WORK: some Pandit work is known. That is the lenient
    reading; tighten it here if "done" should mean every slot is filled."""
    flags = RECORD
    if re.search(r"\d", row.get("Work ID", "")):
        flags |= WORK
    author = row.get("Author ID", "").strip()
    if re.search(r"\d", author) or author == NO_AUTHOR:
        flags |= AUTHOR
    return flags


def load_seti(path):
    """key → best flags among the SETI rows that link there, plus the rows."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_key = {}
    for r in rows:
        flags = id_flags(r)
        keys = set()
        for col in ("Link 1 (main)", "Link 2 (underlying)", "Link 3 (extract)"):
            for link in (r.get(col) or "").split():
                keys |= site_keys(link)
        r["_keys"] = keys
        for k in keys:
            by_key[k] = by_key.get(k, 0) | flags
    return by_key, rows


def load_gretil_files(path):
    """GRETIL item id → every file path the tree lists for it, or {} if absent."""
    if not path or not Path(path).exists():
        return {}
    tree = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for w in tree.get("works", []):
        files = w.get("files") or []
        for f in files:
            out[f] = files
    return out


# ---------------------------------------------------------------- build

def build(search_path, seti_path, gretil_path):
    index = json.loads(Path(search_path).read_text(encoding="utf-8"))
    seti_by_key, seti_rows = load_seti(seti_path)
    gretil_files = load_gretil_files(gretil_path)

    matched_keys = set()
    collections = []
    for c in COLLECTIONS:
        items = []
        for it in index["items"]:
            # Text-bearing items only: 'lt' set and not PDF-only ('po'). These
            # totals are each Atlas's published text_count.
            if it["a"] != c["code"] or not it.get("lt") or it.get("po"):
                continue
            flags = 0
            for k in item_keys(it, gretil_files):
                if k in seti_by_key:
                    flags |= seti_by_key[k]
                    matched_keys.add(k)
            items.append([int(it.get("b") or 0), flags])
        if not items:
            continue   # not in this copy of the index (the public one has three Atlases)
        # Biggest first, so the heaps settle with the big texts at the bottom.
        items.sort(key=lambda x: -x[0])
        out = {k: v for k, v in c.items() if k != "seti"}
        out.update(texts=len(items), bytes=sum(b for b, _ in items), items=items)
        collections.append(out)

    # SETI rows for these collections whose links matched nothing: either a
    # link rule is missing here, or the row points at a page the Atlas lacks.
    unmatched = {}
    for c in COLLECTIONS:
        if not c["seti"]:
            continue
        rows = [r for r in seti_rows if r.get("Collection") == c["seti"]]
        unmatched[c["name"]] = sum(1 for r in rows if not (r["_keys"] & matched_keys))

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "search_json": {"path": str(search_path), "generated": index.get("generated")},
            "seti_master": {"path": str(seti_path), "rows": len(seti_rows)},
            "gretil_tree": {"path": str(gretil_path), "used": bool(gretil_files)},
        },
        "flags": {"record": RECORD, "work": WORK, "author": AUTHOR},
        "seti_rows_unmatched": unmatched,
        "collections": collections,
    }


def main():
    cfg = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))["inputs"]

    def rel(p):
        return (ROOT / p).resolve() if p else None

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--search-json", type=Path, default=rel(cfg.get("search_json")))
    ap.add_argument("--seti-master", type=Path, default=rel(cfg.get("seti_master")))
    ap.add_argument("--gretil-tree", type=Path, default=rel(cfg.get("gretil_tree")))
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    for name in ("search_json", "seti_master"):
        p = getattr(args, name)
        if not p or not p.exists():
            sys.exit(f"{name} not found: {p}\nSet it in config.toml or pass --{name.replace('_', '-')}.")

    data = build(args.search_json, args.seti_master, args.gretil_tree)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # A short report, so a build says what it found without opening the page.
    print(f"wrote {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    if not data["inputs"]["gretil_tree"]["used"]:
        print("  (no GRETIL tree.json: GRETIL matched on the index id only)")
    print(f"  {'collection':22s} {'texts':>7s} {'in SETI':>8s} {'+work':>7s} {'+author':>8s}   MB moved")
    for c in data["collections"]:
        its = c["items"]
        rec = [x for x in its if x[1] & RECORD]
        mb = sum(b for b, _ in rec) / 1e6
        print(f"  {c['name']:22s} {c['texts']:7d} {len(rec):8d} "
              f"{sum(1 for x in its if x[1] & WORK):7d} {sum(1 for x in its if x[1] & AUTHOR):8d}"
              f"   {mb:,.1f} of {c['bytes'] / 1e6:,.1f}")
    for name, n in data["seti_rows_unmatched"].items():
        if n:
            print(f"  {n} SETI {name} rows matched no Atlas item")


if __name__ == "__main__":
    main()
