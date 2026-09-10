"""Offline tests.

The collectors themselves need the live internet, which this build environment
does not have, so these tests exercise the parts that actually decide whether
the dashboard is correct - name reconciliation, roll-up, divergence detection,
validation - against fixtures taken from the real source payloads captured on
8 Sep 2026. The HTML fixture below is the genuine row markup from the State
Department advisories page, not an invented approximation.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from collectors.base import Record
from countries import Spine, normalise, resolve, resolve_all, roll_up
from validate import validate

# --- fixtures -------------------------------------------------------------

CANADA_FIXTURE = {
    "metadata": {"generated": {"date": "2026-09-07 14:40:16"}},
    "data": {
        "AF": {"country-eng": "Afghanistan", "country-fra": "Afghanistan",
               "advisory-state": 3, "has-regional-advisory": 0,
               "date-published": {"date": "2026-09-01 09:10:12"},
               "eng": {"url-slug": "afghanistan", "advisory-text": "Avoid all travel"}},
        "DZ": {"country-eng": "Algeria", "country-fra": "Algérie",
               "advisory-state": 1, "has-regional-advisory": 1,
               "date-published": {"date": "2026-09-01 09:05:38"},
               "eng": {"url-slug": "algeria",
                       "advisory-text": "Exercise a high degree of caution (with regional advisories)"}},
        "MM": {"country-eng": "Myanmar", "country-fra": "Myanmar",
               "advisory-state": 3, "date-published": {"date": "2026-05-08 00:00:00"},
               "eng": {"url-slug": "myanmar", "advisory-text": "Avoid all travel"}},
        "CD": {"country-eng": "Democratic Republic of Congo",
               "country-fra": "République démocratique du Congo",
               "advisory-state": 3, "date-published": {"date": "2026-07-15 00:00:00"},
               "eng": {"url-slug": "congo-kinshasa", "advisory-text": "Avoid all travel"}},
        "CI": {"country-eng": "Côte d'Ivoire", "country-fra": "Côte d'Ivoire",
               "advisory-state": 1, "date-published": {"date": "2026-02-18 00:00:00"},
               "eng": {"url-slug": "cote-divoire", "advisory-text": "Exercise a high degree of caution"}},
        "GB": {"country-eng": "United Kingdom", "country-fra": "Royaume-Uni",
               "advisory-state": 0, "date-published": {"date": "2026-05-08 00:00:00"},
               "eng": {"url-slug": "united-kingdom", "advisory-text": "Exercise normal security precautions"}},
        "NG": {"country-eng": "Nigeria", "country-fra": "Nigéria",
               "advisory-state": 2, "has-regional-advisory": 1,
               "date-published": {"date": "2026-08-03 00:00:00"},
               "eng": {"url-slug": "nigeria", "advisory-text": "Avoid non-essential travel"}},
        "BQ": {"country-eng": "Caribbean Netherlands",
               "country-fra": "Pays-Bas caribéens", "advisory-state": 0,
               "date-published": {"date": "2026-08-20 00:00:00"},
               "eng": {"url-slug": "caribbean-netherlands",
                       "advisory-text": "Exercise normal security precautions"}},
        "VA": {"country-eng": "Vatican City", "country-fra": "Cité du Vatican",
               "advisory-state": 0, "date-published": {"date": "2026-05-23 00:00:00"},
               "eng": {"url-slug": "vatican", "advisory-text": "Exercise normal security precautions"}},
    },
}

# Verbatim markup from travel.state.gov, captured 8 Sep 2026.
US_ROW_HTML = """
<table class="usa-table usa-table--destination usa-table--stacked-header usa-table--striped">
<thead><tr><th>Destination</th><th>Level</th><th>Risk Indicators</th><th>Date Issued</th></tr></thead>
<tbody>
<tr>
  <th class="cell" data-label="Destination" scope="row">
    <a href="/en/international-travel/travel-advisories/afghanistan.html">Afghanistan</a></th>
  <td class="cell" data-label="Level"><p class="level-title level-title-4">Level 4: Do not travel</p></td>
  <td class="cell" data-label="Risk Indicators">
    <div class="tsg-utility-risk-pill-container">
      <span class="tsg-utility-risk-pill">UNREST (U)</span>
      <span class="tsg-utility-risk-pill">TERRORISM (T)</span>
    </div></td>
  <td class="cell" data-label="Date Issued">02/20/2026</td>
