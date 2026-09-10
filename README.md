# Global Risk Dashboard — collection pipeline

Phase 1 of the free, public, all-countries risk dashboard. This repository holds
the collectors, the country reconciler, the validator and the snapshot store.
The page itself (Phase 3) and the terrorism composite (Phase 2) are not here yet.

## What runs

```
python pipeline.py                      # full run, writes a snapshot
python pipeline.py --sources ca,uk,us   # subset
python pipeline.py --dry-run            # collect and report, write nothing
python pipeline.py --refresh-fr-slugs   # rebuild France's id->slug map
python test_pipeline.py                 # offline tests, no network needed
```

## Source status, as verified 8 September 2026

| Source | State | Cost per cycle | Notes |
|---|---|---|---|
| Canada | Ready | 1 request | Official JSON, ISO codes, bilingual. The cleanest of the five. |
| United Kingdom | Ready | 1 + ~230 | GOV.UK Content API. `alert_status` is a published field, not an inference. |
| United States | Ready | 1 request | The advisories list page is server-rendered in full. |
| France | Ready | ~200 | Per-country pages. Etalab 2.0 confirmed in the page footer. |
| Japan | **Not ready** | — | The recorded endpoint is the wrong feed. See below. |

Three of these differ from what the sources record said, in both directions.

**United States — was a blocker, now the cheapest source.** The record said the
US column might need per-country crawling. It does not. The list page at
`travel.state.gov/en/international-travel/travel-advisories.html` is fully
server-rendered: one GET returns all 228 destinations with level, risk-indicator
tags and issue date. The five-row table you see in a browser is JavaScript
pagination applied after load, which a plain HTTP fetch never runs.

`cadataapi.state.gov` is also real, public and unauthenticated — but its
`/api/TravelAdvisories` endpoint returns an empty result set today, so it cannot
supply levels. `us.probe_cadataapi()` checks it every cycle and reports into the
run record, so if State ever populates it we find out without looking.

Separately, `/api/CountryTravelInformation` on that API returns full narrative
text for every country — including the `Terrorism:` block of each safety and
security section. That is the raw corpus the Phase 2 phrase ladder needs, and
`us.fetch_country_narratives()` retrieves it.

**France — was "not launch-ready", now ready.** Both open questions closed:

- *Licence.* The country pages themselves carry the grant in their footer:
  "Sauf mention explicite de propriété intellectuelle détenue par des tiers, les
  contenus de ce site sont proposés sous licence etalab-2.0." Licence Ouverte
  2.0 permits commercial reuse with attribution. That is documented on the exact
  pages we read, not inferred from the stale data.gouv.fr dataset. The carve-out
  is real though — third-party IP is excluded, so we take ratings and text and
  never the maps or photographs.
- *Retrieval.* The site was restructured and the old URLs 404. Current shape is
  `/fr/information-par-pays/{slug}/conseils-aux-voyageurs-securite`, which
  carries a structured "Zones de vigilance" block using France's four colour
  bands as headings, its own "dernière actualisation" date, and an explicit
  "information toujours valable à la date du jour" line. That last line is worth
  surfacing on the page: the standing public complaint about France Diplomatie
  going stale is answerable per-country, from the source itself.

**Japan — was "ready to go", is not.** The endpoint in the sources record,
`ezairyu.mofa.go.jp/html/opendata/area/00.xml`, was fetched and read. It is the
consular-mail (領事メール) change feed: embassy notices with a key, an info type,
a timestamp, a title and a lead. It carries no current danger level, and the
served index includes sample rows dated 2019. It is Japan's equivalent of the US
RSS feed — good for "what moved recently", useless as a registry.

Japan's actual 4-level ratings live on `anzen.mofa.go.jp` as per-country HTML.
The interactive risk map is an image map whose script only navigates to those
pages; there is no JSON behind it. So Japan needs a per-country reader (~200
pages per cycle) that has not been built. The licence is not the problem — MOFA
states plainly that the data may be used 営利目的・非営利目的を問わず, commercial
or not.

**This is a decision, not a defect.** Launch without Japan and the composite
still has four sources, clearing its three-source minimum; Japan's column renders
Unrated and says why. Or fund the reader — roughly a day, and it is a
page-structure dependency on a site with no published stability guarantee.
`collectors/japan.py` collects nothing until that is decided, rather than
shipping a column built on the wrong feed.

