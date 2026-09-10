"""The Advon column - one synthesised level, for a Western traveller.

WHY THIS EXISTS, AND WHY IT IS DEFENSIBLE
-----------------------------------------

The four sources are four Western foreign ministries, each assessing risk to
its own nationals. Blending them into a single number needs a justification,
because "publish what's published" is the product's foundation and a blend is
ours, not anyone's.

The justification is Matt's, and it is a good one: on the ground, a Westerner
is a Westerner. Someone in Ouagadougou generally cannot tell an American from a
Frenchman, and mostly is not trying to. For threat that reaches people by
proximity rather than by identity, the four assessments are four looks at the
same underlying situation, and a consensus of them is more robust than any one.

WHERE THAT ARGUMENT STOPS, WHICH MATTERS MORE THAN WHERE IT HOLDS
-----------------------------------------------------------------

It holds for AMBIENT threat - indiscriminate terrorism, street crime, civil
unrest, natural disaster. Nobody checks a passport before a bomb goes off.

It breaks wherever a passport is actually produced and read: wrongful
detention, targeted kidnap, border crossings, arrest and consular access. A US
citizen in Iran and a French citizen in Iran do not face the same risk, and no
amount of looking alike changes that. State publishes exactly these as separate
risk indicators - D for wrongful detention, K for kidnapping - and they are
carried out of the composite as passport-specific flags rather than averaged
into it. Averaging them would be the one way this column could get someone hurt.

HOW THE NUMBER IS BUILT
-----------------------

Consensus, not mean, and not maximum.

  * Consensus is the level most of the sources assign. It is explainable in one
    sentence, produces no fractional levels, and one alarmist or one lagging
    source cannot drag it.
  * The mean would produce 2.5s that mean nothing to a reader.
  * The maximum would let a single stale advisory set the headline for every
    country, which is the failure the capital-city decision was taken to avoid.

Ties go to the more cautious level, stated openly.

The full range is always published alongside, so the synthesis never hides the
spread it came from. Where sources differ by two or more levels the row is
flagged - that divergence is real information, and with four Western
governments it usually means one of them knows something, or one is stale.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# Risk indicators that depend on which passport you hold. Never folded into the
# consensus; surfaced separately.
PASSPORT_SPECIFIC = {
    "D": "Wrongful detention",
    "K": "Kidnapping or hostage taking",
}

# Minimum sources before a synthesis is honest at all.
#
# This slides with how many sources COULD rate the country, because a fixed
# floor of 3 quietly breaks the four source countries. No government publishes
# travel advice about itself, so France can only ever be rated by the US, UK and
# Canada - three sources against a floor of three, meaning a single feed failing
# on a single day pushes France to Unrated. The same is true of the UK, the US
# and Canada. Four prominent countries with zero tolerance is not a design, it
# is an oversight.
#
# So: 3 of 4 where four are available, 2 of 3 where the country is one of the
# sources. Two views is thinner evidence and the row says so.
MIN_SOURCES = 3


def required_sources(available: int) -> int:
    if available >= 4:
        return 3
    return max(2, available - 1)

# ISO codes of the countries whose own governments are sources here. Each one
# has one fewer possible rater than everywhere else. Japan is deferred, so JP is
# not in this set - restore it alongside the collector.
SOURCE_COUNTRIES = {"US", "GB", "CA", "FR"}
ACTIVE_SOURCES = 4

# ---------------------------------------------------------------------------
# What this column is, in the column's own words.
#
# These strings travel with the data rather than living on a methodology page,
# because a caveat behind a link reaches under half the people who see the
# number - measured, not assumed. `validate.py` treats their absence as
# blocking, so the page cannot ship the number without the frame around it.
#
# COLUMN_LABEL names the four governments instead of saying "Western". Naming
# them is precise and attributable, and it lets a reader decide for themselves
# whether this describes their situation, rather than us characterising them.
# The plain-language framing lives in the note underneath, where it belongs.
# ---------------------------------------------------------------------------

COLUMN_LABEL = "Advon consensus"

COLUMN_SUBLABEL = "US · UK · Canada · France"

COLUMN_NOTE = (
    "This is our synthesis, not any one government's rating. It is the level "
    "most of these four governments assign, written for a traveller from a "
    "Western country generally rather than from any particular one."
)

FRAME_NOTE = (
    "Every source here is a Western foreign ministry describing risk to its own "
    "nationals. None of them reports on anyone else's, and risk can differ "
    "substantially by nationality. A traveller on a non-Western passport may "
    "face a materially different situation from the one described here."
)

DISCLOSURES = {
    "label": COLUMN_LABEL,
    "sublabel": COLUMN_SUBLABEL,
    "column_note": COLUMN_NOTE,
    "frame_note": FRAME_NOTE,
}

SCALE = {
    1: "Normal precautions",
    2: "Increased caution",
    3: "Avoid non-essential travel",
    4: "Do not travel",
}


@dataclass
class Western:
    level: int | None
    label: str | None
    basis: str
    contributing: dict[str, int] = field(default_factory=dict)
    range_low: int | None = None
    range_high: int | None = None
    agreement: int = 0
    divergent: bool = False
    passport_flags: list[dict] = field(default_factory=list)
    caveat: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "label": self.label,
            "basis": self.basis,
            "contributing": self.contributing,
            "range_low": self.range_low,
            "range_high": self.range_high,
            "agreement": self.agreement,
            "divergent": self.divergent,
            "passport_flags": self.passport_flags,
            "caveat": self.caveat,
            "notes": self.notes,
            "synthesis": True,
            # Carried on every row, not stored once elsewhere, so a template
            # that renders the number without the frame is impossible to write
            # by accident.
            "disclosure": DISCLOSURES,
        }


def _consensus(levels: list[int]) -> tuple[int, int, str]:
    """Most common level; ties resolved upward. Returns (level, count, basis)."""
    counts = Counter(levels)
    top = max(counts.values())
    tied = sorted([lvl for lvl, n in counts.items() if n == top])
    if len(tied) == 1:
        return tied[0], top, f"{top} of {len(levels)} sources assign this level"
    chosen = tied[-1]
    return (
        chosen,
        top,
        f"{len(tied)} levels tied at {top} source(s) each; "
        f"resolved to the more cautious ({chosen})",
    )


def synthesise(
    source_levels: dict[str, int | None],
    indicators: dict[str, list[str]] | None = None,
    country_name: str = "",
    available: int | None = None,
) -> Western:
    """Build the Advon column for one country.

    `source_levels` is the capital-city level per source, already resolved by
    headline.resolve - so a country with bounded exclusion zones contributes its
    residual level here, not its carve-out level.
    """
    usable = {s: lvl for s, lvl in source_levels.items() if isinstance(lvl, int)}
    available = len(source_levels) if available is None else available
    need = required_sources(available)

    if len(usable) < need:
        return Western(
            level=None,
            label="Unrated",
            basis=(
                f"only {len(usable)} of {available} available sources returned a "
                f"usable level; {need} required"
            ),
            contributing=usable,
        )

    levels = list(usable.values())
    level, agreement, basis = _consensus(levels)
    lo, hi = min(levels), max(levels)

    west = Western(
        level=level,
        label=SCALE.get(level),
        basis=basis,
        contributing=usable,
        range_low=lo,
        range_high=hi,
        agreement=agreement,
        divergent=(hi - lo) >= 2,
    )

    if lo != hi:
        west.caveat = (
            f"These governments range from {lo} to {hi} for "
            f"{country_name or 'this country'}."
        )
    if available < 4:
        west.notes.append(
            f"Only {available} governments rate this country, because no government "
            "publishes travel advice about itself. This level rests on "
            f"{len(usable)} view(s) rather than the usual three or four."
        )
    if west.divergent:
        spread = ", ".join(f"{s.upper()} {l}" for s, l in sorted(usable.items()))
        west.notes.append(
            f"Sources differ by {hi - lo} levels ({spread}). Each assesses risk to "
            "its own nationals, so a gap this wide can be a real difference rather "
            "than a disagreement."
        )

    # Passport-specific risk, kept out of the number on purpose.
    for source, tags in (indicators or {}).items():
        for tag in tags or []:
            code = str(tag).upper()
            if code in PASSPORT_SPECIFIC:
                west.passport_flags.append(
                    {
                        "source": source,
                        "code": code,
                        "label": PASSPORT_SPECIFIC[code],
                        "note": (
                            f"{PASSPORT_SPECIFIC[code]} risk is flagged by "
                            f"{source.upper()} for its own nationals. Risk of this "
                            "kind depends on the passport you hold and is not part "
                            "of the synthesised level."
                        ),
                    }
                )

    return west


def apply_to_row(row: dict) -> dict:
    """Attach the Advon column to a reconciled country row."""
    sources = row.get("sources") or {}
    levels = {s: b.get("level") for s, b in sources.items()}
    indicators = {
        s: (b.get("records") or [{}])[0].get("indicators") or []
        for s, b in sources.items()
    }
    # A country is never rated by its own government, so the number of sources
    # that COULD rate it is one fewer for the source countries themselves.
    available = ACTIVE_SOURCES - (1 if (row.get("iso2") or "").upper() in SOURCE_COUNTRIES else 0)
    row["advon"] = synthesise(
        levels, indicators, row.get("name", ""), available=available
    ).as_dict()
    return row
