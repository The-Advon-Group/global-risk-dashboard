"""Capital cities, keyed by ISO 3166-1 alpha-2.

Decision, 10 September 2026: the dashboard's headline level for a country is the
level that applies to its CAPITAL CITY, not the highest level applying anywhere
in the country. The regional spread is kept and shown as a caveat.

This is a deliberate departure from the Phase 1 roll-up rule and it changes what
the main table means. The reasoning is that a single "worst province" figure
makes most of Africa and half of Asia look uniformly severe, which is neither
true nor useful to someone deciding whether to travel. The cost is that the
caveat has to do real work for countries where the danger is outside the
capital, so the caveat is a first-class field here, never fine print.

`ALIASES` carries the spellings the sources actually use, plus the older or
alternative names that still appear in advisory text - Rangoon for Yangon,
Saigon for Ho Chi Minh City - because a source naming the old form in a
regional carve-out still means the same city.

Seats of government that are not the ISO capital are recorded where the
advisory text tends to use them: Netherlands (The Hague alongside Amsterdam),
Bolivia (La Paz and Sucre), South Africa (three capitals), Côte d'Ivoire
(Abidjan alongside Yamoussoukro).
"""

from __future__ import annotations

import re
import unicodedata

CAPITALS: dict[str, str] = {
    "AF": "Kabul", "AL": "Tirana", "DZ": "Algiers", "AD": "Andorra la Vella",
    "AO": "Luanda", "AG": "Saint John's", "AR": "Buenos Aires", "AM": "Yerevan",
    "AU": "Canberra", "AT": "Vienna", "AZ": "Baku", "BS": "Nassau",
    "BH": "Manama", "BD": "Dhaka", "BB": "Bridgetown", "BY": "Minsk",
    "BE": "Brussels", "BZ": "Belmopan", "BJ": "Porto-Novo", "BT": "Thimphu",
    "BO": "La Paz", "BA": "Sarajevo", "BW": "Gaborone", "BR": "Brasilia",
    "BN": "Bandar Seri Begawan", "BG": "Sofia", "BF": "Ouagadougou",
    "BI": "Gitega", "CV": "Praia", "KH": "Phnom Penh", "CM": "Yaounde",
    "CA": "Ottawa", "CF": "Bangui", "TD": "N'Djamena", "CL": "Santiago",
    "CN": "Beijing", "CO": "Bogota", "KM": "Moroni", "CD": "Kinshasa",
    "CG": "Brazzaville", "CR": "San Jose", "CI": "Yamoussoukro", "HR": "Zagreb",
    "CU": "Havana", "CY": "Nicosia", "CZ": "Prague", "DK": "Copenhagen",
    "DJ": "Djibouti", "DM": "Roseau", "DO": "Santo Domingo", "EC": "Quito",
    "EG": "Cairo", "SV": "San Salvador", "GQ": "Malabo", "ER": "Asmara",
    "EE": "Tallinn", "SZ": "Mbabane", "ET": "Addis Ababa", "FJ": "Suva",
    "FI": "Helsinki", "FR": "Paris", "GA": "Libreville", "GM": "Banjul",
    "GE": "Tbilisi", "DE": "Berlin", "GH": "Accra", "GR": "Athens",
    "GD": "Saint George's", "GT": "Guatemala City", "GN": "Conakry",
    "GW": "Bissau", "GY": "Georgetown", "HT": "Port-au-Prince",
    "HN": "Tegucigalpa", "HU": "Budapest", "IS": "Reykjavik", "IN": "New Delhi",
    "ID": "Jakarta", "IR": "Tehran", "IQ": "Baghdad", "IE": "Dublin",
    "IL": "Jerusalem", "IT": "Rome", "JM": "Kingston", "JP": "Tokyo",
    "JO": "Amman", "KZ": "Astana", "KE": "Nairobi", "KI": "Tarawa",
    "KP": "Pyongyang", "KR": "Seoul", "KW": "Kuwait City", "KG": "Bishkek",
    "LA": "Vientiane", "LV": "Riga", "LB": "Beirut", "LS": "Maseru",
    "LR": "Monrovia", "LY": "Tripoli", "LI": "Vaduz", "LT": "Vilnius",
    "LU": "Luxembourg", "MG": "Antananarivo", "MW": "Lilongwe",
    "MY": "Kuala Lumpur", "MV": "Male", "ML": "Bamako", "MT": "Valletta",
    "MH": "Majuro", "MR": "Nouakchott", "MU": "Port Louis", "MX": "Mexico City",
    "FM": "Palikir", "MD": "Chisinau", "MC": "Monaco", "MN": "Ulaanbaatar",
    "ME": "Podgorica", "MA": "Rabat", "MZ": "Maputo", "MM": "Naypyidaw",
    "NA": "Windhoek", "NR": "Yaren", "NP": "Kathmandu", "NL": "Amsterdam",
    "NZ": "Wellington", "NI": "Managua", "NE": "Niamey", "NG": "Abuja",
    "MK": "Skopje", "NO": "Oslo", "OM": "Muscat", "PK": "Islamabad",
    "PW": "Ngerulmud", "PS": "Ramallah", "PA": "Panama City",
    "PG": "Port Moresby", "PY": "Asuncion", "PE": "Lima", "PH": "Manila",
    "PL": "Warsaw", "PT": "Lisbon", "QA": "Doha", "RO": "Bucharest",
    "RU": "Moscow", "RW": "Kigali", "KN": "Basseterre", "LC": "Castries",
    "VC": "Kingstown", "WS": "Apia", "SM": "San Marino", "ST": "Sao Tome",
    "SA": "Riyadh", "SN": "Dakar", "RS": "Belgrade", "SC": "Victoria",
    "SL": "Freetown", "SG": "Singapore", "SK": "Bratislava", "SI": "Ljubljana",
    "SB": "Honiara", "SO": "Mogadishu", "ZA": "Pretoria", "SS": "Juba",
    "ES": "Madrid", "LK": "Colombo", "SD": "Khartoum", "SR": "Paramaribo",
    "SE": "Stockholm", "CH": "Bern", "SY": "Damascus", "TW": "Taipei",
    "TJ": "Dushanbe", "TZ": "Dodoma", "TH": "Bangkok", "TL": "Dili",
    "TG": "Lome", "TO": "Nuku'alofa", "TT": "Port of Spain", "TN": "Tunis",
    "TR": "Ankara", "TM": "Ashgabat", "TV": "Funafuti", "UG": "Kampala",
    "UA": "Kyiv", "AE": "Abu Dhabi", "GB": "London", "US": "Washington",
    "UY": "Montevideo", "UZ": "Tashkent", "VU": "Port Vila", "VA": "Vatican City",
    "VE": "Caracas", "VN": "Hanoi", "YE": "Sanaa", "ZM": "Lusaka",
    "ZW": "Harare",
    # Territories and dependencies that carry their own advisories.
    "AW": "Oranjestad", "AI": "The Valley", "BM": "Hamilton", "BQ": "Kralendijk",
    "KY": "George Town", "CW": "Willemstad", "PF": "Papeete", "GF": "Cayenne",
    "GP": "Basse-Terre", "GU": "Hagatna", "HK": "Hong Kong", "MO": "Macau",
    "MQ": "Fort-de-France", "MS": "Brades", "NC": "Noumea", "PR": "San Juan",
    "RE": "Saint-Denis", "BL": "Gustavia", "MF": "Marigot", "SX": "Philipsburg",
    "TC": "Cockburn Town", "VG": "Road Town", "VI": "Charlotte Amalie",
    "AS": "Pago Pago", "SH": "Jamestown", "FK": "Stanley", "GI": "Gibraltar",
    "GL": "Nuuk", "FO": "Torshavn",
    # Added 10 Sep 2026: every code in Canada's feed that had no capital here,
    # found by diffing the table against the live spine rather than guessing.
    "PT-20": "Ponta Delgada",      # Azores, as Canada codes it
    "IC": "Las Palmas",            # Canary Islands; co-capital with Santa Cruz
    "CK": "Avarua",                # Cook Islands
    "XK": "Pristina",              # Kosovo
    "YT": "Mamoudzou",             # Mayotte
    "NU": "Alofi",                 # Niue
    "MP": "Saipan",                # Northern Mariana Islands
    "PM": "Saint-Pierre",          # Saint Pierre and Miquelon
    "EH": "Laayoune",              # Western Sahara, de facto seat
}

