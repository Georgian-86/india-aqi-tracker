"""Rewrite the README section between the AQI markers with the latest snapshot."""

from __future__ import annotations

import calendar
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from common import (
    AQI_CATEGORIES,
    CITIES,
    HAZARDOUS,
    CSV_PATH,
    DAILY_CSV_PATH,
    GASES_CSV_PATH,
    IST,
    README_PATH,
    ROOT,
    aqi_category,
    NAQI_CATEGORIES,
    NAQI_HEALTH,
    NAQI_SEVERE,
    Naqi,
    naqi,
    read_rows,
)

START = "<!-- AQI:START -->"
END = "<!-- AQI:END -->"
# The chart lives on its own single-commit `charts` branch (force-pushed by the
# workflow) so a new image every day doesn't pile up in main's history.
CHART_URL = (
    "https://raw.githubusercontent.com/Georgian-86/india-aqi-tracker/charts/aqi_trend.png"
)

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


def render_daily(
    daily_rows: list[dict[str, str]], gas_rows: list[dict[str, str]] | None = None
) -> list[str]:
    """Table of the latest completed day's full-day stats, plus a 7-day mean."""
    if not daily_rows:
        return []
    day = max(r["date"] for r in daily_rows)
    week_start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
    latest = {r["city"]: r for r in daily_rows if r["date"] == day}
    gases = {r["city"]: r for r in (gas_rows or []) if r["date"] == day}

    lines = [
        "",
        f"**Full day {day}** (mean of 24 hourly values — comparable across days, "
        "unlike the single snapshot above)",
        "",
        "| City | Mean AQI | Category | Peak AQI | 7-day mean | Mean PM2.5 (µg/m³) "
        "| India AQI¹ |",
        "|---|--:|---|--:|--:|--:|---|",
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
            f"{_num(r['us_aqi_max'])} | {week_mean} | {_num(r['pm2_5_mean'])} | "
            f"{_india_aqi(r, gases.get(city, {}))} |"
        )
    lines += [
        "",
        "<sub>¹ India's National AQI (CPCB) scale: Good ≤ 50 · Satisfactory ≤ 100 · "
        "Moderate ≤ 200 · Poor ≤ 300 · Very Poor ≤ 400 · Severe. Computed from the day's "
        "mean PM2.5, PM10 and NO₂ (3 of CPCB's 8 pollutants, its minimum), labelled with "
        "the pollutant that sets it. ² marks a day with fewer than 3. Ozone is left out: "
        "the CAMS model's surface ozone runs far above ground measurements over India, "
        "and would make O₃ the main pollutant almost every day. The India figure often "
        "reads better than the US one because US breakpoints are stricter (PM2.5 is "
        "\"Good\" only up to 9 µg/m³ in the US, vs 30 in India).</sub>",
    ]
    lines += _health_advice({
        city: india_result(r, gases.get(city, {})).category for city, r in latest.items()
    })
    return lines


def _health_advice(categories: dict[str, str]) -> list[str]:
    """CPCB health statements for cities at Moderate or worse on India's scale."""
    order = [label for _, label in NAQI_CATEGORIES] + [NAQI_SEVERE]
    worrying = order[order.index("Moderate"):]
    by_category: dict[str, list[str]] = {}
    for city, _, _ in CITIES:
        if categories.get(city) in worrying:
            by_category.setdefault(categories[city], []).append(city)
    if not categories or all(c == "N/A" for c in categories.values()):
        return []
    if not by_category:
        return ["", "**Health (CPCB):** every city was Good or Satisfactory on India's scale. "
                    "Minimal impact, with at most minor discomfort for sensitive people."]
    lines = ["", "**Health (CPCB):**"]
    for category in reversed(worrying):  # worst first
        if category in by_category:
            lines.append(
                f"- **{', '.join(by_category[category])}**, {category}: {NAQI_HEALTH[category]}"
            )
    return lines


