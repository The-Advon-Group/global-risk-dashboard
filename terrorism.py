"""Phase 2 - the terrorism phrase ladder.

DRAFT. Every tier below was built from live source text harvested 8 September
2026 across 22 countries chosen to span the range: obvious highs (Mali,
Somalia, Pakistan), obvious lows (Iceland, Botswana, Uruguay), and the awkward
middle (Poland, Chile, New Zealand, Japan). The strings in `test_terrorism.py`
are verbatim from those pages, not paraphrases.

This file is the one part of the build that encodes judgment rather than fact,
and it is the piece Matt reviews before it goes live.

--------------------------------------------------------------------------
WHY KEYWORD MATCHING WOULD HAVE FAILED, WITH EVIDENCE
--------------------------------------------------------------------------

The plan predicted this. The live text is worse than predicted.

1. FCDO opens the terrorism section of EVERY country - Iceland, Botswana, New
   Zealand included - with the identical sentence:

     "There is a high threat of terrorist attack globally affecting UK
      interests and British nationals..."

   A keyword matcher looking for "high threat of terrorist attack" rates
   Iceland as high-terrorism. The country-specific assessment lives in a
   separate "Terrorism in {country}" subsection underneath. `strip_boilerplate`
   removes the global paragraph before anything else runs.

2. Canada does the same thing regionally. "There is a threat of terrorism in
   Europe. Terrorists have carried out attacks in several European cities."
   appears on Iceland and Poland exactly as it appears on France and Spain. The
   discriminator is whether the passage goes on to name the country itself as a
   place attacks have occurred. France: "including in France". Spain: "In
   Spain, attacks causing deaths and injuries have taken place." Iceland: no
   such sentence.

3. "Although there's no recent history of terrorism in Japan" contains the word
   terrorism and means the opposite of a threat.

4. One word separates FCDO's top two rungs - "very likely" against "likely" -
   so any substring test for "likely" collapses them.

--------------------------------------------------------------------------
THE US NEEDS NO LADDER AT ALL
--------------------------------------------------------------------------

State publishes a "T" risk-indicator tag per destination, already collected in
Phase 1. Checked against the 22-country sample it discriminates cleanly: present
for Mali, Somalia, Nigeria, Pakistan, Kenya, Egypt, France, Spain, Belgium,
Morocco, Turkey, Indonesia, Philippines, Tunisia, Jordan; absent for Iceland,
Japan, New Zealand, Poland, Uruguay, Botswana, Chile. So the US contributes to
breadth from a published flag with no phrase detection anywhere in the path -
which also means the US can never be wrong here in a way we caused.

--------------------------------------------------------------------------
TIERS
--------------------------------------------------------------------------

    NONE     the source has no terrorism section for this country at all
    LOW      terrorism mentioned, explicitly as remote or as generic background
    GENERAL  terrorism named as a real concern for this country
    HIGH     terrorism named as elevated, severe or pervasive
    REVIEW   text present but no pattern matched - never silently defaulted

Breadth counts sources at GENERAL or HIGH. NONE and LOW do not count, and
REVIEW does not count but is reported so the ladder can be corrected.

Breadth is out of FOUR, not five. Japan is deferred until after beta - see
collectors/japan.py - so the methodology page must read "n of 4".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NONE, LOW, GENERAL, HIGH, REVIEW = "none", "low", "general", "high", "review"
COUNTS_AS_ELEVATED = {GENERAL, HIGH}

TIER_RANK = {NONE: 0, LOW: 1, GENERAL: 2, HIGH: 3, REVIEW: -1}


@dataclass
class Verdict:
    source: str
    tier: str
    evidence: str | None      # the phrase that decided it, for the methodology page
    rule: str | None          # which rule fired, so a wrong call is traceable
    note: str | None = None


def _flat(text: str) -> str:
    """Lowercase, de-accent, collapse whitespace, normalise curly quotes."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip().lower()


# ---------------------------------------------------------------------------
# Boilerplate that must be removed before any tier test runs.
# ---------------------------------------------------------------------------

