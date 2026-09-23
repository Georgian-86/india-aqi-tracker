"""Backfill full-day statistics further back than fetch.py's 92-day limit.

Walks backwards from the day before the oldest stored day (or --until) to
--since, one CHUNK_DAYS request at a time, using Open-Meteo's start_date /
end_date. How far back the CAMS global archive goes isn't documented
clearly, so the script discovers it: it stops cleanly when the API rejects
a range (HTTP 400) or a whole chunk comes back with no data for any city,
and reports the earliest day it stored.

Rows go through the same dedupe as the daily job, so re-running is harmless.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import fetch
from common import (
    CITIES,
    DAILY_COLUMNS,
    DAILY_CSV_PATH,
    GAS_COLUMNS,
    GASES_CSV_PATH,
    IST,
    read_rows,
)

CHUNK_DAYS = 60  # 8 cities x 60 days x 24 h x 5 variables per request
# Older archive data can be much slower to serve. The first real backfill got
# 4 read timeouts in a row on a 60-day range, so a range that keeps timing out
# is split in half (down to MIN_CHUNK_DAYS) rather than failing the run.
MIN_CHUNK_DAYS = 7
BACKFILL_TIMEOUT_SECONDS = 60
BACKFILL_ATTEMPTS = 2  # per range; splitting is the main recovery


def chunks(since: date, until: date, size: int = CHUNK_DAYS) -> list[tuple[date, date]]:
    """(start, end) ranges covering since..until, newest first."""
    ranges = []
    end = until
    while end >= since:
        start = max(since, end - timedelta(days=size - 1))
        ranges.append((start, end))
        end = start - timedelta(days=1)
    return ranges


def chunk_params(start: date, end: date) -> dict[str, str]:
    return {
        "latitude": ",".join(str(lat) for _, lat, _ in CITIES),
        "longitude": ",".join(str(lon) for _, _, lon in CITIES),
        "hourly": ",".join(fetch.HOURLY_VARS),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": fetch.TIMEZONE,
    }


def parse_chunk(
    payload: list[dict], start: date, end: date, fetched_at_utc: str
) -> tuple[list[dict[str, str]], int]:
    """Daily rows for every city-day in the range, and how many were missing."""
    fetch.check_locations(payload)
    rows, missing = [], 0
    day = start
    while day <= end:
        for (city, _, _), loc in zip(CITIES, payload):
            hourly = loc.get("hourly") or {}
            row = fetch.day_stats(hourly, hourly.get("time") or [], day.isoformat(), city,
                                  fetched_at_utc)
            if row is None:
                missing += 1
            else:
                rows.append(row)
        day += timedelta(days=1)
    return rows, missing


def default_until(daily_csv_path: Path, now: datetime) -> date:
    """The day before the oldest stored day, or yesterday (IST) if none."""
    days = [r["date"] for r in read_rows(daily_csv_path)]
    if days:
        return date.fromisoformat(min(days)) - timedelta(days=1)
    return now.astimezone(IST).date() - timedelta(days=1)


def main(
    since: date,
    until: date | None = None,
    daily_csv_path: Path = DAILY_CSV_PATH,
    gases_csv_path: Path = GASES_CSV_PATH,
    session: requests.Session | None = None,
    sleep=time.sleep,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    until = until or default_until(daily_csv_path, now)
    if until < since:
        print(f"Nothing to do: history already reaches {until + timedelta(days=1)}.")
        return 0
    fetched_at = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    earliest = None
    total_daily = total_gas = 0

    pending = chunks(since, until)  # newest first
    while pending:
        start, end = pending.pop(0)
        try:
            payload = fetch.fetch_payload(
                session=session, sleep=sleep, params=chunk_params(start, end),
                timeout=BACKFILL_TIMEOUT_SECONDS, max_attempts=BACKFILL_ATTEMPTS,
            )
            rows, missing = parse_chunk(payload, start, end, fetched_at)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 400:  # range outside the archive: we've found the limit
                print(f"{start}..{end}: rejected by the API (HTTP 400); stopping here.")
                break
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except fetch.FetchError as exc:
            days = (end - start).days + 1
            if "timed out" in str(exc) and days > MIN_CHUNK_DAYS:
                middle = start + timedelta(days=days // 2)
                print(f"{start}..{end}: timed out; retrying as two smaller ranges.")
                pending[:0] = [(middle, end), (start, middle - timedelta(days=1))]
                continue
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except (requests.RequestException, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        if not rows:
            print(f"{start}..{end}: no data for any city; the archive ends here.")
            break
        total_daily += fetch.append_rows(daily_csv_path, rows, DAILY_COLUMNS)
        gas_rows = [r for r in rows if r["no2_mean"] or r["o3_max8h"]]
        total_gas += fetch.append_rows(gases_csv_path, gas_rows, GAS_COLUMNS)
        earliest = min(r["date"] for r in rows)
        print(f"{start}..{end}: {len(rows)} city-days"
              + (f", {missing} missing" if missing else ""))

    print(f"Backfill wrote {total_daily} daily and {total_gas} gas row(s)"
          + (f"; history now starts {earliest}." if earliest else "."))
    return 0


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=date.fromisoformat, required=True,
                        help="earliest day to backfill (YYYY-MM-DD)")
    parser.add_argument("--until", type=date.fromisoformat, default=None,
                        help="latest day (default: the day before the oldest stored day)")
    args = parser.parse_args(argv)
    return main(args.since, args.until)


if __name__ == "__main__":
    sys.exit(cli())
