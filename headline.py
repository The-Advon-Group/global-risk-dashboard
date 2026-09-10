"""Choosing the level the dashboard actually publishes.

Decision, 10 September 2026. The headline level for a country is the level that
applies to its CAPITAL CITY. The spread across the rest of the country is kept
and published beside it as a caveat.

This replaces the Phase 1 rule, which took the highest level applying anywhere.
That rule made a country with one dangerous province look uniformly dangerous -
Nigeria reading as "avoid all travel" because of Borno, when Abuja sits two
levels lower.

WHAT THIS COSTS, STATED PLAINLY. For countries where the capital is the safer
part - Nigeria, Mali, Kenya, Egypt - the headline is now the optimistic end of
the range, and the caveat carries the weight. That is the intended behaviour,
but it means `caveat` is not decoration: a row whose capital sits at 2 while
part of the country sits at 4 must say so wherever the row is shown, including
in any compact or summary view. The reverse case exists too - Mogadishu, Kabul
and Port-au-Prince are the dangerous part - and there the headline is the
pessimistic end and the caveat says the country is not uniformly that bad.

HOW THE CAPITAL'S LEVEL IS DETERMINED, in order:

  1. If a source publishes a region-level record naming the capital, use it.
     France does this cleanly; Canada does it in its regional headings.
  2. If the capital is explicitly EXCEPTED from a carve-out - France writes
     "à l'exception de la ville de Kano" - the exception wins over the carve-out
     it sits inside.
  3. If the source publishes regional records but none names the capital, use
     the source's national headline level - PROVIDED the source states one.
     Most carve-outs are about the periphery, so the capital sitting outside
     them means it carries the national figure.
  4. If the source publishes no regional detail at all, use the national level.

Cases 3 and 4 are the common ones and are honest defaults, but they are
recorded in `basis` so a wrong call is traceable rather than invisible.

THE "PROVIDED THE SOURCE STATES ONE" CLAUSE, added 10 September 2026 after the
fifth live run. Canada, the FCDO and State each issue a level for the country as
a whole. France does not: it publishes zones and colours them, and the
country-wide number is one WE computed by taking the worst zone. Feeding our own
worst-zone figure back in as "the national level" undid the entire point of this
module - the first live run to surface it had France rating Seychelles, Panama,
Jamaica, Uganda and about fifty others at level 4, Seychelles because the red
zone is the high seas north of the archipelago and the code could not tell that
from a red zone over the capital.

So when a source publishes named zones and states no country-wide level, and no
zone names the capital, this uses the LEAST severe band that source published
rather than the worst. That reads France's own model correctly: the bands listed
are what France singled out, and a capital in none of them is not in the worst
one. It can still understate - Nigeria prints red and orange and no green, so
Abuja comes out orange - which is why the spread caveat is mandatory on these
rows and says how much higher parts of the country are rated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from capitals import capital_of, mentioned_in

# France writes exceptions as "à l'exception de X" / "sauf X". Canada and the
# FCDO write them as "with the exception of" / "except for" / "other than".
EXCEPTION = re.compile(
    r"(?:a l'exception de|a l'exception des|sauf(?! raison)|"
    r"with the exception of|except(?: for)?|other than|excluding)\b",
    re.I,
)

# A zone that describes itself as everywhere the other zones do not cover.
# France writes "le reste du pays" and "le reste du territoire"; the FCDO writes
# "the rest of the country". A capital named in no other zone is in this one,
# which is better evidence than any inference about which band to fall back to.
RESIDUAL = re.compile(
    r"(?:le\s+)?reste\s+du\s+(?:pays|territoire)|"
    r"reste\s+de\s+l[ae']|"
    r"rest\s+of\s+the\s+(?:country|territory)|"
    r"remainder\s+of\s+the\s+country|"
    r"elsewhere\s+in\s+the\s+country",
    re.I,
)


@dataclass
class Headline:
    level: int | None
    basis: str
    capital: str | None = None
    regional_min: int | None = None
    regional_max: int | None = None
    caveat: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def uniform(self) -> bool:
        return self.regional_min == self.regional_max


def _capital_from_regions(
    records: list[dict], iso2: str
) -> tuple[int | None, str, str | None, list[int]]:
    """Find a regional record that names the capital.

    Two distinct outcomes, and conflating them was a real bug:

      * The capital is named as being IN a carve-out. Its level is that
        record's level.
      * The capital is named in an EXCEPTION to a carve-out - France writes
        "Etats de Borno, Yobe, Jigawa et Kano, a l'exception de la ville de
        Kano". That means the capital is emphatically NOT the surrounding
        record's level. Taking that level would publish the exact opposite of
        what the source says.

    So an exception does not yield a level, it EXCLUDES one. The excluded
    levels come back in the fourth return value; the caller falls through to
    another regional record or to the national level, and records that it did.
    """
    hit_plain: tuple[int, str] | None = None
    excluded: list[int] = []
    excepted_name: str | None = None

    for rec in records:
        level = rec.get("level")
        if not isinstance(level, int):
            continue
        haystack = " ".join(
            str(rec.get(k) or "") for k in ("region", "level_label", "raw_name")
        )
        name = mentioned_in(haystack, iso2)
        if not name:
            continue
        # Look at the words just before the capital's name to see whether it is
        # being excepted out of the surrounding carve-out.
        flat = haystack.lower()
        idx = flat.find(name.lower())
        window = flat[max(0, idx - 60):idx]
        if EXCEPTION.search(window):
            excluded.append(level)
            excepted_name = name
        elif hit_plain is None or level > hit_plain[0]:
            hit_plain = (level, name)

    if hit_plain and hit_plain[0] not in excluded:
        return (hit_plain[0], "capital named in a regional record",
                hit_plain[1], excluded)
    if excluded:
        return (None, "", excepted_name, excluded)
    return None, "", None, []


def _residual_level(records: list[dict]) -> int | None:
    """The level of the zone the source says covers the rest of the country.

    Where a source marks more than one - it happens when a page says "the rest
    of the region" in one band and "the rest of the country" in another - the
    more cautious of them wins, because the ambiguity is ours and should not
    resolve in the reassuring direction.
    """
    hits = [
        rec.get("level")
        for rec in records
        if isinstance(rec.get("level"), int) and RESIDUAL.search(str(rec.get("region") or ""))
    ]
    return max(hits) if hits else None


def resolve(
    records: list[dict],
    iso2: str,
    national_level: int | None,
    national_stated: bool = True,
) -> Headline:
    """Pick the published level for one source's view of one country.

    `national_stated` says whether `national_level` is the source's own
    country-wide figure or our roll-up of its zones. False means the source
    never issued a country-wide level, so falling back to it would be quoting
    ourselves - see the module docstring.
    """
    capital = capital_of(iso2)
    regional = [r for r in records if r.get("region")]
    levels = [r.get("level") for r in records if isinstance(r.get("level"), int)]
    if isinstance(national_level, int):
        levels.append(national_level)

    lo = min(levels) if levels else None
    hi = max(levels) if levels else None

    if capital is None:
        # Some entries genuinely have no capital - Antarctica, Tokelau - and
        # others are simply missing from the table. Either way the row still
        # needs its spread caveat: the first live run refused to publish
        # Western Sahara precisely because this branch returned without one,
        # which was the validator catching a real hole rather than a false
        # alarm. The caveat here names no city, because there isn't one to name.
        head = Headline(
            level=national_level,
            basis="no capital on file for this territory; source's national level used",
            capital=None,
            regional_min=lo,
            regional_max=hi,
            notes=["no capital on file - see capitals.py"],
        )
        head.caveat = build_caveat(head)
        return head

    level, basis, matched, excluded = (None, "", None, [])
    if regional:
        level, basis, matched, excluded = _capital_from_regions(regional, iso2)

    extra_notes: list[str] = []
    if level is None and excluded:
        # The capital was explicitly excepted out of a carve-out. We know what
        # it is NOT. Fall back to the best remaining evidence, and never let the
        # excluded level through.
        candidates = [
            r.get("level") for r in regional
            if isinstance(r.get("level"), int) and r.get("level") not in excluded
        ]
        if (national_stated and isinstance(national_level, int)
                and national_level not in excluded):
            level = national_level
            basis = ("capital excepted from a regional carve-out; "
                     "source's national level used instead")
        elif candidates:
            level = min(candidates)
            basis = ("capital excepted from a regional carve-out; "
                     "lowest remaining regional level used")
        else:
            level = None
            basis = ("capital excepted from a regional carve-out and no other "
                     "level applies")
        extra_notes.append(
            f"source excepts {matched or capital} from level "
            f"{'/'.join(str(x) for x in sorted(set(excluded)))} - verify"
        )

    if level is None and not excluded:
        zone_levels = [
            r.get("level") for r in regional if isinstance(r.get("level"), int)
        ]
        residual = _residual_level(regional)
        if regional and not national_stated and residual is not None:
            # The source itself says which band covers everywhere the other
            # zones do not. A capital named in no other zone is in that one,
            # which is the source's own answer rather than our inference.
            level = residual
            basis = ("capital named in no zone; source's own 'rest of the "
                     "country' band used")
        elif regional and not national_stated and zone_levels:
            # No residual band either. The capital is in none of the zones the
            # source named, so it is not in the worst one. Publish the least
            # severe band the source printed and let the caveat carry the
            # spread. This is the weakest step in the chain and it says so.
            level = min(zone_levels)
            basis = (
                "source states no country-wide level, no named zone covers the "
                "capital and none is marked as covering the rest; least severe "
                "band the source published used"
            )
            extra_notes.append(
                "capital not named in any zone - level inferred from the "
                "source's least severe band, which may understate"
            )
        else:
            level = national_level
            basis = (
                "no regional record names the capital; source's national level used"
                if regional
                else "source publishes no regional detail; national level used"
            )

    head = Headline(
        level=level,
        basis=basis,
        capital=capital,
        regional_min=lo,
        regional_max=hi,
    )
    head.notes.extend(extra_notes)
    if matched and matched != capital:
        head.notes.append(f"matched on '{matched}'")

    head.caveat = build_caveat(head)
    return head


def build_caveat(head: Headline) -> str | None:
    """The sentence that must travel with the row wherever it is shown.

    Returns None only when the country genuinely carries one level throughout,
    which is the only case where a bare headline tells the whole story.
    """
    if head.level is None or head.regional_max is None or head.regional_min is None:
        return None
    if head.regional_max == head.regional_min == head.level:
        return None

    # Where there is no capital to name, say what the level actually is rather
    # than referring to a city that does not exist.
    where = f"applies to {head.capital}" if head.capital else "is the country-wide figure"
    if head.regional_max > head.level:
        return (
            f"This level {where}. Parts of the country are rated "
            f"higher, up to level {head.regional_max}."
        )
    if head.regional_min < head.level:
        return (
            f"This level {where}. Parts of the country are rated "
            f"lower, down to level {head.regional_min}."
        )
    return None


def apply_to_row(row: dict) -> dict:
    """Rewrite one reconciled country row to publish capital-based levels.

    Keeps the previous roll-up under `country_high` so nothing is lost and the
    detail view can show both.
    """
    iso2 = row.get("iso2") or ""
    for source, bucket in (row.get("sources") or {}).items():
        records = bucket.get("records") or []
        national = bucket.get("level")
        # Defaults to True so a bucket that predates this field, or a test that
        # does not set it, behaves as before.
        stated = bucket.get("national_stated", True)
        head = resolve(records, iso2, national, national_stated=stated)

        bucket["country_high"] = national
        bucket["level"] = head.level
        bucket["level_basis_capital"] = head.basis
        bucket["capital"] = head.capital
        bucket["regional_min"] = head.regional_min
        bucket["regional_max"] = head.regional_max
        bucket["caveat"] = head.caveat
        bucket["uniform"] = head.uniform
        for note in head.notes:
            bucket.setdefault("notes", []).append(note)
    return row