def india_result(row: dict[str, str], gas: dict[str, str]) -> Naqi:
    """India AQI for one city-day, deliberately without O₃ (see README caveats:
    CAMS surface ozone is strongly biased high over India)."""
    return naqi(row.get("pm2_5_mean"), row.get("pm10_mean"), gas.get("no2_mean"))


def _india_aqi(row: dict[str, str], gas: dict[str, str]) -> str:
    result = india_result(row, gas)
    if result.category == "N/A":
        return "–"
    value = "Severe (401+)" if result.index is None else f"{result.index:.0f} {result.category}"
    return f"{value} · {result.prominent}{'' if result.complete else '²'}"


SUMMARY_DAYS = 30
CATEGORY_SHORT = {
    "Good": "Good",
    "Moderate": "Moderate",
    "Unhealthy for Sensitive Groups": "USG",
    "Unhealthy": "Unhealthy",
    "Very Unhealthy": "V. Unhealthy",
    "Hazardous": "Hazardous",
}


def _summary_window(daily_rows: list[dict[str, str]]) -> tuple[str, str] | None:
    """(start, end) of the last SUMMARY_DAYS days, or None with under 2 days of
    data (a summary would only repeat the single-day table)."""
    days_present = sorted({r["date"] for r in daily_rows})
    if len(days_present) < 2:
        return None
    end = days_present[-1]
    return (date.fromisoformat(end) - timedelta(days=SUMMARY_DAYS - 1)).isoformat(), end


def render_summary(daily_rows: list[dict[str, str]]) -> list[str]:
    """Days per EPA category, mean and worst day per city over the last 30 days."""
    if (window := _summary_window(daily_rows)) is None:
        return []
    start, end = window
    window = [r for r in daily_rows if start <= r["date"] <= end]
    n_days = len({r["date"] for r in window})
    categories = [label for _, label in AQI_CATEGORIES] + [HAZARDOUS]

    header = " | ".join(f"{CATEGORY_ICON[c]} {CATEGORY_SHORT[c]}" for c in categories)
    lines = [
        "",
        f"**Last {SUMMARY_DAYS} days** ({start} to {end}, full-day means · "
        f"{n_days} day{'s' if n_days != 1 else ''} of data): days in each category",
        "",
        f"| City | {header} | Mean | Worst day |",
        "|---|" + "--:|" * len(categories) + "--:|---|",
    ]
    for city, _, _ in CITIES:
        rows = [r for r in window if r["city"] == city]
        if not rows:
            continue
        counts = {c: 0 for c in categories}
        for r in rows:
            counts[aqi_category(r["us_aqi_mean"])] += 1
        cells = " | ".join(str(counts[c]) if counts[c] else "·" for c in categories)
        mean = sum(float(r["us_aqi_mean"]) for r in rows) / len(rows)
        worst = max(rows, key=lambda r: (float(r["us_aqi_mean"]), r["date"]))
        lines.append(
            f"| {city} | {cells} | {mean:.0f} | "
            f"{float(worst['us_aqi_mean']):.0f} on {worst['date']} |"
        )
    return lines


