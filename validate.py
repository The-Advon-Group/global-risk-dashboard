"""Load-time validation.

The 13-country dashboard renders the word "undefined" when a field is missing.
That defect is on its cleanup list, and the point of this module is that this
build never inherits it. The rule here is simple: every cell is either a real
value, or Unrated with a stated reason. There is no third state, and a missing
field is a validation finding rather than something the page discovers at
render time.

`blocking` findings should stop a publish. Everything else is reported and
shipped, because a dashboard that refuses to render because Vanuatu is missing
is worse than one that says Vanuatu is Unrated.
"""

from __future__ import annotations

from collections import Counter

# Sources needed before the composite can be scored at all (plan, Phase 2).
COMPOSITE_MINIMUM = 3

# Japan is deferred until after beta, so the denominator is four, not five.
# Imported from the collector so restoring Japan stays a one-line change.
from collectors.japan import ACTIVE_SOURCE_COUNT as ACTIVE_SOURCES

REQUIRED_FIELDS = ("iso2", "name")
REQUIRED_SOURCE_FIELDS = ("url", "retrieved_at")


def _is_provisional(bucket: dict) -> bool:
    """Is this cell a real reading, or a placeholder standing in for one?

    The FCDO issues an advise-against alert for a minority of countries. For the
    rest it says nothing we can grade, and `collectors/uk.py` fills the gap with
    a provisional level 1 pending the Phase 2 phrase ladder, which is what
    separates "nothing to flag here" from "be careful here". A cell like that
    looks identical to a confident level 1 on the page, and it is not one.

    Counting them is the point: a column that is mostly placeholder is a
    different product from one that is mostly readings, and nobody should have
    to guess which we have.
    """
    for record in bucket.get("records") or []:
        haystack = " ".join(
            [str(record.get("level_basis") or "")] +
            [str(note) for note in (record.get("notes") or [])]
        ).lower()
        if "provisional" in haystack or "not yet applied" in haystack:
            return True
    return False


def validate(
    countries: dict,
    status: dict,
    unmapped: list[dict],
    selected: list[str],
) -> dict:
    findings: list[dict] = []
    summary: list[str] = []

    working = [k for k, v in status.items() if v.get("ok")]
    failed = [k for k, v in status.items() if not v.get("ok")]

    if not countries:
        findings.append(
            {
                "level": "blocking",
                "code": "no_countries",
                "detail": "reconciliation produced zero countries",
            }
        )

    if len(working) < COMPOSITE_MINIMUM:
        findings.append(
            {
                "level": "warning",
                "code": "below_composite_minimum",
                "detail": (
                    f"only {len(working)} of {ACTIVE_SOURCES} sources returned usable data "
                    f"({', '.join(working) or 'none'}); the terrorism composite "
                    f"needs {COMPOSITE_MINIMUM}. Composite renders Unrated."
                ),
            }
        )

    # Per-country structural checks. Nothing here is allowed to reach the page
    # as an empty string or a missing key.
    missing_fields = 0
    missing_url = 0
    unrated_cells = Counter()
    coverage = Counter()
    provisional = Counter()

    for iso2, row in countries.items():
        for field in REQUIRED_FIELDS:
            if not row.get(field):
                missing_fields += 1
                findings.append(
                    {
                        "level": "blocking",
                        "code": "missing_required_field",
                        "detail": f"{iso2}: '{field}' is empty",
                    }
                )

        for source in selected:
            bucket = (row.get("sources") or {}).get(source)
            if not bucket:
                unrated_cells[source] += 1
                continue
            coverage[source] += 1
            if bucket.get("level") is None:
                unrated_cells[source] += 1
            if _is_provisional(bucket):
                provisional[source] += 1
            for field in REQUIRED_SOURCE_FIELDS:
                if not bucket.get(field):
                    missing_url += 1
                    findings.append(
                        {
                            "level": "warning",
                            "code": "missing_source_field",
                            "detail": f"{iso2}/{source}: '{field}' is empty",
                        }
                    )

            # The capital-city headline is only honest if the caveat travels
            # with it. A row whose country is not uniformly rated MUST carry a
            # caveat naming the spread - otherwise the table shows Abuja's
            # level and silently implies it covers Borno. This is blocking on
            # purpose: it is the one way the capital-city decision could
            # actively mislead someone.
            if bucket.get("uniform") is False and not bucket.get("caveat"):
                findings.append(
                    {
                        "level": "blocking",
                        "code": "missing_spread_caveat",
                        "detail": (
                            f"{iso2}/{source}: level is the capital's but the "
                            "country is not uniformly rated and no caveat was built"
                        ),
                    }
                )

    # The synthesised column must never render without saying what it is.
    # A reader who takes "Azerbaijan 2" for a government rating has received
    # the wrong message, and no government said 2 - three said 2 and one said
    # 3. Blocking, for the same reason the spread caveat is blocking.
    for iso2, row in countries.items():
        advon = row.get("advon")
        if not advon:
            continue
        disclosure = advon.get("disclosure") or {}
        for field in ("label", "column_note", "frame_note"):
            if not disclosure.get(field):
                findings.append(
                    {
                        "level": "blocking",
                        "code": "missing_synthesis_disclosure",
                        "detail": (
                            f"{iso2}: the Advon column is missing '{field}'. The "
                            "synthesised level must not publish without the frame "
                            "that says whose view it represents."
                        ),
                    }
                )
        if advon.get("synthesis") is not True:
            findings.append(
                {
                    "level": "blocking",
                    "code": "synthesis_not_marked",
                    "detail": f"{iso2}: Advon column is not marked as a synthesis",
                }
            )

    # Sources disagreeing by two levels or more. Per the plan this is a feature,
    # not an error - five governments reaching different conclusions is real
    # information and no free competitor surfaces it.
    divergent: list[dict] = []
    for iso2, row in countries.items():
        levels = {
            src: b.get("level")
            for src, b in (row.get("sources") or {}).items()
            if isinstance(b.get("level"), int)
        }
        if len(levels) >= 2:
            spread = max(levels.values()) - min(levels.values())
            if spread >= 2:
                divergent.append(
                    {"iso2": iso2, "name": row.get("name"), "spread": spread, "levels": levels}
                )
    divergent.sort(key=lambda d: -d["spread"])

    for item in unmapped:
        findings.append(
            {
                "level": "warning",
                "code": "unmapped_name",
                "detail": f"{item['source']}: {item['reason']}",
            }
        )

    total = len(countries)
    summary.append(f"{total} countries reconciled")
    for source in selected:
        got = coverage.get(source, 0)
        pct = (got / total * 100) if total else 0
        line = (
            f"{source}: {got}/{total} rows ({pct:.0f}%), "
            f"{unrated_cells.get(source, 0)} unrated"
        )
        holding = provisional.get(source, 0)
        if holding:
            share = (holding / got * 100) if got else 0
            line += f", {holding} provisional ({share:.0f}% of the column)"
        summary.append(line)
    if failed:
        summary.append(f"failed sources: {', '.join(failed)}")
    if unmapped:
        summary.append(f"{len(unmapped)} names need an alias entry")
    if divergent:
        summary.append(f"{len(divergent)} countries where sources disagree by 2+ levels")

    return {
        "blocking": [f for f in findings if f["level"] == "blocking"],
        "warnings": [f for f in findings if f["level"] == "warning"],
        "coverage": dict(coverage),
        "unrated": dict(unrated_cells),
        "provisional": dict(provisional),
        "unmapped_names": unmapped,
        "divergent": divergent[:50],
        "sources_working": working,
        "sources_failed": failed,
        "summary": summary,
    }
