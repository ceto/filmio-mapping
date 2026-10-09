import unittest

from filmio_mapping import match
from filmio_mapping.filmio import Title


class FakeTmdb(object):
    def __init__(self, results, details=None):
        self.results = results        # {(kind, query): [result, ...]}
        self.details_by_id = details or {}
        self.searches = []
        self.requests = 0

    def search(self, kind, query, year=None):
        self.searches.append((kind, query, year))
        return self.results.get((kind, query), [])

    def details(self, kind, tmdb_id):
        return self.details_by_id.get(tmdb_id, {})


def movie(tmdb_id, title, year, original=None):
    return {"id": tmdb_id, "title": title, "original_title": original or title,
            "release_date": "%s-01-01" % year if year else ""}


class NormalizeTest(unittest.TestCase):
    def test_accents_case_punctuation(self):
        self.assertEqual(match.normalize("Hogyan tudnék élni nélküled?"), "hogyan tudnek elni nelkuled")
        self.assertEqual(match.normalize("  Café  Marylin – Extra "), "cafe marylin extra")

    def test_articles(self):
        self.assertIn("rozsa", match.title_forms("A rózsa"))
        self.assertIn("raven", match.title_forms("The Raven"))


class MatchTest(unittest.TestCase):
    def test_single_match_with_imdb(self):
        title = Title("f1", "movie", "Hogyan tudnék élni nélküled?", "How Could I Live Without You?", 2024, 6291)
        tmdb = FakeTmdb({("movie", "How Could I Live Without You?"): [movie(10, "Hogyan tudnék élni nélküled?", 2024,
                                                                            "Hogyan tudnék élni nélküled?")]},
                        {10: {"runtime": 105, "external_ids": {"imdb_id": "tt123456"}}})
        result = match.match(tmdb, title)
        self.assertEqual((result.status, result.tmdb_id, result.imdb), (match.MATCHED, 10, "tt123456"))
        self.assertEqual(tmdb.searches[0], ("movie", "How Could I Live Without You?", 2024))

    def test_year_outside_tolerance_is_rejected(self):
        title = Title("f1", "movie", "Aglaja", None, 2012, None)
        tmdb = FakeTmdb({("movie", "Aglaja"): [movie(1, "Aglaja", 2015)]})
        self.assertEqual(match.match(tmdb, title).status, match.NOT_FOUND)

    def test_extra_is_not_matched_to_the_feature_by_runtime(self):
        title = Title("x", "movie", "Moszkva tér", None, 2001, 600)  # a 10 minute extra
        tmdb = FakeTmdb({("movie", "Moszkva tér"): [movie(5, "Moszkva tér", 2001)]}, {5: {"runtime": 88}})
        result = match.match(tmdb, title)
        self.assertEqual((result.status, result.reason), (match.NOT_FOUND, "runtime differs"))

    def test_two_candidates_resolved_by_runtime(self):
        title = Title("f", "movie", "Szerelem", None, 1971, 5520)
        tmdb = FakeTmdb({("movie", "Szerelem"): [movie(1, "Szerelem", 1971), movie(2, "Szerelem", 1970)]},
                        {1: {"runtime": 92}, 2: {"runtime": 20}})
        self.assertEqual(match.match(tmdb, title).tmdb_id, 1)

    def test_two_candidates_without_runtime_are_ambiguous(self):
        title = Title("f", "movie", "Szerelem", None, 1971, None)
        tmdb = FakeTmdb({("movie", "Szerelem"): [movie(1, "Szerelem", 1971), movie(2, "Szerelem", 1970)]})
        self.assertEqual(match.match(tmdb, title).status, match.AMBIGUOUS)

    def test_no_year_and_several_results_is_ambiguous(self):
        title = Title("s", "tvshow", "Cella", None, None, None)
        tmdb = FakeTmdb({("tvshow", "Cella"): [{"id": 1, "name": "Cella", "first_air_date": "2023-01-01"},
                                                {"id": 2, "name": "Cellar", "first_air_date": "2010-01-01"}]})
        self.assertEqual(match.match(tmdb, title).status, match.AMBIGUOUS)

    def test_series_match(self):
        title = Title("s", "tvshow", "Aranybulla", None, 2022, None)
        tmdb = FakeTmdb({("tvshow", "Aranybulla"): [{"id": 77, "name": "Aranybulla", "original_name": "Aranybulla",
                                                      "first_air_date": "2022-03-01"}]},
                        {77: {"external_ids": {"imdb_id": "tt9999999"}}})
        result = match.match(tmdb, title)
        self.assertEqual((result.status, result.tmdb_id, result.imdb), (match.MATCHED, 77, "tt9999999"))

    def test_different_title_is_not_matched(self):
        title = Title("f", "movie", "Az ötödik pecsét", None, 1976, 6509)
        tmdb = FakeTmdb({("movie", "Az ötödik pecsét"): [movie(3, "The Sixth Seal", 1976)]})
        self.assertEqual(match.match(tmdb, title).status, match.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
