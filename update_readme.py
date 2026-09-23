"""Rewrite the README section between the AQI markers with the latest snapshot."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from common import (
    CITIES,
    CSV_PATH,
    DAILY_CSV_PATH,
    IST,
    README_PATH,
    aqi_category,
    read_rows,
)

START = "<!-- AQI:START -->"
END = "<!-- AQI:END -->"
CHART_REL = "charts/aqi_trend.png"

CATEGORY_ICON = {
    "Good": "🟢",
    "Moderate": "🟡",
    "Unhealthy for Sensitive Groups": "🟠",
    "Unhealthy": "🔴",
    "Very Unhealthy": "🟣",
    "Hazardous": "🟤",
    "N/A": "⚪",
}


def _num(value: str) -> str:
    if not value:
        return "–"
    f = float(value)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def _fetched_ist(rows: list[dict[str, str]]) -> str | None:
    """Latest fetched_at_utc among rows, as 'HH:MM IST' (None if unparseable)."""
    stamps = []
    for r in rows:
        try:
            stamps.append(datetime.fromisoformat(r["fetched_at_utc"].replace("Z", "+00:00")))
        except (KeyError, ValueError):
            continue
    if not stamps:
        return None
    return f"{max(stamps).astimezone(IST):%H:%M} IST"


# Readings further apart than this in time of day aren't compared: AQI has a
# strong daily cycle, so 08:47 vs 22:00 would mostly measure the cycle.
MAX_TIME_OF_DAY_GAP_MIN = 180


def _minute_of_day_ist(fetched_at_utc: str) -> int | None:
    try:
        t = datetime.fromisoformat(fetched_at_utc.replace("Z", "+00:00")).astimezone(IST)
    except ValueError:
        return None
    return t.hour * 60 + t.minute


def _change(current: dict[str, str], previous: dict[str, str] | None) -> str:
    """Signed AQI change vs the previous reading, e.g. '▲ 12'; '–' if not comparable."""
    if previous is None or not current["us_aqi"] or not previous["us_aqi"]:
        return "–"
    a = _minute_of_day_ist(current["fetched_at_utc"])
    b = _minute_of_day_ist(previous["fetched_at_utc"])
    if a is None or b is None:
        return "–"
    gap = abs(a - b)
    if min(gap, 24 * 60 - gap) > MAX_TIME_OF_DAY_GAP_MIN:
        return "–"
    delta = round(float(current["us_aqi"]) - float(previous["us_aqi"]))
    if delta == 0:
        return "="
    return f"{'▲' if delta > 0 else '▼'} {abs(delta)}"


def _previous_reading(
    rows: list[dict[str, str]], city: str, before: str
) -> dict[str, str] | None:
    earlier = [r for r in rows if r["city"] == city and r["date"] < before]
    return max(earlier, key=lambda r: r["date"]) if earlier else None


def render_daily(daily_rows: list[dict[str, str]]) -> list[str]:
    """Table of the latest completed day's full-day stats, plus a 7-day mean."""
    if not daily_rows:
        return []
    day = max(r["date"] for r in daily_rows)
    week_start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
    latest = {r["city"]: r for r in daily_rows if r["date"] == day}

    lines = [
        "",
        f"**Full day {day}** (mean of 24 hourly values — comparable across days, "
        "unlike the single snapshot above)",
        "",
        "| City | Mean AQI | Category | Peak AQI | 7-day mean | Mean PM2.5 (µg/m³) |",
        "|---|--:|---|--:|--:|--:|",
    ]
    for city, _, _ in CITIES:
        r = latest.get(city)
        if r is None:
            continue
        week = [
            float(w["us_aqi_mean"]) for w in daily_rows
            if w["city"] == city and week_start <= w["date"] <= day
        ]
        week_mean = f"{sum(week) / len(week):.0f}"
        if len(week) < 7:
            week_mean += f" ({len(week)}d)"
        cat = aqi_category(r["us_aqi_mean"])
        lines.append(
            f"| {city} | {float(r['us_aqi_mean']):.0f} | {CATEGORY_ICON[cat]} {cat} | "
            f"{_num(r['us_aqi_max'])} | {week_mean} | {_num(r['pm2_5_mean'])} |"
        )
    return lines


def render_section(
    rows: list[dict[str, str]], daily_rows: list[dict[str, str]] | None = None
) -> str:
    if not rows:
        body = "_No data collected yet — the first snapshot arrives with the next scheduled run._"
        return f"{START}\n{body}\n{END}"

    latest = max(r["date"] for r in rows)
    today = {r["city"]: r for r in rows if r["date"] == latest}
    days = len({r["date"] for r in rows})
    fetched = _fetched_ist(list(today.values()))
    details = [f"fetched {fetched}"] if fetched else []
    details.append(f"{days} day{'s' if days != 1 else ''} collected")

    lines = [
        f"**Latest snapshot: {latest}** ({' · '.join(details)})",
        "",
        "| City | US AQI | Category | vs prev. | PM2.5 (µg/m³) | PM10 (µg/m³) | NO₂ (µg/m³) | O₃ (µg/m³) |",
        "|---|--:|---|:-:|--:|--:|--:|--:|",
    ]
    for city, _, _ in CITIES:
        r = today.get(city)
        if r is None:
            continue
        cat = aqi_category(r["us_aqi"])
        change = _change(r, _previous_reading(rows, city, latest))
        lines.append(
            f"| {city} | {_num(r['us_aqi'])} | {CATEGORY_ICON[cat]} {cat} | {change} | "
            f"{_num(r['pm2_5'])} | {_num(r['pm10'])} | {_num(r['no2'])} | {_num(r['o3'])} |"
        )
    lines += [
        "",
        "<sub>vs prev.: change since the previous snapshot; “–” when there is none or the "
        "two were taken more than 3 h apart in time of day (AQI has a daily cycle).</sub>",
    ]
    lines += render_daily(daily_rows or [])
    lines += ["", f"![US AQI trend by city]({CHART_REL})"]
    return f"{START}\n" + "\n".join(lines) + f"\n{END}"


def update_readme(
    readme_text: str,
    rows: list[dict[str, str]],
    daily_rows: list[dict[str, str]] | None = None,
) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(readme_text):
        raise ValueError(f"README is missing the {START} ... {END} markers")
    section = render_section(rows, daily_rows)
    return pattern.sub(lambda _: section, readme_text, count=1)


def main(
    readme_path: Path = README_PATH,
    csv_path: Path = CSV_PATH,
    daily_csv_path: Path = DAILY_CSV_PATH,
) -> int:
    try:
        new_text = update_readme(
            readme_path.read_text(encoding="utf-8"),
            read_rows(csv_path),
            read_rows(daily_csv_path),
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    readme_path.write_text(new_text, encoding="utf-8")
    print(f"Updated {readme_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