</tr>
<tr>
  <th class="cell" data-label="Destination" scope="row">
    <a href="/en/international-travel/travel-advisories/burma.html">Burma (Myanmar)</a></th>
  <td class="cell" data-label="Level"><p class="level-title level-title-4">Level 4: Do not travel</p></td>
  <td class="cell" data-label="Risk Indicators"><div class="tsg-utility-risk-pill-container">
      <span class="tsg-utility-risk-pill">CRIME (C)</span></div></td>
  <td class="cell" data-label="Date Issued">05/08/2026</td>
</tr>
<tr>
  <th class="cell" data-label="Destination" scope="row">
    <a href="/en/international-travel/travel-advisories/andorra.html">Andorra</a></th>
  <td class="cell" data-label="Level"><p class="level-title level-title-1">Level 1: Exercise normal precautions</p></td>
  <td class="cell" data-label="Risk Indicators"></td>
  <td class="cell" data-label="Date Issued">05/21/2026</td>
</tr>
</tbody></table>
"""

# The genuinely awkward names, exactly as each source spells them.
AWKWARD = {
    "Burma (Myanmar)": "MM",
    "Côte d'Ivoire (Ivory-Coast)": "CI",
    "Democratic Republic of the Congo (D.R.C.)": "CD",
    "United Kingdom of Great Britain and Northern Ireland": "GB",
    "The Gambia": "GM",
    "The Kyrgyz Republic": "KG",
    "Vatican City (Holy See)": "VA",
    "Bonaire, Sint Eustatius, and Saba": "BQ",
    "Saba and Sint Eustatius": "BQ",
    "Bonaire": "BQ",
    "Republic of North Macedonia": "MK",
    "Martinique (French West Indies)": "MQ",
    "Nigéria": "NG",        # French spelling, resolved via Canada's bilingual spine
    "Algérie": "DZ",
    "Royaume-Uni": "GB",
}

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


def test_normalise() -> None:
    print("normalise()")
    check("strips accents", normalise("Côte d'Ivoire") == "cote divoire",
          normalise("Côte d'Ivoire"))
    check("drops parentheticals", normalise("Burma (Myanmar)") == "burma",
          normalise("Burma (Myanmar)"))
    check("drops leading 'the'", normalise("The Gambia") == "gambia")
    check("Niger and Nigeria stay distinct", normalise("Niger") != normalise("Nigeria"))


def test_canada_levels() -> None:
    print("Canada level mapping")
    from collectors import canada as ca

    # Exercise the pure mapping without touching the network.
    for iso2, entry in CANADA_FIXTURE["data"].items():
        state = entry["advisory-state"]
        expected = state + 1
        text_level = ca._level_from_text(entry["eng"]["advisory-text"])
        check(f"{iso2}: state {state} -> level {expected}",
              text_level == expected,
              f"text gave {text_level}")


def test_us_parser() -> None:
    print("US HTML parser")
    import re
    soup = BeautifulSoup(US_ROW_HTML, "html.parser")
    table = soup.select_one("table.usa-table--destination")
    check("finds the destination table", table is not None)
    rows = table.find("tbody").find_all("tr")
    check("finds 3 rows", len(rows) == 3, f"got {len(rows)}")

    LEVEL_CLASS = re.compile(r"level-title-(\d)")
    parsed = []
    for tr in rows:
        el = tr.find(class_=LEVEL_CLASS)
        m = LEVEL_CLASS.search(" ".join(el.get("class", [])))
        pills = [
            re.search(r"\(([A-Z])\)\s*$", p.get_text(strip=True)).group(1)
            for p in tr.select(".tsg-utility-risk-pill")
        ]
        parsed.append((tr.find("a").get_text(strip=True), int(m.group(1)), pills))

    check("Afghanistan level 4 with U+T", parsed[0] == ("Afghanistan", 4, ["U", "T"]),
          str(parsed[0]))
    check("Andorra level 1 with no indicators", parsed[2] == ("Andorra", 1, []),
          str(parsed[2]))


def test_reconciliation() -> None:
    print("Country reconciliation")
    spine = Spine.from_canada(CANADA_FIXTURE)
    # 9 from the fixture, plus CA, US and FR seeded (GB is already in it).
    check("spine built from Canada", len(spine.by_iso) == 12, str(len(spine.by_iso)))

    # Canada publishes no advice about Canada, so the spine has a hole where
    # Canada should be. The first live run found this as the FCDO's "Canada"
    # failing to resolve.
    check("Canada is in the spine despite not being in its own feed",
          resolve("Canada", spine).iso2 == "CA")
    for name, code in (("United States", "US"), ("France", "FR"),
                       ("Royaume-Uni", "GB")):
        check(f"source country {name!r} resolves", resolve(name, spine).iso2 == code,
              f"got {resolve(name, spine).iso2}")

    for name, expected in AWKWARD.items():
        res = resolve(name, spine)
        check(f"{name!r} -> {expected}", res.iso2 == expected,
              f"got {res.iso2} via {res.method}")

    # The trap this whole module exists to avoid.
    res = resolve("Niger", spine)
    check("'Niger' does not resolve to Nigeria", res.iso2 != "NG",
          f"got {res.iso2}")

    res = resolve("Wakanda", spine)
    check("unknown name is reported, not guessed", res.iso2 is None, str(res))


def test_rollup() -> None:
    print("Regional roll-up")
    check("takes the highest region", roll_up([1, 3, 2]) == 3)
    check("ignores None rather than zeroing", roll_up([None, 2]) == 2)
    check("all-None stays unrated", roll_up([None, None]) is None)
    check("empty stays unrated", roll_up([]) is None)


def _row(iso2: str, name: str, levels: dict[str, int | None]) -> dict:
    return {
        "iso2": iso2,
        "name": name,
        "sources": {
            src: {
                "level": lvl,
                "url": f"https://example.invalid/{src}/{iso2}",
                "retrieved_at": "2026-09-08T13:00:00+00:00",
                "records": [],
            }
            for src, lvl in levels.items()
        },
    }


def test_validation() -> None:
    print("Validation")
    countries = {
        "NG": _row("NG", "Nigeria", {"us": 3, "ca": 3, "uk": 4}),
        "TH": _row("TH", "Thailand", {"us": 2, "ca": 1, "uk": 4}),   # 3-level spread
        "AD": _row("AD", "Andorra", {"us": 1}),
        "XX": _row("XX", "", {"us": 1}),                              # missing name
    }
    status = {"us": {"ok": True, "count": 4}, "ca": {"ok": True, "count": 3},
              "uk": {"ok": True, "count": 3}, "fr": {"ok": False, "error": "timeout"}}
    report = validate(countries, status, [{"source": "uk", "name": "Wakanda",
                                           "reason": "no match"}], ["us", "ca", "uk", "fr"])

    check("empty name is blocking", any(f["code"] == "missing_required_field"
                                        for f in report["blocking"]))
    check("divergence detected", any(d["iso2"] == "TH" for d in report["divergent"]),
          str(report["divergent"]))
    check("widest spread ranked first", report["divergent"][0]["iso2"] == "TH")
    check("unmapped name reported", any(f["code"] == "unmapped_name"
                                        for f in report["warnings"]))
    check("failed source listed", report["sources_failed"] == ["fr"],
          str(report["sources_failed"]))
    check("France counted as unrated everywhere", report["unrated"].get("fr") == 4,
          str(report["unrated"]))

    # The whole point: nothing renders as undefined.
    blob = json.dumps(report)
    check("no 'undefined' anywhere in the report", "undefined" not in blob.lower())


def test_record_shape() -> None:
    print("Record shape")
    rec = Record(source="us", source_name="State", raw_name="Nigeria",
                 url="https://example.invalid")
    d = rec.as_dict()
    for key in ("source", "raw_name", "url", "retrieved_at", "level", "notes"):
        check(f"record has {key}", key in d)
    check("level defaults to None not 0", d["level"] is None)
    check("no empty-string placeholders", "" not in
          [v for v in d.values() if isinstance(v, str)])




def test_live_run_gaps() -> None:
    """Names the first live run could not resolve, 10 Sep 2026."""
    print("Unmapped names from the live run")
    spine = Spine.from_canada(CANADA_FIXTURE)
    for name, code in [
        ("Western Sahara", "EH"), ("USA", "US"), ("Israel", "IL"),
        ("Palestine", "PS"), ("Federated States of Micronesia", "FM"),
        ("Wallis and Futuna", "WF"), ("St Pierre & Miquelon", "PM"),
        ("St Maarten", "SX"), ("Pitcairn Island", "PN"),
        ("British Indian Ocean Territory", "IO"),
        ("South Georgia and the South Sandwich Islands", "GS"),
    ]:
        check(f"{name!r} -> {code}", resolve(name, spine).iso2 == code,
              f"got {resolve(name, spine).iso2}")


def test_multi_country_pages() -> None:
    """One source page covering several countries must reach all of them."""
    print("Multi-country source pages")
    spine = Spine.from_canada(CANADA_FIXTURE)

    got = [r.iso2 for r in resolve_all("Cook Islands, Tokelau and Niue", spine)]
    check("FCDO's combined Pacific page reaches all three",
          got == ["CK", "TK", "NU"], str(got))
    check("each carries a note explaining the shared page",
          all(r.note and "covering" in r.note
              for r in resolve_all("Cook Islands, Tokelau and Niue", spine)))

    got = [r.iso2 for r in resolve_all("St Martin and St Barthelemy", spine)]
    check("St Martin and St Barthelemy reach both", got == ["MF", "BL"], str(got))

    got = [r.iso2 for r in resolve_all("Nigeria", spine)]
    check("an ordinary name still resolves to exactly one", got == ["NG"], str(got))


def test_ambiguous_never_guessed() -> None:
    """'Congo' must never be resolved by guessing which one."""
    print("Ambiguous names")
    spine = Spine.from_canada(CANADA_FIXTURE)
    res = resolve_all("Congo", spine)
    check("Congo resolves to nothing", [r.iso2 for r in res] == [None], str(res))
    check("and says why", res[0].note and "ambiguous" in res[0].note.lower(),
          str(res[0].note))
    check("the specific ones still work",
          resolve("Democratic Republic of the Congo (D.R.C.)", spine).iso2 == "CD"
          and resolve("Republic of the Congo", spine).iso2 == "CG")


def test_france_slugs() -> None:
    """Slug derivation, verified against all 197 live entries on 10 Sep 2026."""
    print("France slug derivation")
    from collectors.france import slugify
    for label, expect in [
        ("Afghanistan", "afghanistan"),
        ("Afrique du Sud", "afrique-du-sud"),
        ("Burkina Faso", "burkina-faso"),
        ("Vatican (Saint-Siege)", "vatican-saint-siege"),
    ]:
        check(f"{label!r} -> {expect}", slugify(label) == expect, slugify(label))


if __name__ == "__main__":
    for fn in (test_normalise, test_canada_levels, test_us_parser,
               test_reconciliation, test_rollup, test_validation, test_record_shape,
               test_live_run_gaps, test_multi_country_pages,
               test_ambiguous_never_guessed, test_france_slugs):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
