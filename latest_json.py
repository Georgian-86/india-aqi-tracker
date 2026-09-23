"""Write data/latest.json: the latest snapshot and full day for every city.

For other programs (dashboards, bots, widgets) that want today's numbers without
parsing the CSVs. Unlike the CSVs it is rewritten on every run. The output is
deterministic (no generation timestamp), so it only changes when the data does
and doesn't add a commit on its own. Consumers should check `snapshot.date`
for staleness.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from common import (
    CITIES,
    CSV_PATH,
    DAILY_CSV_PATH,
    GASES_CSV_PATH,
    ROOT,
    aqi_category,
    read_rows,
)
from update_readme import india_result

JSON_PATH = ROOT / "data" / "latest.json"
SCHEMA_VERSION = 1
ATTRIBUTION = (
    "Air quality data from Open-Meteo (open-meteo.com), CC BY 4.0, generated using "
    "Copernicus Atmosphere Monitoring Service information. Model estimates, not "
    "ground measurements."
)


def _num(value: str | None) -> float | None:
    return float(value) if value else None


def _snapshot(rows: list[dict[str, str]]) -> dict | None:
    if not rows:
        return None
    day = max(r["date"] for r in rows)
    today = {r["city"]: r for r in rows if r["date"] == day}
    cities = []
    for city, lat, lon in CITIES:
        r = today.get(city)
        if r is None:
            continue
        cities.append({
            "city": city, "lat": lat, "lon": lon,
            "us_aqi": _num(r["us_aqi"]),
            "us_category": aqi_category(r["us_aqi"]),
            "pm2_5": _num(r["pm2_5"]), "pm10": _num(r["pm10"]),
            "no2": _num(r["no2"]), "o3": _num(r["o3"]),
            "fetched_at_utc": r["fetched_at_utc"],
        })
    return {"date": day, "cities": cities}


def _full_day(daily_rows: list[dict[str, str]], gas_rows: list[dict[str, str]]) -> dict | None:
    if not daily_rows:
        return None
    day = max(r["date"] for r in daily_rows)
    latest = {r["city"]: r for r in daily_rows if r["date"] == day}
    gases = {r["city"]: r for r in gas_rows if r["date"] == day}
    cities = []
    for city, _, _ in CITIES:
        r = latest.get(city)
        if r is None:
            continue
        gas = gases.get(city, {})
        india = india_result(r, gas)
        cities.append({
            "city": city,
            "hours": int(r["hours"]),
            "us_aqi_mean": _num(r["us_aqi_mean"]),
            "us_aqi_max": _num(r["us_aqi_max"]),
            "us_category": aqi_category(r["us_aqi_mean"]),
            "pm2_5_mean": _num(r["pm2_5_mean"]),
            "pm10_mean": _num(r["pm10_mean"]),
            "no2_mean": _num(gas.get("no2_mean")),
            "india_aqi": None if india.category == "N/A" else {
                # index is null for Severe: CPCB's scale has no number above 500.
                "index": None if india.index is None else round(india.index),
                "category": india.category,
                "prominent": india.prominent,
                "pollutants": india.pollutants,
            },
        })
    return {"date": day, "cities": cities}


def build(
    rows: list[dict[str, str]],
    daily_rows: list[dict[str, str]],
    gas_rows: list[dict[str, str]],
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot": _snapshot(rows),
        "full_day": _full_day(daily_rows, gas_rows),
        "units": {"concentrations": "µg/m³"},
        "notes": {
            "india_aqi": "CPCB National AQI from full-day mean PM2.5, PM10 and NO₂. "
                         "O₃ is excluded (CAMS surface ozone is biased high over India).",
        },
        "attribution": ATTRIBUTION,
    }


def main(
    json_path: Path = JSON_PATH,
    csv_path: Path = CSV_PATH,
    daily_csv_path: Path = DAILY_CSV_PATH,
    gases_csv_path: Path = GASES_CSV_PATH,
) -> int:
    try:
        data = build(read_rows(csv_path), read_rows(daily_csv_path), read_rows(gases_csv_path))
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
