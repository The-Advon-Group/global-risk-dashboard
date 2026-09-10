"""United States - State Department travel advisories.

Public domain. Attribution to the Bureau of Consular Affairs appreciated,
not required.

WHERE THE LEVELS COME FROM, settled 10 September 2026 across runs #4 to #6.

The advisories list page is server-rendered and carries every destination with
its level, State's own risk-indicator tags and the issue date. It is also behind
Cloudflare, and returns HTTP 403 to an honestly-identified program. This build
does not try to get past that - no spoofed browser user agent, no headless
browser driven at the challenge. The data is public domain and State publishes
it for reuse, but the front door is theirs to lock, and picking it would make
every other claim this project makes about attribution and good faith worth
less. `probe_us_routes()` asks each published route politely once per run and
records what each one says, so a door that opens later gets noticed.

Of the five published routes, three answer:

  * `_res/rss/TAsTWs.xml` ANSWERS, and the note this docstring used to carry -
    "a change feed of ~21 recently-updated advisories, not usable as a
    registry" - is out of date. On 10 Sep 2026 it returned 216 items, one per
    destination, every one carrying its level in the title ("Suriname - Level 1:
    Exercise Normal Precautions") and again as a category. That is the US
    column, and it costs one request.
  * `/api/CountryTravelInformation` answers with ~5.9MB of per-country narrative
    but does not currently parse as XML - see `probe_us_shape()`.
  * `/api/TravelAdvisories` answers with an empty ArrayOfRss, as it has since
    8 Sep.

WHAT THE FEED DOES NOT CARRY. State's risk-indicator tags - the (C)(T)(K) pills
on the list page - are structured data there and prose here. `collect()` reads
them out of the advisory summary instead, and every record says so in
`indicators_basis`, because an inferred flag and a published one are not the
same thing and the difference must not disappear into the same field.
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


RSS_FEED = "https://travel.state.gov/_res/rss/TAsTWs.xml"

# "Suriname - Level 1: Exercise Normal Precautions" and
# "Mexico Travel Advisory - Level 2: Exercise Increased Caution" both occur, so
# the split is on the level rather than on the dash.
TITLE = re.compile(r"^(?P<name>.+?)\s*[-–]\s*Level\s*(?P<level>[1-4])\s*:\s*(?P<label>.+)$")
TRAILING_ADVISORY = re.compile(r"\s*Travel\s+Advisory\s*$", re.I)

# The summary says "due to crime, terrorism, and kidnapping". These map that
# prose onto State's own indicator letters. Ordered longest-first so "civil
# unrest" is not swallowed by "unrest".
INDICATOR_PHRASES: list[tuple[str, str]] = [
    ("K", r"kidnapping|hostage[- ]taking|abduction"),
    ("D", r"wrongful detention|unjust (?:arrest|detention)|exit ban"),
    ("T", r"terroris"),
    ("U", r"civil unrest|unrest|armed conflict|war\b|violence"),
    ("C", r"\bcrime\b|criminal"),
    ("H", r"health (?:risk|care|emergenc)|disease outbreak|\bepidemic\b"),
    ("N", r"natural disaster|hurricane|earthquake|volcan|cyclone|typhoon"),
]
DUE_TO = re.compile(r"due to\b(?P<reasons>[^.]{0,300})", re.I)
TAG_STRIP = re.compile(r"<[^>]+>")


def collect() -> list[Record]:
    """One request to State's advisory feed, one record per destination."""
    from xml.etree import ElementTree as ET

    try:
        xml = get(RSS_FEED, timeout=60).text
    except CollectorError as exc:
        raise CollectorError(f"US advisory feed unreachable: {exc}") from exc

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise CollectorError(f"US advisory feed did not parse as XML: {exc}") from exc

    records: list[Record] = []
    skipped: list[str] = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        match = TITLE.match(title)
        if not match:
            # Not an advisory - the feed also carries the occasional alert with
            # no level. Recorded rather than silently dropped.
            if title:
                skipped.append(title[:80])
            continue

        name = TRAILING_ADVISORY.sub("", match.group("name")).strip()
        level = int(match.group("level"))
        label = f"Level {level}: {match.group('label').strip()}"

        summary = _plain(item.findtext("description") or "")
        indicators = _indicators_from(summary)

        rec = Record(
            source=SOURCE,
            source_name=SOURCE_NAME,
            raw_name=name,
            url=(item.findtext("link") or "").strip(),
            level=level,
            level_label=label,
            level_basis="State Department 4-level advisory scale (native)",
            indicators=indicators,
            source_updated=(item.findtext("pubDate") or "").strip() or None,
        )
        rec.notes.append(
            "risk indicators read from the advisory summary text, not from "
            "State's published risk-indicator tags"
            if indicators
            else "no risk indicators stated in the advisory summary"
        )
        records.append(rec)

    if len(records) < 150:
        raise CollectorError(
            f"US advisory feed yielded only {len(records)} destinations; "
            f"expected ~216. Refusing to publish a partial column. "
            f"Skipped titles: {skipped[:5]}"
        )
    return records


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_STRIP.sub(" ", html).replace("&nbsp;", " ")).strip()


def _indicators_from(summary: str) -> list[str]:
    """State's indicator letters, inferred from the advisory summary.

    Scoped to the "due to ..." clause where there is one. That clause is State's
    own list of why the level is what it is, so reading it is closer to the
    published tags than scanning the whole summary would be - a paragraph that
    merely mentions crime elsewhere should not raise the crime flag.
    """
    clause = DUE_TO.search(summary)
    text = (clause.group("reasons") if clause else "").lower()
    if not text:
        return []
    found: list[str] = []
    for letter, pattern in INDICATOR_PHRASES:
        if re.search(pattern, text) and letter not in found:
            found.append(letter)
    return found


def collect_from_list_page() -> list[Record]:
    """The original list-page reader. Behind Cloudflare since 10 Sep 2026.

    Kept, unused, because `probe_us_routes()` watches that door every cycle and
    this is what to call the day it opens: the list page carries State's own
    risk-indicator tags, which the feed only carries as prose.
    """
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
