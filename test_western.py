"""Tests for the Advon synthesis column and the parts/whole-country fix.

The two anchor cases are the ones that motivated the whole design:

  Burkina Faso  FCDO avoid_all_travel_to_WHOLE_COUNTRY   -> 4 everywhere
  Azerbaijan    FCDO avoid_all_travel_to_PARTS           -> low baseline,
                                                            named zones high

Before the fix both published as 4. Levels below are the real ones: the US
rates Azerbaijan 3 and Burkina Faso 4, and the FCDO's alert_status values are
verbatim from the Content API on 10 September 2026.
"""

from __future__ import annotations

from western import PASSPORT_SPECIFIC, apply_to_row, synthesise

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


def test_anchor_cases() -> None:
    print("The two cases that motivated this")
    # Azerbaijan: capital-level per source after the parts fix.
    az = synthesise({"us": 3, "uk": 1, "ca": 2, "fr": 2}, country_name="Azerbaijan")
    check("Azerbaijan consensus is 2, not 4", az.level == 2,
          f"got {az.level} - {az.basis}")
    check("Azerbaijan range published", (az.range_low, az.range_high) == (1, 3),
          f"{az.range_low}-{az.range_high}")
    check("Azerbaijan flagged as divergent", az.divergent)
    check("Azerbaijan carries a range caveat", bool(az.caveat), str(az.caveat))

    bf = synthesise({"us": 4, "uk": 4, "ca": 4, "fr": 4}, country_name="Burkina Faso")
    check("Burkina Faso is 4", bf.level == 4)
    check("Burkina Faso not divergent", not bf.divergent)
    check("uniform country carries no range caveat", bf.caveat is None, str(bf.caveat))
    check("the two no longer publish the same number", az.level != bf.level)


def test_consensus_rules() -> None:
    print("Consensus")
    w = synthesise({"us": 2, "uk": 2, "ca": 2, "fr": 3})
    check("majority wins", w.level == 2, f"got {w.level}")
    check("agreement count reported", w.agreement == 3, str(w.agreement))

    w = synthesise({"us": 4, "uk": 1, "ca": 1, "fr": 1})
    check("one alarmist source cannot drag the consensus", w.level == 1,
          f"got {w.level}")
    check("but the outlier still shows in the range", w.range_high == 4)

    w = synthesise({"us": 2, "uk": 2, "ca": 3, "fr": 3})
    check("ties resolve to the more cautious level", w.level == 3, f"got {w.level}")
    check("tie-break is stated in the basis", "cautious" in w.basis, w.basis)

    w = synthesise({"us": 1, "uk": 1, "ca": 1, "fr": 1})
    check("unanimous is unanimous", w.level == 1 and not w.divergent)
    check("no fractional levels ever", isinstance(w.level, int))


def test_thin_data() -> None:
    print("Not enough sources")
    w = synthesise({"us": 2, "uk": None, "ca": None, "fr": None})
    check("fewer than 3 usable -> Unrated", w.label == "Unrated", str(w.label))
    check("level is None, not 0", w.level is None)
    check("reason stated", "required" in w.basis, w.basis)

    w = synthesise({"us": 2, "uk": 2, "ca": 2, "fr": None})
    check("exactly 3 usable is enough", w.level == 2, f"got {w.level}")
    check("the absent source is not counted as agreement", w.agreement == 3)


def test_passport_specific_stays_out() -> None:
    print("Passport-specific risk is not averaged in")
    w = synthesise(
        {"us": 2, "uk": 2, "ca": 2, "fr": 2},
        indicators={"us": ["C", "T", "D"], "uk": [], "ca": [], "fr": []},
        country_name="Somewhere",
    )
    check("level unaffected by the D indicator", w.level == 2)
    check("wrongful detention surfaced as a flag",
          any(f["code"] == "D" for f in w.passport_flags), str(w.passport_flags))
    check("flag names the source", w.passport_flags[0]["source"] == "us")
    check("flag explains it is passport-dependent",
          "passport" in w.passport_flags[0]["note"])

    w2 = synthesise({"us": 2, "uk": 2, "ca": 2, "fr": 2},
                    indicators={"us": ["C", "T", "U"]})
    check("ambient indicators raise no passport flag", w2.passport_flags == [],
          str(w2.passport_flags))
    check("K is treated as passport-specific", "K" in PASSPORT_SPECIFIC)


def test_divergence_note() -> None:
    print("Divergence")
    w = synthesise({"us": 4, "uk": 2, "ca": 2, "fr": 2}, country_name="Testland")
    check("2-level gap flags divergent", w.divergent)
    check("note explains it may be real, not disagreement",
          any("its own nationals" in n for n in w.notes), str(w.notes))
    check("note lists each source's level",
          any("US 4" in n for n in w.notes), str(w.notes))

    w = synthesise({"us": 3, "uk": 2, "ca": 2, "fr": 2})
    check("1-level gap is not divergent", not w.divergent)
    check("but the range is still published", (w.range_low, w.range_high) == (2, 3))


