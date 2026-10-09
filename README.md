# filmio-mapping

Maps titles of the Hungarian streaming service [Filmio](https://filmio.hu/) to their [TMDB](https://www.themoviedb.org/) and IMDb ids. The data file is read by an unofficial, personal Kodi add-on (plugin.video.filmio), so that films and series played through it can be recognised, for example by the Trakt scrobbler.

Not affiliated with or endorsed by Filmio, Nemzeti Filmintézet, TMDB or IMDb.

> This product uses the TMDB API but is not endorsed or certified by TMDB.

## Data

`data/mapping.json` (format version 1):

```json
{
  "version": 1,
  "generated": "2026-10-09T12:00:00Z",
  "items": {
    "<filmio id>": {"type": "movie",  "tmdb": 123, "imdb": "tt0123456"},
    "<filmio id>": {"type": "tvshow", "tmdb": 456}
  }
}
```

- `<filmio id>` is the id of a film or series in Filmio's public catalogue.
- The file contains ids only; no TMDB metadata is copied.
- Only unambiguous matches are included. A missing title is preferred over a wrong one.

## How it is built

`generate.py`:
1. reads Filmio's public catalogue (films and series, no account needed),
2. searches TMDB by original title and title, using the year when known,
3. accepts a match only if the title and year agree and exactly one candidate remains (for films the runtime must agree too),
4. writes `data/mapping.json` and a `report.md` listing new, ambiguous and unmatched titles.

`overrides.json` holds manual corrections and always wins. An existing entry is never replaced automatically.

```sh
export TMDB_READ_TOKEN=...          # TMDB API read access token (or TMDB_API_KEY)
python3 generate.py --limit 50      # try a few titles
python3 generate.py                 # full catalogue
python3 -m unittest discover -s tests -t .
```

The GitHub Actions workflow (`.github/workflows/update.yml`) runs the same steps and commits the mapping when it changes. It runs weekly (Monday 04:00 UTC) and can be started manually. The TMDB credential is a repository secret (`TMDB_READ_TOKEN`) and never part of the repository.

Standard library only, Python 3.8+.
