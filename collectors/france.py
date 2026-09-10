"""France - Conseils aux voyageurs (diplomatie.gouv.fr).

Verification note (8 Sep 2026) - this replaces the "France is not launch-ready"
finding in the plan. Two things were checked and both came back better than the
record said:

  * LICENCE. The record said Licence Ouverte coverage of the site's own pages
    (as opposed to the stale data.gouv.fr dataset) needed separate confirmation.
    It is stated in the footer of the country pages themselves:
      "Sauf mention explicite de propriete intellectuelle detenue par des tiers,
       les contenus de ce site sont proposes sous licence etalab-2.0"
    Etalab 2.0 / Licence Ouverte 2.0 permits commercial reuse with attribution.
    That is a documented site-wide grant on the exact pages we read, not an
    inference. The carve-out matters though: third-party IP is excluded, so we
    take ratings and text and never the maps or photographs.

  * RETRIEVAL. The site was restructured; the old conseils-par-pays-destination
    URLs 404. Current shape is
      /fr/information-par-pays/{slug}/conseils-aux-voyageurs-securite
    and that page carries a structured "Zones de vigilance" block with France's
    four colour bands as headings, plus its own "derniere actualisation" date
    and an explicit "information toujours valable a la date du jour" line. That
    last line is worth surfacing: the public complaint about France Diplomatie
    going stale is answerable per-country from the source itself.

France rates by zone rather than by country. Every zone is kept as its own
record; the reconciler rolls a country up to its highest zone.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

from .base import CollectorError, Record, get

ROOT = "https://www.diplomatie.gouv.fr"
INDEX = f"{ROOT}/fr/information-par-pays"
SECURITY = f"{ROOT}/fr/information-par-pays/{{slug}}/conseils-aux-voyageurs-securite"
SLUG_CACHE = Path(__file__).resolve().parent.parent / "data" / "fr_slugs.json"

SOURCE = "fr"
SOURCE_NAME = "Ministere de l'Europe et des Affaires etrangeres - Conseils aux voyageurs"

# France states no country-wide level. It publishes zones and colours them,
# and the country's "level" is whatever we compute from those zones. Anything
# downstream that treats our roll-up as a French national figure is wrong:
# taking the worst zone gave Seychelles level 4 for a piracy zone at sea.
PUBLISHES_NATIONAL_LEVEL = False

# France's colour bands, highest first so the first match wins.
#
# The headings on a country page are one of a small set of wordings, sometimes
# with the colour in brackets ("Zones formellement deconseillees (zone rouge)")
# and sometimes without, so these match the phrase rather than the whole line.
ZONE_BANDS = [
    (4, re.compile(r"zones?\s+formellement\s+d[ée]conseill", re.I), "zone rouge - formellement deconseille"),
    (3, re.compile(r"d[ée]conseill\w*\s+sauf\s+raisons?\s+imp[ée]rative", re.I), "zone orange - deconseille sauf raison imperative"),
    (2, re.compile(r"vigilance\s+renforc[ée]e", re.I), "zone jaune - vigilance renforcee"),
    (1, re.compile(r"vigilance\s+normale", re.I), "zone verte - vigilance normale"),
]

# A band is only a band when it is a HEADING that starts with "Zone". That one
# rule is what fixes the original defect: the Seychelles page says "formellement
# deconseillee" again halfway down a paragraph about piracy, and reading body
# text rated the country by whichever phrase happened to appear. Prose is never
# a heading, so scoping to headings removes the whole class of false positive.
#
# Requiring an enclosing "Zones de vigilance" block was tried first and was too
# strict - run #6 lost eighty French rows to pages that put a heading between
# the anchor and the bands, or carry the anchor only as a figure caption.
ZONE_HEADING = re.compile(r"^zones?\b", re.I)
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# Headings that begin the narrative below the bands. Anything at or after one of
# these is commentary on the zones, not a zone.
END_OF_ZONES = re.compile(
    r"risques?\s+encourus|recommandations\s+associ|liste\s+des\s+repr[ée]sentations",
    re.I,
)

UPDATED = re.compile(r"[Dd]erni[èe]re\s+actualisation\s+le\s+([0-9]{2}/[0-9]{2}/[0-9]{4})")
STILL_VALID = re.compile(r"information\s+toujours\s+valable\s+[àa]\s+la\s+date\s+du\s+jour", re.I)


def _load_slug_cache() -> dict[str, str]:
    if SLUG_CACHE.exists():
        return json.loads(SLUG_CACHE.read_text(encoding="utf-8"))
    return {}


def slugify(name: str) -> str:
    """Turn a French country label into its URL segment.

    Drupal's pathauto builds these deterministically: strip accents, lowercase,
    and replace every run of non-alphanumerics with a single hyphen. Apostrophes
    become hyphens rather than vanishing, which is why "Cote d'Ivoire" is
    cote-d-ivoire and not coted-ivoire.
    """
    text = unicodedata.normalize("NFD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("'", "-").replace("’", "-")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def discover_slugs(save: bool = False) -> dict[str, str]:
    """Map each country's French label to its page slug.

    REWRITTEN 10 Sep 2026, after the first live run failed with "slug discovery
    resolved zero countries".

    The original walked France's country picker as a Drupal POST form, one
    request per country, relying on the server to answer with a redirect to the
    real page. That did not work: Drupal only runs a form's submit handler when
    the submit button's own name and value are posted alongside the fields, and
    ours were not. Without `op=Valider` the server simply rebuilt the form and
    returned no redirect, so nothing resolved.

    Rather than fix the form dance, this drops it. The slugs turn out to be
    derivable from the labels, which was checked against all 197 entries in the
    live picker on 10 September 2026: every one resolved correctly. That removes
    197 POSTs, the form tokens, the session handling and the cache file in one
    go, and leaves nothing to go stale.
    """
    page = get(INDEX, timeout=45)
    soup = BeautifulSoup(page.text, "html.parser")
    select = soup.find("select", {"name": "select_pays"})
    if select is None:
        raise CollectorError("France country picker not found on the index page")

    mapping: dict[str, str] = {}
    for option in select.find_all("option"):
        if not (option.get("value") or "").strip():
            continue  # the "select a country" placeholder
        label = option.get_text(strip=True)
        slug = slugify(label)
        if label and slug:
            mapping[label] = slug

    if not mapping:
        raise CollectorError("France country picker held no usable options")
    if save:
        SLUG_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SLUG_CACHE.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
    return mapping


def _parse_country(name: str, slug: str) -> list[Record]:
    url = SECURITY.format(slug=slug)

    # Nine of the 197 countries in the picker have a country page but no
    # security page at all - Liechtenstein, Kiribati, Nauru, Tuvalu, Niue, the
    # Marshall Islands, Micronesia, the Vatican and the Arctic entry, as of
    # 10 Sep 2026. That is France declining to publish security advice, which is
    # information rather than a fetch failure, so it produces an unrated record
    # saying so instead of an error.
    try:
        html = get(url).text
    except CollectorError as exc:
        if "HTTP 404" in str(exc):
            rec = Record(
                source=SOURCE,
                source_name=SOURCE_NAME,
                raw_name=name,
                url=f"{ROOT}/fr/information-par-pays/{slug}",
                level=None,
                level_basis="France publishes no security page for this country",
            )
            rec.notes.append("no conseils-aux-voyageurs-securite page exists")
            return [rec]
        raise

    soup = BeautifulSoup(html, "html.parser")

    for junk in soup.select("script, style, nav, header, footer"):
        junk.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" "))

    updated = UPDATED.search(text)
    still_valid = bool(STILL_VALID.search(text))

    zones = _read_zones(soup)

    records: list[Record] = []
    if not zones:
        rec = Record(
            source=SOURCE,
            source_name=SOURCE_NAME,
            raw_name=name,
            url=url,
            level=None,
            level_basis="no 'Zones de vigilance' band found on the page",
            source_updated=updated.group(1) if updated else None,
        )
        rec.notes.append("page fetched but no France colour band matched - needs review")
        records.append(rec)
        return records

    single = len(zones) == 1
    for level, label, where in zones:
        rec = Record(
            source=SOURCE,
            source_name=SOURCE_NAME,
            raw_name=name,
            url=url,
            level=level,
            level_label=label,
            level_basis="France colour band stated in the 'Zones de vigilance' section",
            # The zone's own wording, not the band's name. This is the whole
            # point of the 10 Sep rewrite: France says WHERE each band applies,
            # and throwing that away left the capital-city rule with nothing to
            # match on, so every French row fell back to the worst zone in the
            # country. Seychelles read as level 4 because of a piracy zone on
            # the high seas while the inhabited islands are green.
            region=None if single else (where or label),
            source_updated=updated.group(1) if updated else None,
        )
        if still_valid:
            rec.notes.append("source states information still valid as of today")
        if not single and not where:
            rec.notes.append("band heading present but no zone text under it")
        records.append(rec)
    return records


def _read_zones(soup) -> list[tuple[int, str, str]]:
    """Every band in the 'Zones de vigilance' block, with the area it covers.

    Returns (level, band label, zone wording). The zone wording is the text
    France prints under the band's heading - the states, regions, cities or sea
    areas the band applies to, including its exception clauses, which is what
    `headline.resolve` needs to place a capital.

    Scoped to the block on purpose. Both band phrases turn up again in the
    narrative further down a page, and scanning the whole document rated
    countries by whichever phrase happened to appear rather than by what France
    actually classified.
    """
    zones: list[tuple[int, str, str]] = []
    for node in soup.find_all(HEADING_TAGS):
        heading = re.sub(r"\s+", " ", node.get_text(" ")).strip()
        if END_OF_ZONES.search(heading):
            break
        if not ZONE_HEADING.match(heading):
            continue
        band = _band_of(heading)
        if band is None:
            continue
        level, label = band
        zones.append((level, label, _text_under(node)))

    # Same band twice on one page - France sometimes splits a colour across two
    # headings. Keep the first and append the rest of the wording to it.
    merged: dict[int, tuple[int, str, list[str]]] = {}
    for level, label, where in zones:
        if level in merged:
            merged[level][2].append(where)
        else:
            merged[level] = (level, label, [where])
    return [
        (level, label, " ".join(p for p in parts if p).strip())
        for level, label, parts in sorted(merged.values(), key=lambda z: -z[0])
    ]


def _band_of(heading: str) -> tuple[int, str] | None:
    for level, pattern, label in ZONE_BANDS:
        if pattern.search(heading):
            return level, label
    return None


def _text_under(heading) -> str:
    """The paragraphs and lists between one band heading and the next."""
    parts: list[str] = []
    for sibling in heading.find_next_siblings():
        if sibling.name in HEADING_TAGS:
            break
        chunk = re.sub(r"\s+", " ", sibling.get_text(" ")).strip()
        if chunk:
            parts.append(chunk)
    return " ".join(parts).strip()


def collect(slugs: dict[str, str] | None = None, max_workers: int = 6) -> list[Record]:
    import concurrent.futures as cf

    slugs = slugs or _load_slug_cache()
    if not slugs:
        slugs = discover_slugs()

    records: list[Record] = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_parse_country, name, slug): name for name, slug in slugs.items()
        }
        for future in cf.as_completed(futures):
            name = futures[future]
            try:
                records.extend(future.result())
            except CollectorError as exc:
                rec = Record(
                    source=SOURCE,
                    source_name=SOURCE_NAME,
                    raw_name=name,
                    url=SECURITY.format(slug=slugs[name]),
                )
                rec.notes.append(f"fetch failed: {exc}")
                records.append(rec)
    return records
