"""TMDB v3 client with an optional on-disk response cache.

Credentials come from the environment, never from the repository:
- TMDB_API_KEY:    v3 API key (sent as the api_key query parameter; preferred), or
- TMDB_READ_TOKEN: API read access token (v4 style, sent as a Bearer header).
"""
import hashlib
import json
import os
import time

from filmio_mapping import http

API = "https://api.themoviedb.org/3"


class Tmdb(object):
    def __init__(self, read_token=None, api_key=None, cache_dir=None, get_json=http.get_json,
                 min_interval=0.03, clock=time.monotonic, sleep=time.sleep):
        if not read_token and not api_key:
            raise ValueError("set TMDB_API_KEY (or TMDB_READ_TOKEN)")
        self.read_token = read_token
        self.api_key = api_key
        self.cache_dir = cache_dir
        self._get_json = get_json
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._last = 0.0
        self.requests = 0

    @classmethod
    def from_env(cls, cache_dir=None):
        return cls(os.environ.get("TMDB_READ_TOKEN"), os.environ.get("TMDB_API_KEY"), cache_dir)

    def _cache_path(self, path, params):
        if not self.cache_dir:
            return None
        key = json.dumps([path, sorted(params)], ensure_ascii=False)
        return os.path.join(self.cache_dir, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")

    def get(self, path, **params):
        params = [(k, v) for k, v in params.items() if v is not None]
        cache = self._cache_path(path, params)
        if cache and os.path.exists(cache):
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)
        wait = self.min_interval - (self.clock() - self._last)
        if wait > 0:
            self.sleep(wait)
        headers, query = {}, list(params)
        if self.api_key:
            query.append(("api_key", self.api_key))
        else:
            headers["Authorization"] = "Bearer " + self.read_token
        try:
            data = self._get_json(API + path, query, headers=headers)
        except http.HttpError as exc:
            if exc.status != 404:
                raise
            data = None
        self._last = self.clock()
        self.requests += 1
        if cache:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        return data

    def search(self, kind, query, year=None):
        if kind == "movie":
            data = self.get("/search/movie", query=query, year=year, language="hu-HU", include_adult="false")
        else:
            data = self.get("/search/tv", query=query, first_air_date_year=year, language="hu-HU",
                            include_adult="false")
        return (data or {}).get("results") or []

    def details_or_none(self, kind, tmdb_id):
        """Details with external ids; None if TMDB no longer has the title."""
        path = "/movie/%d" % tmdb_id if kind == "movie" else "/tv/%d" % tmdb_id
        return self.get(path, append_to_response="external_ids", language="hu-HU")

    def details(self, kind, tmdb_id):
        return self.details_or_none(kind, tmdb_id) or {}
