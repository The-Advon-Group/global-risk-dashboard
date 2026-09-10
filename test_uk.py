"""Tests for reading the FCDO's advice.

The case these exist for is Somalia. The FCDO records it as
`avoid_all_travel_to_parts`, and its own words in the same document are:

    "FCDO advises against all travel to Somalia, including Somaliland, except
     for the regions of Awdal, Maroodijeh, and Sahil."

That is the whole country with three exceptions. Reading `alert_status` alone
and treating it as a carve-out with a safe remainder published Somalia at
level 1 in run #8, alongside Libya, Iraq, Myanmar, Sudan and the Central
African Republic. Benin and Azerbaijan are the other shape - a genuinely bounded
area inside an otherwise ordinary country - and must keep behaving that way.

The passages below are the FCDO's real wording, read on 10 September 2026.
"""

from __future__ import annotations

from collectors.uk import ALERT_TO_LEVEL, WHOLE_COUNTRY, covers_whole_country

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


SOMALIA = (
    "Areas where FCDO advises against travel Parts of Somalia, including "
    "Somaliland FCDO advises against all travel to Somalia, including "
    "Somaliland, except for the regions of Awdal, Maroodijeh, and Sahil. FCDO "
    "advises against all but essential travel to the regions of Awdal, "
    "Maroodijeh, and Sahil. This is due to the threat from terrorist groups."
)

BENIN = (
    "Areas where FCDO advises against travel Northern Benin FCDO advises "
    "against all travel to the area north of and including the Parc National "
    "de la Pendjari. There have been kidnappings in Benin."
)

AZERBAIJAN = (
    "Areas where FCDO advises against travel FCDO advises against all travel "
    "to the Nagorno-Karabakh region and to areas of Azerbaijan within 5km of "
    "the border with Armenia."
)

GEORGIA = (
    "Areas where FCDO advises against travel South Ossetia and Abkhazia FCDO "
    "advises against all travel to the Russian-occupied regions of South "
    "Ossetia and Abkhazia."
)


def test_whole_country_with_exceptions() -> None:
    print("An advisory that names the country itself")
    check("Somalia is recognised as covering the country",
          covers_whole_country(SOMALIA, "Somalia") is True)

    print("Advisories that name an area inside the country")
    check("Benin stays a carve-out", covers_whole_country(BENIN, "Benin") is False)
    check("Azerbaijan stays a carve-out - the country name appears, but as "
          "'areas of Azerbaijan within 5km'",
          covers_whole_country(AZERBAIJAN, "Azerbaijan") is False)
    check("Georgia stays a carve-out",
          covers_whole_country(GEORGIA, "Georgia") is False)


def test_wording_variants() -> None:
    print("Wordings that mean the same thing")
    for text in (
        "FCDO advises against all travel to Ruritania.",
        "FCDO advises against all travel to the whole of Ruritania.",
        "FCDO advises against all but essential travel to Ruritania, except "
        "for the capital.",
    ):
        check(f"{text[:52]}...", covers_whole_country(text, "Ruritania") is True)

    print("Wordings that do not")
    for text in (
        "FCDO advises against all travel to northern Ruritania.",
        "FCDO advises against all travel to the Ruritania-Syldavia border area.",
        "There have been protests in Ruritania.",
    ):
        check(f"{text[:52]}...", covers_whole_country(text, "Ruritania") is False)


def test_missing_input() -> None:
    print("Nothing to read")
    check("empty text", covers_whole_country("", "Somalia") is False)
    check("empty country name", covers_whole_country(SOMALIA, "") is False)
    check("a country name with regex characters does not blow up",
          covers_whole_country("FCDO advises against all travel to Cote d'Ivoire (Ivory "
                               "Coast).", "Cote d'Ivoire (Ivory Coast)") is True)


def test_alert_vocabulary() -> None:
    print("The FCDO's published vocabulary")
    check("every whole-country value has a level",
          WHOLE_COUNTRY <= set(ALERT_TO_LEVEL), str(WHOLE_COUNTRY - set(ALERT_TO_LEVEL)))
    check("avoid all travel outranks avoid all but essential",
          ALERT_TO_LEVEL["avoid_all_travel_to_whole_country"]
          > ALERT_TO_LEVEL["avoid_all_but_essential_travel_to_whole_country"])
    check("the parts variants carry the same severity as their whole-country twins",
          ALERT_TO_LEVEL["avoid_all_travel_to_parts"]
          == ALERT_TO_LEVEL["avoid_all_travel_to_whole_country"])


if __name__ == "__main__":
    for fn in (test_whole_country_with_exceptions, test_wording_variants,
               test_missing_input, test_alert_vocabulary):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
