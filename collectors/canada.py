"""Canada - Travel Advice and Advisories (travel.gc.ca).

Cleanest of the five. One JSON document, all destinations, ISO codes already
present, official open dataset under the Open Government Licence - Canada.

Endpoint verified live 8 Sep 2026. Update frequency published as "Continual".

Canada's own scale is 0-3 in `advisory-state`:
    0  Exercise normal security precautions
    1  Exercise a high degree of caution
    2  Avoid non-essential travel
    3  Avoid all travel
which is our 1-4 scale offset by one. We map on the numeric field and use the
English advisory text as a cross-check, because the numeric field is the thing
Canada actually maintains and the text is generated from it.
"""

from __future__ import annotations

from .base import Record, get

INDEX = "https://data.international.gc.ca/travel-voyage/index-alpha-eng.json"
PAGE = "https://travel.gc.ca/destinations/{slug}"

SOURCE = "ca"
SOURCE_NAME = "Global Affairs Canada - Travel Advice and Advisories"

# Canada states a level for the country as a whole (`advisory-state`) and then
# lists regions that differ from it. The country-wide figure is Canada's own.
PUBLISHES_NATIONAL_LEVEL = True

# Cross-check strings. If the text and the number disagree we trust the number
# and record the disagreement rather than silently picking one.
TEXT_TO_LEVEL = {
    "exercise normal security precautions": 1,
    "exercise a high degree of caution": 2,
    "avoid non-essential travel": 3,
    "avoid all travel": 4,
}


def _level_from_text(text: str) -> int | None:
    low = (text or "").lower()
    for phrase, lvl in TEXT_TO_LEVEL.items():
        if low.startswith(phrase):
            return lvl
    return None


def collect() -> list[Record]:
    payload = get(INDEX).json()
    data = payload.get("data") or {}
    generated = (payload.get("metadata", {}).get("generated", {}) or {}).get("date")

    records: list[Record] = []
    for iso2, entry in data.items():
        eng = entry.get("eng") or {}
        slug = eng.get("url-slug") or ""
        text = eng.get("advisory-text") or ""

        state = entry.get("advisory-state")
        level = state + 1 if isinstance(state, int) and 0 <= state <= 3 else None

        notes: list[str] = []
        from_text = _level_from_text(text)
        if level is None:
            level = from_text
            if level is not None:
                notes.append("level derived from advisory text; numeric state missing")
        elif from_text is not None and from_text != level:
            notes.append(
                f"source disagreement: advisory-state={state} but text reads '{text}'"
            )

        if level is None:
            notes.append("no usable advisory level in source record")

        rec = Record(
            source=SOURCE,
            source_name=SOURCE_NAME,
            raw_name=entry.get("country-eng") or eng.get("name") or iso2,
            url=PAGE.format(slug=slug) if slug else "https://travel.gc.ca/destinations",
            iso2=(iso2 or "").upper() or None,
            level=level,
            level_label=text or None,
            level_basis="advisory-state field (0-3) + 1",
            source_updated=(entry.get("date-published") or {}).get("date"),
            notes=notes,
        )
        # Canada flags that regional advisories exist but the index does not
        # carry them. Record the flag so the detail view can say so honestly
        # rather than implying the whole country sits at this level.
        if entry.get("has-regional-advisory"):
            rec.notes.append("source has regional advisories not present in the index feed")
        records.append(rec)

    if not records:
        from .base import CollectorError

        raise CollectorError("Canada index returned zero destinations")

    for r in records:
        r.notes.append(f"feed generated {generated}") if generated else None
    return records
