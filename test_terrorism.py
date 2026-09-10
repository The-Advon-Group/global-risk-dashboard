"""Tests for the phrase ladder, using verbatim source text.

Every string below was harvested from the live source on 8 September 2026. None
is paraphrased, and the near-miss cases are the point: Iceland carrying FCDO's
global "high threat" boilerplate, Japan's "no recent history of terrorism",
Poland and Iceland getting Canada's Europe paragraph while France and Spain get
the same paragraph plus a country-specific claim.
"""

from __future__ import annotations

from terrorism import (
    GENERAL, HIGH, LOW, NONE, REVIEW,
    Verdict, classify_ca, classify_fr, classify_uk, classify_us, score,
)

FAILS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILS
    if ok:
        print(f"  PASS  {label}")
    else:
        FAILS += 1
        print(f"  FAIL  {label}  {detail}")


UK_GLOBAL = ("There is a high threat of terrorist attack globally affecting UK "
             "interests and British nationals, including from groups and individuals "
             "who view the UK and British nationals as targets. ")

# --- UK, verbatim "Terrorism in {country}" subsections --------------------
UK = {
    "Nigeria": (UK_GLOBAL + "Terrorists are very likely to try to carry out attacks in "
                "Nigeria. The primary terrorist threat in Nigeria comes from Islamic State "
                "West Africa (ISWA) and Boko Haram.", HIGH),
    "Mali": (UK_GLOBAL + "Terrorists are very likely to try to carry out attacks in Mali. "
             "Several terrorist groups operate in Mali, including JNIM and ISSP.", HIGH),
    "France": (UK_GLOBAL + "Terrorists are very likely to try to carry out attacks in "
               "France. Terrorism attacks could be indiscriminate, including in places "
               "visited by tourists.", HIGH),
    "Spain": (UK_GLOBAL + "Terrorists are likely to try and carry out attacks in Spain. "
              "Attacks could be indiscriminate, including in places visited by foreign "
              "nationals.", GENERAL),
    "Belgium": (UK_GLOBAL + "Terrorists are likely to try to carry out attacks in Belgium. "
                "Terrorism attacks could be indiscriminate.", GENERAL),
    "Turkey": (UK_GLOBAL + "Terrorists are likely to try to carry out attacks in Turkey. "
               "Most terrorist attacks have occurred in southeast Turkey, Ankara and "
               "Istanbul.", GENERAL),
    "Chile": (UK_GLOBAL + "Terrorists are likely to try to carry out attacks in Chile. Some "
              "individuals or groups claiming to represent the interests of indigenous "
              "communities have carried out attacks in the Araucania region.", GENERAL),
    "Japan": (UK_GLOBAL + "Although there's no recent history of terrorism in Japan, "
              "attacks cannot be ruled out.", LOW),
    "Iceland": (UK_GLOBAL + "Although there's no recent history of terrorism in Iceland, "
                "attacks cannot be ruled out.", LOW),
    "Poland": (UK_GLOBAL + "Terrorist attacks in Poland cannot be ruled out. Attacks could "
               "be indiscriminate including in places visited by foreign nationals.", LOW),
    "New Zealand": (UK_GLOBAL + "Terrorist attacks in New Zealand cannot be ruled out.", LOW),
}

