"""Tests for the run report.

The report exists because the fourth dry run produced a log nobody could read.
So the things worth testing are the things that made it unreadable: repetition,
and useful output being crowded out or dropped entirely.
"""

from __future__ import annotations

from report import format_report

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


def sample_report() -> dict:
    unmapped = [{"source": "fr", "name": "Birmanie", "reason": "no match for 'Birmanie'"}] * 3
    unmapped += [{"source": "fr", "name": "Irak", "reason": "no match for 'Irak'"}]
    unmapped += [{"source": "uk", "name": "Congo", "reason": "ambiguous between CG and CD"}] * 2
    return {
        "blocking": [{"level": "blocking", "code": "missing_spread_caveat",
                      "detail": "EH/uk: no caveat was built"}],
        "warnings": [
            {"level": "warning", "code": "unmapped_name", "detail": "fr: no match for 'Irak'"},
            {"level": "warning", "code": "missing_source_field",
             "detail": "VU/fr: 'url' is empty"},
        ],
        "unmapped_names": unmapped,
        "divergent": [{"iso2": "AZ", "name": "Azerbaijan", "spread": 2,
                       "levels": {"ca": 2, "uk": 4}}],
        "summary": ["231 countries reconciled", "ca: 230/231 rows (100%), 0 unrated"],
        "coverage": {"ca": 230},
        "unrated": {},
        "sources_working": ["ca"],
        "sources_failed": ["us"],
    }


def test_repetition_collapses() -> None:
    print("Repeated warnings are counted, not repeated")
    text = format_report(sample_report(), {"ca": {"ok": True, "count": 230}})
    check("Birmanie appears once", text.count("Birmanie") == 1,
          f"appeared {text.count('Birmanie')} times")
    check("its count is shown", "(x3)" in text, text)
    check("a single occurrence carries no count suffix",
          "no match for 'Irak'  (x" not in text)


def test_blocking_printed_in_full() -> None:
    print("Blocking findings are never abbreviated")
    text = format_report(sample_report(), {})
    check("the finding's detail is present", "EH/uk: no caveat was built" in text)
    check("the code is present", "missing_spread_caveat" in text)

    clean = dict(sample_report(), blocking=[])
    text2 = format_report(clean, {})
    check("a clean run says so explicitly", "BLOCKING (0)" in text2 and "none" in text2)


def test_failed_source_is_visible() -> None:
    print("A failed source states its reason")
    status = {"us": {"ok": False, "error": "HTTP 403 from travel.state.gov", "count": 0},
              "ca": {"ok": True, "count": 230}}
    text = format_report(sample_report(), status)
    check("failure is named", "us: FAILED" in text)
    check("reason is carried", "HTTP 403" in text)
    check("working source shows its count", "ca: 230 records" in text)


def test_probe_always_prints() -> None:
    print("The US probe reaches the log")
    probe = {
        "list_page": {"status": 403, "usable": False,
                      "note": "refused as automated traffic - not circumvented by design"},
        "open_data_xml": {"status": 200, "usable": True, "bytes": 900,
                          "note": "228 country elements"},
        "_summary": {"open": ["open_data_xml"], "closed": ["list_page"]},
    }
    text = format_report(sample_report(), {}, probe=probe)
    check("closed route is shown", "CLOSED" in text and "list_page" in text)
    check("open route is shown", "OPEN" in text and "open_data_xml" in text)
    check("the refusal note survives", "not circumvented by design" in text)
    check("usable routes are summarised", "usable routes: open_data_xml" in text)

    shut = {"list_page": {"status": 403, "usable": False, "note": "refused"},
            "_summary": {"open": [], "closed": ["list_page"]}}
    text2 = format_report(sample_report(), {}, probe=shut)
    check("all-closed says the column cannot be built",
          "the US column cannot be built" in text2)


def test_stays_short() -> None:
    print("The report does not grow with repetition")
    small = format_report(sample_report(), {})
    big_data = sample_report()
    big_data["unmapped_names"] = big_data["unmapped_names"] * 40
    big = format_report(big_data, {})
    check("40x the occurrences does not lengthen the report much",
          len(big) < len(small) + 60, f"{len(small)} -> {len(big)}")


def test_no_probe_no_section() -> None:
    print("Sections that have nothing to say are absent")
    text = format_report(sample_report(), {})
    check("no probe section without a probe", "US ROUTE PROBE" not in text)
    check("no japan line without japan status", "JAPAN:" not in text)


if __name__ == "__main__":
    for fn in (test_repetition_collapses, test_blocking_printed_in_full,
               test_failed_source_is_visible, test_probe_always_prints,
               test_stays_short, test_no_probe_no_section):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
