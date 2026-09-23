"""Shared constants and helpers for the AQI tracker scripts."""

from __future__ import annotations

import csv
from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "aqi.csv"
DAILY_CSV_PATH = ROOT / "data" / "aqi_daily.csv"
CHART_PATH = ROOT / "charts" / "aqi_trend.png"
README_PATH = ROOT / "README.md"

IST = timezone(timedelta(hours=5, minutes=30), "IST")

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
# Full-day statistics for a completed IST day, computed from hourly data.
DAILY_COLUMNS = [
    "date", "city", "hours", "us_aqi_mean", "us_aqi_max", "pm2_5_mean", "pm10_mean",
    "fetched_at_utc",
]

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


# India's National AQI (CPCB, 2014). Bands per pollutant, 24-hour average
# concentration in µg/m³: (conc_low, conc_high, index_low, index_high).
# Interpolation is continuous across band edges. Above the last band is
# "Severe" (401+); CPCB gives no upper concentration, so no number is invented.
NAQI_BANDS: dict[str, list[tuple[float, float, int, int]]] = {
    "pm2_5": [(0, 30, 0, 50), (30, 60, 50, 100), (60, 90, 100, 200),
              (90, 120, 200, 300), (120, 250, 300, 400)],
    "pm10": [(0, 50, 0, 50), (50, 100, 50, 100), (100, 250, 100, 200),
             (250, 350, 200, 300), (350, 430, 300, 400)],
}
NAQI_CATEGORIES: list[tuple[int, str]] = [
    (50, "Good"),
    (100, "Satisfactory"),
    (200, "Moderate"),
    (300, "Poor"),
    (400, "Very Poor"),
]
NAQI_SEVERE = "Severe"


def naqi_subindex(pollutant: str, conc: float) -> float | None:
    """CPCB sub-index for a 24 h mean concentration; None means Severe (>400)."""
    if conc < 0:
        raise ValueError(f"negative concentration {conc}")
    for c_lo, c_hi, i_lo, i_hi in NAQI_BANDS[pollutant]:
        if conc <= c_hi:
            return i_lo + (conc - c_lo) * (i_hi - i_lo) / (c_hi - c_lo)
    return None


def naqi(pm2_5: str | float | None, pm10: str | float | None) -> tuple[float | None, str]:
    """PM-based India AQI: the worse of the PM2.5 and PM10 sub-indices.

    Returns (index, category); index is None for Severe, and category is
    "N/A" when neither concentration is available. Official NAQI needs at
    least three pollutants, so this is an approximation driven by PM, which
    dominates in Indian cities.
    """
    subs = []
    for pollutant, value in (("pm2_5", pm2_5), ("pm10", pm10)):
        if value in (None, ""):
            continue
        sub = naqi_subindex(pollutant, float(value))
        if sub is None:
            return None, NAQI_SEVERE
        subs.append(sub)
    if not subs:
        return None, "N/A"
    index = max(subs)
    for upper, label in NAQI_CATEGORIES:
        if index <= upper:
            return index, label
    return index, NAQI_SEVERE


def read_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    """Return all rows of the CSV as dicts, or [] if the file doesn't exist."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
