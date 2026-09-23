"""Shared constants and helpers for the AQI tracker scripts."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "aqi.csv"
CHART_PATH = ROOT / "charts" / "aqi_trend.png"
README_PATH = ROOT / "README.md"

# (name, latitude, longitude) — order matters: the API returns results in
# the same order as the coordinates we send.
CITIES: list[tuple[str, float, float]] = [
    ("Delhi", 28.6139, 77.2090),
    ("Mumbai", 19.0760, 72.8777),
    ("Bengaluru", 12.9716, 77.5946),
    ("Kolkata", 22.5726, 88.3639),
    ("Chennai", 13.0827, 80.2707),
]

COLUMNS = ["date", "city", "us_aqi", "pm2_5", "pm10", "no2", "o3", "fetched_at_utc"]

# US EPA AQI breakpoints: (upper bound inclusive, label).
AQI_CATEGORIES: list[tuple[int, str]] = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
]
HAZARDOUS = "Hazardous"


def aqi_category(aqi: float | int | str | None) -> str:
    """Map a US AQI value to its EPA category name ("N/A" if missing)."""
    if aqi is None or aqi == "":
        return "N/A"
    try:
        value = float(aqi)
    except (TypeError, ValueError):
        return "N/A"
    if value < 0:
        return "N/A"
    for upper, label in AQI_CATEGORIES:
        if value <= upper:
            return label
    return HAZARDOUS


def read_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    """Return all rows of the CSV as dicts, or [] if the file doesn't exist."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
