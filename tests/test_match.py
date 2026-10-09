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
        self.assertEqual(tmdb.searches[:2], [("movie", "How Could I Live Without You?", 2024),
                                             ("movie", "How Could I Live Without You?", None)])

    def test_year_outside_tolerance_is_rejected(self):
        title = Title("f1", "movie", "Aglaja", None, 2012, None)
        tmdb = FakeTmdb({("movie", "Aglaja"): [movie(1, "Aglaja", 2015)]})
        self.assertEqual(match.match(tmdb, title).status, match.NOT_FOUND)

    def test_production_vs_release_year_within_tolerance(self):
        # Filmio gives the production year; TMDB's year filter is exact, so only
        # the search without a year finds it.
        title = Title("f", "movie", "Szegénylegények", "The Round-Up", 1965, 5248)

        class YearStrict(FakeTmdb):
            def search(self, kind, query, year=None):
                self.searches.append((kind, query, year))
                return [] if year else self.results.get((kind, query), [])
        tmdb = YearStrict({("movie", "Szegénylegények"): [movie(94663, "Szegénylegények", 1966)]},
                          {94663: {"runtime": 87}})
        result = match.match(tmdb, title)
        self.assertEqual((result.status, result.tmdb_id, result.year_relaxed), (match.MATCHED, 94663, False))
        self.assertIn(("movie", "Szegénylegények", None), tmdb.searches)

    def test_late_premiere_accepted_only_with_runtime(self):
        title = Title("f", "movie", "A tanú", "The Witness", 1969, 6285)
        results = {("movie", "A tanú"): [movie(40987, "A tanú", 1979), movie(2149, "A tanú teste", 1993)]}
        result = match.match(FakeTmdb(results, {40987: {"runtime": 105, "external_ids": {"imdb_id": "tt0079985"}}}), title)
        self.assertEqual((result.status, result.tmdb_id, result.year_relaxed), (match.MATCHED, 40987, True))
        no_runtime = match.match(FakeTmdb(results, {40987: {}}), title)
        self.assertEqual(no_runtime.status, match.NOT_FOUND)
        wrong_runtime = match.match(FakeTmdb(results, {40987: {"runtime": 60}}), title)
        self.assertEqual(wrong_runtime.status, match.NOT_FOUND)

    def test_late_premiere_ignores_generic_english_title(self):
        title = Title("f", "movie", "A tanú", "The Witness", 1969, 6285)
        results = {("movie", "The Witness"): [movie(40987, "A tanú", 1979), movie(1, "The Witness", 2019),
                                              movie(2, "The Witness", 1992)]}
        result = match.match(FakeTmdb(results, {40987: {"runtime": 108}}), title)
        self.assertEqual((result.status, result.tmdb_id), (match.MATCHED, 40987))

    def test_dubbed_version_maps_to_the_original_work(self):
        self.assertEqual(match.base_title("HUNYADI - szinkronos változat"), "HUNYADI")
        self.assertEqual(match.base_title("Valami (szinkronos változat)"), "Valami")
        self.assertEqual(match.base_title("Szinkron"), "Szinkron")
        title = Title("s", "tvshow", "HUNYADI - szinkronos változat", None, 2024, None)
        tmdb = FakeTmdb({("tvshow", "HUNYADI"): [{"id": 271050, "name": "Hunyadi", "first_air_date": "2025-03-01"}]})
        result = match.match(tmdb, title)
        self.assertEqual((result.status, result.tmdb_id), (match.MATCHED, 271050))

    def test_late_premiere_needs_a_known_year_within_limit(self):
        title = Title("f", "movie", "Ünnepeink", None, 1981, 3000)
        far = FakeTmdb({("movie", "Ünnepeink"): [movie(1, "Ünnepeink", 2011)]}, {1: {"runtime": 50}})
        self.assertEqual(match.match(far, title).status, match.NOT_FOUND)
        unknown = FakeTmdb({("movie", "Ünnepeink"): [movie(1, "Ünnepeink", None)]}, {1: {"runtime": 50}})
        self.assertEqual(match.match(unknown, title).status, match.NOT_FOUND)

    def test_native_original_title_breaks_a_tie(self):
        title = Title("f", "movie", "A vizsga", "The Exam", 2011, None)
        tmdb = FakeTmdb({("movie", "The Exam"): [movie(980356, "The Exam", 2011), movie(84093, "A vizsga", 2011)]},
                        {84093: {"external_ids": {"imdb_id": "tt1912996"}}})
        self.assertEqual(match.match(tmdb, title).tmdb_id, 84093)

    def test_two_native_titles_stay_ambiguous(self):
        title = Title("f", "movie", "Sarajevo", None, 1940, None)
        tmdb = FakeTmdb({("movie", "Sarajevo"): [movie(1, "Sarajevo", 1940), movie(2, "Sarajevo", 1940)]})
        self.assertEqual(match.match(tmdb, title).status, match.AMBIGUOUS)

    def test_late_premiere_not_accepted_with_two_same_titled_candidates(self):
        title = Title("f", "movie", "Lúdas Matyi", None, 1990, 4194)
        tmdb = FakeTmdb({("movie", "Lúdas Matyi"): [movie(1, "Lúdas Matyi", 1977), movie(2, "Lúdas Matyi", 1950)]},
                        {1: {"runtime": 70}, 2: {"runtime": 70}})
        self.assertEqual(match.match(tmdb, title).status, match.NOT_FOUND)

    def test_series_year_is_never_relaxed(self):
        title = Title("s", "tvshow", "BP Underground", None, 2017, None)
        tmdb = FakeTmdb({("tvshow", "BP Underground"): [{"id": 1, "name": "BP Underground", "first_air_date": "2023-01-01"}]})
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
