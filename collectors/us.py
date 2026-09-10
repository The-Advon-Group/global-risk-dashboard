"""United States - State Department travel advisories.

Public domain. Attribution to the Bureau of Consular Affairs appreciated,
not required.

Verification note (8 Sep 2026) - this replaces the "US feed is narrower than
assumed" blocker in the plan:

  * The RSS feed at travel.state.gov/_res/rss/TAsTWs.xml is a change feed of ~21
    recently-updated advisories. Not usable as a registry. Unchanged.
  * cadataapi.state.gov IS a real, public, unauthenticated API - but its
    `/api/TravelAdvisories` endpoint currently returns an empty ArrayOfRss, so
    it does not supply levels today. Kept in `probe_cadataapi()` below so a
    future run notices if State fills it in.
  * The advisories LIST PAGE is fully server-rendered: a single GET returns all
    ~228 destinations with level, risk-indicator tags and issue date. The
    client-side pagination that makes the page look like it holds five rows is
    applied by JavaScript after load and does not affect a plain HTTP fetch.

So the US column costs one request, not 195.

`/api/CountryTravelInformation` on the same API returns the full narrative text
(including the "Terrorism:" block of each country's safety-and-security
section) for every country. That is the raw input the Phase 2 phrase ladder
needs, and `fetch_country_narratives()` retrieves it.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import CollectorError, Record, get

LIST_PAGE = "https://travel.state.gov/en/international-travel/travel-advisories.html"
BASE = "https://travel.state.gov"
NARRATIVE_API = "https://cadataapi.state.gov/api/CountryTravelInformation"
ADVISORY_API = "https://cadataapi.state.gov/api/TravelAdvisories"

SOURCE = "us"
SOURCE_NAME = "U.S. Department of State, Bureau of Consular Affairs - Travel Advisories"

LEVEL_CLASS = re.compile(r"level-title-(\d)")
INDICATOR_LETTER = re.compile(r"\(([A-Z])\)\s*$")

# State's risk-indicator tags are presence/absence flags, not graded scores.
INDICATOR_NAMES = {
    "C": "Crime",
    "T": "Terrorism",
    "U": "Civil Unrest",
    "H": "Health",
    "N": "Natural Disaster",
    "K": "Kidnapping or Hostage Taking",
    "D": "Wrongful Detention",
    "E": "Time-limited Event",
    "O": "Other",
}


def collect() -> list[Record]:
    html = get(LIST_PAGE).text
    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.usa-table--destination")
    if table is None:
        raise CollectorError(
            "US advisories list page did not contain the destination table - "
            "the page template has probably changed"
        )

    body = table.find("tbody")
    rows = body.find_all("tr") if body else []
    if not rows:
        raise CollectorError("US advisories table present but held no rows")

    records: list[Record] = []
    for tr in rows:
        anchor = tr.find("a")
        if anchor is None:
            continue
        name = anchor.get_text(strip=True)
        href = anchor.get("href") or ""
        url = BASE + href if href.startswith("/") else href

        notes: list[str] = []

        level_el = tr.find(class_=LEVEL_CLASS)
        level = None
        level_label = None
        if level_el is not None:
            match = LEVEL_CLASS.search(" ".join(level_el.get("class", [])))
            if match:
                level = int(match.group(1))
            level_label = level_el.get_text(strip=True)
        if level is None:
            notes.append("no advisory level found in row")

        indicators: list[str] = []
        for pill in tr.select(".tsg-utility-risk-pill"):
            letter = INDICATOR_LETTER.search(pill.get_text(strip=True))
            if letter:
                indicators.append(letter.group(1))
            else:
                notes.append(f"unparsed risk indicator: {pill.get_text(strip=True)}")

        issued = None
        for td in tr.find_all("td"):
            if (td.get("data-label") or "").lower() == "date issued":
                issued = td.get_text(strip=True)
        if issued is None:
            cells = tr.find_all("td")
            issued = cells[-1].get_text(strip=True) if cells else None

        records.append(
            Record(
                source=SOURCE,
                source_name=SOURCE_NAME,
                raw_name=name,
                url=url,
                level=level,
                level_label=level_label,
                level_basis="State Department 4-level advisory scale (native)",
                indicators=indicators,
                source_updated=issued,
                notes=notes,
            )
        )

    if len(records) < 150:
        raise CollectorError(
            f"US list page yielded only {len(records)} destinations; expected ~228. "
            "Refusing to publish a partial column."
        )
    return records


def probe_cadataapi() -> dict:
    """Check whether State's API has started serving advisories.

    Cheap, runs each cycle, and writes a line into the run report. If this ever
    returns populated=True the list-page scrape can be retired for a supported
    API, which is strictly better.
    """
    try:
        text = get(ADVISORY_API, retries=1, timeout=20).text
    except CollectorError as exc:
        return {"reachable": False, "populated": False, "detail": str(exc)}
    populated = "<Rss" in text or "<item" in text
    return {
        "reachable": True,
        "populated": populated,
        "detail": "endpoint returns an empty ArrayOfRss" if not populated else "now populated",
    }


def fetch_country_narratives() -> dict[str, dict[str, str]]:
    """Full per-country narrative text, keyed by ISO2 tag.

    ~5.8MB. Used by the Phase 2 phrase ladder, not by the Phase 1 table, so the
    pipeline only calls this when composite scoring is enabled.
    """
    from xml.etree import ElementTree as ET

    xml = get(NARRATIVE_API, timeout=120).text
    root = ET.fromstring(xml)
    ns = {"m": "http://schemas.datacontract.org/2004/07/CADataAPIService.Models"}
    out: dict[str, dict[str, str]] = {}
    for node in root.findall("m:CountryInformation", ns):
        def field(tag: str) -> str:
            el = node.find(f"m:{tag}", ns)
            return (el.text or "") if el is not None else ""

        tag = field("tag").strip().upper()
        if not tag:
            continue
        out[tag] = {
            "name": field("geopoliticalarea").strip(),
            "safety_and_security": field("safety_and_security"),
            "health": field("health"),
            "last_update": field("last_update_date").strip(),
        }
    return out
