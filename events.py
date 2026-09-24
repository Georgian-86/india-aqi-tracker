"""Log when a city's US AQI category changes: data/aqi_events.csv.

Runs every 3 hours (.github/workflows/events.yml). It reads the current US
AQI for every city and appends a row only when a city has moved to a
different category since its last logged one, so the log (and the commit
history) follows the air: nothing on a steady day, several rows when smog
or dust moves through.

A change counts only once the reading is MARGIN points past the edge of the
recorded category. A city hovering at 99-102 would otherwise flip between
Moderate and "Unhealthy for Sensitive Groups" on every run.

The first reading of a city is logged with an empty from_category, to
establish its state.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import fetch
from common import (
    AQI_CATEGORIES,
    CITIES,
    EVENT_COLUMNS,
    EVENTS_CSV_PATH,
    HAZARDOUS,
    aqi_category,
    read_rows,
)

MARGIN = 10  # AQI points past the edge of the recorded category
ORDER = [label for _, label in AQI_CATEGORIES] + [HAZARDOUS]
UPPER = {label: upper for upper, label in AQI_CATEGORIES}  # inclusive; none for Hazardous


def build_params() -> dict[str, str]:
    """Current values only: a small request, still one call for all cities."""
    return {
        "latitude": ",".join(f"{lat}" for _, lat, _ in CITIES),
        "longitude": ",".join(f"{lon}" for _, _, lon in CITIES),
        "current": ",".join(fetch.CURRENT_VARS),
        "timezone": fetch.TIMEZONE,
    }


def last_categories(event_rows: list[dict[str, str]]) -> dict[str, str]:
    """Each city's most recently logged category."""
    state: dict[str, str] = {}
    for r in sorted(event_rows, key=lambda r: r["time_ist"]):
        state[r["city"]] = r["to_category"]
    return state


def changed(previous: str | None, aqi: float) -> bool:
    """Whether a reading has left the previous category by at least MARGIN."""
    if previous is None:
        return True  # first reading: establishes the state
    i = ORDER.index(previous)
    if i < len(ORDER) - 1 and aqi >= UPPER[previous] + MARGIN:
        return True  # moved up
    if i > 0 and aqi <= UPPER[ORDER[i - 1]] - MARGIN:
        return True  # moved down
    return False


def detect(
    readings: list[dict[str, str]], state: dict[str, str]
) -> tuple[list[dict[str, str]], list[str]]:
    """Event rows for readings that change their city's category.

    readings are fetch.parse_payload rows plus a "time_ist" key. Returns
    (events, cities skipped for having no US AQI).
    """
    events, skipped = [], []
    for r in readings:
        if not r["us_aqi"]:
            skipped.append(r["city"])
            continue
        aqi = float(r["us_aqi"])
        previous = state.get(r["city"])
        if not changed(previous, aqi) or aqi_category(aqi) == previous:
            continue
        events.append({
            "time_ist": r["time_ist"],
            "city": r["city"],
            "from_category": previous or "",
            "to_category": aqi_category(aqi),
            "us_aqi": r["us_aqi"],
            "pm2_5": r["pm2_5"],
            "pm10": r["pm10"],
            "fetched_at_utc": r["fetched_at_utc"],
        })
    return events, skipped


def summary(events: list[dict[str, str]]) -> str:
    """Commit message for the logged events (all share one time)."""
    when = events[0]["time_ist"].replace("T", " ")
    changes = ", ".join(
        f"{e['city']} → {e['to_category']}" if e["from_category"] else f"{e['city']} {e['to_category']}"
        for e in events
    )
    return f"data: AQI change {when} IST: {changes}"


def main(
    events_csv_path: Path = EVENTS_CSV_PATH,
    summary_path: Path | None = None,
    session: requests.Session | None = None,
    sleep=time.sleep,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    fetched_at = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        payload = fetch.fetch_payload(session=session, sleep=sleep, params=build_params())
        rows = fetch.parse_payload(payload, fetched_at)  # also checks count and order
        fetch.check_fresh(payload, now)
    except (requests.RequestException, fetch.FetchError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for row, loc in zip(rows, payload):
        row["time_ist"] = loc["current"]["time"]  # e.g. 2026-09-24T15:45, IST
    events, skipped = detect(rows, last_categories(read_rows(events_csv_path)))
    written = fetch.append_rows(events_csv_path, events, EVENT_COLUMNS, key=("time_ist", "city"))

    for r in rows:
        print(f"{r['time_ist']}  {r['city']:<10} AQI={r['us_aqi'] or 'MISSING'}")
    print(f"{written} category change(s) logged to {events_csv_path}")
    if skipped:
        # The daily job fails loudly on missing values; here a gap just means
        # no event can be detected for that city this time.
        print(f"WARNING: no us_aqi for {', '.join(skipped)}", file=sys.stderr)
    if written and summary_path is not None:
        summary_path.write_text(summary(events) + "\n", encoding="utf-8")
    return 0


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary-file", type=Path, default=None,
                        help="write a one-line commit message here if anything was logged")
    args = parser.parse_args(argv)
    return main(summary_path=args.summary_file)


if __name__ == "__main__":
    sys.exit(cli())
