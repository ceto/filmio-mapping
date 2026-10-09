#!/usr/bin/env python3
"""Build data/mapping.json (Filmio id -> TMDB/IMDb ids) and a review report.

    TMDB_API_KEY=... python3 generate.py [--limit N] [--refresh]

Rules:
- overrides.json always wins ({"tmdb": null} means "never map this title").
- Entries from the previous mapping are kept as they are; only new titles
  are searched (use --refresh to re-check, which still never replaces an
  existing entry, it only reports disagreements).
- Only unambiguous matches are added (filmio_mapping/match.py).
- Titles that left the catalogue are dropped, unless the catalogue looks
  incomplete (fewer than 90% of the previously mapped titles still present).
- Every run re-reads the IMDb id of every mapped title (TMDB data must not be
  kept longer than 6 months) and drops titles TMDB no longer has (overrides
  excepted).
"""
import argparse
import datetime
import json
import os
import sys

from filmio_mapping import filmio, match, output, tmdb as tmdb_module

HERE = os.path.dirname(os.path.abspath(__file__))


def load_overrides(path):
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    overrides = {}
    for filmio_id, value in raw.items():
        if filmio_id.startswith("_"):
            continue  # comments
        if value is None or value.get("tmdb") is None:
            overrides[filmio_id] = None
        else:
            overrides[filmio_id] = output.entry(value["type"], value["tmdb"], value.get("imdb"))
    return overrides


def build(titles, previous, overrides, tmdb, refresh=False, log=print):
    items, report = {}, {"matched": [], "kept": [], "override": [], "excluded": [],
                         "ambiguous": [], "not_found": [], "disagreements": []}
    for i, title in enumerate(titles, 1):
        if title.id in overrides:
            if overrides[title.id] is None:
                report["excluded"].append(title)
            else:
                items[title.id] = overrides[title.id]
                report["override"].append(title)
            continue
        old = previous.get(title.id)
        if old and not refresh:
            items[title.id] = old
            report["kept"].append(title)
            continue
        result = match.match(tmdb, title)
        if old:
            items[title.id] = old
            report["kept"].append(title)
            if result.status == match.MATCHED and result.tmdb_id != old["tmdb"]:
                report["disagreements"].append((title, old["tmdb"], result.tmdb_id))
        elif result.status == match.MATCHED:
            items[title.id] = output.entry(title.kind, result.tmdb_id, result.imdb)
            report["matched"].append((title, result))
        else:
            report[result.status].append((title, result))
        if i % 50 == 0:
            log("%d/%d titles, %d TMDB requests" % (i, len(titles), tmdb.requests))
    refresh_details(items, overrides, tmdb, report, log)
    return items, report


def refresh_details(items, overrides, tmdb, report, log=print):
    """Re-read the IMDb id of every mapped title from TMDB."""
    report.setdefault("removed", [])
    for n, filmio_id in enumerate(sorted(items), 1):
        item = items[filmio_id]
        override = overrides.get(filmio_id)
        info = tmdb.details_or_none(item["type"], item["tmdb"])
        if info is None:
            if override:
                continue  # trust the manual entry
            report["removed"].append((filmio_id, item["tmdb"]))
            del items[filmio_id]
            continue
        imdb = (info.get("external_ids") or {}).get("imdb_id") or (override or {}).get("imdb") or item.get("imdb")
        items[filmio_id] = output.entry(item["type"], item["tmdb"], imdb)
        if n % 100 == 0:
            log("refreshed %d/%d, %d TMDB requests" % (n, len(items), tmdb.requests))


def write_report(path, titles, report, items):
    def line(title):
        return "%s | %s | %s | %s" % (title.id, title.kind, title.title, title.year or "?")
    out = ["# Mapping report", "",
           "Generated: %s" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "",
           "| | count |", "|---|---|",
           "| catalogue titles | %d |" % len(titles),
           "| mapped (total) | %d |" % len(items),
           "| of which new with a different year | %d |" % sum(1 for _, r in report["matched"] if r.year_relaxed)]
    for key in ("matched", "kept", "override", "excluded", "ambiguous", "not_found", "disagreements", "removed"):
        out.append("| %s | %d |" % (key, len(report.get(key, []))))
    relaxed = [(t, r) for t, r in report["matched"] if r.year_relaxed]
    out += ["", "## New matches with a different year (please check these)", ""]
    out += ["- %s -> tmdb %s%s: %s" % (line(t), r.tmdb_id, " / " + r.imdb if r.imdb else "", r.reason)
            for t, r in relaxed]
    out += ["", "## New matches (please spot-check)", ""]
    out += ["- %s -> tmdb %s%s" % (line(t), r.tmdb_id, " / " + r.imdb if r.imdb else "")
            for t, r in report["matched"] if not r.year_relaxed]
    out += ["", "## Ambiguous (candidates for overrides.json)", ""]
    out += ["- %s: %s; %s" % (line(t), r.reason, "; ".join(r.candidates)) for t, r in report["ambiguous"]]
    out += ["", "## Disagreements with the existing mapping", ""]
    out += ["- %s: mapped %s, search now says %s" % (line(t), old, new) for t, old, new in report["disagreements"]]
    out += ["", "## Removed (TMDB no longer has them)", ""]
    out += ["- %s: tmdb %s" % (fid, tid) for fid, tid in report.get("removed", [])]
    out += ["", "## Not found", ""]
    out += ["- %s: %s" % (line(t), r.reason) for t, r in report["not_found"]]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=os.path.join(HERE, "data", "mapping.json"))
    parser.add_argument("--report", default=os.path.join(HERE, "report.md"))
    parser.add_argument("--overrides", default=os.path.join(HERE, "overrides.json"))
    parser.add_argument("--cache", default=os.path.join(HERE, ".cache", "tmdb"),
                        help="TMDB response cache ('' to disable)")
    parser.add_argument("--limit", type=int, help="only the first N titles (for trying things out)")
    parser.add_argument("--refresh", action="store_true", help="re-check existing entries (report only)")
    args = parser.parse_args(argv)

    tmdb = tmdb_module.Tmdb.from_env(cache_dir=args.cache or None)
    previous = output.load(args.out)
    overrides = load_overrides(args.overrides)
    titles = filmio.catalogue(limit=args.limit)
    print("catalogue: %d films and series" % len(titles))

    present = {t.id for t in titles}
    if not args.limit and previous and len(present & set(previous)) < 0.9 * len(previous):
        print("catalogue looks incomplete (%d of %d mapped titles present); not writing"
              % (len(present & set(previous)), len(previous)), file=sys.stderr)
        return 2

    items, report = build(titles, previous, overrides, tmdb, refresh=args.refresh)
    if args.limit:
        # A partial run must not drop the rest of an existing mapping.
        items = dict(previous, **items)
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if items != previous:
        output.write(args.out, items, generated)
        print("wrote %s (%d entries)" % (args.out, len(items)))
    else:
        print("mapping unchanged (%d entries)" % len(items))
    write_report(args.report, titles, report, items)
    print("report: %s; TMDB requests: %d" % (args.report, tmdb.requests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
