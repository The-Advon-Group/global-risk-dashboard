"""Run every collector, reconcile to ISO codes, validate, snapshot.

Usage:
    python pipeline.py                 # full run, writes a snapshot + latest.json
    python pipeline.py --sources ca,uk # subset
    python pipeline.py --dry-run       # collect and report, write nothing
    python pipeline.py --refresh-fr-slugs

Failure policy, per the plan:
  * A source that cannot be reached does not fail the run. Its column carries
    the last known value from the previous snapshot with an ageing timestamp,
    and falls to Unrated once past STALENESS_HOURS.
  * A source that returns implausibly little data fails loudly instead of
    publishing a partial column.
  * Nothing is ever rendered as "undefined". A value is either present, or
    explicitly Unrated with a stated reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collectors import canada, france, japan, uk, us
from collectors.base import CollectorError, Record, get, utcnow
from countries import SHARED_PAGE_NOTE, Spine, resolve_all, roll_up
from headline import apply_to_row
from report import format_report
from validate import validate
from western import apply_to_row as western_column

ROOT = Path(__file__).resolve().parent
SNAPSHOTS = ROOT / "snapshots"
DATA = ROOT / "data"
LATEST = DATA / "latest.json"

# How long a source's last known value stays publishable once the source itself
# has stopped answering.
STALENESS_HOURS = {"us": 24, "uk": 24, "ca": 24, "fr": 72, "jp": 72}

SOURCES = {
    "ca": ("Canada", canada.collect),
    "uk": ("United Kingdom", uk.collect),
    "us": ("United States", us.collect),
    "fr": ("France", france.collect),
    "jp": ("Japan", japan.collect),
}

# Minimum destinations a source must return before we will publish its column.
MIN_EXPECTED = {"ca": 150, "uk": 150, "us": 150, "fr": 100, "jp": 0}

# Read from the collectors rather than restated here, so a source that changes
# what it publishes changes this in one place.
NATIONAL_LEVEL_STATED = {
    "ca": canada.PUBLISHES_NATIONAL_LEVEL,
    "uk": uk.PUBLISHES_NATIONAL_LEVEL,
    "us": us.PUBLISHES_NATIONAL_LEVEL,
    "fr": france.PUBLISHES_NATIONAL_LEVEL,
    "jp": getattr(japan, "PUBLISHES_NATIONAL_LEVEL", True),
}


def _load_previous() -> dict:
    if LATEST.exists():
        try:
            return json.loads(LATEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _age_hours(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def collect_all(selected: list[str]) -> tuple[dict[str, list[Record]], dict[str, dict]]:
    results: dict[str, list[Record]] = {}
    status: dict[str, dict] = {}

    for key in selected:
        label, fn = SOURCES[key]
        try:
            records = fn()
        except CollectorError as exc:
            status[key] = {"ok": False, "error": str(exc), "count": 0}
            results[key] = []
            print(f"  {key}: FAILED - {exc}", file=sys.stderr)
            continue

        floor = MIN_EXPECTED.get(key, 0)
        if floor and len(records) < floor:
            status[key] = {
                "ok": False,
                "error": f"only {len(records)} records, expected at least {floor}",
                "count": len(records),
            }
            results[key] = []
            print(f"  {key}: REFUSED partial column ({len(records)} < {floor})", file=sys.stderr)
            continue

        results[key] = records
        status[key] = {"ok": True, "count": len(records), "error": None}
        print(f"  {key}: {len(records)} records")

    return results, status


def build_spine(records: dict[str, list[Record]]) -> Spine:
    """Canada's bilingual feed is the spine; other sources extend it."""
    try:
        payload = get(canada.INDEX).json()
        spine = Spine.from_canada(payload)
    except CollectorError:
        spine = Spine()
        print("  spine: Canada unavailable, falling back to names seen in other sources",
              file=sys.stderr)

    if not spine.by_iso:
        for recs in records.values():
            for rec in recs:
                if rec.iso2:
                    spine.add(rec.iso2, rec.raw_name)
    return spine


