"""Fetch current air quality for Indian cities (common.CITIES) into data/aqi.csv.

One request covers all cities (Open-Meteo accepts comma-separated coordinates
and returns a JSON array in the same order). Rows are keyed by (date, city);
re-running on the same IST day adds nothing.

The same request also returns yesterday's hourly series, from which we derive
full-day statistics (data/aqi_daily.csv). Unlike the single snapshot, these
don't depend on what time of day the job happened to run.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from common import (
    CITIES,
    COLUMNS,
    CSV_PATH,
    DAILY_COLUMNS,
    DAILY_CSV_PATH,
    GAS_COLUMNS,
    GASES_CSV_PATH,
    IST,
    read_rows,
)

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEZONE = "Asia/Kolkata"
CURRENT_VARS = ["us_aqi", "pm2_5", "pm10", "nitrogen_dioxide", "ozone"]
HOURLY_VARS = ["us_aqi", "pm2_5", "pm10", "nitrogen_dioxide", "ozone"]
O3_WINDOW_HOURS = 8
# Skip a city's daily stats (and fail) if fewer hours than this have data.
MIN_DAILY_HOURS = 20
# Open-Meteo serves at most this many past days; used for one-off backfills.
MAX_PAST_DAYS = 92
# API variable -> CSV column
FIELD_MAP = {
    "us_aqi": "us_aqi",
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "nitrogen_dioxide": "no2",
    "ozone": "o3",
}

MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2
TIMEOUT_SECONDS = 30
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Open-Meteo snaps coordinates to the CAMS grid (~0.4°); anything further
# off means the response isn't in the order we asked for.
COORD_TOLERANCE_DEG = 0.5
# "current" is normally <1h old; older means the model feed is stuck.
MAX_DATA_AGE = timedelta(hours=6)


class FetchError(RuntimeError):
    pass


def build_params(past_days: int = 1) -> dict[str, str]:
    return {
        "latitude": ",".join(f"{lat}" for _, lat, _ in CITIES),
        "longitude": ",".join(f"{lon}" for _, _, lon in CITIES),
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_VARS),
        # The previous `past_days` IST days + today, in local hours.
        "past_days": str(past_days),
        "forecast_days": "1",
        "timezone": TIMEZONE,
    }


def fetch_payload(
    session: requests.Session | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    sleep=time.sleep,
    past_days: int = 1,
) -> list[dict]:
    """GET the API with exponential backoff on network errors and 429/5xx."""
    session = session or requests.Session()
    params = build_params(past_days)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
            if resp.status_code in RETRYABLE_STATUS:
                raise FetchError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            if resp.status_code != 200:
                # Client errors won't fix themselves; fail fast.
                raise requests.HTTPError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}", response=resp
                )
            payload = resp.json()
            # A single location comes back as an object; normalise to a list.
            return payload if isinstance(payload, list) else [payload]
        except (requests.ConnectionError, requests.Timeout, FetchError) as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
            print(
                f"Attempt {attempt}/{max_attempts} failed ({exc}); retrying in {delay}s",
                file=sys.stderr,
            )
            sleep(delay)

    raise FetchError(f"Giving up after {max_attempts} attempts: {last_error}")


def _fmt(value) -> str:
    return "" if value is None else str(value)


def parse_payload(payload: list[dict], fetched_at_utc: str) -> list[dict[str, str]]:
    """Turn the API response into one CSV row per city."""
    if len(payload) != len(CITIES):
        raise FetchError(
            f"Expected {len(CITIES)} locations in response, got {len(payload)}"
        )

    rows = []
    for (city, lat, lon), loc in zip(CITIES, payload):
        got_lat, got_lon = loc.get("latitude"), loc.get("longitude")
        if (
            got_lat is None
            or got_lon is None
            or abs(got_lat - lat) > COORD_TOLERANCE_DEG
            or abs(got_lon - lon) > COORD_TOLERANCE_DEG
        ):
            raise FetchError(
                f"Location {city} came back as ({got_lat}, {got_lon}), "
                f"expected ~({lat}, {lon}); response order changed?"
            )
        current = loc.get("current")
        if not current or "time" not in current:
            raise FetchError(f"Missing 'current' block for {city}: {loc!r:.200}")
        # current.time is local (Asia/Kolkata), e.g. "2026-09-23T08:45".
        date = current["time"][:10]
        row = {"date": date, "city": city, "fetched_at_utc": fetched_at_utc}
        for api_key, column in FIELD_MAP.items():
            row[column] = _fmt(current.get(api_key))
        rows.append(row)
    return rows


def check_fresh(payload: list[dict], now: datetime) -> None:
    """Fail if any location's current.time (IST) is older than MAX_DATA_AGE.

    Without this, a stale response dated yesterday would be silently
    deduped away and the run would look green while recording nothing.
    """
    for (city, _, _), loc in zip(CITIES, payload):
        observed = datetime.fromisoformat(loc["current"]["time"]).replace(tzinfo=IST)
        if now - observed > MAX_DATA_AGE:
            raise FetchError(
                f"Stale data for {city}: current.time={loc['current']['time']} IST, "
                f"now={now.astimezone(IST):%Y-%m-%dT%H:%M} IST"
            )


def _mean(values: list[float]) -> str:
    return f"{sum(values) / len(values):.1f}"


def parse_daily(
    payload: list[dict], fetched_at_utc: str, days: int = 1
) -> tuple[list[dict[str, str]], list[str]]:
    """Full-day stats for each of the `days` IST days before current.time.

    Returns (rows, skipped), rows ordered by date then city. An entry in
    skipped ("City YYYY-MM-DD") means fewer than MIN_DAILY_HOURS of that
    day's 24 hours had a us_aqi value.
    """
    per_day: dict[str, list[dict[str, str]]] = {}
    skipped = []
    for (city, _, _), loc in zip(CITIES, payload):
        today = datetime.fromisoformat(loc["current"]["time"]).date()
        hourly = loc.get("hourly") or {}
        times = hourly.get("time") or []
        for back in range(days, 0, -1):
            day = (today - timedelta(days=back)).isoformat()
            row = _day_stats(hourly, times, day, city, fetched_at_utc)
            if row is None:
                skipped.append(f"{city} {day}")
            else:
                per_day.setdefault(day, []).append(row)
    rows = [r for day in sorted(per_day) for r in per_day[day]]
    return rows, skipped


def _day_stats(
    hourly: dict, times: list[str], day: str, city: str, fetched_at_utc: str
) -> dict[str, str] | None:
    idx = [i for i, t in enumerate(times) if t.startswith(day)]

    def series(key: str) -> list[float]:
        values = hourly.get(key) or []
        return [values[i] for i in idx if i < len(values) and values[i] is not None]

    aqi, pm25, pm10 = series("us_aqi"), series("pm2_5"), series("pm10")
    if len(aqi) < MIN_DAILY_HOURS:
        return None
    no2 = series("nitrogen_dioxide")
    ozone = hourly.get("ozone") or []
    ozone_by_hour = [ozone[i] if i < len(ozone) else None for i in idx]  # keeps gaps
    return {
        "date": day,
        "city": city,
        "hours": str(len(aqi)),
        "us_aqi_mean": _mean(aqi),
        "us_aqi_max": _fmt(max(aqi)),
        "pm2_5_mean": _mean(pm25) if pm25 else "",
        "pm10_mean": _mean(pm10) if pm10 else "",
        "no2_mean": _mean(no2) if len(no2) >= MIN_DAILY_HOURS else "",
        "o3_max8h": _max_window_mean(ozone_by_hour),
        "fetched_at_utc": fetched_at_utc,
    }


def _max_window_mean(values: list[float | None], window: int = O3_WINDOW_HOURS) -> str:
    """Highest mean over `window` consecutive hours within the day, ignoring
    any window with a missing hour; "" if there is no complete window."""
    means = [
        sum(chunk) / window
        for start in range(len(values) - window + 1)
        if None not in (chunk := values[start:start + window])
    ]
    return f"{max(means):.1f}" if means else ""


def append_rows(
    path: Path, rows: list[dict[str, str]], columns: list[str] = COLUMNS
) -> int:
    """Append rows whose (date, city) isn't already present. Returns count written."""
    existing = {(r["date"], r["city"]) for r in read_rows(path)}
    new_rows = [r for r in rows if (r["date"], r["city"]) not in existing]
    if not new_rows:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        # Rows may carry fields for another file (gas stats); keep only ours.
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def main(
    csv_path: Path = CSV_PATH,
    daily_csv_path: Path = DAILY_CSV_PATH,
    gases_csv_path: Path = GASES_CSV_PATH,
    session: requests.Session | None = None,
    sleep=time.sleep,
    now: datetime | None = None,
    past_days: int = 1,
) -> int:
    now = now or datetime.now(timezone.utc)
    try:
        payload = fetch_payload(session=session, sleep=sleep, past_days=past_days)
        fetched_at = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = parse_payload(payload, fetched_at)
        check_fresh(payload, now)
        daily_rows, daily_skipped = parse_daily(payload, fetched_at, past_days)
    except (requests.RequestException, FetchError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # A row without us_aqi is useless and, once written, would block a later
    # run from filling that (date, city) slot. Store the complete rows, skip
    # the rest and fail so the backup run retries them.
    complete = [r for r in rows if r["us_aqi"] != ""]
    missing = [r["city"] for r in rows if r["us_aqi"] == ""]

    written = append_rows(csv_path, complete)
    for r in rows:
        print(f"{r['date']}  {r['city']:<10} AQI={r['us_aqi'] or 'MISSING'}")
    print(f"Wrote {written} new row(s) to {csv_path}")

    daily_written = append_rows(daily_csv_path, daily_rows, DAILY_COLUMNS)
    for r in daily_rows[-len(CITIES):]:  # a backfill would print hundreds
        print(
            f"{r['date']}  {r['city']:<10} 24h mean AQI={r['us_aqi_mean']} "
            f"max={r['us_aqi_max']} ({r['hours']}h)"
        )
    print(f"Wrote {daily_written} new row(s) to {daily_csv_path}")
    gas_rows = [r for r in daily_rows if r["no2_mean"] or r["o3_max8h"]]
    gas_written = append_rows(gases_csv_path, gas_rows, GAS_COLUMNS)
    print(f"Wrote {gas_written} new row(s) to {gases_csv_path}")

    failed = False
    if missing:
        print(f"ERROR: no us_aqi for {', '.join(missing)}; not stored", file=sys.stderr)
        failed = True
    if daily_skipped:
        print(
            f"ERROR: fewer than {MIN_DAILY_HOURS} hourly values for "
            f"{len(daily_skipped)} city-day(s), not stored: {', '.join(daily_skipped[:20])}",
            file=sys.stderr,
        )
        failed = True
    return 1 if failed else 0


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--past-days",
        type=int,
        default=1,
        help=f"complete past IST days to compute daily stats for (1-{MAX_PAST_DAYS}); "
        "use a large value once to backfill history",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.past_days <= MAX_PAST_DAYS:
        parser.error(f"--past-days must be between 1 and {MAX_PAST_DAYS}")
    return main(past_days=args.past_days)


if __name__ == "__main__":
    sys.exit(cli())