# --- Canada, verbatim "Terrorism" sections --------------------------------
CA = {
    "Pakistan": ("There is a high threat of terrorism in Pakistan. The security situation "
                 "is fragile and unpredictable. Several terrorist groups are present.", HIGH),
    "Mali": ("All of Mali is exposed to terrorist attacks. Since 2022, there has been an "
             "increase in terrorist attacks in central, western and southern Mali.", HIGH),
    "Nigeria": ("There is a threat of terrorism throughout Nigeria, particularly in the "
                "Middle Belt, the northern and the northeastern areas of the country.", GENERAL),
    "Jordan": ("There is a threat of terrorism. Transnational and domestic terrorist groups "
               "have planned and carried out attacks in Jordan.", GENERAL),
    "New Zealand": ("There is a threat of terrorism. Far-right domestic terrorists have "
                    "carried out attacks in New Zealand, the most recent being the 2019 "
                    "shootings in Christchurch at two mosques.", GENERAL),
    # The four that share Canada's Europe paragraph. France, Spain and Belgium go
    # on to name themselves; Iceland and Poland do not.
    "France": ("There is a threat of terrorism in Europe. Terrorists have carried out "
               "attacks in several European cities, including in France. Additional attacks "
               "can occur.", GENERAL),
    "Spain": ("There is a threat of terrorism in Europe. Terrorists have carried out attacks "
              "in several European cities. In Spain, attacks causing deaths and injuries "
              "have taken place.", GENERAL),
    "Iceland": ("There is a threat of terrorism in Europe. Terrorists have carried out "
                "attacks in several European cities. Terrorist attacks could occur at any "
                "time. Targets could include: government buildings", LOW),
    "Poland": ("There is a threat of terrorism in Europe. Terrorist attacks have occurred in "
               "a number of European cities. There is a potential for other violent "
               "incidents. Targets could include: government buildings,", LOW),
    "Japan": (None, NONE),
    "Botswana": (None, NONE),
    "Uruguay": (None, NONE),
}

# --- France, verbatim -----------------------------------------------------
FR = {
    "Nigeria": ("Terrorisme Le risque terroriste est élevé au Nigéria : en raison des "
                "exactions répétées de Boko Haram et de l'Etat islamique dans le Nord-Est.", HIGH),
    "Pakistan": ("Risque terroriste Le risque terroriste reste très élevé sur l'ensemble du "
                 "territoire.", HIGH),
    "Turkey": ("Risque terroriste Le risque terroriste reste élevé sur l'ensemble du "
               "territoire, en raison notamment de la proximité immédiate avec des zones de "
               "conflit.", HIGH),
    "Somalia": ("Des actes de terrorisme sont commis quotidiennement par Al Shabaab dans les "
                "principales localités du sud et du centre de la Somalie.", HIGH),
    "Morocco": ("Le Maroc demeure un pays sûr et sous contrôle des autorités, mais qui reste "
                "exposé à la menace terroriste.", GENERAL),
    "Indonesia": ("Risque terroriste Le pays a connu des actes terroristes, dont les attentats "
                  "de Bali de 2002, ayant causé la mort de ressortissants étrangers.", GENERAL),
    "Chile": ("Terrorisme Des attentats avec des colis piégés ont été commis au cours des "
              "dernières années à Santiago.", GENERAL),
    "Japan": (None, NONE),
    "Poland": (None, NONE),
    "New Zealand": (None, NONE),
    "Botswana": (None, NONE),
}

# France relaying Spain's own number - must not be read as France's own HIGH.
FR_SPAIN = ("Menace terroriste Le niveau de menace terroriste est évalué à 4 sur 5 par le "
            "ministère de l'Intérieur espagnol. Il est recommandé d'appliquer les "
            "recommandations des autorités.")


def test_uk() -> None:
    print("UK / FCDO ladder")
    for country, (text, expected) in UK.items():
        v = classify_uk(text, country)
        check(f"{country} -> {expected}", v.tier == expected,
              f"got {v.tier} via {v.rule}")

    # The headline trap.
    v = classify_uk(UK["Iceland"][0], "Iceland")
    check("Iceland is NOT high despite 'high threat' boilerplate", v.tier == LOW,
          f"got {v.tier}")
    v = classify_uk(UK_GLOBAL, "Nowhere")
    check("global boilerplate alone yields NONE", v.tier == NONE, f"got {v.tier}")
    check("very likely and likely are not conflated",
          classify_uk(UK["France"][0], "France").tier !=
          classify_uk(UK["Spain"][0], "Spain").tier)


def test_ca() -> None:
    print("Canada ladder")
    for country, (text, expected) in CA.items():
        v = classify_ca(text, country)
        check(f"{country} -> {expected}", v.tier == expected,
              f"got {v.tier} via {v.rule}")

    check("Europe boilerplate splits on whether the country is named",
          classify_ca(CA["France"][0], "France").tier == GENERAL
          and classify_ca(CA["Iceland"][0], "Iceland").tier == LOW)
    check("missing section is NONE, not REVIEW",
          classify_ca(None, "Japan").tier == NONE)