# Entries that genuinely have no capital city. They are not omissions, and the
# code must not treat them as gaps to be filled later: Antarctica has no
# government, and Tokelau's three atolls rotate the seat annually rather than
# holding one. Rows for these publish the source's country-wide figure and say
# so in the caveat instead of naming a city.
NO_CAPITAL = {"AQ": "Antarctica has no capital", "TK": "Tokelau's seat rotates annually"}

# Additional names for the same city, including seats of government that differ
# from the ISO capital and older forms still used in advisory prose.
ALIASES: dict[str, list[str]] = {
    "NL": ["The Hague", "'s-Gravenhage", "Den Haag"],
    "BO": ["Sucre"],
    "ZA": ["Cape Town", "Bloemfontein", "Johannesburg"],
    "CI": ["Abidjan"],
    "BJ": ["Cotonou"],
    "TZ": ["Dar es Salaam"],
    "MM": ["Nay Pyi Taw", "Yangon", "Rangoon"],
    "VN": ["Ha Noi"],
    "KZ": ["Nur-Sultan", "Astana", "Almaty"],
    "IL": ["Tel Aviv"],
    "PS": ["Ramallah", "Gaza City"],
    "LK": ["Sri Jayawardenepura Kotte"],
    "SZ": ["Lobamba"],
    "US": ["Washington DC", "Washington, D.C."],
    "GB": ["London"],
    "CD": ["Kinshasa"],
    "MY": ["Putrajaya"],
    "TR": ["Istanbul"],  # not the capital, but carve-outs routinely name it
    "MA": ["Casablanca"],
    "EG": ["Cairo"],
    "NG": ["Abuja"],
    # Added 10 Sep 2026. Some sources locate a capital by naming the island or
    # region it sits on rather than the city - France's Seychelles page bands
    # "Mahe, Praslin, La Digue et Silhouette" as green without mentioning
    # Victoria, which is on Mahe.
    "SC": ["Mahe"],
    "MU": ["Ile Maurice"],
    "MV": ["Male Atoll"],
}

