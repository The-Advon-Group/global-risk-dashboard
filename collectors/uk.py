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

# The FCDO states a level for the whole country only when its advice covers the
# whole country. For a parts-only advisory it says "advice against all travel to
# PARTS of X", which is not a verdict on X - the country-wide number in that case
# is our roll-up of the carve-out and the residual, and feeding it back in as the
# FCDO's own figure republishes the carve-out as the country. Whole-country
# advisories are unaffected: they produce one record with no region, so
# `headline.resolve` uses the national level either way.
PUBLISHES_NATIONAL_LEVEL = False

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

        warnings = _warnings_text(details)
        if whole or covers_whole_country(warnings, name):
            rec.level = carve_level
            rec.level_basis = (
                "FCDO alert_status, whole country"
                if whole
                else "FCDO advises against travel to the country itself, "
                     "with named exceptions"
            )
            if not whole:
                rec.notes.append(
                    "alert_status says 'to parts', but the FCDO's own wording "
                    "advises against travel to the country with exceptions"
                )
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
        # The region text matters as much as the level. Without it this record
        # is invisible to `headline.resolve`, which only looks at records that
        # name a place - so the carve-out won by being the only regional record
        # and the whole country took its level. Run #7 had the FCDO rating
        # Benin, Georgia, Armenia, Burundi and Cote d'Ivoire at 4 for exactly
        # that reason. "the rest of the country" is what the FCDO's own map
        # calls it, and `headline.RESIDUAL` recognises it.
        rec.region = "the rest of the country"

        # An advisory with TWO "to parts" alerts is telling us about two tiers,
        # and the lower one is what covers the ground the higher one does not.
        # Ukraine carries both: "avoid all travel" to Crimea and the border
        # oblasts, and "avoid all but essential travel" to the rest. Handing the
        # remainder the provisional 1 published Ukraine at level 1 in run #9,
        # which is not remotely what the FCDO says. Where there is only one
        # alert, we genuinely have nothing about the remainder and the
        # provisional level stands.
        lower = sorted({ALERT_TO_LEVEL[s] for s in known})
        if len(lower) > 1:
            rec.level = lower[0]
            rec.level_basis = (
                "rest of country - the FCDO's lower advise-against tier, which "
                "covers what the higher one does not"
            )
        else:
            rec.level = RESIDUAL_LEVEL
            rec.level_basis = (
                "rest of country - FCDO advises against travel only to named parts"
            )
            rec.notes.append(
                "provisional level 1 - refine to 1 vs 2 once phrase ladder lands"
            )
        rec.notes.append(
            f"carve-out at level {carve_level} applies to named parts, not the whole country"
        )
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


def _warnings_text(details: dict) -> str:
    part = next(
        (p for p in (details.get("parts") or []) if p.get("slug") == "warnings-and-insurance"),
        None,
    )
    if not part:
        return ""
    import re as _re

    return _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", part.get("body") or "")).strip()


def covers_whole_country(text: str, country: str) -> bool:
    """Does a "to parts" advisory in fact cover the country, minus exceptions?

    `alert_status` only says whole or parts, and "parts" turns out to cover two
    opposite shapes. Somalia is recorded as `avoid_all_travel_to_parts`, and the
    FCDO's own words are:

        "FCDO advises against all travel to Somalia, including Somaliland,
         except for the regions of Awdal, Maroodijeh, and Sahil."

    That is the whole country with three exceptions, not a carve-out with a safe
    remainder - so treating it as parts-only and handing the rest of the country
    the residual level published Somalia at 1 in run #8. Benin, where the FCDO
    names a northern border strip, is the other shape and is genuinely a
    carve-out.

    The two are distinguishable from the sentence itself: this one names the
    COUNTRY as the thing advised against. So that is what this looks for, and
    only within the advise-against sentence, so a passing mention of the country
    elsewhere in the section does not count.
    """
    import re as _re

    if not text or not country:
        return False
    name = _re.escape(country.strip())
    # "advises against all travel to Somalia" / "to the whole of Somalia" /
    # "against all but essential travel to Somalia", allowing a leading article.
    # The trailing guard is a negative lookahead rather than \b for two reasons:
    # "the Ruritania-Syldavia border area" must NOT match, because that names a
    # strip and not the country, and a name ending in a bracket - the spine
    # spells one "Cote d'Ivoire (Ivory Coast)" - has no word boundary after it.
    pattern = (
        r"advises\s+against\s+(?:all\s+travel|all\s+but\s+essential\s+travel)\s+to\s+"
        r"(?:the\s+whole\s+of\s+)?(?:the\s+)?" + name + r"(?![\w-])"
    )
    return bool(_re.search(pattern, text, _re.I))


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