## How the pieces fit

**Collectors** (`collectors/`) each return a list of identical `Record` dicts:
source, the name exactly as that government spells it, level on the shared 1–4
scale, the source's own wording, how the level was derived, indicators, the link
to the original page, when the source last changed it, and when we retrieved it.
A collector never invents a value; if it cannot determine a level it emits
`None` and says why in `notes`.

**Reconciliation** (`countries.py`) is the step that usually breaks projects like
this. Canada's feed is the spine — it is the only source publishing ISO 3166-1
alpha-2 codes directly, and because it is bilingual it gives each country's
English *and* French name against that code, which does most of France's
reconciliation for free. Everything else resolves by supplied ISO code, then an
explicit alias table, then normalised English, then normalised French, then a
bounded prefix match. A name that survives all five is reported as unmapped. It
is never guessed.

The alias table exists because the sources genuinely disagree about names:
"Burma (Myanmar)", "Côte d'Ivoire (Ivory-Coast)", "Democratic Republic of the
Congo (D.R.C.)", "The Kyrgyz Republic", "United Kingdom of Great Britain and
Northern Ireland". State also lists the Caribbean Netherlands four different
ways in one table — "Bonaire", "Saba", "Saba and Sint Eustatius", and "Bonaire,
Sint Eustatius, and Saba" — all of which are ISO `BQ`. And it publishes Monaco
under its France page and Vatican City under its Italy page, which looks like a
data error until the detail view says so; `SHARED_PAGE_NOTE` makes it say so.

Alias keys are folded through `normalise()` at import, so an entry can never
silently rot into an unreachable key. That bug existed and the test suite caught
it.

**Roll-up.** Regional ratings are stored as their own records and a country takes
the highest level of any rated region. Unrated regions are ignored rather than
counted as zero, so a country whose only records are unrated stays unrated.

**Validation** (`validate.py`) exists because the 13-country dashboard renders
the word "undefined" when a field is missing, and that defect is not being
inherited. Every cell is either a real value or Unrated with a stated reason.
There is no third state. Missing required fields block a publish; everything
else is reported and shipped, because a dashboard that refuses to render over
one missing country is worse than one that says that country is Unrated.

The validator also surfaces **disagreement**: where sources differ by two levels
or more, ranked widest first. Per the plan that is a feature — five governments
looking at the same country and reaching different conclusions is real
information, and no free competitor shows it.

**Failure handling.** A source that cannot be reached does not fail the run. Its
column carries the last known value from the previous snapshot, marked stale
with its age, and falls to Unrated once past the per-source staleness limit
(24h for the daily-ish sources, 72h for France and Japan). A source that returns
implausibly little data fails loudly instead of publishing a partial column —
`MIN_EXPECTED` sets the floor.

**Snapshots** are written to `snapshots/YYYY/MM/` every run, plus `data/latest.json`.
History accrues from day one, which also works around MOFA deleting posted
information after a year.

## Tests

`python test_pipeline.py` runs offline. The fixtures are real payloads captured
on 8 September 2026 — the US HTML is genuine row markup from the live page, not
an approximation — and the awkward-names test uses the actual strings each
government publishes. 48 checks, no network required.

## Anonymity — read before the first commit

A public repository exposes the commit author's name and email on every commit.
The GitHub account, the organisation and the local git identity all need to be a
project identity from the very first commit, not a personal one. Retrofitting
this means rewriting history, and by then copies may already exist.

Set `COMMIT_NAME` and `COMMIT_EMAIL` as repository variables before enabling the
workflow; it falls back to `risk-dashboard-bot` if they are unset.

## Attribution

Each source has its own stated requirement and they differ. CDC needs four
specific statements including a non-endorsement disclaimer; Japan needs a set
citation format plus a disclosure if content is edited; Copernicus needs wording
that changes depending on whether data was modified; the JRC notice needs source
acknowledgement; OGL and OGL-Canada have their own forms; Etalab 2.0 needs
attribution and excludes third-party IP. This gets written once, carefully, in
Phase 3, checked against each source's own words.

## Not done yet

- Phase 2: terrorism composite, phrase ladder, the 20-country hand-check
- Phase 3: the page, per-country detail views, the attribution block
- Phase 4: scheduled runs, the 60-day keepalive, the external staleness check
- Japan: the decision above
- Crime: ships Unrated, per the September 2026 decision
