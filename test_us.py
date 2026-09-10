"""Tests for reading State's advisory feed.

The fixture is the real shape of travel.state.gov/_res/rss/TAsTWs.xml, read on
10 September 2026: 216 items, a level in every title and again as a category,
and the risk indicators present only as prose in the summary.

The cases that matter are the ones the live feed actually contains: two title
wordings, a country with no "due to" clause at all, a multi-country title, and
an item whose category list does not end in "advisory" - filtering on that
category would have dropped Yemen and Greenland.
"""

from __future__ import annotations

from collectors.us import TITLE, _indicators_from, _plain

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


def title(text: str):
    return TITLE.match(text)


def test_title_wordings() -> None:
    print("Both title wordings in the live feed")
    m = title("Suriname - Level 1: Exercise Normal Precautions")
    check("plain title parses", m is not None)
    check("name", m and m.group("name") == "Suriname", m and m.group("name"))
    check("level", m and m.group("level") == "1")
    check("label", m and m.group("label") == "Exercise Normal Precautions")

    m2 = title("Mexico Travel Advisory - Level 2: Exercise Increased Caution")
    check("'Travel Advisory' wording parses", m2 is not None)
    check("the suffix is still in the raw name for the caller to strip",
          m2 and m2.group("name") == "Mexico Travel Advisory", m2 and m2.group("name"))

    m3 = title("Mainland China, Hong Kong & Macau - Level 2: Exercise Increased Caution")
    check("multi-country title keeps its whole name",
          m3 and m3.group("name") == "Mainland China, Hong Kong & Macau",
          m3 and m3.group("name"))

    check("an item with no level does not parse",
          title("Worldwide Caution") is None)
    check("a level above 4 does not parse",
          title("Nowhere - Level 5: Invented") is None)


def test_indicators_from_prose() -> None:
    print("Indicators read out of the 'due to' clause")
    got = _indicators_from(
        "Reconsider travel to Nigeria due to crime, terrorism, unrest, "
        "kidnapping, and inconsistent access to healthcare."
    )
    check("crime found", "C" in got, str(got))
    check("terrorism found", "T" in got, str(got))
    check("unrest found", "U" in got, str(got))
    check("kidnapping found", "K" in got, str(got))

    check("no clause means no indicators, not a guess",
          _indicators_from("Suriname is generally a safe destination.") == [])

    check("wrongful detention wording is recognised",
          _indicators_from(
              "Exercise increased caution due to the arbitrary enforcement of "
              "local laws, the use of exit bans, and the risk of unjust arrest "
              "or detention.") == ["D"])

    print("The clause is the scope, not the whole summary")
    got2 = _indicators_from(
        "Exercise normal precautions in Ruritania. Petty crime occurs in the "
        "capital. There was no change to the advisory level."
    )
    check("crime mentioned outside a 'due to' clause does not raise the flag",
          got2 == [], str(got2))


def test_plain_text() -> None:
    print("Summaries arrive as HTML")
    out = _plain("Exercise normal precaution<p>in <b>Suriname</b>.</p>&nbsp;Review this.")
    check("tags removed", "<" not in out and ">" not in out, out)
    check("entities removed", "&nbsp;" not in out, out)
    check("words survive", "Suriname" in out and "Review this" in out, out)
    check("no double spacing", "  " not in out, repr(out))


def test_indicator_letters_are_states() -> None:
    print("Inferred letters stay inside State's own vocabulary")
    from collectors.us import INDICATOR_NAMES, INDICATOR_PHRASES
    letters = {letter for letter, _ in INDICATOR_PHRASES}
    check("every inferred letter is one State publishes",
          letters <= set(INDICATOR_NAMES), str(letters - set(INDICATOR_NAMES)))


if __name__ == "__main__":
    for fn in (test_title_wordings, test_indicators_from_prose, test_plain_text,
               test_indicator_letters_are_states):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
