"""Turning a run's validation output into something a person can read.

Written 10 September 2026, after the fourth dry run. The run itself was fine -
no blocking findings, three sources in, 231 countries reconciled - but the log
was unreadable: `json.dumps(report)[:4000]` spent its whole budget on the same
warning repeated in five-line JSON blocks, and the one genuinely new piece of
information in the run, the US route probe, was computed and then thrown away
because the dry-run branch returned before printing it.

Two rules here, and they are the same rule twice:

  * Say each distinct thing once, with a count. Fifty copies of "no match for
    Birmanie" is one fact and forty-nine repetitions.
  * Never spend the log on what is working. Blocking findings and unmapped
    names get printed in full because they are the list of things somebody has
    to go and fix. Everything else is a count.

The unmapped-name block is the important one. It is the only place the run
tells us which country labels a source uses that we have no alias for, and
each line is directly actionable: add it to ALIASES, or decide it is a place
we do not cover.
"""

from __future__ import annotations

from collections import Counter, defaultdict

RULE = "-" * 72


def _bullet(lines: list[str], text: str) -> None:
    lines.append(f"  {text}")


def format_report(
    report: dict,
    status: dict,
    spine_size: int | None = None,
    probe: dict | None = None,
    japan: dict | None = None,
    shape: dict | None = None,
) -> str:
    """One screen that says what the run found and what needs a human."""
    out: list[str] = []

    # ---- What came back -------------------------------------------------
    out.append(RULE)
    out.append("SOURCES")
    for key, state in sorted(status.items()):
        if state.get("ok"):
            _bullet(out, f"{key}: {state.get('count', 0)} records")
        else:
            _bullet(out, f"{key}: FAILED - {state.get('error', 'no reason given')}")
    if spine_size is not None:
        _bullet(out, f"spine: {spine_size} canonical countries")

    out.append("")
    out.append("COVERAGE")
    for line in report.get("summary", []):
        _bullet(out, line)

    # ---- What must be fixed before publishing ---------------------------
    blocking = report.get("blocking") or []
    out.append("")
    out.append(f"BLOCKING ({len(blocking)})")
    if not blocking:
        _bullet(out, "none")
    for finding in blocking:
        _bullet(out, f"[{finding['code']}] {finding['detail']}")

    # ---- Names we could not place ---------------------------------------
    # Printed in full and deduplicated, because this is the to-do list.
    unmapped = report.get("unmapped_names") or []
    by_source: dict[str, Counter] = defaultdict(Counter)
    for item in unmapped:
        by_source[item.get("source", "?")][item.get("reason", "")] += 1

    out.append("")
    plural = "occurrence" if len(unmapped) == 1 else "occurrences"
    out.append(f"UNMAPPED NAMES ({len(unmapped)} {plural}, "
               f"{sum(len(c) for c in by_source.values())} distinct)")
    if not unmapped:
        _bullet(out, "none")
    for source in sorted(by_source):
        _bullet(out, f"{source}:")
        for reason, count in sorted(by_source[source].items()):
            suffix = f"  (x{count})" if count > 1 else ""
            out.append(f"      {reason}{suffix}")

    # ---- Everything else, counted ---------------------------------------
    others = [w for w in (report.get("warnings") or []) if w.get("code") != "unmapped_name"]
    codes = Counter(w.get("code", "?") for w in others)
    out.append("")
    out.append(f"OTHER WARNINGS ({len(others)})")
    if not others:
        _bullet(out, "none")
    for code, count in codes.most_common():
        examples = [w["detail"] for w in others if w.get("code") == code][:3]
        _bullet(out, f"{code}: {count}")
        for example in examples:
            out.append(f"      e.g. {example}")
        if count > len(examples):
            out.append(f"      ... and {count - len(examples)} more")

    # ---- Where governments disagree -------------------------------------
    divergent = report.get("divergent") or []
    out.append("")
    out.append(f"SOURCES DISAGREE BY 2+ LEVELS ({len(divergent)} shown)")
    if not divergent:
        _bullet(out, "none")
    for item in divergent[:12]:
        levels = " ".join(f"{k}={v}" for k, v in sorted(item.get("levels", {}).items()))
        _bullet(out, f"{item.get('iso2')} {item.get('name')}: spread {item.get('spread')}  {levels}")
    if len(divergent) > 12:
        _bullet(out, f"... and {len(divergent) - 12} more")

    # ---- The US route probe ---------------------------------------------
    # This is the only part of the run that can change on its own without
    # anybody editing code, so it prints every cycle whether or not it moved.
    if probe:
        out.append("")
        out.append("US ROUTE PROBE")
        summary = probe.get("_summary") or {}
        for name in sorted(k for k in probe if k != "_summary"):
            entry = probe[name] or {}
            mark = "OPEN  " if entry.get("usable") else "CLOSED"
            code = entry.get("status")
            _bullet(out, f"{mark} {name:<18} HTTP {code if code is not None else '-':<4} "
                         f"{entry.get('note', '')}")
        if summary.get("open"):
            _bullet(out, f"usable routes: {', '.join(summary['open'])}")
        else:
            _bullet(out, "no published US route answered - the US column cannot be built")

    if shape:
        out.append("")
        out.append("US ROUTE SHAPE - can a level be read out of what answers?")
        for name, entry in sorted(shape.items()):
            if entry.get("error"):
                _bullet(out, f"{name}: ERROR {entry['error']}")
                continue
            _bullet(out, f"{name}:")
            for key, value in sorted(entry.items()):
                shown = value if not isinstance(value, list) else ", ".join(map(str, value))
                out.append(f"      {key}: {shown}")

    if japan:
        out.append("")
        out.append(f"JAPAN: {japan.get('decision', '?')} - {japan.get('reason', '')}")

    out.append(RULE)
    return "\n".join(out)
