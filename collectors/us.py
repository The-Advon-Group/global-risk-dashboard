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

# State issues one level per destination.
PUBLISHES_NATIONAL_LEVEL = True

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


# Official, published routes to US advisory data. The point of probing all of
# them each cycle is that we do not know which State will serve to a program.
CANDIDATE_ROUTES = {
    "list_page": LIST_PAGE,
    "advisories_api": ADVISORY_API,
    "country_info_api": NARRATIVE_API,
    "rss_change_feed": "https://travel.state.gov/_res/rss/TAsTWs.xml",
    "open_data_xml": (
        "https://cadatacatalog.state.gov/dataset/4a387c35-29cb-4902-b91d-3da0dc02e4b2"
        "/resource/4c727464-8e6f-4536-b0a5-0a343dc6c7ff/download/traveladvisory.xml"
    ),
}


def probe_us_routes() -> dict:
    """Ask each published US route whether it will answer an honest request.

    Written 10 Sep 2026 after the first live run failed with HTTP 403. That 403
    is Cloudflare bot protection on travel.state.gov, and it is not something
    this build will try to defeat - no spoofed browser user agent, no headless
    browser driven at the challenge. The data is public domain and State
    publishes it for reuse, but the front door is theirs to lock, and picking it
    would make every other claim this project makes about attribution and good
    faith worth less.

    So instead: identify ourselves honestly, try each route State actually
    publishes, and record what each one says. Whatever answers, we use. The
    result rides in every run record so the picture stays current - a route that
    opens later gets noticed without anyone checking by hand.
    """
    results: dict[str, dict] = {}
    for name, url in CANDIDATE_ROUTES.items():
        try:
            resp = get(url, retries=1, timeout=30)
            body = resp.text
            results[name] = {
                "status": resp.status_code,
                "usable": True,
                "bytes": len(body),
                "note": _describe(name, body),
            }
        except CollectorError as exc:
            detail = str(exc)
            blocked = "HTTP 403" in detail
            results[name] = {
                "status": 403 if blocked else None,
                "usable": False,
                "note": (
                    "refused as automated traffic - not circumvented by design"
                    if blocked
                    else detail[:160]
                ),
            }
    results["_summary"] = {
        "open": sorted(k for k, v in results.items() if v.get("usable")),
        "closed": sorted(k for k, v in results.items() if not v.get("usable")),
    }
    return results


def _describe(name: str, body: str) -> str:
    if name == "advisories_api":
        return ("still an empty ArrayOfRss"
                if "<Rss" not in body and "<item" not in body else "now populated")
    if name == "list_page":
        count = body.count("level-title-")
        return f"{count} advisory levels present in the HTML"
    if name == "open_data_xml":
        return f"{body.count('<Country')} country elements"
    return f"{len(body)} bytes returned"


# Kept so older callers and the pipeline keep working.
def probe_cadataapi() -> dict:
    return probe_us_routes()


LEVEL_IN_TEXT = re.compile(r"Level\s*([1-4])\b", re.I)


def probe_us_shape() -> dict:
    """Ask the two open routes whether a LEVEL can be read out of them.

    Run #5 established that `CountryTravelInformation` and the RSS change feed
    both answer while the HTML list page and the open-data XML do not. That
    settles reachability and nothing else: a route that returns six megabytes of
    narrative is only useful for the advisory column if a level is in there
    somewhere.

    So this reports the SHAPE - which fields exist, how many entries, whether a
    "Level N" string appears and in which field - rather than the content. The
    point is to decide how to rebuild the US column without hauling six
    megabytes of prose through anybody's eyes first.
    """
    from xml.etree import ElementTree as ET

    out: dict[str, dict] = {}

    try:
        xml = get(NARRATIVE_API, timeout=120).text
        root = ET.fromstring(xml)
        entries = list(root)
        fields: list[str] = []
        if entries:
            fields = [
                child.tag.rsplit("}", 1)[-1] for child in entries[0]
            ]
        with_level = 0
        level_fields: set[str] = set()
        for node in entries[:40]:
            for child in node:
                if child.text and LEVEL_IN_TEXT.search(child.text[:400]):
                    level_fields.add(child.tag.rsplit("}", 1)[-1])
            if any(child.text and LEVEL_IN_TEXT.search(child.text[:400]) for child in node):
                with_level += 1
        out["country_info_api"] = {
            "entries": len(entries),
            "fields": sorted(set(fields)),
            "level_string_in_first_40": with_level,
            "fields_carrying_a_level": sorted(level_fields),
        }
    except (CollectorError, ET.ParseError) as exc:
        out["country_info_api"] = {"error": str(exc)[:200]}

    try:
        feed = get(CANDIDATE_ROUTES["rss_change_feed"], timeout=60).text
        root = ET.fromstring(feed)
        items = root.findall(".//item")
        titles = [(it.findtext("title") or "").strip() for it in items]
        levelled = [t for t in titles if LEVEL_IN_TEXT.search(t)]
        out["rss_change_feed"] = {
            "items": len(items),
            "titles_with_a_level": len(levelled),
            "sample_title": (levelled or titles or [""])[0][:120],
        }
    except (CollectorError, ET.ParseError) as exc:
        out["rss_change_feed"] = {"error": str(exc)[:200]}

    return out


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
