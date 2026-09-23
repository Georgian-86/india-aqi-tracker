"""Fetch current air quality for five Indian cities and append it to data/aqi.csv.

One request covers all cities (Open-Meteo accepts comma-separated coordinates
and returns a JSON array in the same order). Rows are keyed by (date, city);
re-running on the same IST day adds nothing.
"""

from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from common import CITIES, COLUMNS, CSV_PATH, IST, read_rows

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEZONE = "Asia/Kolkata"
CURRENT_VARS = ["us_aqi", "pm2_5", "pm10", "nitrogen_dioxide", "ozone"]
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


def build_params() -> dict[str, str]:
    return {
        "latitude": ",".join(f"{lat}" for _, lat, _ in CITIES),
        "longitude": ",".join(f"{lon}" for _, _, lon in CITIES),
        "current": ",".join(CURRENT_VARS),
        "timezone": TIMEZONE,
    }


def fetch_payload(
    session: requests.Session | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    sleep=time.sleep,
) -> list[dict]:
    """GET the API with exponential backoff on network errors and 429/5xx."""
    session = session or requests.Session()
    params = build_params()
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


def append_rows(path: Path, rows: list[dict[str, str]]) -> int:
    """Append rows whose (date, city) isn't already present. Returns count written."""
    existing = {(r["date"], r["city"]) for r in read_rows(path)}
    new_rows = [r for r in rows if (r["date"], r["city"]) not in existing]
    if not new_rows:
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def main(
    csv_path: Path = CSV_PATH,
    session: requests.Session | None = None,
    sleep=time.sleep,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    try:
        payload = fetch_payload(session=session, sleep=sleep)
        fetched_at = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = parse_payload(payload, fetched_at)
        check_fresh(payload, now)
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
    if missing:
        print(f"ERROR: no us_aqi for {', '.join(missing)}; not stored", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