def test_fr() -> None:
    print("France ladder")
    for country, (text, expected) in FR.items():
        v = classify_fr(text, country)
        check(f"{country} -> {expected}", v.tier == expected,
              f"got {v.tier} via {v.rule}")

    v = classify_fr(FR_SPAIN, "Spain")
    check("relayed host-nation level capped at general", v.tier == GENERAL,
          f"got {v.tier} via {v.rule}")
    check("relayed level is flagged in the note", bool(v.note), str(v.note))
    check("accents do not break matching",
          classify_fr(FR["Pakistan"][0], "Pakistan").tier == HIGH)


def test_us() -> None:
    print("US indicator flag")
    check("T tag -> general", classify_us(["U", "C", "H", "K", "T"]).tier == GENERAL)
    check("no T tag -> none", classify_us(["U", "C", "H"]).tier == NONE)
    check("empty indicators -> none", classify_us([]).tier == NONE)
    check("no advisory row -> none", classify_us(None, has_row=False).tier == NONE)
    check("Chile has no T tag despite three other sources naming terrorism",
          classify_us(["U", "C", "H"]).tier == NONE)


def test_unmatched_is_flagged() -> None:
    print("Unmatched text")
    odd = ("In the context of regional escalation, Iran-aligned militia groups have "
           "threatened to target US interests across the region.")
    v = classify_uk(UK_GLOBAL + odd, "Jordan")
    check("non-standard FCDO wording -> REVIEW, not a silent default",
          v.tier == REVIEW, f"got {v.tier}")
    check("REVIEW carries the offending text as evidence", bool(v.evidence))


def test_score() -> None:
    print("Composite scoring")
    levels = {"us": 4, "uk": 4, "ca": 4, "fr": 4}
    verdicts = [
        Verdict("us", GENERAL, "T", "us:t-tag"),
        Verdict("uk", HIGH, "very likely", "uk:very-likely"),
        Verdict("ca", HIGH, "all of Mali", "ca:wholly-exposed"),
        Verdict("fr", HIGH, "eleve", "fr:eleve"),
    ]
    out = score(verdicts, levels)
    check("Mali-shaped input -> Severe", out["band"] == "Severe", str(out["band"]))
    check("breadth counts all four", out["breadth"] == 4, str(out["breadth"]))

    quiet = [
        Verdict("us", NONE, None, "us:no-t-tag"),
        Verdict("uk", LOW, "cannot be ruled out", "uk:cannot-be-ruled-out"),
        Verdict("ca", NONE, None, "ca:no-section"),
        Verdict("fr", NONE, None, "fr:no-mention"),
    ]
    out = score(quiet, {"us": 1, "uk": 1, "ca": 1, "fr": 1})
    check("Japan-shaped input -> Baseline", out["band"] == "Baseline", str(out["band"]))
    check("breadth zero", out["breadth"] == 0)

    thin = [Verdict("us", GENERAL, "T", "us:t-tag"),
            Verdict("uk", REVIEW, "odd", "uk:unmatched"),
            Verdict("ca", REVIEW, "odd", "ca:unmatched")]
    out = score(thin, {"us": 3})
    check("fewer than 3 usable sources -> Unrated", out["band"] == "Unrated",
          str(out["band"]))
    check("Unrated states its reason", bool(out["reason"]))

    review = [Verdict("us", GENERAL, "T", "us:t-tag"),
              Verdict("uk", HIGH, "very likely", "uk:very-likely"),
              Verdict("ca", GENERAL, "threat", "ca:threat-of-terrorism"),
              Verdict("fr", REVIEW, "odd", "fr:unmatched")]
    out = score(review, {"us": 2, "uk": 2, "ca": 2})
    check("REVIEW source is reported, not counted",
          out["needs_review"] == ["fr"] and out["breadth"] == 3,
          f"{out['needs_review']} breadth={out['breadth']}")


if __name__ == "__main__":
    for fn in (test_uk, test_ca, test_fr, test_us,
               test_unmatched_is_flagged, test_score):
        fn()
    print()
    print("FAILURES:", FAILS)
    raise SystemExit(1 if FAILS else 0)
