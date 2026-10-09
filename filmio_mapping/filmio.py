"""Reads the public Filmio catalogue (no account needed).

Endpoints as verified for the add-on (plugin.video.filmio, docs/feasibility.md §5):
- GET {CMS}/config -> data.app.search.searchCarouselId
- GET {CMS}/carousels/{id}?page&pageSize -> data[], meta.pagination.total
  (pageCount is wrong; page by total). The search carousel without a query
  lists the whole catalogue: MOVIE, SERIES, EPISODE and TAG items.
"""
from filmio_mapping import http

CMS = "https://cms-prod-filmio.connectmedia.hu/api"
PAGE_SIZE = 100


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class Title(object):
    """A film or series from the Filmio catalogue."""

    def __init__(self, filmio_id, kind, title, original_title=None, year=None, length=None):
        self.id = filmio_id
        self.kind = kind                    # "movie" or "tvshow"
        self.title = title
        self.original_title = original_title
        self.year = year if year and 1880 <= year <= 2100 else None
        self.length = length                # seconds, films only

    def __repr__(self):
        return "Title(%r, %r, %r, %r)" % (self.id, self.kind, self.title, self.year)


KINDS = {"MOVIE": "movie", "SERIES": "tvshow"}


def title_from(item):
    kind = KINDS.get((item or {}).get("type"))
    if not kind or not item.get("id") or not (item.get("title") or "").strip():
        return None
    return Title(item["id"], kind, item["title"].strip(),
                 (item.get("originalTitle") or "").strip() or None,
                 _int(item.get("year")), _int(item.get("length")))


def catalogue(get_json=http.get_json, limit=None, log=print):
    """All films and series, deduplicated by id."""
    config = get_json(CMS + "/config")
    carousel = (((config.get("data") or {}).get("app") or {}).get("search") or {}).get("searchCarouselId")
    if not carousel:
        raise RuntimeError("Filmio config has no search carousel")
    titles, page, total = {}, 1, None
    while total is None or (page - 1) * PAGE_SIZE < total:
        payload = get_json("%s/carousels/%s" % (CMS, carousel), [("page", page), ("pageSize", PAGE_SIZE)])
        total = ((payload.get("meta") or {}).get("pagination") or {}).get("total") or 0
        data = payload.get("data") or []
        if not data:
            break
        for item in data:
            title = title_from(item)
            if title:
                titles.setdefault(title.id, title)
        log("catalogue page %d: %d titles so far (of %d items)" % (page, len(titles), total))
        if limit and len(titles) >= limit:
            break
        page += 1
    result = sorted(titles.values(), key=lambda t: t.id)
    return result[:limit] if limit else result
