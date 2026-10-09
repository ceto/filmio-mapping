import json
import os
import tempfile
import unittest

import generate
from filmio_mapping import filmio, http, match, output
from filmio_mapping.filmio import Title
from tests.test_match import FakeTmdb, movie


class OutputTest(unittest.TestCase):
    def test_validate_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data", "mapping.json")
            doc = output.write(path, {"b": output.entry("movie", 2, "tt0000002"), "a": output.entry("tvshow", 1)},
                               "2026-10-09T00:00:00Z")
            self.assertEqual(list(doc["items"]), ["a", "b"])
            self.assertEqual(output.load(path), doc["items"])

    def test_invalid_documents(self):
        for doc in ({"version": 2, "items": {}}, {"version": 1, "items": {"a": {"type": "episode", "tmdb": 1}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": "1"}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "imdb": "nm1"}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "extra": 1}}}):
            with self.assertRaises(ValueError):
                output.validate(doc)

    def test_entry_drops_bad_imdb(self):
        self.assertEqual(output.entry("movie", "5", "bogus"), {"type": "movie", "tmdb": 5})


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.titles = [Title("new", "movie", "Aglaja", None, 2012, None),
                       Title("old", "movie", "Szelíd", None, 2022, None),
                       Title("ovr", "movie", "Valami", None, 2000, None),
                       Title("off", "movie", "Más", None, 2000, None),
                       Title("amb", "movie", "Szerelem", None, None, None)]
        self.tmdb = FakeTmdb({("movie", "Aglaja"): [movie(1, "Aglaja", 2012)],
                              ("movie", "Szelíd"): [movie(99, "Szelíd", 2022)],
                              ("movie", "Szerelem"): [movie(7, "Szerelem", 1971), movie(8, "Szerelem", 1970)]})

    def test_rules(self):
        previous = {"old": output.entry("movie", 42)}
        overrides = {"ovr": output.entry("movie", 5), "off": None}
        items, report = generate.build(self.titles, previous, overrides, self.tmdb, log=lambda m: None)
        self.assertEqual(items, {"new": {"type": "movie", "tmdb": 1}, "old": {"type": "movie", "tmdb": 42},
                                 "ovr": {"type": "movie", "tmdb": 5}})
        self.assertEqual([t.id for t in report["kept"]], ["old"])
        self.assertEqual([t.id for t in report["excluded"]], ["off"])
        self.assertEqual([t.id for t, _ in report["ambiguous"]], ["amb"])
        self.assertNotIn(("movie", "Szelíd", 2022), self.tmdb.searches)  # kept entries are not searched

    def test_refresh_reports_but_never_replaces(self):
        previous = {"old": output.entry("movie", 42)}
        items, report = generate.build(self.titles, previous, {}, self.tmdb, refresh=True, log=lambda m: None)
        self.assertEqual(items["old"]["tmdb"], 42)
        self.assertEqual([(t.id, a, b) for t, a, b in report["disagreements"]], [("old", 42, 99)])

    def test_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "overrides.json")
            with open(path, "w") as fh:
                json.dump({"_comment": "x", "a": {"type": "movie", "tmdb": 3, "imdb": "tt0000003"},
                           "b": {"tmdb": None}, "c": None}, fh)
            self.assertEqual(generate.load_overrides(path),
                             {"a": {"type": "movie", "tmdb": 3, "imdb": "tt0000003"}, "b": None, "c": None})


class CatalogueTest(unittest.TestCase):
    def test_pages_by_total_and_keeps_films_and_series(self):
        pages = {1: [{"id": "m1", "type": "MOVIE", "title": "A", "year": "1999", "length": 100},
                     {"id": "e1", "type": "EPISODE", "title": "Ep"},
                     {"id": "s1", "type": "SERIES", "title": "S", "year": "0"}],
                 2: [{"id": "m1", "type": "MOVIE", "title": "A"}, {"id": "t1", "type": "TAG", "title": "tag"}]}

        def get_json(url, params=None):
            if url.endswith("/config"):
                return {"data": {"app": {"search": {"searchCarouselId": "abc"}}}}
            page = dict(params)["page"]
            # pageCount is deliberately wrong, as on the real API
            return {"data": pages.get(page, []), "meta": {"pagination": {"page": page, "pageCount": 1, "total": 105}}}
        titles = filmio.catalogue(get_json=get_json, log=lambda m: None)
        self.assertEqual([(t.id, t.kind, t.year) for t in titles], [("m1", "movie", 1999), ("s1", "tvshow", None)])


class HttpTest(unittest.TestCase):
    def test_retries_then_raises_without_query_string(self):
        from urllib.error import URLError
        calls = []

        def opener(req, timeout=None):
            calls.append(req.full_url)
            raise URLError("down")
        with self.assertRaises(http.HttpError) as ctx:
            http.get_json("https://api.example/x", [("api_key", "SECRET")], opener=opener, sleep=lambda s: None,
                          retries=2)
        self.assertEqual(len(calls), 3)
        self.assertNotIn("SECRET", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