def reconcile(records: dict[str, list[Record]], spine: Spine) -> tuple[dict, list[dict]]:
    countries: dict[str, dict] = {}
    unmapped: list[dict] = []

    for source, recs in records.items():
        for rec in recs:
            # resolve_all, not resolve: a handful of source pages cover several
            # countries at once, and each one has to receive the record.
            for res in resolve_all(rec.raw_name, spine, supplied_iso2=rec.iso2):
                if res.iso2 is None:
                    unmapped.append(
                        {"source": source, "name": rec.raw_name, "reason": res.note}
                    )
                    continue

                rec.iso2 = res.iso2
                row = countries.setdefault(
                    res.iso2,
                    {
                        "iso2": res.iso2,
                        "name": spine.by_iso.get(res.iso2, rec.raw_name),
                        "sources": {},
                    },
                )
                bucket = row["sources"].setdefault(
                    source, {"records": [], "level": None}
                )
                entry = rec.as_dict()
                entry["match_method"] = res.method
                if res.note:
                    entry.setdefault("notes", []).append(res.note)
                shared = SHARED_PAGE_NOTE.get((source, res.iso2))
                if shared:
                    entry.setdefault("notes", []).append(shared)
                bucket["records"].append(entry)

    for row in countries.values():
        for source, bucket in row["sources"].items():
            # The highest-region roll-up is computed first and kept as
            # `country_high`; `apply_to_row` then overwrites `level` with the
            # capital-city figure and attaches the caveat.
            levels = [r.get("level") for r in bucket["records"]]
            bucket["level"] = roll_up(levels)
            # Whether that roll-up is the source's own country-wide figure or
            # purely ours. France publishes zones and no national level, and
            # treating our worst-zone roll-up as France's verdict is what put
            # fifty countries on level 4 in run #5.
            bucket["national_stated"] = NATIONAL_LEVEL_STATED.get(source, True)
            bucket["regional"] = any(r.get("region") for r in bucket["records"])
            bucket["url"] = bucket["records"][0].get("url")
            bucket["source_updated"] = bucket["records"][0].get("source_updated")
            bucket["retrieved_at"] = bucket["records"][0].get("retrieved_at")
        apply_to_row(row)
        western_column(row)

    return countries, unmapped


def carry_forward(countries: dict, status: dict, previous: dict) -> list[dict]:
    """Hold last known values for failed sources; age them out honestly."""
    notices: list[dict] = []
    prev_countries = (previous.get("countries") or {})

    for key, state in status.items():
        if state.get("ok"):
            continue
        limit = STALENESS_HOURS.get(key, 24)
        carried = aged = 0
        for iso2, row in countries.items():
            old = (prev_countries.get(iso2) or {}).get("sources", {}).get(key)
            if not old:
                continue
            age = _age_hours(old.get("retrieved_at"))
            if age is not None and age > limit:
                aged += 1
                continue
            carried_entry = dict(old)
            carried_entry["stale"] = True
            carried_entry["stale_hours"] = round(age, 1) if age is not None else None
            carried_entry["stale_reason"] = state.get("error")
            row["sources"][key] = carried_entry
            carried += 1
        notices.append(
            {
                "source": key,
                "error": state.get("error"),
                "carried_forward": carried,
                "dropped_as_stale": aged,
                "staleness_limit_hours": limit,
            }
        )
    return notices


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="ca,uk,us,fr,jp")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-fr-slugs", action="store_true")
    args = parser.parse_args()

    if args.refresh_fr_slugs:
        print("Rebuilding France slug map...")
        mapping = france.discover_slugs()
        print(f"  resolved {len(mapping)} countries")
        return 0

    selected = [s.strip() for s in args.sources.split(",") if s.strip() in SOURCES]
    started = utcnow()

    print(f"Collecting from: {', '.join(selected)}")
    records, status = collect_all(selected)

    spine = build_spine(records)
    print(f"Spine: {len(spine.by_iso)} canonical countries")

    countries, unmapped = reconcile(records, spine)

    previous = _load_previous()
    notices = carry_forward(countries, status, previous)

    report = validate(countries, status, unmapped, selected)

    # Probed on every run, including dry runs, because it is the one thing that
    # can change without anybody editing code: a route State currently refuses
    # may start answering, and nobody would notice by hand.
    probe = us.probe_us_routes() if "us" in selected else None

    # Only worth asking once a route is known to answer, and only while the
    # US collector is broken - once the column is rebuilt this stops being a
    # question and the flag can go.
    shape = None
    if probe and (probe.get("_summary") or {}).get("open") and not status.get("us", {}).get("ok"):
        shape = us.probe_us_shape()

    snapshot = {
        "run_started": started,
        "run_finished": utcnow(),
        "sources_requested": selected,
        "source_status": status,
        "carry_forward": notices,
        "state_api_probe": probe,
        "state_route_shape": shape,
        "japan_status": japan.STATUS,
        "validation": report,
        "countries": countries,
    }

    print()
    print(
        format_report(
            report,
            status,
            spine_size=len(spine.by_iso),
            probe=probe,
            japan=japan.STATUS,
            shape=shape,
        )
    )

    if args.dry_run:
        # The snapshot is still built, so write it beside the run rather than
        # throwing it away. It is NOT in `data/` or `snapshots/`, so the commit
        # step never sees it; the workflow uploads it as a run artifact instead.
        # That gives the page something real to be built against without
        # publishing anything.
        out = ROOT / "run-snapshot.json"
        out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"DRY RUN - nothing committed; snapshot written to {out.name} "
              f"({out.stat().st_size // 1024} KB)")
        return 0 if not report["blocking"] else 1

    stamp = datetime.now(timezone.utc)
    out_dir = SNAPSHOTS / stamp.strftime("%Y") / stamp.strftime("%m")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    DATA.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Snapshot: {path.relative_to(ROOT)}")
    return 1 if report["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