def render_india_summary(
    daily_rows: list[dict[str, str]], gas_rows: list[dict[str, str]]
) -> list[str]:
    """Days per CPCB category and the main pollutants per city, last 30 days."""
    if (window := _summary_window(daily_rows)) is None:
        return []
    start, end = window
    gases = {(g["date"], g["city"]): g for g in gas_rows}
    categories = [label for _, label in NAQI_CATEGORIES] + [NAQI_SEVERE]

    lines = [
        "",
        f"**Last {SUMMARY_DAYS} days on India's scale** ({start} to {end}, CPCB categories "
        "from PM2.5, PM10 and NO₂): days in each category, and which pollutant set the "
        "index how often",
        "",
        f"| City | {' | '.join(categories)} | Main pollutants |",
        "|---|" + "--:|" * len(categories) + "---|",
    ]
    for city, _, _ in CITIES:
        results = [
            india_result(r, gases.get((r["date"], city), {}))
            for r in daily_rows
            if r["city"] == city and start <= r["date"] <= end
        ]
        results = [res for res in results if res.category != "N/A"]
        if not results:
            continue
        counts = {c: sum(res.category == c for res in results) for c in categories}
        cells = " | ".join(str(counts[c]) if counts[c] else "·" for c in categories)
        prominent: dict[str, int] = {}
        for res in results:
            prominent[res.prominent] = prominent.get(res.prominent, 0) + 1
        main = " · ".join(
            f"{name} {n}" for name, n in sorted(prominent.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        lines.append(f"| {city} | {cells} | {main} |")
    return lines


def _staleness_warning(latest: str, as_of: date | None) -> list[str]:
    """A visible warning when today's (IST) snapshot is missing. The README step
    runs even when fetch.py fails, so readers see a problem, not stale numbers."""
    if as_of is None:
        return []
    age = (as_of - date.fromisoformat(latest)).days
    if age < 1:
        return []
    return [
        f"> ⚠️ **Data may be out of date:** the latest snapshot is from {latest}, "
        f"{age} day{'s' if age != 1 else ''} ago. The daily job may be failing; see "
        "[Actions](../../actions/workflows/daily.yml).",
        "",
    ]


def render_section(
    rows: list[dict[str, str]],
    daily_rows: list[dict[str, str]] | None = None,
    gas_rows: list[dict[str, str]] | None = None,
    as_of: date | None = None,
    report_months: list[str] | None = None,
) -> str:
    """as_of: today's IST date, to flag stale data (None skips the check).
    report_months: 'YYYY-MM' of existing reports/ files, linked at the end."""
    if not rows:
        body = "_No data collected yet — the first snapshot arrives with the next scheduled run._"
        return f"{START}\n{body}\n{END}"

    latest = max(r["date"] for r in rows)
    today = {r["city"]: r for r in rows if r["date"] == latest}
    days = len({r["date"] for r in rows})
    fetched = _fetched_ist(list(today.values()))
    details = [f"fetched {fetched}"] if fetched else []
    details.append(f"{days} day{'s' if days != 1 else ''} collected")

    lines = _staleness_warning(latest, as_of) + [
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
    lines += render_daily(daily_rows or [], gas_rows)
    lines += render_summary(daily_rows or [])
    lines += render_india_summary(daily_rows or [], gas_rows or [])
    lines += ["", f"![US AQI trend by city]({CHART_URL})"]
    if report_months:
        links = " · ".join(
            f"[{calendar.month_abbr[int(m[5:])]} {m[:4]}](reports/{m}.md)"
            for m in sorted(report_months, reverse=True)
        )
        lines += ["", f"**Monthly reports:** {links}"]
    return f"{START}\n" + "\n".join(lines) + f"\n{END}"


def update_readme(
    readme_text: str,
    rows: list[dict[str, str]],
    daily_rows: list[dict[str, str]] | None = None,
    gas_rows: list[dict[str, str]] | None = None,
    as_of: date | None = None,
    report_months: list[str] | None = None,
) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(readme_text):
        raise ValueError(f"README is missing the {START} ... {END} markers")
    section = render_section(rows, daily_rows, gas_rows, as_of, report_months)
    return pattern.sub(lambda _: section, readme_text, count=1)


def main(
    readme_path: Path = README_PATH,
    csv_path: Path = CSV_PATH,
    daily_csv_path: Path = DAILY_CSV_PATH,
    gases_csv_path: Path = GASES_CSV_PATH,
    reports_dir: Path = ROOT / "reports",
) -> int:
    try:
        new_text = update_readme(
            readme_path.read_text(encoding="utf-8"),
            read_rows(csv_path),
            read_rows(daily_csv_path),
            read_rows(gases_csv_path),
            as_of=datetime.now(IST).date(),
            report_months=[p.stem for p in sorted(reports_dir.glob("????-??.md"))],
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    readme_path.write_text(new_text, encoding="utf-8")
    print(f"Updated {readme_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