# French spellings, added 10 Sep 2026 after run #7.
#
# France names cities in French, and the table above is in English, so
# `mentioned_in` could not find a single one of them. Algeria is the case that
# made it obvious: France's green band says "Alger et Oran sont en zones de
# vigilance normale" - it puts the capital in the safest band and names it -
# and the matcher was looking for "Algiers". The row came out right only by
# accident, because the lowest band happened to be the right answer.
#
# Only the names that actually differ are listed. Accents are irrelevant here
# because matching runs on the de-accented form, but they are written as France
# writes them so the table can be checked against the source by eye.
FRENCH_CAPITALS: dict[str, list[str]] = {
    "DZ": ["Alger"], "EG": ["Le Caire"], "GB": ["Londres"], "RU": ["Moscou"],
    "CN": ["Pékin"], "IQ": ["Bagdad"], "SY": ["Damas"], "IR": ["Téhéran"],
    "CU": ["La Havane"], "GR": ["Athènes"], "PL": ["Varsovie"], "AT": ["Vienne"],
    "BE": ["Bruxelles"], "DK": ["Copenhague"], "PT": ["Lisbonne"],
    "RO": ["Bucarest"], "CY": ["Nicosie"], "LB": ["Beyrouth"], "SA": ["Riyad"],
    "OM": ["Mascate"], "KW": ["Koweït"], "AE": ["Abou Dabi"],
    "GE": ["Tbilissi"], "AM": ["Erevan"], "AZ": ["Bakou"], "TM": ["Achgabat"],
    "UZ": ["Tachkent"], "TJ": ["Douchanbé"], "KG": ["Bichkek"], "AF": ["Kaboul"],
    "NP": ["Katmandou"], "BD": ["Dacca"], "MM": ["Rangoun"], "VN": ["Hanoï"],
    "KR": ["Séoul"], "PH": ["Manille"], "SG": ["Singapour"],
    "ET": ["Addis-Abeba"], "SO": ["Mogadiscio"], "TZ": ["Dar es Salam"],
    "ZA": ["Le Cap"], "MX": ["Mexico"], "DO": ["Saint-Domingue"],
    "PA": ["Panama"], "GT": ["Guatemala"], "MA": ["Rabat", "Marrakech"],
    "TR": ["Istanbul", "Ankara"], "IL": ["Jérusalem"], "PS": ["Gaza"],
    "CH": ["Berne"], "IT": ["Rome"], "ES": ["Madrid"], "DE": ["Berlin"],
    "NL": ["La Haye", "Amsterdam"], "SE": ["Stockholm"], "NO": ["Oslo"],
    "IE": ["Dublin"], "IS": ["Reykjavik"], "FI": ["Helsinki"],
    "UA": ["Kiev", "Kyiv"], "BY": ["Minsk"], "MD": ["Chisinau"],
    "RS": ["Belgrade"], "AL": ["Tirana"], "MK": ["Skopje"],
    "LY": ["Tripoli"], "TN": ["Tunis"], "MR": ["Nouakchott"],
    "CM": ["Yaoundé"], "CI": ["Abidjan"], "CD": ["Kinshasa"],
    "MG": ["Antananarivo"], "KM": ["Moroni"], "LK": ["Colombo"],
    "TH": ["Bangkok"], "KH": ["Phnom Penh"], "LA": ["Vientiane"],
    "ID": ["Jakarta"], "MY": ["Kuala Lumpur"], "IN": ["New Delhi"],
    "PK": ["Islamabad"], "JP": ["Tokyo"], "BR": ["Brasilia"],
    "AR": ["Buenos Aires"], "CO": ["Bogota"], "VE": ["Caracas"],
    "PE": ["Lima"], "CL": ["Santiago"], "BO": ["La Paz"],
    "HT": ["Port-au-Prince"], "JM": ["Kingston"], "NG": ["Abuja", "Lagos"],
}

