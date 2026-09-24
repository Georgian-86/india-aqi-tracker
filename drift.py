"""Flag likely CAMS model changes (step changes) in the stored history.

CAMS is upgraded from time to time, and the data then shifts in a way real
air doesn't. The 4-year backfill found two: NO₂ in every city halved at the
end of June 2023, and Delhi's pre-monsoon PM10 roughly quadrupled from 2025.
Both were found by hand; this makes the same check automatic.

For one month and pollutant it compares each city's monthly mean with the
same month a year earlier (same season, so the monsoon/winter cycle cancels):

- all-cities step: the median ratio across cities is beyond ALL_CITIES_RATIO
  (either direction). Real pollution doesn't move 40% in 8 cities at once.
- single-city step: one city's ratio is beyond CITY_RATIO (either direction).

Tuned on the real history (Aug 2022 - Sep 2026): it flags the NO₂ step in
every month whose year-earlier month predates it (Aug 2023 - May 2024), and
Delhi's PM10, with no flags at all for PM2.5 or US AQI in 25 comparable months.

It is a warning, not a correction: the data is stored as the API returned it.
Run `python drift.py` to scan the whole history.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from common import CITIES, DAILY_CSV_PATH, GASES_CSV_PATH, read_rows

POLLUTANTS = {  # column -> display name
    "pm2_5_mean": "PM2.5",
    "pm10_mean": "PM10",
    "no2_mean": "NO₂",
    "us_aqi_mean": "US AQI",
}
MIN_DAYS = 20  # days of data for a monthly mean to count
MIN_CITIES = 6  # cities needed for an all-cities verdict
ALL_CITIES_RATIO = 1 / 0.6  # median ratio beyond ×1.67 or ÷1.67
CITY_RATIO = 3.0  # one city beyond ×3 or ÷3

Means = dict[tuple[str, str, str], float]  # (column, city, 'YYYY-MM') -> mean


@dataclass(frozen=True)
class Finding:
    pollutant: str  # column name
    month: str
    kind: str  # "all-cities" or "city"
    median_ratio: float
    cities: dict[str, float]  # city -> ratio; for "city", only the outliers

    def describe(self) -> str:
        name = POLLUTANTS[self.pollutant]
        prev = previous_year(self.month)
        if self.kind == "all-cities":
            return (f"{name}: the median city is ×{self.median_ratio:.2f} vs {prev} "
                    f"across {len(self.cities)} cities, which suggests a model change "
                    "rather than a real change in air quality.")
        parts = ", ".join(f"{c} ×{r:.1f}" for c, r in self.cities.items())
        return f"{name}: {parts} vs {prev}, far outside the other cities (median ×{self.median_ratio:.2f})."


def previous_year(month: str) -> str:
    return f"{int(month[:4]) - 1}{month[4:]}"


def monthly_means(daily_rows: list[dict[str, str]], gas_rows: list[dict[str, str]]) -> Means:
    values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for rows in (daily_rows, gas_rows):
        for r in rows:
            for col in POLLUTANTS:
                if r.get(col):
                    values[(col, r["city"], r["date"][:7])].append(float(r[col]))
    return {k: sum(v) / len(v) for k, v in values.items() if len(v) >= MIN_DAYS}


def _beyond(ratio: float, limit: float) -> bool:
    return ratio > limit or ratio < 1 / limit


def check_month(means: Means, month: str) -> list[Finding]:
    """Findings for one month vs the same month a year earlier (may be empty)."""
    prev = previous_year(month)
    findings = []
    for col in POLLUTANTS:
        ratios = {
            city: means[(col, city, month)] / means[(col, city, prev)]
            for city, _, _ in CITIES
            if means.get((col, city, month)) and means.get((col, city, prev))
        }
        if len(ratios) < MIN_CITIES:
            continue
        med = median(ratios.values())
        if _beyond(med, ALL_CITIES_RATIO):
            findings.append(Finding(col, month, "all-cities", med, ratios))
            continue  # every city moved; single-city outliers would just repeat it
        outliers = {c: r for c, r in ratios.items() if _beyond(r, CITY_RATIO)}
        if outliers:
            findings.append(Finding(col, month, "city", med, outliers))
    return findings


def comparable(means: Means, month: str) -> bool:
    """Whether the year-earlier month has enough data to compare at all."""
    prev = previous_year(month)
    return any(k[2] == prev for k in means)


def main(daily_csv_path: Path = DAILY_CSV_PATH, gases_csv_path: Path = GASES_CSV_PATH) -> int:
    means = monthly_means(read_rows(daily_csv_path), read_rows(gases_csv_path))
    months = sorted({k[2] for k in means})
    checked = [m for m in months if comparable(means, m)]
    found = 0
    for month in checked:
        for f in check_month(means, month):
            print(f"{month}  {f.describe()}")
            found += 1
    print(f"Checked {len(checked)} month(s) against the year before; {found} finding(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
