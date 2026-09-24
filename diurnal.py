"""When in the day each city's air is usually cleanest and worst.

From data/aqi_hourly.csv, averages hourly PM2.5 for each IST hour over the
last WINDOW_DAYS days, then finds the WINDOW_HOURS-long stretch with the
lowest and the highest mean (wrapping past midnight). It's a model profile:
CAMS captures the daily cycle driven by the boundary layer and traffic, but
not local sources at street level.

Why PM2.5 and not the hourly US AQI: Open-Meteo computes the hourly US AQI
from 24-hour rolling PM means and 8-hour O₃ means, as the EPA defines it, so
it hardly moves within a day and peaks with afternoon ozone. On the first 30
days of real data it put Delhi's worst hours at 17:00-20:00 with a spread of
26 AQI points; hourly PM2.5 shows the actual cycle (worst around midnight,
cleanest mid-afternoon, ~1.5x apart).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from common import CITIES

WINDOW_DAYS = 30
WINDOW_HOURS = 3
MIN_DAYS = 14  # each hour needs this many days of data for a city to be shown
COLUMN = "pm2_5"


@dataclass(frozen=True)
class Profile:
    city: str
    days: int
    best_start: int  # IST hour the cleanest stretch starts
    best_mean: float
    worst_start: int
    worst_mean: float

    @staticmethod
    def span(start: int) -> str:
        return f"{start:02d}:00–{(start + WINDOW_HOURS) % 24:02d}:00"


def hourly_means(
    hourly_rows: list[dict[str, str]], days: int = WINDOW_DAYS
) -> tuple[str, str, dict[str, list[tuple[float, int] | None]]] | None:
    """(start, end, city -> 24 × (mean, days) or None) over the last `days` days."""
    dates = sorted({r["date"] for r in hourly_rows if r[COLUMN]})
    if not dates:
        return None
    end = dates[-1]
    start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    values: dict[tuple[str, int], list[float]] = defaultdict(list)
    for r in hourly_rows:
        if r[COLUMN] and start <= r["date"] <= end:
            values[(r["city"], int(r["hour"]))].append(float(r[COLUMN]))
    means = {
        city: [
            (sum(v) / len(v), len(v)) if (v := values.get((city, h))) else None
            for h in range(24)
        ]
        for city, _, _ in CITIES
    }
    return start, end, means


def profiles(
    hourly_rows: list[dict[str, str]], days: int = WINDOW_DAYS
) -> tuple[str, str, list[Profile]] | None:
    """Cleanest and worst WINDOW_HOURS stretch per city with enough data."""
    result = hourly_means(hourly_rows, days)
    if result is None:
        return None
    start, end, means = result
    out = []
    for city, _, _ in CITIES:
        hours = means[city]
        if any(h is None or h[1] < MIN_DAYS for h in hours):
            continue
        windows = [
            (sum(hours[(s + k) % 24][0] for k in range(WINDOW_HOURS)) / WINDOW_HOURS, s)
            for s in range(24)
        ]
        best, worst = min(windows), max(windows)
        out.append(Profile(city, min(h[1] for h in hours), best[1], best[0], worst[1], worst[0]))
    return (start, end, out) if out else None
