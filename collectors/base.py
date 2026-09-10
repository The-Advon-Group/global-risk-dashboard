"""Shared plumbing for every source collector.

Every collector returns a list of Record dicts with an identical shape, so the
reconciler and the page never need to know which government produced a row.

Design rules that matter downstream:
  * A collector NEVER invents a value. If it cannot determine a level it emits
    level=None and appends a reason to `notes`. The validator surfaces those.
  * Regional ratings are kept as separate records with `region` set. The
    country-level roll-up happens in the reconciler, not here, so the raw
    regional detail survives into the per-country detail view.
  * `retrieved_at` is stamped per record so "last verified" is honest even when
    one source failed and its column is serving a previous value.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import requests

USER_AGENT = (
    "AdvonGroup-GlobalRiskDashboard/0.1 "
    "(+https://github.com/advon-risk/global-risk-dashboard; public-source aggregator)"
)

# The shared 4-point scale every source is mapped onto.
#   1 = normal precautions
#   2 = increased caution
#   3 = reconsider / avoid non-essential travel
#   4 = do not travel
SCALE = {
    1: "Normal precautions",
    2: "Increased caution",
    3: "Avoid non-essential travel",
    4: "Do not travel",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Record:
    source: str                      # short key: us, uk, ca, fr, jp
    source_name: str                 # human label used in attribution
    raw_name: str                    # the name exactly as the source spells it
    url: str                         # link to the original page for this entry
    retrieved_at: str = field(default_factory=utcnow)
    iso2: str | None = None          # filled by the reconciler, not the collector
    region: str | None = None        # None = whole-country rating
    level: int | None = None         # 1-4 on the shared scale, or None
    level_label: str | None = None   # the source's own wording, untranslated
    level_basis: str | None = None   # how `level` was derived - shown in the UI
    indicators: list[str] = field(default_factory=list)  # e.g. ["T", "C"]
    source_updated: str | None = None  # when the SOURCE last changed it
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CollectorError(RuntimeError):
    """Raised when a source cannot be retrieved at all.

    The pipeline catches this per-source so one dead feed never takes the whole
    run down; the column falls back to the previous snapshot and ages.
    """


def get(url: str, *, timeout: int = 45, retries: int = 3, **kwargs) -> requests.Response:
    """GET with a real UA, linear backoff, and a hard failure that says why."""
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en,fr;q=0.8,ja;q=0.6"}
    headers.update(kwargs.pop("headers", {}))
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, **kwargs)
            if resp.status_code == 200:
                return resp
            last = CollectorError(f"HTTP {resp.status_code} from {url}")
        except requests.RequestException as exc:  # network-level failure
            last = exc
        if attempt < retries:
            time.sleep(2 * attempt)
    raise CollectorError(f"{url} unreachable after {retries} attempts: {last}")
