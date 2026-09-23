"""Fetch current air quality for five Indian cities and append it to data/aqi.csv.

One request covers all cities (Open-Meteo accepts comma-separated coordinates
and returns a JSON array in the same order). Rows are keyed by (date, city);
re-running on the same IST day adds nothing.
"""

from __future__ import annotations

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from common import CITIES, COLUMNS, CSV_PATH, read_rows

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
    for (city, _, _), loc in zip(CITIES, payload):
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(
    csv_path: Path = CSV_PATH,
    session: requests.Session | None = None,
    sleep=time.sleep,
) -> int:
    try:
        payload = fetch_payload(session=session, sleep=sleep)
        rows = parse_payload(payload, utc_now_iso())
    except (requests.RequestException, FetchError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    written = append_rows(csv_path, rows)
    for r in rows:
        print(f"{r['date']}  {r['city']:<10} AQI={r['us_aqi'] or 'n/a'}")
    print(f"Wrote {written} new row(s) to {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
