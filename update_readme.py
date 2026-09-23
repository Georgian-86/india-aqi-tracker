"""Rewrite the README section between the AQI markers with the latest snapshot."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from common import CITIES, CSV_PATH, IST, README_PATH, aqi_category, read_rows

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


def render_section(rows: list[dict[str, str]]) -> str:
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
        "| City | US AQI | Category | PM2.5 (µg/m³) | PM10 (µg/m³) | NO₂ (µg/m³) | O₃ (µg/m³) |",
        "|---|--:|---|--:|--:|--:|--:|",
    ]
    for city, _, _ in CITIES:
        r = today.get(city)
        if r is None:
            continue
        cat = aqi_category(r["us_aqi"])
        lines.append(
            f"| {city} | {_num(r['us_aqi'])} | {CATEGORY_ICON[cat]} {cat} | "
            f"{_num(r['pm2_5'])} | {_num(r['pm10'])} | {_num(r['no2'])} | {_num(r['o3'])} |"
        )
    lines += ["", f"![US AQI trend by city]({CHART_REL})"]
    return f"{START}\n" + "\n".join(lines) + f"\n{END}"


def update_readme(readme_text: str, rows: list[dict[str, str]]) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(readme_text):
        raise ValueError(f"README is missing the {START} ... {END} markers")
    section = render_section(rows)
    return pattern.sub(lambda _: section, readme_text, count=1)


def main(readme_path: Path = README_PATH, csv_path: Path = CSV_PATH) -> int:
    try:
        new_text = update_readme(readme_path.read_text(encoding="utf-8"), read_rows(csv_path))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    readme_path.write_text(new_text, encoding="utf-8")
    print(f"Updated {readme_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
