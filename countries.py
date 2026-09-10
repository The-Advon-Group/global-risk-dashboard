"""Country reconciliation.

This is the step that usually breaks projects like this, so it is built to fail
loudly rather than quietly. Nothing is ever dropped: a name that cannot be
resolved goes into the run report as an unmapped name, with the source that
produced it, and the table renders that source's cell as Unrated for that row.
No silent guessing, no "undefined".

THE SPINE. Rather than pinning a hand-typed ISO list that will drift, the
canonical set is built at run time from Canada's feed, which is the only source
of the five that publishes ISO 3166-1 alpha-2 codes directly - and, because it
is bilingual, publishes each country's English AND French name against that
code. That second fact does most of France's reconciliation work for free.

Everything else resolves by:
    1. exact ISO2 the source supplied (Canada only)
    2. explicit alias table below (the observed awkward cases)
    3. normalised-name match against the English spine
    4. normalised-name match against the French spine
    5. unresolved -> reported, never guessed
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Names the sources spell in a way no normalisation will reconcile.
# Keyed by normalised name (see `normalise`), value is ISO 3166-1 alpha-2.
ALIASES: dict[str, str] = {
    # --- United States list quirks, observed 8 Sep 2026 ---
    "burma myanmar": "MM",
    "burma": "MM",
    "cote divoire ivory coast": "CI",
    "ivory coast": "CI",
    "democratic republic of the congo drc": "CD",
    "democratic republic of the congo": "CD",
    "republic of the congo": "CG",
    "republic of north macedonia": "MK",
    "north macedonia": "MK",
    "gambia": "GM",
    "kyrgyz republic": "KG",
    "kyrgyzstan": "KG",
    "united kingdom of great britain and northern ireland": "GB",
    "united kingdom": "GB",
    "vatican city holy see": "VA",
    "holy see": "VA",
    "south korea": "KR",
    "korea south": "KR",
    "north korea": "KP",
    "korea north": "KP",
    "timor leste": "TL",
    "east timor": "TL",
    "cabo verde": "CV",
    "cape verde": "CV",
    "czechia": "CZ",
    "czech republic": "CZ",
    "macau": "MO",
    "macao": "MO",
    "taiwan": "TW",
    "antarctica": "AQ",
    "eswatini": "SZ",
    "swaziland": "SZ",
    "turkiye": "TR",
    "turkey": "TR",
    "laos": "LA",
    "brunei": "BN",
    "syria": "SY",
    "russia": "RU",
    "iran": "IR",
    "bolivia": "BO",
    "venezuela": "VE",
    "tanzania": "TZ",
    "moldova": "MD",
    "vietnam": "VN",
    # Caribbean entries the US splits, merges and duplicates. BQ is the ISO code
    # for Bonaire, Sint Eustatius and Saba as one entity; State lists it up to
    # four different ways in the same table.
    "bonaire": "BQ",
    "bonaire sint eustatius and saba": "BQ",
    "saba": "BQ",
    "saba and sint eustatius": "BQ",
    "sint eustatius": "BQ",
    "sint maarten": "SX",
    "curacao": "CW",
    "martinique": "MQ",
    "saint barthelemy": "BL",
    "saint martin": "MF",
    "french saint martin": "MF",
    "reunion": "RE",
    "guadeloupe": "GP",
    "french guiana": "GF",
    "french polynesia": "PF",
    "turks and caicos islands": "TC",
    "new caledonia": "NC",
    # Territories the US advises on under a neighbour's page. The rating is
    # still about the territory, so it keeps its own code and the detail view
    # notes that the source page is shared.
    "west bank": "PS",
    "gaza strip": "PS",
    "palestinian territories": "PS",
    # --- UK / FCDO wordings ---
    "the gambia": "GM",
    "st kitts and nevis": "KN",
    "st lucia": "LC",
    "st vincent and the grenadines": "VC",
    "st helena ascension and tristan da cunha": "SH",
    "british virgin islands": "VG",
    "us virgin islands": "VI",
    "hong kong": "HK",
    "occupied palestinian territories": "PS",
    # --- added 10 Sep 2026, from the first live run's unmapped list ---
    "western sahara": "EH",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "israel": "IL",
    "palestine": "PS",
    "federated states of micronesia": "FM",
    "micronesia": "FM",
    "wallis and futuna": "WF",
    "st pierre and miquelon": "PM",
    "saint pierre and miquelon": "PM",
    "st maarten": "SX",
    "south georgia and the south sandwich islands": "GS",
    "british indian ocean territory": "IO",
    "pitcairn island": "PN",
    "pitcairn": "PN",
    "arctique": "AQ",
    "arctic": "AQ",
    # --- French exonyms, from run #5's unmapped list, 10 Sep 2026 ---
    # France's picker uses French country names throughout, and the spine is
    # built from Canada's English feed, so anything whose French name is not a
    # near-spelling of the English one arrived unmapped. These are France's own
    # labels, taken from the run report rather than guessed at.
    "bielorussie": "BY",
    "birmanie": "MM",
    "cap vert": "CV",
    "iles fidji": "FJ",
    "fidji": "FJ",
    "irak": "IQ",
    "kirghizstan": "KG",
    "libye": "LY",
    "moldavie": "MD",
    "republique des palaos": "PW",
    "palaos": "PW",
    "republique tcheque": "CZ",
    "tchequie": "CZ",
    "saint christophe et nieves": "KN",
    "saint vincent et les grenadines": "VC",
    "timor oriental": "TL",
    "turquie": "TR",
    "vatican": "VA",
    "saint siege": "VA",
    "etats federes de micronesie": "FM",
    "micronesie": "FM",
}

# Some sources publish ONE page covering SEVERAL countries. The FCDO does this
# for a handful of small territories. A one-name-to-one-country model silently
# loses the others: before this existed, "Cook Islands, Tokelau and Niue"
# prefix-matched to the Cook Islands alone and Tokelau and Niue quietly received
# no UK rating at all. That is exactly the silent gap this build is meant not to
# have, so these names resolve to every country they cover and the record is
# duplicated across them, each noting the shared page.
MULTI_COUNTRY: dict[str, list[str]] = {
    "cook islands tokelau and niue": ["CK", "TK", "NU"],
    "st martin and st barthelemy": ["MF", "BL"],
    "saint martin and saint barthelemy": ["MF", "BL"],
    "bonaire st eustatius saba": ["BQ"],
    "bonaire sint eustatius saba": ["BQ"],
    "antarctica british antarctic territory": ["AQ"],
    # France publishes one page titled "Israel / Palestine" covering both, and
    # its zone bands run across the whole of it.
    "israel palestine": ["IL", "PS"],
    # State's feed carries one advisory titled "Mainland China, Hong Kong &
    # Macau" and separate items for the two territories. Hong Kong and Macau
    # therefore hold two US records each, and the roll-up takes the higher -
    # which is the combined advisory whenever State rates the mainland above the
    # territory. That is deliberate rather than a merge bug: State is telling
    # both things, and the detail view shows both records.
    "mainland china hong kong and macau": ["CN", "HK", "MO"],
    "mainland china": ["CN"],
}

# Names that are genuinely ambiguous and must NEVER be guessed. "Congo" is the
# obvious one: the FCDO uses it for the Republic of the Congo and lists the
# Democratic Republic separately, but other sources use it the other way round.
# Resolving it by proximity or prefix would put a level-3 advisory on the wrong
# country, so it is reported as unmapped with the reason stated.
AMBIGUOUS: dict[str, str] = {
    "congo": "ambiguous between Republic of the Congo (CG) and "
             "Democratic Republic of the Congo (CD) - source must be checked",
}

# Sources that advise on a territory via another country's page. Recorded so
# the detail view can say "the US publishes this under its France page" rather
# than looking like a data error.
SHARED_PAGE_NOTE: dict[tuple[str, str], str] = {
    ("us", "MC"): "State publishes Monaco within its France advisory",
    ("us", "VA"): "State publishes Vatican City within its Italy advisory",
}

def _build_alias_index() -> dict[str, str]:
    """Fold the alias table through `normalise` so its keys can never rot.

    Written by hand, the table is easy to get subtly wrong: an entry keyed
    "martinique french west indies" looks right but is unreachable, because
    normalise() strips the bracketed part before lookup and the incoming name
    arrives as "martinique". Normalising the keys at import removes that whole
    class of dead entry and makes the table's spelling irrelevant.
    """
    index: dict[str, str] = {}
    for raw, iso2 in ALIASES.items():
        key = normalise(raw)
        if key:
            index[key] = iso2
    return index


_PARENS = re.compile(r"\([^)]*\)")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")
_LEADING_THE = re.compile(r"^the\s+")


def normalise(name: str) -> str:
    """Fold a country name to a comparable key.

    Strips accents, drops bracketed alternates, removes punctuation and a
    leading "the". Deliberately conservative: it never reorders words or
    truncates, because doing so is how "Congo" ends up on the wrong row.
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ").replace("'", "").replace("’", "")
    text = _PARENS.sub(" ", text)
    text = _NONWORD.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    text = _LEADING_THE.sub("", text)
    return text