for _code, _names in FRENCH_CAPITALS.items():
    ALIASES.setdefault(_code, [])
    for _name in _names:
        if _name not in ALIASES[_code]:
            ALIASES[_code].append(_name)


def _flat(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.replace("'", "'")).strip().lower()


def names_for(iso2: str) -> list[str]:
    """Every name a source might use for this country's capital.

    The ISO capital comes first; it is the one shown to the reader. Aliases
    follow and are used only for matching against regional carve-out text.
    """
    code = (iso2 or "").upper()
    primary = CAPITALS.get(code)
    if not primary:
        return []
    out = [primary]
    for alias in ALIASES.get(code, []):
        if alias not in out:
            out.append(alias)
    return out


def capital_of(iso2: str) -> str | None:
    return CAPITALS.get((iso2 or "").upper())


def mentioned_in(text: str, iso2: str) -> str | None:
    """Return the capital name a passage mentions, or None.

    Matched on word boundaries against the de-accented form, so "Bamako" in
    "Bamako et ses environs" matches and "Niamey" never matches inside another
    word. Returns the name that matched, so the caller can quote it.
    """
    if not text:
        return None
    flat = _flat(text)
    for name in names_for(iso2):
        if re.search(rf"\b{re.escape(_flat(name))}\b", flat):
            return name
    return None