def test_apply_to_row() -> None:
    print("Applying to a row")
    row = {
        "iso2": "AZ", "name": "Azerbaijan",
        "sources": {
            "us": {"level": 3, "records": [{"indicators": ["T", "O"]}]},
            "uk": {"level": 1, "records": [{"indicators": []}]},
            "ca": {"level": 2, "records": [{"indicators": []}]},
            "fr": {"level": 2, "records": [{"indicators": []}]},
        },
    }
    out = apply_to_row(row)
    check("advon column attached", "advon" in out)
    check("consensus is 2", out["advon"]["level"] == 2, str(out["advon"]["level"]))
    check("marked as our synthesis", out["advon"]["synthesis"] is True)
    check("source levels preserved untouched",
          out["sources"]["us"]["level"] == 3)
    check("contributing levels recorded",
          out["advon"]["contributing"] == {"us": 3, "uk": 1, "ca": 2, "fr": 2},
          str(out["advon"]["contributing"]))

    import json
    check("no 'undefined' in output", "undefined" not in json.dumps(out).lower())


def test_uk_parts_fix() -> None:
    print("UK parts vs whole-country")
    import collectors.uk as uk

    check("whole-country statuses map to the carve level",
          uk.ALERT_TO_LEVEL["avoid_all_travel_to_whole_country"] == 4)
    check("residual level defined for parts-only advisories",
          uk.RESIDUAL_LEVEL == 1)
    check("whole-country set contains both whole variants",
          uk.WHOLE_COUNTRY == {
              "avoid_all_travel_to_whole_country",
              "avoid_all_but_essential_travel_to_whole_country",
          }, str(uk.WHOLE_COUNTRY))

    region = uk._carve_region({
        "parts": [{
            "slug": "warnings-and-insurance",
            "body": "<h2>Areas where FCDO advises against travel</h2>"
                    "<h3>Azerbaijan-Armenia border</h3><p>within 5km</p>"
                    "<h3>South-western Azerbaijan</h3><p>conflict areas</p>"
                    "<h2>Limited consular support</h2>",
        }]
    })
    check("named exclusion zones extracted",
          region == "Azerbaijan-Armenia border; South-western Azerbaijan", str(region))
    check("boilerplate headings excluded",
          region and "Areas where" not in region and "consular" not in region)





def test_disclosure_travels_with_the_number() -> None:
    print("Synthesis disclosure")
    from western import DISCLOSURES
    from validate import validate

    row = {"iso2": "AZ", "name": "Azerbaijan", "sources": {
        s: {"level": l, "url": "u", "retrieved_at": "t", "records": [{}]}
        for s, l in (("us", 3), ("uk", 1), ("ca", 2), ("fr", 2))}}
    apply_to_row(row)
    d = row["advon"]["disclosure"]

    check("disclosure rides on the row", bool(d))
    check("label names the synthesis, not a government",
          "Advon" in d["label"], d["label"])
    check("sublabel names all four sources",
          all(x in d["sublabel"] for x in ("US", "UK", "Canada", "France")), d["sublabel"])
    check("column note says it is not any one government's rating",
          "not any one government" in d["column_note"], d["column_note"])
    check("frame note states the Western-source limit",
          "Western" in d["frame_note"] and "nationality" in d["frame_note"],
          d["frame_note"])

    ok = validate({"AZ": row}, {"us": {"ok": True}}, [], ["us", "uk", "ca", "fr"])
    check("complete disclosure passes validation",
          not [f for f in ok["blocking"] if "synthesis" in f["code"]],
          str(ok["blocking"]))

    stripped = {"AZ": {**row, "advon": {**row["advon"], "disclosure": {}}}}
    bad = validate(stripped, {"us": {"ok": True}}, [], ["us", "uk", "ca", "fr"])
    check("stripping the disclosure blocks the publish",
          any(f["code"] == "missing_synthesis_disclosure" for f in bad["blocking"]),
          str([f["code"] for f in bad["blocking"]]))

    unmarked = {"AZ": {**row, "advon": {**row["advon"], "synthesis": False}}}
    bad2 = validate(unmarked, {"us": {"ok": True}}, [], ["us", "uk", "ca", "fr"])
    check("an unmarked synthesis blocks the publish",
          any(f["code"] == "synthesis_not_marked" for f in bad2["blocking"]))


if __name__ == "__main__":
    for fn in (test_anchor_cases, test_consensus_rules, test_thin_data,
               test_passport_specific_stays_out, test_divergence_note,
               test_apply_to_row, test_uk_parts_fix,
               test_disclosure_travels_with_the_number):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
