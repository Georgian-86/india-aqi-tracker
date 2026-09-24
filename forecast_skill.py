"""How far CAMS's day-ahead forecast lands from the day's full-day mean.

Pairs each row of data/aqi_forecast.csv (issued the day before) with the
matching row of data/aqi_daily.csv once that day has passed, and summarises
the last WINDOW_DAYS per city: mean absolute error and bias of the full-day
mean US AQI, and how often the forecast got the US category right.

Both sides come from CAMS: the "actual" is the model's hourly values for the
day, fetched after it ended. So this measures how much the forecast moved by
the time the day happened, not accuracy against ground monitoring stations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from common import CITIES, aqi_category

WINDOW_DAYS = 30
MIN_PAIRS = 7  # a city needs at least this many forecast/actual pairs to be shown


@dataclass(frozen=True)
class Skill:
    city: str
    pairs: int
    mae: float  # mean |forecast - actual|, US AQI points
    bias: float  # mean (forecast - actual); > 0 means the forecast ran high
    category_hits: int  # pairs where the forecast's US category matched

    @property
    def hit_rate(self) -> float:
        return self.category_hits / self.pairs


def pairs(
    forecast_rows: list[dict[str, str]], daily_rows: list[dict[str, str]]
) -> list[tuple[str, str, float, float]]:
    """(date, city, forecast mean, actual mean) for every day that has both."""
    actual = {(r["date"], r["city"]): r["us_aqi_mean"] for r in daily_rows if r["us_aqi_mean"]}
    out = []
    for f in forecast_rows:
        a = actual.get((f["date"], f["city"]))
        if a and f["us_aqi_mean"]:
            out.append((f["date"], f["city"], float(f["us_aqi_mean"]), float(a)))
    return out


def skill(
    forecast_rows: list[dict[str, str]],
    daily_rows: list[dict[str, str]],
    days: int = WINDOW_DAYS,
) -> tuple[str, str, list[Skill]] | None:
    """(start, end, per-city Skill) over the last `days` days that have pairs.

    Cities with fewer than MIN_PAIRS pairs are left out; None if none qualify.
    """
    matched = pairs(forecast_rows, daily_rows)
    if not matched:
        return None
    end = max(d for d, *_ in matched)
    start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    result = []
    for city, _, _ in CITIES:
        mine = [(fc, ac) for d, c, fc, ac in matched if c == city and start <= d <= end]
        if len(mine) < MIN_PAIRS:
            continue
        errors = [fc - ac for fc, ac in mine]
        result.append(Skill(
            city=city,
            pairs=len(mine),
            mae=sum(abs(e) for e in errors) / len(errors),
            bias=sum(errors) / len(errors),
            category_hits=sum(aqi_category(fc) == aqi_category(ac) for fc, ac in mine),
        ))
    return (start, end, result) if result else None
