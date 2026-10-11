# filmio-mapping

Maps titles of the Hungarian streaming service [Filmio](https://filmio.hu/) to their [TMDB](https://www.themoviedb.org/) and IMDb ids, with the IMDb rating and vote count and the Rotten Tomatoes score. The data file is read by an unofficial, personal Kodi add-on (plugin.video.filmio), so that films and series played through it can be recognised, for example by the Trakt scrobbler.

Not affiliated with or endorsed by Filmio, Nemzeti Filmintézet, TMDB, IMDb or OMDb.

> This product uses the TMDB API but is not endorsed or certified by TMDB.

IMDb ratings, vote counts and Rotten Tomatoes scores come from the [OMDb API](https://www.omdbapi.com/) (CC BY-NC 4.0).

## Data

`data/mapping.json` (format version 1):

```json
{
  "version": 1,
  "generated": "2026-10-09T12:00:00Z",
  "items": {
    "<filmio id>": {"type": "movie",  "tmdb": 123, "imdb": "tt0123456", "imdbRating": 7.8, "imdbVotes": 12345, "rottenTomatoes": 85},
    "<filmio id>": {"type": "tvshow", "tmdb": 456}
  }
}
```

- `<filmio id>` is the id of a film or series in Filmio's public catalogue.
- `imdb`, `imdbRating`, `imdbVotes` and `rottenTomatoes` (the Tomatometer, in percent) are optional. The last three are only present with an `imdb` id, and only for titles that have them.
- Apart from the ids and these ratings, nothing is copied: no TMDB metadata or images.
- Every run re-reads the TMDB data of all mapped titles, so nothing in the file is older than one run (TMDB terms: no caching beyond 6 months). Titles TMDB no longer has are dropped.
- Every run also re-reads the ratings from OMDb. If OMDb cannot be asked (no key, daily request limit), the previous values stay.
- Only unambiguous matches are included. A missing title is preferred over a wrong one.

## How it is built

`generate.py`:
1. reads Filmio's public catalogue (films and series, no account needed),
2. searches TMDB by original title and title, using the year when known,
3. accepts a match only if the title and year agree and exactly one candidate remains (for films the runtime must agree too),
4. looks up the IMDb rating and vote count and the Rotten Tomatoes score of every title with an IMDb id in OMDb,
5. writes `data/mapping.json` and a `report.md` listing new, ambiguous and unmatched titles.

`overrides.json` holds manual corrections and always wins. An existing entry is never replaced automatically.

```sh
export TMDB_API_KEY=...             # TMDB v3 API key (or TMDB_READ_TOKEN)
export OMDB_API_KEY=...             # OMDb API key (optional; without it ratings are not refreshed)
python3 generate.py --limit 50      # try a few titles
python3 generate.py                 # full catalogue
python3 -m unittest discover -s tests -t .
```

The GitHub Actions workflow (`.github/workflows/update.yml`) runs the same steps and commits the mapping when it changes. It runs weekly (Monday 04:00 UTC) and can be started manually. The credentials are repository secrets (`TMDB_API_KEY`, `OMDB_API_KEY`) and never part of the repository. OMDb's free key allows 1000 requests a day; a run needs one per title with an IMDb id.

Standard library only, Python 3.8+.
