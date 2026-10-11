"""OMDb client: IMDb rating and vote count and Rotten Tomatoes score by IMDb id.

The credential comes from the environment, never from the repository:
- OMDB_API_KEY: OMDb API key (sent as the apikey query parameter).

The free key allows 1000 requests a day; once the limit is reached OMDb
answers 401, which get_json raises as http.HttpError.
"""
import os

from filmio_mapping import http

API = "https://www.omdbapi.com/"


class Omdb(object):
    def __init__(self, api_key, get_json=http.get_json):
        if not api_key:
            raise ValueError("set OMDB_API_KEY")
        self.api_key = api_key
        self._get_json = get_json
        self.requests = 0

    @classmethod
    def from_env(cls):
        """A client, or None if OMDB_API_KEY is not set."""
        key = os.environ.get("OMDB_API_KEY")
        return cls(key) if key else None

    def ratings(self, imdb_id):
        """(IMDb rating, IMDb votes, Rotten Tomatoes percentage) of a title,
        each None if there is none; None if OMDb does not know the title or
        could not answer."""
        data = self._get_json(API, [("i", imdb_id), ("apikey", self.api_key)])
        self.requests += 1
        if not isinstance(data, dict) or data.get("Response") != "True":
            return None
        tomatoes = [r.get("Value") for r in data.get("Ratings") or []
                    if isinstance(r, dict) and r.get("Source") == "Rotten Tomatoes"]
        return (_number(data.get("imdbRating"), float), _number(data.get("imdbVotes"), int),
                _number(tomatoes[0], int) if tomatoes else None)


def _number(value, kind):
    """"7.8" -> 7.8, "12,345" -> 12345, "85%" -> 85, "N/A" -> None."""
    try:
        number = kind(str(value).replace(",", "").rstrip("%"))
    except ValueError:
        return None
    return number if number >= 0 else None
