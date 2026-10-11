"""The mapping document (format version 1), as plugin.video.filmio reads it.

Consumer: plugin.video.filmio resources/lib/filmio/mapping.py. Keep both in sync.
"""
import json
import os
import re

FORMAT_VERSION = 1
TYPES = ("movie", "tvshow")
IMDB = re.compile(r"^tt\d{5,10}$")
RATINGS = ("imdbRating", "imdbVotes", "rottenTomatoes")  # in the order entry() takes them


def entry(kind, tmdb_id, imdb=None, rating=None, votes=None, tomatoes=None):
    """rating and votes are IMDb's and tomatoes (the Rotten Tomatoes
    percentage) is looked up by IMDb id, so they are only kept with one."""
    item = {"type": kind, "tmdb": int(tmdb_id)}
    if imdb and IMDB.match(imdb):
        item["imdb"] = imdb
        if rating is not None:
            item["imdbRating"] = rating
        if votes is not None:
            item["imdbVotes"] = votes
        if tomatoes is not None:
            item["rottenTomatoes"] = tomatoes
    return item


def validate(document):
    """Raise ValueError unless document is a valid version-1 mapping."""
    if not isinstance(document, dict) or document.get("version") != FORMAT_VERSION:
        raise ValueError("version must be %d" % FORMAT_VERSION)
    items = document.get("items")
    if not isinstance(items, dict):
        raise ValueError("items must be an object")
    for key, item in items.items():
        if not isinstance(key, str) or not key:
            raise ValueError("bad key %r" % key)
        if not isinstance(item, dict) or item.get("type") not in TYPES:
            raise ValueError("bad type for %s" % key)
        tmdb = item.get("tmdb")
        if isinstance(tmdb, bool) or not isinstance(tmdb, int) or tmdb <= 0:
            raise ValueError("bad tmdb id for %s" % key)
        if "imdb" in item and not (isinstance(item["imdb"], str) and IMDB.match(item["imdb"])):
            raise ValueError("bad imdb id for %s" % key)
        rating, votes = item.get("imdbRating"), item.get("imdbVotes")
        if "imdbRating" in item and (isinstance(rating, bool) or not isinstance(rating, (int, float))
                                     or not 0 <= rating <= 10):
            raise ValueError("bad imdb rating for %s" % key)
        if "imdbVotes" in item and (isinstance(votes, bool) or not isinstance(votes, int) or votes < 0):
            raise ValueError("bad imdb votes for %s" % key)
        tomatoes = item.get("rottenTomatoes")
        if "rottenTomatoes" in item and (isinstance(tomatoes, bool) or not isinstance(tomatoes, int)
                                         or not 0 <= tomatoes <= 100):
            raise ValueError("bad rotten tomatoes score for %s" % key)
        if set(item) & {"imdbRating", "imdbVotes", "rottenTomatoes"} and "imdb" not in item:
            raise ValueError("ratings without imdb id for %s" % key)
        if set(item) - {"type", "tmdb", "imdb", "imdbRating", "imdbVotes", "rottenTomatoes"}:
            raise ValueError("unknown fields for %s" % key)


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            document = json.load(fh)
    except FileNotFoundError:
        return {}
    validate(document)
    return document["items"]


def write(path, items, generated):
    document = {"version": FORMAT_VERSION, "generated": generated,
                "items": {k: items[k] for k in sorted(items)}}
    validate(document)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=0, separators=(",", ":"))
        fh.write("\n")
    os.replace(tmp, path)
    return document