_ALIAS_INDEX: dict[str, str] = _build_alias_index()
_MULTI_INDEX: dict[str, list[str]] = {
    normalise(k): v for k, v in MULTI_COUNTRY.items() if normalise(k)
}
_AMBIGUOUS_INDEX: dict[str, str] = {
    normalise(k): v for k, v in AMBIGUOUS.items() if normalise(k)
}


def resolve_all(name: str, spine: "Spine", *, supplied_iso2: str | None = None) -> list["Resolution"]:
    """Resolve a source's name to EVERY country it covers.

    Almost always one. Returns several only for the shared pages listed in
    MULTI_COUNTRY, and none at all for a name in AMBIGUOUS or one nothing
    matches - in which case the single unresolved Resolution carries the reason.
    """
    key = normalise(name)
    if key in _AMBIGUOUS_INDEX:
        return [Resolution(None, "ambiguous", _AMBIGUOUS_INDEX[key])]
    if key in _MULTI_INDEX:
        codes = _MULTI_INDEX[key]
        return [
            Resolution(code, "multi-country page",
                       f"'{name}' is one source page covering {len(codes)} countries")
            for code in codes
        ]
    return [resolve(name, spine, supplied_iso2=supplied_iso2)]


@dataclass
class Spine:
    """Canonical country set, built from Canada's bilingual feed."""

    by_iso: dict[str, str] = field(default_factory=dict)          # ISO2 -> English name
    eng_index: dict[str, str] = field(default_factory=dict)       # normalised eng -> ISO2
    fra_index: dict[str, str] = field(default_factory=dict)       # normalised fra -> ISO2

    @classmethod
    def from_canada(cls, payload: dict) -> "Spine":
        spine = cls()
        for iso2, entry in (payload.get("data") or {}).items():
            code = (iso2 or "").upper()
            if not code:
                continue
            eng = entry.get("country-eng") or ""
            fra = entry.get("country-fra") or ""
            spine.by_iso[code] = eng or code
            if eng:
                spine.eng_index[normalise(eng)] = code
            if fra:
                spine.fra_index[normalise(fra)] = code

        # Canada publishes no advice about Canada, so the spine built from its
        # feed has a Canada-shaped hole in it. The first live run surfaced this
        # as the FCDO's "Canada" failing to resolve. Every source country has
        # the same gap in its own feed, so all four are seeded explicitly - they
        # are countries the dashboard must be able to list even though the
        # source that names them cannot.
        for code, eng, fra in (
            ("CA", "Canada", "Canada"),
            ("US", "United States", "États-Unis"),
            ("GB", "United Kingdom", "Royaume-Uni"),
            ("FR", "France", "France"),
        ):
            spine.by_iso.setdefault(code, eng)
            spine.eng_index.setdefault(normalise(eng), code)
            spine.fra_index.setdefault(normalise(fra), code)
        return spine

    def add(self, iso2: str, name: str) -> None:
        code = iso2.upper()
        self.by_iso.setdefault(code, name)
        self.eng_index.setdefault(normalise(name), code)