BOILERPLATE = {
    # FCDO's global paragraph, present on every country including Iceland.
    # Bounded to the single global sentence. An earlier version ran to a
    # lookahead for the country-specific opener, which meant any country whose
    # wording departs from the standard formula - Jordan does - had its entire
    # section eaten and came back NONE instead of REVIEW. Ending at the first
    # full stop cannot do that.
    "uk": [
        re.compile(
            r"there is a high threat of terrorist attack globally[^.]*\.",
            re.I,
        ),
    ],
    # Canada's regional paragraph. Removed only for the purpose of tier tests;
    # `_ca_names_country` still inspects the original to see whether the country
    # itself is named as a place attacks have happened.
    "ca": [
        re.compile(
            r"there(?:'s| is| ’s) a threat of terrorism in (?:europe|the region)\.?\s*"
            r"(?:terrorists? (?:have carried out|attacks have occurred)[^.]*\.)?",
            re.I,
        ),
    ],
    "fr": [],
    "us": [],
}


def strip_boilerplate(source: str, text: str) -> str:
    out = text or ""
    for pattern in BOILERPLATE.get(source, []):
        out = pattern.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip()


# ---------------------------------------------------------------------------
# UK - FCDO. The most controlled vocabulary of the four, and a genuine ladder.
# Feed this the "Terrorism in {country}" subsection, NOT the whole
# safety-and-security part.
# ---------------------------------------------------------------------------

UK_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (LOW, re.compile(r"no recent history of terrorism"), "uk:no-recent-history"),
    (HIGH, re.compile(r"terrorists? are very likely to try (?:and|to) carry out attacks"), "uk:very-likely"),
    (GENERAL, re.compile(r"terrorists? are likely to try (?:and|to) carry out attacks"), "uk:likely"),
    (LOW, re.compile(r"terrorist attacks? in [^.]{0,60} cannot be ruled out"), "uk:cannot-be-ruled-out"),
    (LOW, re.compile(r"attacks cannot be ruled out"), "uk:cannot-be-ruled-out-short"),
]

# ---------------------------------------------------------------------------
# Canada. Flatter than the UK: mostly one general register, with a small number
# of genuinely elevated phrasings, and - importantly - silence as its low signal.
# ---------------------------------------------------------------------------

CA_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (HIGH, re.compile(r"high threat of terrorism"), "ca:high-threat"),
    (HIGH, re.compile(r"all of [a-zÀ-ſ' -]+ is exposed to terrorist attacks"), "ca:wholly-exposed"),
    (HIGH, re.compile(r"acts? of terrorism (?:are|is) committed daily|terrorist attacks occur daily"), "ca:daily"),
    (GENERAL, re.compile(r"there(?:'s| is) a threat of terrorism"), "ca:threat-of-terrorism"),
    (GENERAL, re.compile(r"threat of terrorism throughout"), "ca:threat-throughout"),
]

# Does Canada's Europe/regional boilerplate go on to name this country as a
# place attacks have actually occurred? France, Spain and Belgium do. Iceland
# and Poland do not. That distinction is the whole difference between GENERAL
# and LOW for European countries.
def _ca_names_country(text: str, country: str) -> bool:
    if not country:
        return False
    flat, name = _flat(text), _flat(country)
    if not name or not re.search(rf"\b{re.escape(name)}\b", flat):
        return False

    # Look both ways around the country mention, not just forward. Canada writes
    # "Terrorists have carried out attacks in several European cities, including
    # in France." - the attack word sits BEFORE the country name, so a
    # forward-only window misses it and France is scored as generic boilerplate.
    evidence = re.compile(r"attack|bomb|kill|death|injur|casualt", re.I)
    for match in re.finditer(rf"\b{re.escape(name)}\b", flat):
        start = max(0, match.start() - 160)
        if evidence.search(flat[start:match.end() + 160]):
            return True
    return False


# ---------------------------------------------------------------------------
# France. Section headed Terrorisme / Risque terroriste / Menace terroriste.
# Silence is again the low signal - and France is silent more often than the
# others, which is why absence must be treated as real information rather than
# as a fetch failure.
# ---------------------------------------------------------------------------

