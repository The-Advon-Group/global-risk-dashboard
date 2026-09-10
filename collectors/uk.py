"""United Kingdom - FCDO foreign travel advice, via the GOV.UK Content API.

Open Government Licence, commercial reuse permitted with attribution.

Verification note (8 Sep 2026): the plan assumed FCDO severity would have to be
inferred from prose, and called that mapping "a judgment call". It does not.
Each country document carries `details.alert_status`, a machine-readable array
using a fixed vocabulary. That turns three of the four rungs of the UK ladder
into a published field rather than our interpretation. Only the bottom rung
(level 1 vs 2, "is the terrorism language elevated") still needs the Phase 2
phrase ladder, and until that exists this collector says so instead of guessing.

The index (`links.children`) lists every country, so no crawling is needed to
discover the set; one detail fetch per country gets the alert status.
"""

from __future__ import annotations

import concurrent.futures as cf

from .base import CollectorError, Record, get

INDEX = "https://www.gov.uk/api/content/foreign-travel-advice"

SOURCE = "uk"
SOURCE_NAME = "UK Foreign, Commonwealth & Development Office - travel advice"

# FCDO's published alert vocabulary -> our shared 1-4 scale.
# "to_parts" keeps the same severity: per the agreed rule, a country rolls up to
# the highest severity applying to any part of it, and the region detail is
# preserved in `region_note` for the per-country view.
ALERT_TO_LEVEL = {
    "avoid_all_travel_to_whole_country": 4,
    "avoid_all_travel_to_parts": 4,
    "avoid_all_but_essential_travel_to_whole_country": 3,
    "avoid_all_but_essential_travel_to_parts": 3,
}

WHOLE_COUNTRY = {
    "avoid_all_travel_to_whole_country",
    "avoid_all_but_essential_travel_to_whole_country",
}


def _index() -> list[dict]:
    payload = get(INDEX).json()
    children = (payload.get("links") or {}).get("children") or []
    if not children:
        raise CollectorError("GOV.UK travel advice index returned no children")
    return children


# Residual level for the part of a country NOT covered by a "to parts" carve-out.
# The FCDO states no number for it; what it states is the absence of an
# advise-against for the rest of the country, which is our level 1 (provisional
# until the Phase 2 terrorism tier separates 1 from 2).
RESIDUAL_LEVEL = 1


def _one(child: dict) -> list[Record]:
    api_url = child.get("api_url") or ""
    web_url = child.get("web_url") or ""
    name = ((child.get("details") or {}).get("country") or {}).get("name") \
        or (child.get("title") or "").replace(" travel advice", "")

    rec = Record(
        source=SOURCE,
        source_name=SOURCE_NAME,
        raw_name=name,
        url=web_url,
        source_updated=child.get("public_updated_at"),
    )

    try:
        detail = get(api_url).json() if api_url else {}
    except CollectorError as exc:
        rec.notes.append(f"detail fetch failed: {exc}")
        return rec

    details = detail.get("details") or {}
    statuses = details.get("alert_status") or []
    rec.level_label = ", ".join(statuses) if statuses else "no travel-advice-against alert"
    rec.source_updated = details.get("updated_at") or rec.source_updated

    known = [s for s in statuses if s in ALERT_TO_LEVEL]
    unknown = [s for s in statuses if s not in ALERT_TO_LEVEL]
    if unknown:
        rec.notes.append(f"unrecognised alert_status value(s): {', '.join(unknown)}")

    if known:
        carve_level = max(ALERT_TO_LEVEL[s] for s in known)
        whole = any(s in WHOLE_COUNTRY for s in known)

        if whole:
            rec.level = carve_level
            rec.level_basis = "FCDO alert_status, whole country"
            return [rec]

        # "to parts" only. This is the fix for the Azerbaijan class of error.
        #
        # Previously the carve-out level was applied to the whole country, so
        # Azerbaijan - where the FCDO advises against travel only to Nagorno-
        # Karabakh and a 5km strip along the Armenian border - came out at the
        # same level as Burkina Faso, where the FCDO advises against all travel
        # to the entire country. Two very different situations, one number.
        #
        # The FCDO publishes the distinction itself: `_to_whole_country` against
        # `_to_parts`. So a parts-only advisory now emits TWO records - the
        # carve-out as a regional record, and the rest of the country at the
        # residual level. The capital then takes the residual unless it is
        # named in a carve-out, which is what `headline.resolve` decides.
        carve = Record(
            source=SOURCE,
            source_name=SOURCE_NAME,
            raw_name=name,
            url=web_url,
            level=carve_level,
            level_label=rec.level_label,
            level_basis="FCDO alert_status, applies to named parts only",
            region=_carve_region(details) or "parts of country (see FCDO regional risks)",
            source_updated=rec.source_updated,
        )
        rec.level = RESIDUAL_LEVEL
        rec.level_basis = (
            "rest of country - FCDO advises against travel only to named parts"
        )
        rec.notes.append(
            f"carve-out at level {carve_level} applies to named parts, not the whole country"
        )
        rec.notes.append("provisional level 1 - refine to 1 vs 2 once phrase ladder lands")
        return [rec, carve]
    else:
        # No advise-against alert. Distinguishing level 1 from level 2 depends on
        # the terrorism-language tier, which is Phase 2 work and is deliberately
        # not guessed here.
        rec.level = 1
        rec.level_basis = (
            "no FCDO advise-against alert; terrorism-language tier not yet applied"
        )
        rec.notes.append("provisional level 1 - refine to 1 vs 2 once phrase ladder lands")

    return [rec]


def _carve_region(details: dict) -> str | None:
    """Pull the named areas out of the FCDO's warnings section.

    The FCDO lists them under "Areas where FCDO advises against travel" as
    subheadings - "Azerbaijan-Armenia border", "South-western Azerbaijan". Those
    names are what makes a bounded exclusion legible to a reader, so they are
    worth carrying even though the level does not depend on them.
    """
    import re

    part = next(
        (p for p in (details.get("parts") or []) if p.get("slug") == "warnings-and-insurance"),
        None,
    )
    if not part:
        return None
    body = part.get("body") or ""
    heads = [
        re.sub(r"<[^>]+>", "", m).strip()
        for m in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", body, re.I | re.S)
    ]
    named = [
        h for h in heads
        if h and not re.match(r"^(areas where|limited consular|find out more)", h, re.I)
    ]
    return "; ".join(named[:6]) or None


def collect(max_workers: int = 8) -> list[Record]:
    children = _index()
    records: list[Record] = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        for group in pool.map(_one, children):
            records.extend(group)
    return records
