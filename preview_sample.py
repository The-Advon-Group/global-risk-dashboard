"""Score the 22-country harvested sample and print the table.

Not part of the pipeline. This exists so the ladder's output can be eyeballed
against intuition before it goes anywhere near the page, and so Matt's review
has concrete rows to argue with rather than rules in the abstract.

All inputs are the real text and real tags harvested 8 Sep 2026.
"""

from __future__ import annotations

from terrorism import classify_ca, classify_fr, classify_uk, classify_us, score
from test_terrorism import CA, FR, UK

# US: level and risk-indicator letters, verbatim from the advisories list page.
US = {
    "Belgium": (2, "T"), "Botswana": (2, "C"), "Chile": (2, "UCH"),
    "Egypt": (2, "TOCH"), "France": (2, "UT"), "Iceland": (1, ""),
    "Indonesia": (2, "UNT"), "Japan": (1, ""), "Jordan": (2, "TO"),
    "Kenya": (2, "UCHKTO"), "Mali": (4, "CKTUH"), "Morocco": (2, "T"),
    "New Zealand": (1, ""), "Nigeria": (3, "UCHKT"), "Pakistan": (3, "TCKO"),
    "Philippines": (2, "UCKT"), "Poland": (1, ""), "Somalia": (4, "UCKTOH"),
    "Spain": (2, "UT"), "Tunisia": (2, "TUC"), "Turkey": (2, "TO"),
    "Uruguay": (2, "C"),
}

# UK level derived from alert_status, on the shared 1-4 scale after roll-up.
UK_LEVEL = {
    "Nigeria": 4, "Mali": 4, "Somalia": 4, "Pakistan": 4, "Kenya": 4,
    "Indonesia": 4, "Philippines": 4, "Tunisia": 4, "Turkey": 4,
    "France": 1, "Spain": 1, "Belgium": 1, "Morocco": 1, "Japan": 1,
    "Iceland": 1, "Poland": 1, "New Zealand": 1, "Chile": 1,
}

# Canada level from advisory-state + 1.
CA_LEVEL = {
    "Nigeria": 3, "Mali": 4, "Somalia": 4, "Pakistan": 4, "Kenya": 3,
    "Indonesia": 2, "Philippines": 2, "Tunisia": 2, "Turkey": 2,
    "France": 2, "Spain": 2, "Belgium": 2, "Morocco": 2, "Japan": 1,
    "Iceland": 1, "Poland": 2, "New Zealand": 1, "Chile": 2, "Jordan": 2,
    "Botswana": 1, "Uruguay": 1, "Egypt": 3,
}

FR_LEVEL = {
    "Nigeria": 4, "Mali": 4, "Somalia": 4, "Pakistan": 4, "Turkey": 3,
    "Morocco": 2, "Indonesia": 2, "Chile": 2, "Japan": 1, "Poland": 1,
    "New Zealand": 1, "Botswana": 1, "Spain": 1,
}

COUNTRIES = ["Mali", "Somalia", "Pakistan", "Nigeria", "Turkey", "Indonesia",
             "Morocco", "Spain", "Belgium", "France", "Chile", "Jordan",
             "New Zealand", "Poland", "Iceland", "Japan", "Botswana", "Uruguay"]


NOT_HARVESTED = "n/a"


def row(country: str) -> tuple[str, dict, list, set[str]]:
    """Score one country.

    A source this preview did not harvest text for is NOT the same thing as a
    source that says nothing, and conflating the two would make the table lie in
    the direction of "quieter than reality". Unharvested sources are dropped
    from the verdict list entirely, which means they also count against the
    three-source minimum - the honest behaviour.
    """
    verdicts = []
    gaps: set[str] = set()

    level, tags = US.get(country, (None, ""))
    if country in US:
        verdicts.append(classify_us(list(tags) if tags else []))
    else:
        gaps.add("us")

    if country in UK:
        verdicts.append(classify_uk(UK[country][0], country))
    else:
        gaps.add("uk")

    if country in CA:
        verdicts.append(classify_ca(CA[country][0], country))
    else:
        gaps.add("ca")

    if country in FR:
        verdicts.append(classify_fr(FR[country][0], country))
    else:
        gaps.add("fr")

    levels = {
        "us": level,
        "uk": UK_LEVEL.get(country),
        "ca": CA_LEVEL.get(country),
        "fr": FR_LEVEL.get(country),
    }
    return country, score(verdicts, levels), verdicts, gaps


if __name__ == "__main__":
    print("n/a = this preview did not harvest that source for that country;")
    print("     it is NOT the source saying nothing.")
    print()
    print(f"{'Country':<13} {'US':<8} {'UK':<8} {'CA':<8} {'FR':<8} "
          f"{'Br':<3} {'Sev':<5} Band")
    print("-" * 78)
    caveats, reviews = [], []
    for c in COUNTRIES:
        name, s, vs, gaps = row(c)
        tiers = {v.source: v.tier for v in vs}
        for g in gaps:
            tiers[g] = NOT_HARVESTED
        br = "-" if s["breadth"] is None else str(s["breadth"])
        sev = "-" if s["severity"] is None else f"{s['severity']:.1f}"
        flag = " *" if s.get("caveat") else ""
        print(f"{name:<13} {tiers['us']:<8} {tiers['uk']:<8} {tiers['ca']:<8} "
              f"{tiers['fr']:<8} {br:<3} {sev:<5} {s['band']}{flag}")
        if s.get("caveat"):
            caveats.append((name, s["caveat"]))
        rev = [v.source for v in vs if v.tier == "review"]
        if rev:
            reviews.append((name, rev))

    print()
    print("* outside the agreed band table:")
    for name, note in caveats:
        print(f"    {name}: {note}")
    if not caveats:
        print("    none")

    print()
    print("Sources needing a new rule (REVIEW):")
    for name, rev in reviews:
        print(f"    {name}: {', '.join(rev)}")
    if not reviews:
        print("    none in this sample")