FR_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (HIGH, re.compile(r"risque terroriste (?:est |reste |demeure )?(?:tres|extremement) eleve"), "fr:tres-eleve"),
    (HIGH, re.compile(r"(?:risque|menace) terroriste (?:est |reste |demeure )?eleve"), "fr:eleve"),
    (HIGH, re.compile(r"actes? de terrorisme sont commis quotidiennement"), "fr:quotidien"),
    (HIGH, re.compile(r"presence de groupes terroristes et des risques d'attentat"), "fr:groupes-presents"),
    (GENERAL, re.compile(r"expose[e]? a la menace terroriste"), "fr:expose"),
    (GENERAL, re.compile(r"a connu des actes terroristes"), "fr:a-connu"),
    (GENERAL, re.compile(r"attentats? .{0,60}(?:ont ete commis|a ete commis)"), "fr:attentats-commis"),
    (GENERAL, re.compile(r"activites terroristes"), "fr:activites"),
    (GENERAL, re.compile(r"risque terroriste"), "fr:risque-generique"),
    (GENERAL, re.compile(r"menace terroriste"), "fr:menace-generique"),
]

# France sometimes relays the HOST country's own numeric threat level, e.g. for
# Spain: "Le niveau de menace terroriste est evalue a 4 sur 5 par le ministere
# de l'Interieur espagnol." That is Spain's assessment, reported by France, not
# France's own. Treated as GENERAL and flagged, because counting another
# government's number as France's opinion would double-count it.
FR_RELAYED = re.compile(
    r"(?:niveau (?:de menace|d'alerte) terroriste[^.]{0,80}(?:evalue|fixe)[^.]{0,60}"
    r"(?:par (?:le|les) (?:ministere|autorites)|autorites locales))",
    re.I,
)


def classify_uk(section_text: str | None, country: str = "") -> Verdict:
    if not section_text or not section_text.strip():
        return Verdict("uk", NONE, None, "uk:no-section",
                       "no country-specific terrorism subsection")
    body = _flat(strip_boilerplate("uk", section_text))
    if not body:
        return Verdict("uk", NONE, None, "uk:only-global-boilerplate",
                       "only the global paragraph was present")
    for tier, pattern, rule in UK_RULES:
        match = pattern.search(body)
        if match:
            return Verdict("uk", tier, match.group(0)[:160], rule)
    return Verdict("uk", REVIEW, body[:160], "uk:unmatched",
                   "text present but no FCDO pattern matched - needs a rule")


def classify_ca(section_text: str | None, country: str = "") -> Verdict:
    if not section_text or not section_text.strip():
        return Verdict("ca", NONE, None, "ca:no-section",
                       "Canada publishes no terrorism heading for this country")
    original = section_text
    body = _flat(strip_boilerplate("ca", section_text))

    for tier, pattern, rule in CA_RULES:
        match = pattern.search(body)
        if match:
            return Verdict("ca", tier, match.group(0)[:160], rule)

    # Only the regional boilerplate remained. Elevated only if the passage names
    # this country as somewhere attacks have happened.
    if _flat(original) and "threat of terrorism in europe" in _flat(original):
        if _ca_names_country(original, country):
            return Verdict("ca", GENERAL, "regional boilerplate naming this country",
                           "ca:europe-names-country")
        return Verdict("ca", LOW, "regional boilerplate only", "ca:europe-generic",
                       "Canada's Europe paragraph without a country-specific claim")

    return Verdict("ca", REVIEW, body[:160] or None, "ca:unmatched",
                   "text present but no Canadian pattern matched")


def classify_fr(section_text: str | None, country: str = "") -> Verdict:
    if not section_text or not section_text.strip():
        return Verdict("fr", NONE, None, "fr:no-mention",
                       "no terrorism mention on the France security page")
    body = _flat(section_text)
    if "terroris" not in body and "attentat" not in body:
        return Verdict("fr", NONE, None, "fr:no-mention",
                       "no terrorism mention on the France security page")

    relayed = FR_RELAYED.search(body)
    for tier, pattern, rule in FR_RULES:
        match = pattern.search(body)
        if match:
            note = None
            if relayed:
                note = ("France is relaying the host country's own threat level, "
                        "not stating its own")
                if tier == HIGH:
                    tier = GENERAL
                    note += " - capped at general so it is not counted twice"
            return Verdict("fr", tier, match.group(0)[:160], rule, note)

    if relayed:
        return Verdict("fr", GENERAL, relayed.group(0)[:160], "fr:relayed-host-level",
                       "France relays the host country's own numeric threat level")
    return Verdict("fr", REVIEW, body[:160], "fr:unmatched",
                   "terrorism mentioned but no French pattern matched")


