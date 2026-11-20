"""Link rules: one real item per collection, and the link spellings a SETI row
might use for it, which must all reduce to a key the item also has.

The items are copied from Sāgarasaṅgama's search.json and the GRETIL Atlas
tree.json (November 2026). Run from the repo root:

    python3 -m unittest
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_progress import ebs_reader_id, item_keys, item_parts, site_keys


class LinkKeys(unittest.TestCase):

    def assertLinksMatch(self, item, links, gretil_files=None):
        keys = item_keys(item, gretil_files or {})
        for link in links:
            with self.subTest(link=link):
                self.assertTrue(site_keys(link) & keys,
                                f"{link} → {site_keys(link)}, item has {keys}")

    def test_sanskrit_documents(self):
        # Key is the doc id; the page and every download stem reduce to it.
        item = {"a": "d", "i": "doc_deities_misc/svAmIsamarthasahasranAmastotramarAThI"}
        base = "sanskritdocuments.org/doc_deities_misc/svAmIsamarthasahasranAmastotramarAThI"
        self.assertLinksMatch(item, [
            "https://" + base + ".html",
            "http://www." + base + ".itx",
            "https://" + base + "-sa.pdf",
            "https://" + base + ".pdf",
        ])

    def test_wikisource(self):
        # The stored URL, percent-encoded or not, spaces or underscores,
        # desktop or mobile, /wiki/ or index.php?title=.
        url = ("https://sa.wikisource.org/wiki/%E0%A4%9C%E0%A4%AF%E0%A4%BE%E0%A4%96"
               "%E0%A5%8D%E0%A4%AF%E0%A4%B8%E0%A4%82%E0%A4%B9%E0%A4%BF%E0%A4%A4%E0%A4%BE")
        item = {"a": "w", "u": url}
        self.assertLinksMatch(item, [
            url,
            "https://sa.wikisource.org/wiki/जयाख्यसंहिता",
            "http://sa.m.wikisource.org/wiki/जयाख्यसंहिता/",
            "https://sa.wikisource.org/w/index.php?title=जयाख्यसंहिता",
        ])

    def test_wikisource_spaces(self):
        item = {"a": "w", "u": "https://sa.wikisource.org/wiki/ऋग्वेदः_सूक्तं_१.१"}
        self.assertLinksMatch(item, ["https://sa.wikisource.org/wiki/ऋग्वेदः सूक्तं १.१"])

    def test_ebharatisampat_reader_id(self):
        # Manusmṛti, serial 2503. This bookid was checked against the live
        # site on 2026-11-19: readbook3?bookid=<it> declares BOOK_ID = '2503'.
        self.assertEqual(ebs_reader_id("2503"), "PT1BVVVKa2NaWmxXcmRsUlJwWFRXSlZV")

    def test_ebharatisampat(self):
        item = {"a": "e", "i": "NjYyMjg3NDk1ODcyMDQy", "s": "2503"}
        rid = ebs_reader_id("2503")
        self.assertLinksMatch(item, [
            "https://www.ebharatisampat.in/readSearch.php?id=NjYyMjg3NDk1ODcyMDQy",
            f"https://www.ebharatisampat.in/readbook3?bookid={rid}&bookname=x",
            f"https://ebharatisampat.in/read_chapter?bookid={rid}",
            f"https://www.ebharatisampat.in/ebook_pdf?bookid={rid}",
        ])

    def test_gretil(self):
        # The index carries the TEI file; SETI links the legacy .htm. The
        # tree's file list bridges them. Göttingen and the mirror agree.
        files = ["corpustei/sa_pataJjali-yogasUtra-alt.xml",
                 "corpustei/transformations/plaintext/sa_pataJjali-yogasUtra-alt.txt",
                 "1_sanskr/6_sastra/3_phil/yoga/yogasutu.htm"]
        item = {"a": "g", "i": files[0]}
        self.assertLinksMatch(item, [
            "http://gretil.sub.uni-goettingen.de/gretil/1_sanskr/6_sastra/3_phil/yoga/yogasutu.htm",
            "https://gretil.sub.uni-goettingen.de/gretil/corpustei/sa_pataJjali-yogasUtra-alt.xml",
            "https://tylergneill.github.io/gretil-mirror/gretil/1_sanskr/6_sastra/3_phil/yoga/yogasutu.htm",
        ], gretil_files={f: files for f in files})

    def test_jain_elibrary(self):
        # Panchsangrah, sr_no 001014: viewer at any page, and the text page.
        item = {"a": "j", "i": "001014"}
        self.assertLinksMatch(item, [
            "https://jainqq.org/explore/001014/1",
            "https://www.jainqq.org/explore/001014/37",
            "https://jainqq.org/explore/1014",
            "https://jainqq.org/booktext/Panchsangrah/001014",
        ])

    def test_no_false_matches(self):
        # Different texts must not share a key.
        self.assertFalse(site_keys("https://jainqq.org/explore/001015/1")
                         & item_keys({"a": "j", "i": "001014"}, {}))
        self.assertFalse(site_keys("https://sanskritdocuments.org/doc_deities_misc/other.html")
                         & item_keys({"a": "d", "i": "doc_deities_misc/svAmIsamarthasahasranAmastotramarAThI"}, {}))
        self.assertEqual(site_keys("https://tylergneill.github.io/gretil-atlas/"),
                         {"url:tylergneill.github.io/gretil-atlas"})



class GretilParts(unittest.TestCase):
    """A GRETIL text counts over its legacy main files, not as all or nothing."""

    FILES = ["corpustei/sa_mahAbhArata.xml",
             "1_sanskr/2_epic/mbh/mbh_01_u.htm",
             "1_sanskr/2_epic/mbh/mbh_02_u.htm",
             "1_sanskr/2_epic/mbh/mbh_03_u.htm",
             "1_sanskr/2_epic/mbh/ext/bhgce__u.htm"]
    KINDS = {FILES[1]: "main", FILES[2]: "main", FILES[3]: "main", FILES[4]: "version"}

    def parts(self):
        item = {"a": "g", "i": self.FILES[1]}
        return item_parts(item, {f: self.FILES for f in self.FILES}, self.KINDS)

    def registered(self, links):
        keys = set().union(*(site_keys(l) for l in links))
        return [bool(p & keys) for p in self.parts()]

    def test_one_part_per_main_file(self):
        self.assertEqual(len(self.parts()), 3)

    def test_share_of_mains(self):
        base = "http://gretil.sub.uni-goettingen.de/gretil/"
        self.assertEqual(self.registered([base + self.FILES[1], base + self.FILES[2]]),
                         [True, True, False])

    def test_version_file_moves_nothing(self):
        base = "http://gretil.sub.uni-goettingen.de/gretil/"
        self.assertEqual(self.registered([base + self.FILES[4]]), [False, False, False])

    def test_tei_file_registers_whole(self):
        base = "http://gretil.sub.uni-goettingen.de/gretil/"
        self.assertEqual(self.registered([base + self.FILES[0]]), [True, True, True])

    def test_other_collections_one_part(self):
        self.assertEqual(len(item_parts({"a": "j", "i": "001014"}, {}, {})), 1)


if __name__ == "__main__":
    unittest.main()
