import json
import os
import tempfile
import unittest

import generate
from filmio_mapping import filmio, http, match, omdb, output
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
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "extra": 1}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "imdb": "tt0000001", "imdbRating": "7"}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "imdb": "tt0000001", "imdbVotes": 1.5}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "imdb": "tt0000001", "rottenTomatoes": 101}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "rottenTomatoes": 80}}},
                    {"version": 1, "items": {"a": {"type": "movie", "tmdb": 1, "imdbRating": 7.0}}}):
            with self.assertRaises(ValueError):
                output.validate(doc)

    def test_entry_drops_bad_imdb(self):
        self.assertEqual(output.entry("movie", "5", "bogus", 7.1, 10, 80), {"type": "movie", "tmdb": 5})

    def test_entry_with_ratings(self):
        item = output.entry("movie", 5, "tt0000005", 7.1, 1234, 85)
        self.assertEqual(item, {"type": "movie", "tmdb": 5, "imdb": "tt0000005", "imdbRating": 7.1, "imdbVotes": 1234,
                                "rottenTomatoes": 85})
        output.validate({"version": 1, "items": {"a": item}})
        self.assertEqual(output.entry("movie", 5, "tt0000005", None, 3),
                         {"type": "movie", "tmdb": 5, "imdb": "tt0000005", "imdbVotes": 3})


class RefreshTest(unittest.TestCase):
    def test_refresh_updates_imdb_and_drops_gone_titles(self):
        tmdb = FakeTmdb({}, {1: {"external_ids": {"imdb_id": "tt0000011"}}, 2: {}})
        tmdb.gone = {3, 4}
        items = {"a": output.entry("movie", 1), "b": output.entry("movie", 2, "tt0000002"),
                 "c": output.entry("tvshow", 3), "d": output.entry("movie", 4)}
        report = {}
        generate.refresh_details(items, {"d": output.entry("movie", 4)}, tmdb, report, log=lambda m: None)
        self.assertEqual(items, {"a": {"type": "movie", "tmdb": 1, "imdb": "tt0000011"},
                                 "b": {"type": "movie", "tmdb": 2, "imdb": "tt0000002"},
                                 "d": {"type": "movie", "tmdb": 4}})
        self.assertEqual(report["removed"], [("c", 3)])

    def test_refresh_keeps_ratings_only_with_the_same_imdb_id(self):
        tmdb = FakeTmdb({}, {1: {"external_ids": {"imdb_id": "tt0000001"}}, 2: {"external_ids": {"imdb_id": "tt0000022"}}})
        items = {"a": output.entry("movie", 1, "tt0000001", 7.0, 10, 90),
                 "b": output.entry("movie", 2, "tt0000002", 6.0, 20, 50)}
        generate.refresh_details(items, {}, tmdb, {}, log=lambda m: None)
        self.assertEqual(items, {"a": {"type": "movie", "tmdb": 1, "imdb": "tt0000001", "imdbRating": 7.0, "imdbVotes": 10,
                                       "rottenTomatoes": 90},
                                 "b": {"type": "movie", "tmdb": 2, "imdb": "tt0000022"}})


class FakeOmdb(object):
    def __init__(self, answers, fail_on=None):
        self.answers, self.fail_on, self.requests = answers, fail_on, 0

    def ratings(self, imdb_id):
        if imdb_id == self.fail_on:
            raise http.HttpError(401, "https://www.omdbapi.com/")
        self.requests += 1
        return self.answers.get(imdb_id)


class RatingsTest(unittest.TestCase):
    def items(self):
        return {"a": output.entry("movie", 1, "tt0000001", 5.0, 5), "b": output.entry("movie", 2),
                "c": output.entry("movie", 3, "tt0000003", 6.0, 6), "d": output.entry("tvshow", 4, "tt0000004", 4.0, 4),
                "e": output.entry("movie", 5, "tt0000005", 3.0, 3)}

    def test_updates_clears_and_keeps(self):
        items = self.items()
        fake = FakeOmdb({"tt0000001": (7.8, 12345, 91), "tt0000003": (None, None, None), "tt0000005": (None, 4, None)})
        generate.refresh_ratings(items, fake, log=lambda m: None)
        self.assertEqual(items["a"], {"type": "movie", "tmdb": 1, "imdb": "tt0000001", "imdbRating": 7.8, "imdbVotes": 12345,
                                      "rottenTomatoes": 91})
        self.assertEqual(items["b"], {"type": "movie", "tmdb": 2})
        self.assertEqual(items["c"], {"type": "movie", "tmdb": 3, "imdb": "tt0000003"})  # IMDb has none
        self.assertEqual(items["d"]["imdbRating"], 4.0)  # OMDb does not know it: kept
        self.assertEqual(items["e"], {"type": "movie", "tmdb": 5, "imdb": "tt0000005", "imdbVotes": 4})
        self.assertEqual(fake.requests, 4)  # nothing asked for the title without an IMDb id

    def test_request_limit_keeps_the_rest(self):
        items, logged = self.items(), []
        generate.refresh_ratings(items, FakeOmdb({"tt0000001": (7.8, 12345, None)}, fail_on="tt0000003"), log=logged.append)
        self.assertEqual(items["a"]["imdbRating"], 7.8)
        self.assertEqual((items["c"]["imdbRating"], items["d"]["imdbRating"]), (6.0, 4.0))
        self.assertEqual(len(logged), 1)

    def test_client_parses_omdb_answers(self):
        answers = {"tt1": {"Response": "True", "imdbRating": "7.8", "imdbVotes": "1,234,567",
                           "Ratings": [{"Source": "Internet Movie Database", "Value": "7.8/10"},
                                       {"Source": "Rotten Tomatoes", "Value": "85%"}]},
                   "tt2": {"Response": "True", "imdbRating": "N/A", "imdbVotes": "N/A"},
                   "tt3": {"Response": "False", "Error": "Incorrect IMDb ID."}}
        calls = []

        def get_json(url, params=None):
            calls.append((url, dict(params)))
            return answers[dict(params)["i"]]
        client = omdb.Omdb("KEY", get_json=get_json)
        self.assertEqual(client.ratings("tt1"), (7.8, 1234567, 85))
        self.assertEqual(client.ratings("tt2"), (None, None, None))
        self.assertIsNone(client.ratings("tt3"))
        self.assertEqual(calls[0], ("https://www.omdbapi.com/", {"i": "tt1", "apikey": "KEY"}))
        with self.assertRaises(ValueError):
            omdb.Omdb("")


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

    def test_kept_entries_get_refreshed_details(self):
        previous = {"old": output.entry("movie", 42)}
        self.tmdb.details_by_id[42] = {"external_ids": {"imdb_id": "tt0000042"}}
        items, _ = generate.build(self.titles, previous, {}, self.tmdb, log=lambda m: None)
        self.assertEqual(items["old"], {"type": "movie", "tmdb": 42, "imdb": "tt0000042"})

    def test_build_adds_ratings(self):
        self.tmdb.details_by_id[1] = {"external_ids": {"imdb_id": "tt0000001"}}
        items, _ = generate.build(self.titles, {}, {}, self.tmdb, log=lambda m: None,
                                  omdb=FakeOmdb({"tt0000001": (8.1, 900, None)}))
        self.assertEqual(items["new"], {"type": "movie", "tmdb": 1, "imdb": "tt0000001", "imdbRating": 8.1, "imdbVotes": 900})


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
