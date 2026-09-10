"""Japan - MOFA overseas safety information.

CORRECTION (8 Sep 2026). The sources record lists Japan as one of three sources
that are "ready to go", with the endpoint
    www.ezairyu.mofa.go.jp/html/opendata/area/00.xml
described as all-region, all-country coverage. That endpoint was fetched and
read. It is not a registry of current danger levels.

What the MOFA open-data service actually publishes is 領事メール - consular mail
notices from embassies and consulates - as a change feed, in three verbosity
levels, refreshed every five minutes. The records carry keyCd, infoType,
leaveDate, area/country codes, a title and a lead paragraph. There is no
current-danger-level field, and the index files served include sample rows
dated 2019. It is the Japanese equivalent of the US RSS change feed: useful for
"what moved recently", useless as the source of a country's standing rating.

Japan's actual 4-level 危険情報 ratings live on anzen.mofa.go.jp as per-country
HTML. The interactive risk map is an image map whose script only navigates to
those pages - there is no JSON behind it to read.

So Japan is NOT launch-ready as a level source on the strength of the recorded
endpoint. Two honest options, and the choice is Matt's:

  A. Launch without Japan. The composite is designed for this: it needs 3 of 5
     sources and, with the US and France both now resolved, 4 remain. Japan's
     column renders Unrated and says why.
  B. Build a per-country reader against anzen.mofa.go.jp (~200 pages per cycle).
     Feasible, and the licence is confirmed and generous - MOFA's own open-data
     page states the data may be used 営利目的・非営利目的を問わず, commercial or
     not - but it is a page-structure dependency on a site that has no published
     stability guarantee, and it is a day of work rather than an hour.

Until that decision is made this module deliberately collects nothing rather
than shipping a column built on the wrong feed. The change feed is still worth
having for the "what changed recently" signal, so `collect_mail_feed()` is
implemented and wired to nothing.

LICENCE, confirmed verbatim on MOFA's open-data index page:
    サイト内のオープンデータは無償であり、営利目的・非営利目的を問わず利用いただけます。
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from .base import CollectorError, Record, get

MAIL_FEED_ALL = "https://www.ezairyu.mofa.go.jp/html/opendata/area/00.xml"
NEW_ARRIVALS = "https://www.ezairyu.mofa.go.jp/html/opendata/area/newarrival.xml"
RISK_MAP = "https://www.anzen.mofa.go.jp/riskmap/"

SOURCE = "jp"
SOURCE_NAME = "Ministry of Foreign Affairs of Japan - Overseas Safety Information"

STATUS = {
    "launch_ready": False,
    "decision": "DEFERRED - settled 10 September 2026",
    "reason": (
        "The recorded open-data endpoint is a consular-mail change feed, not a "
        "registry of current danger levels. Country levels require a per-country "
        "reader against anzen.mofa.go.jp, which is not built."
    ),
    "licence": "Japan Public Data License 1.0 - commercial use explicitly permitted",
    "plan": (
        "Launch on four sources. Revisit the per-country reader after beta. "
        "Until then breadth is out of 4, the Japan column renders Unrated with "
        "this reason shown, and the methodology page must not say 'five "
        "governments'."
    ),
}

# Denominator for the composite while Japan is out. Imported rather than
# hardcoded in two places, so restoring Japan is a one-line change.
ACTIVE_SOURCE_COUNT = 4


def collect() -> list[Record]:
    """Returns nothing, on purpose. See the module docstring."""
    return []


def collect_mail_feed(new_only: bool = True) -> list[dict]:
    """Consular-mail notices. Change detection only - carries no danger level."""
    url = NEW_ARRIVALS if new_only else MAIL_FEED_ALL
    try:
        root = ET.fromstring(get(url, timeout=60).text)
    except (CollectorError, ET.ParseError) as exc:
        raise CollectorError(f"MOFA mail feed unavailable: {exc}") from exc

    out: list[dict] = []
    for mail in root.iter("mail"):
        def text(tag: str) -> str | None:
            el = mail.find(tag)
            return el.text if el is not None else None

        country = mail.find("country")
        out.append(
            {
                "key": text("keyCd"),
                "info_type": text("infoType"),
                "issued": text("leaveDate"),
                "country_code": (country.find("cd").text if country is not None and country.find("cd") is not None else None),
                "title": text("title"),
                "url": text("infoUrl"),
            }
        )
    return out
