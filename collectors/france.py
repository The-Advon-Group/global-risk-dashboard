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
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import USER_AGENT, CollectorError, Record, get

ROOT = "https://www.diplomatie.gouv.fr"
INDEX = f"{ROOT}/fr/information-par-pays"
SECURITY = f"{ROOT}/fr/information-par-pays/{{slug}}/conseils-aux-voyageurs-securite"
SLUG_CACHE = Path(__file__).resolve().parent.parent / "data" / "fr_slugs.json"

SOURCE = "fr"
SOURCE_NAME = "Ministere de l'Europe et des Affaires etrangeres - Conseils aux voyageurs"

# France's colour bands, highest first so the first match wins.
ZONE_BANDS = [
    (4, re.compile(r"zones?\s+formellement\s+d[ée]conseill", re.I), "zone rouge - formellement deconseille"),
    (3, re.compile(r"d[ée]conseill\w*\s+sauf\s+raison\s+imp[ée]rative", re.I), "zone orange - deconseille sauf raison imperative"),
    (2, re.compile(r"vigilance\s+renforc[ée]e", re.I), "zone jaune - vigilance renforcee"),
    (1, re.compile(r"vigilance\s+normale", re.I), "zone verte - vigilance normale"),
]

UPDATED = re.compile(r"[Dd]erni[èe]re\s+actualisation\s+le\s+([0-9]{2}/[0-9]{2}/[0-9]{4})")
STILL_VALID = re.compile(r"information\s+toujours\s+valable\s+[àa]\s+la\s+date\s+du\s+jour", re.I)


def _load_slug_cache() -> dict[str, str]:
    if SLUG_CACHE.exists():
        return json.loads(SLUG_CACHE.read_text(encoding="utf-8"))
    return {}


def discover_slugs(save: bool = True) -> dict[str, str]:
    """Resolve France's internal node ids to URL slugs.

    The country picker is a Drupal POST form carrying opaque numeric ids; the
    server answers with a redirect to the real slug. We walk it once and cache
    the result, because the mapping changes about as often as the country list
    does. Run with --refresh-fr-slugs to rebuild.
    """
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    page = session.get(INDEX, timeout=45)
    soup = BeautifulSoup(page.text, "html.parser")
    select = soup.find("select", {"name": "select_pays"})
    if select is None:
        raise CollectorError("France country picker not found on the index page")

    form = select.find_parent("form")
    hidden = {
        i.get("name"): i.get("value", "")
        for i in (form.find_all("input", {"type": "hidden"}) if form else [])
        if i.get("name")
    }

    mapping: dict[str, str] = {}
    for option in select.find_all("option"):
        value = (option.get("value") or "").strip()
        label = option.get_text(strip=True)
        if not value:
            continue
        payload = dict(hidden)
        payload["select_pays"] = value
        try:
            resp = session.post(INDEX, data=payload, timeout=45, allow_redirects=True)
        except requests.RequestException:
            continue
        match = re.search(r"/fr/information-par-pays/([a-z0-9-]+)", resp.url)
        if match:
            mapping[label] = match.group(1)

    if not mapping:
        raise CollectorError("France slug discovery resolved zero countries")
    if save:
        SLUG_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SLUG_CACHE.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
    return mapping


def _parse_country(name: str, slug: str) -> list[Record]:
    url = SECURITY.format(slug=slug)
    html = get(url).text
    soup = BeautifulSoup(html, "html.parser")

    for junk in soup.select("script, style, nav, header, footer"):
        junk.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" "))

    updated = UPDATED.search(text)
    still_valid = bool(STILL_VALID.search(text))

    found: list[tuple[int, str]] = []
    for level, pattern, label in ZONE_BANDS:
        if pattern.search(text):
            found.append((level, label))

    records: list[Record] = []
    if not found:
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

    for level, label in found:
        rec = Record(
            source=SOURCE,
            source_name=SOURCE_NAME,
            raw_name=name,
            url=url,
            level=level,
            level_label=label,
            level_basis="France colour band stated in the 'Zones de vigilance' section",
            region=None if len(found) == 1 else label,
            source_updated=updated.group(1) if updated else None,
        )
        if still_valid:
            rec.notes.append("source states information still valid as of today")
        records.append(rec)
    return records


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