@dataclass
class Resolution:
    iso2: str | None
    method: str
    note: str | None = None


def resolve(name: str, spine: Spine, *, supplied_iso2: str | None = None) -> Resolution:
    if supplied_iso2:
        code = supplied_iso2.upper()
        if code in spine.by_iso:
            return Resolution(code, "iso2 supplied by source")
        spine.add(code, name)
        return Resolution(code, "iso2 supplied by source (not in spine; added)")

    key = normalise(name)
    if not key:
        return Resolution(None, "unresolved", "empty name")

    if key in _AMBIGUOUS_INDEX:
        return Resolution(None, "ambiguous", _AMBIGUOUS_INDEX[key])
    if key in _ALIAS_INDEX:
        return Resolution(_ALIAS_INDEX[key], "alias table")
    if key in spine.eng_index:
        return Resolution(spine.eng_index[key], "english name match")
    if key in spine.fra_index:
        return Resolution(spine.fra_index[key], "french name match")

    # Last chance: a source name that contains the spine name as a whole prefix,
    # e.g. "Nigeria travel advice". Requires a word boundary so "Niger" never
    # swallows "Nigeria".
    for index in (spine.eng_index, spine.fra_index):
        for candidate, code in index.items():
            if candidate and re.match(rf"{re.escape(candidate)}\b", key):
                return Resolution(code, "prefix match", f"matched spine name '{candidate}'")

    return Resolution(None, "unresolved", f"no match for '{name}' (normalised: '{key}')")


def roll_up(levels: list[int | None]) -> int | None:
    """A country takes the highest level of any of its rated regions.

    None values are ignored rather than treated as zero; a country whose only
    records are unrated stays unrated.
    """
    real = [lvl for lvl in levels if isinstance(lvl, int)]
    return max(real) if real else None
