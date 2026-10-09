"""Matching rules: accept only unambiguous matches. A wrong id is worse than
none (it would put a wrong film into someone's Trakt history).

Pure functions; the TMDB access is passed in.
"""
import re
import unicodedata

MATCHED, AMBIGUOUS, NOT_FOUND = "matched", "ambiguous", "not_found"
YEAR_TOLERANCE = 1
ARTICLES = ("a ", "az ", "the ")


def normalize(text):
    """Case-, accent- and punctuation-insensitive form of a title."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = re.sub(r"[^0-9a-z]+", " ", text).strip()
    return text


def title_forms(*titles):
    forms = set()
    for title in titles:
        norm = normalize(title)
        if not norm:
            continue
        forms.add(norm)
        for article in ARTICLES:
            if norm.startswith(article):
                forms.add(norm[len(article):])
    return forms


def _year(date):
    try:
        return int((date or "")[:4])
    except ValueError:
        return None


class Candidate(object):
    def __init__(self, tmdb_id, names, year):
        self.id = tmdb_id
        self.names = names
        self.year = year

    @classmethod
    def from_result(cls, kind, result):
        if kind == "movie":
            names = (result.get("title"), result.get("original_title"))
            year = _year(result.get("release_date"))
        else:
            names = (result.get("name"), result.get("original_name"))
            year = _year(result.get("first_air_date"))
        return cls(result.get("id"), names, year)


class Result(object):
    def __init__(self, status, tmdb_id=None, imdb=None, reason="", candidates=()):
        self.status = status
        self.tmdb_id = tmdb_id
        self.imdb = imdb
        self.reason = reason
        self.candidates = list(candidates)


def runtime_ok(filmio_seconds, tmdb_minutes):
    """None when either is unknown; otherwise whether the lengths agree
    (within 10%, at least 5 minutes). Keeps extras and shorts away from the
    feature film of the same name."""
    if not filmio_seconds or not tmdb_minutes:
        return None
    filmio_minutes = filmio_seconds / 60.0
    return abs(filmio_minutes - tmdb_minutes) <= max(5.0, 0.10 * tmdb_minutes)


def candidates_for(tmdb, title):
    """Search by original title and by title, with the year when known."""
    seen, found = set(), []
    queries = [q for q in (title.original_title, title.title) if q]
    for query in queries:
        for result in tmdb.search(title.kind, query, title.year):
            cand = Candidate.from_result(title.kind, result)
            if cand.id and cand.id not in seen:
                seen.add(cand.id)
                found.append(cand)
    return found


def match(tmdb, title):
    forms = title_forms(title.title, title.original_title)
    candidates = candidates_for(tmdb, title)
    plausible = []
    for cand in candidates:
        if not (title_forms(*cand.names) & forms):
            continue
        if title.year and (cand.year is None or abs(cand.year - title.year) > YEAR_TOLERANCE):
            continue
        plausible.append(cand)
    summary = ["%s %s (%s)" % (c.id, c.names[0], c.year) for c in candidates[:5]]
    if not plausible:
        return Result(NOT_FOUND, reason="no title/year match", candidates=summary)

    details = {c.id: tmdb.details(title.kind, c.id) for c in plausible}
    if title.kind == "movie":
        checked = [(c, runtime_ok(title.length, details[c.id].get("runtime"))) for c in plausible]
        if any(ok is False for _, ok in checked):
            plausible = [c for c, ok in checked if ok is not False]
            if not plausible:
                return Result(NOT_FOUND, reason="runtime differs", candidates=summary)
        if len(plausible) > 1:
            confirmed = [c for c, ok in checked if ok is True and c in plausible]
            if len(confirmed) == 1:
                plausible = confirmed
    if len(plausible) > 1:
        return Result(AMBIGUOUS, reason="%d candidates" % len(plausible), candidates=summary)
    if title.year is None and len(candidates) > 1:
        return Result(AMBIGUOUS, reason="no year to tell candidates apart", candidates=summary)

    chosen = plausible[0]
    imdb = ((details[chosen.id].get("external_ids") or {}).get("imdb_id")) or None
    return Result(MATCHED, chosen.id, imdb, candidates=summary)