def classify_us(indicators: list[str] | None, has_row: bool = True) -> Verdict:
    """No phrase ladder. State publishes the flag."""
    if not has_row:
        return Verdict("us", NONE, None, "us:no-advisory",
                       "no State Department advisory for this destination")
    tags = [t.upper() for t in (indicators or [])]
    if "T" in tags:
        return Verdict("us", GENERAL, "risk indicator T (Terrorism)", "us:t-tag")
    return Verdict("us", NONE, None, "us:no-t-tag",
                   "State lists risk indicators for this destination but not T")


# ---------------------------------------------------------------------------
# Composite. Two numbers, not one weighted blend - per the agreed methodology.
# ---------------------------------------------------------------------------

MIN_SOURCES = 3


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(ordered[mid]) if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def score(verdicts: list[Verdict], levels: dict[str, int | None]) -> dict:
    """Breadth, severity and band.

    breadth  - how many sources currently name terrorism as an elevated concern
    severity - median advisory level among those sources, on the shared 1-4 scale
    """
    usable = [v for v in verdicts if v.tier != REVIEW]
    elevated = [v for v in usable if v.tier in COUNTS_AS_ELEVATED]

    if len(usable) < MIN_SOURCES:
        return {
            "band": "Unrated",
            "breadth": None,
            "severity": None,
            "reason": (
                f"only {len(usable)} of {len(verdicts)} sources returned usable "
                f"terrorism text; {MIN_SOURCES} required"
            ),
            "verdicts": [v.__dict__ for v in verdicts],
        }

    breadth = len(elevated)
    sev_levels = [
        levels[v.source] for v in elevated
        if isinstance(levels.get(v.source), int)
    ]
    severity = _median(sev_levels) if sev_levels else 0.0

    caveat = None
    if severity >= 3.5 and breadth >= 3:
        band = "Severe"
    elif (severity >= 3 and breadth >= 2) or (breadth >= 1 and 4 in sev_levels and len(sev_levels) == 1):
        band = "High"
    elif severity >= 2 and breadth >= 1:
        band = "Elevated"
    elif breadth == 0:
        band = "Baseline"
    else:
        # SETTLED 10 SEP 2026.
        # breadth >= 1 but severity < 2: at least one government names terrorism
        # as a concern, yet every government that does rates the country low.
        # New Zealand lands here - Canada's terrorism section cites Christchurch
        # 2019 - as does Chile, on parcel bombs in Santiago.
        #
        # Matt's call: hold the status at Baseline, because nothing here
        # requires a change of status, but record what the sources actually said
        # as something to monitor. So the band does not move and the evidence
        # does not disappear - it becomes a watch note attached to the row.
        band = "Baseline"
        caveat = (
            f"Baseline, with {breadth} source(s) naming terrorism at a low "
            "advisory level - recorded to monitor, no change of status"
        )

    # Watch notes: what a source said about terrorism that did not move the
    # band. These exist so a Baseline row still carries its evidence - the
    # reader sees that Canada cites Christchurch without New Zealand being
    # rated as though an attack were expected.
    watch = []
    if band == "Baseline":
        for v in verdicts:
            if v.tier in COUNTS_AS_ELEVATED or (v.tier == LOW and v.evidence):
                watch.append({
                    "source": v.source,
                    "tier": v.tier,
                    "said": v.evidence,
                    "rule": v.rule,
                })

    return {
        "band": band,
        "breadth": breadth,
        "severity": severity,
        "sources_elevated": [v.source for v in elevated],
        "reason": None,
        "caveat": caveat,
        "watch_notes": watch,
        "needs_review": [v.source for v in verdicts if v.tier == REVIEW],
        "verdicts": [v.__dict__ for v in verdicts],
    }
