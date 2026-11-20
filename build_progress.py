"""Build docs/data/progress.json: how much of each Sāgarasaṅgama collection SETI covers.

What it reads (read-only, nothing else):

  * Sāgarasaṅgama's published search index, docs/data/search.json. One item per
    Atlas entry, with the Atlas code ('a'), its id ('i', or a whole URL 'u' for
    Wikisource), its size in bytes ('b'), and whether it bears text. This is the
    whole heap: every text-bearing item, per collection.
  * The SETI master, data/seti-master.csv. One row per registered e-text, with
    up to three links and the Pandit work and author IDs.
  * Optionally the GRETIL Atlas tree.json, which lists every file of a GRETIL
    item and what kind each is (see item_parts below for why that matters).

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

  * Over how many parts? A text is what its Atlas says it is (one search-index
    item, so the totals are each Atlas's published text_count). Most are one
    part, registered or not. A GRETIL text can be several legacy files (the
    Mahābhārata is eighteen), and SETI registers files, so such a text counts
    as the share of its main files that SETI has: 12 of 18 parvans registered
    moves 12/18 of the Mahābhārata, in texts and in bytes. Crediting the whole
    text for any one file made GRETIL read ~95%.

What it writes: one JSON file the page reads. Each collection carries its
items as compact [bytes, [flags of each part]] pairs so the page can redraw
the heaps for any toggle setting without another build. No titles, to keep the
file small.

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
# GRETIL and Jain eLibrary take the colours from Sāgarasaṅgama's
# add-gretil-and-jain-2 branch (growth.js), which is not yet on its main; the
# placeholder_colour flag marks them until it is. Drop the flag, and recheck
# the hexes, once main carries them. `seti` is the Collection value SETI uses
# for it, where SETI has one.
COLLECTIONS = [
    {"code": "w", "name": "Sanskrit Wikisource", "site": "sa.wikisource.org",
     "light": "#2a78d6", "dark": "#3987e5", "seti": None},
    {"code": "d", "name": "Sanskrit Documents", "site": "sanskritdocuments.org",
     "light": "#1baf7a", "dark": "#199e70", "seti": None},
    {"code": "e", "name": "E-bhāratīsampat", "site": "ebharatisampat.in",
     "light": "#eb6834", "dark": "#d95926", "seti": None},
    {"code": "g", "name": "GRETIL", "site": "gretil.sub.uni-goettingen.de",
     "light": "#c9a227", "dark": "#d4ad2f", "seti": "GRETIL", "placeholder_colour": True},
    {"code": "j", "name": "Jain eLibrary", "site": "jainqq.org",
     "light": "#8e5bd6", "dark": "#9b6ee0", "seti": None, "placeholder_colour": True},
]

# Sanskrit Documents serves one document under several stems: the .html page
# and a download per script. Copied from Sāgarasaṅgama's search.js
# DOWNLOAD_SUFFIXES (itself copied from the Atlas's app.js), longest first so
# "-sa.pdf" is stripped before ".pdf".
SD_SUFFIXES = sorted(
    {".html", ".htm", ".itx", ".pdf", "-ta.pdf", "-te.pdf", "-kn.pdf", "-gu.pdf",
     "-bn.pdf", "-or.pdf", "-ml.pdf", "-pa.pdf", "-as.pdf", "-sa.pdf"},
    key=len, reverse=True)

# Where a GRETIL file can be linked: Göttingen itself (SETI's rows) and the
# mirror Sāgarasaṅgama's search page links to (tylergneill.github.io/
# gretil-mirror/gretil/...). Both put the corpus path after "/gretil/".
GRETIL_HOSTS = {"gretil.sub.uni-goettingen.de", "tylergneill.github.io"}


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
        # MediaWiki treats spaces and underscores in a title as the same. The
        # Atlas stores sa.wikisource.org/wiki/<Title>; the mobile host
        # (sa.m.wikisource.org) and /w/index.php?title=<Title> are the same page.
        host = host.replace(".m.wikisource.org", ".wikisource.org")
        if path == "/w/index.php":
            title = urllib.parse.parse_qs(query).get("title")
            if title:
                path = "/wiki/" + title[0]
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

    if host in GRETIL_HOSTS and "/gretil/" in path:
        # Everything after /gretil/ is the file's path in the corpus, which is
        # what the GRETIL Atlas's ids and tree files are. The same path on
        # Göttingen's site and on the mirror Sāgarasaṅgama links to is one file.
        return {"gretil:" + path.split("/gretil/", 1)[1]}

    if host == "jainqq.org":
        # Jain eLibrary (jainqq.org) keys a book by its six-digit serial (sr_no): the Atlas
        # links /explore/<srno>/1 (page viewer, any page number) and
        # /booktext/<title slug>/<srno> (the OCR text). Leading zeros are
        # dropped so "1014" and "001014" agree.
        m = (re.fullmatch(r"/explore/(\d+)(?:/\d+)?", path)
             or re.fullmatch(r"/booktext/[^/]+/(\d+)", path))
        if m:
            return {"jq:" + jq_serial(m.group(1))}

    return {"url:" + host + path + ("?" + query if query else "")}


def jq_serial(s):
    """A Jain eLibrary serial without its zero padding ("001014" → "1014")."""
    return s.lstrip("0") or "0"


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
    if a == "j":
        return {"jq:" + jq_serial(i)}
    return {f"{a}:{i}"}   # an Atlas with no rule here: counts, never matches


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
    """Two maps from the GRETIL Atlas tree.json, or ({}, {}) if it is absent.

    files: any file path of an item → every file path the tree lists for it.
    kinds: file path → the tree's file_kinds entry ("main", "version" or
           "index"). Only legacy .htm files have one; TEI files have none."""
    if not path or not Path(path).exists():
        return {}, {}
    tree = json.loads(Path(path).read_text(encoding="utf-8"))
    files_of, kinds = {}, {}
    for w in tree.get("works", []):
        files = w.get("files") or []
        for f in files:
            files_of[f] = files
        kinds.update(w.get("file_kinds") or {})
    return files_of, kinds


def item_parts(it, gretil_files, gretil_kinds):
    """The parts an item's registration is measured over: a list of key sets.

    Every collection but GRETIL: one part, the item's own keys.

    GRETIL, with the tree: one part per legacy *main* file, since that is what
    SETI registers. Version and index files are left out: a version is another
    rendering of the same text, not a further part of it, so a SETI row on one
    does not register the item's main text. A TEI file (corpustei/...) stands
    for the whole item, so its keys go into every part: a SETI row on it
    registers all of them. An item with no legacy main file (born TEI) is one
    part made of its TEI files."""
    if it["a"] == "g" and it.get("i") in gretil_files:
        files = gretil_files[it["i"]]
        whole = {"gretil:" + f for f in files if f.startswith("corpustei/")}
        mains = [f for f in files if gretil_kinds.get(f) == "main"]
        if mains:
            return [{"gretil:" + f} | whole for f in mains]
        if whole:
            return [whole]
    return [item_keys(it, gretil_files)]


# ---------------------------------------------------------------- build

def build(search_path, seti_path, gretil_path):
    index = json.loads(Path(search_path).read_text(encoding="utf-8"))
    seti_by_key, seti_rows = load_seti(seti_path)
    gretil_files, gretil_kinds = load_gretil_files(gretil_path)

    seen_keys = set()      # keys of any file of any item SETI links to
    counted_keys = set()   # keys that count toward an item's progress
    collections = []
    for c in COLLECTIONS:
        items = []
        for it in index["items"]:
            # Text-bearing items only: everything not flagged PDF-only ('po').
            # That gives exactly each Atlas's published text_count (the index's
            # own `reconciles` check is indexed - pdf_only == text_count).
            # Don't also require 'lt': it marks a local-text link, which some
            # text-bearing items lack (all of GRETIL, ~100 Wikisource pages).
            if it["a"] != c["code"] or it.get("po"):
                continue
            seen_keys |= item_keys(it, gretil_files) & seti_by_key.keys()
            parts = []
            for keys in item_parts(it, gretil_files, gretil_kinds):
                flags = 0
                for k in keys & seti_by_key.keys():
                    flags |= seti_by_key[k]
                    counted_keys.add(k)
                parts.append(flags)
            items.append([int(it.get("b") or 0), parts])
        if not items:
            continue   # not in this copy of the index (the public one has three Atlases)
        # Biggest first, so the heaps settle with the big texts at the bottom.
        items.sort(key=lambda x: -x[0])
        out = {k: v for k, v in c.items() if k != "seti"}
        out.update(texts=len(items), bytes=sum(b for b, _ in items), items=items)
        collections.append(out)

    # SETI rows for these collections that move nothing: either they link
    # nothing the Atlas has (a link rule missing here, or a page the Atlas
    # lacks), or only a file that doesn't count (a GRETIL version file).
    unmatched, uncounted = {}, {}
    for c in COLLECTIONS:
        if not c["seti"]:
            continue
        rows = [r for r in seti_rows if r.get("Collection") == c["seti"]]
        unmatched[c["name"]] = sum(1 for r in rows if not (r["_keys"] & seen_keys))
        uncounted[c["name"]] = sum(1 for r in rows
                                   if r["_keys"] & seen_keys and not (r["_keys"] & counted_keys))

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "search_json": {"path": str(search_path), "generated": index.get("generated")},
            "seti_master": {"path": str(seti_path), "rows": len(seti_rows)},
            "gretil_tree": {"path": str(gretil_path), "used": bool(gretil_files)},
        },
        "flags": {"record": RECORD, "work": WORK, "author": AUTHOR},
        "seti_rows_unmatched": unmatched,
        "seti_rows_version_only": uncounted,
        "collections": collections,
    }


def share(parts, need):
    """Fraction of an item's parts whose flags include every bit of `need`."""
    return sum(1 for f in parts if f & need == need) / len(parts)


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
        rec = sum(share(p, RECORD) for _, p in its)
        mb = sum(b * share(p, RECORD) for b, p in its) / 1e6
        print(f"  {c['name']:22s} {c['texts']:7d} {rec:8.1f} "
              f"{sum(share(p, RECORD | WORK) for _, p in its):7.1f} "
              f"{sum(share(p, RECORD | AUTHOR) for _, p in its):8.1f}"
              f"   {mb:,.1f} of {c['bytes'] / 1e6:,.1f}")
    for name, n in data["seti_rows_unmatched"].items():
        if n:
            print(f"  {n} SETI {name} rows matched no Atlas item")
    for name, n in data["seti_rows_version_only"].items():
        if n:
            print(f"  {n} SETI {name} rows link only a version file, so move nothing")

if __name__ == "__main__":
    main()
