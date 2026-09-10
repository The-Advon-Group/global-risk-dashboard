"""Tests for capital-city headline levels.

The regional strings are the real shapes the sources produce - France's
"à l'exception de la ville de Kano" carve-out exception, Canada's
"Calabar and Lagos - Exercise a high degree of caution" regional heading.

The cases that matter most are the two directions of asymmetry:
  * Nigeria, where the capital is SAFER than the worst region, so the headline
    drops and the caveat has to warn upward.
  * Somalia, where the capital IS the dangerous part, so the headline stays
    high and the caveat says the rest is not uniformly that bad.
"""

from __future__ import annotations

from capitals import capital_of, mentioned_in, names_for
from headline import apply_to_row, resolve

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


def rec(level, region=None, label="", name=""):
    return {"level": level, "region": region, "level_label": label, "raw_name": name}


def test_capitals_table() -> None:
    print("Capitals table")
    check("Nigeria -> Abuja", capital_of("NG") == "Abuja")
    check("Myanmar -> Naypyidaw", capital_of("MM") == "Naypyidaw")
    check("lowercase iso works", capital_of("ng") == "Abuja")
    check("unknown code -> None", capital_of("ZZ") is None)
    check("Netherlands aliases include The Hague",
          "The Hague" in names_for("NL"))
    check("Myanmar aliases include Rangoon", "Rangoon" in names_for("MM"))
    check("ISO capital is listed first", names_for("NL")[0] == "Amsterdam")

    check("accent-insensitive match",
          mentioned_in("déplacements à Yaoundé déconseillés", "CM") == "Yaounde")
    check("word-boundary match, no substring hits",
          mentioned_in("the Niamey road", "NE") == "Niamey")
    check("does not match inside another word",
          mentioned_in("Limassol", "PE") is None,
          "Lima must not match inside Limassol")
    check("empty text -> None", mentioned_in("", "NG") is None)


def test_capital_safer_than_country() -> None:
    print("Capital safer than the worst region (Nigeria)")
    records = [
        rec(4, region="Borno, Yobe and Adamawa states", label="Avoid all travel"),
        rec(3, region="Niger Delta states", label="Avoid non-essential travel"),
        rec(2, region="Abuja and Lagos", label="Exercise a high degree of caution"),
    ]
    h = resolve(records, "NG", national_level=4)
    check("headline is the capital's level, not the worst region", h.level == 2,
          f"got {h.level} via {h.basis}")
    check("regional max preserved", h.regional_max == 4, str(h.regional_max))
    check("caveat warns upward", h.caveat and "rated higher" in h.caveat, str(h.caveat))
    check("caveat names the city", h.caveat and "Abuja" in h.caveat, str(h.caveat))
    check("not marked uniform", not h.uniform)


def test_capital_is_the_danger() -> None:
    print("Capital is the dangerous part (Somalia)")
    records = [
        rec(4, region="Mogadishu", label="Avoid all travel"),
        rec(3, region="Somaliland", label="Avoid non-essential travel"),
    ]
    h = resolve(records, "SO", national_level=4)
    check("headline stays at 4", h.level == 4, f"got {h.level}")
    check("caveat points downward", h.caveat and "rated lower" in h.caveat, str(h.caveat))
    check("regional min preserved", h.regional_min == 3, str(h.regional_min))


def test_exception_clause_wins() -> None:
    print("Capital excepted out of a carve-out")
    # France's real shape: a level-4 carve-out that explicitly excepts a city.
    records = [
        rec(4, region="Etats de Borno, Yobe, Jigawa et Kano, "
                      "a l'exception de la ville d'Abuja",
            label="zone rouge - formellement deconseille"),
        rec(2, region="reste du pays", label="zone jaune"),
    ]
    h = resolve(records, "NG", national_level=2)
    check("capital is NOT given the level it was excepted from", h.level != 4,
          f"got {h.level} via {h.basis}")
    check("falls back to a level that is not excluded", h.level == 2,
          f"got {h.level} via {h.basis}")
    check("basis records that an exception was used",
          "excepted" in h.basis, h.basis)
    check("note flags it for verification",
          any("excepts" in n for n in h.notes), str(h.notes))

    # The excluded level must never leak through, even when it is the only
    # national figure on offer.
    h2 = resolve(records, "NG", national_level=4)
    check("excluded level is refused even as the national fallback",
          h2.level != 4, f"got {h2.level} via {h2.basis}")


def test_no_regional_detail() -> None:
    print("Source publishes no regional detail")
    h = resolve([rec(2)], "PL", national_level=2)
    check("falls back to national level", h.level == 2)
    check("basis says so", "no regional detail" in h.basis, h.basis)
    check("uniform country needs no caveat", h.caveat is None, str(h.caveat))

    print("Regions exist but none names the capital")
    records = [rec(4, region="northern border area"), rec(2, region=None)]
    h = resolve(records, "KE", national_level=4)
    check("uses the national level", h.level == 4, f"got {h.level}")
    check("basis is explicit", "no regional record names the capital" in h.basis,
          h.basis)


def test_unknown_capital() -> None:
    print("Territory with no capital on file")
    h = resolve([rec(1)], "ZZ", national_level=1)
    check("still returns a level", h.level == 1)
    check("flags the gap rather than failing",
          any("capital unknown" in n for n in h.notes), str(h.notes))
    check("no caveat invented", h.caveat is None)


def test_apply_to_row() -> None:
    print("Applying to a reconciled row")
    row = {
        "iso2": "NG",
        "name": "Nigeria",
        "sources": {
            "uk": {
                "level": 4,
                "records": [
                    rec(4, region="Borno state"),
                    rec(2, region="Abuja"),
                ],
            },
            "us": {"level": 3, "records": [rec(3)]},
        },
    }
    out = apply_to_row(row)
    uk = out["sources"]["uk"]
    check("uk headline dropped to the capital", uk["level"] == 2, str(uk["level"]))
    check("previous roll-up kept as country_high", uk["country_high"] == 4,
          str(uk["country_high"]))
    check("caveat attached", bool(uk["caveat"]))
    check("capital recorded on the bucket", uk["capital"] == "Abuja")
    us = out["sources"]["us"]
    check("source with no regions keeps its level", us["level"] == 3)
    check("uniform source carries no caveat", us["caveat"] is None)


def test_no_undefined() -> None:
    print("No undefined leaks")
    import json
    row = {"iso2": "NG", "name": "Nigeria",
           "sources": {"fr": {"level": None, "records": [rec(None, region="x")]}}}
    blob = json.dumps(apply_to_row(row))
    check("no 'undefined' in output", "undefined" not in blob.lower())
    check("null level survives as null",
          apply_to_row(row)["sources"]["fr"]["level"] is None)


if __name__ == "__main__":
    for fn in (test_capitals_table, test_capital_safer_than_country,
               test_capital_is_the_danger, test_exception_clause_wins,
               test_no_regional_detail, test_unknown_capital,
               test_apply_to_row, test_no_undefined):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
