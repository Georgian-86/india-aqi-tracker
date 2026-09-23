"""Render charts/aqi_trend.png: US AQI per city over every collected day.

Plots the full-day mean (data/aqi_daily.csv) once any exists, since it's
comparable across days. Until then it falls back to the single daily
snapshot (data/aqi.csv).
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from common import (  # noqa: E402
    AQI_CATEGORIES,
    CHART_PATH,
    CITIES,
    CSV_PATH,
    DAILY_CSV_PATH,
    read_rows,
)

# Fixed categorical order, one hue per city (never reassigned by rank).
CITY_COLORS = {
    "Delhi": "#2a78d6",
    "Mumbai": "#eb6834",
    "Bengaluru": "#1baf7a",
    "Kolkata": "#eda100",
    "Chennai": "#e87ba4",
    "Hyderabad": "#008300",
    "Pune": "#4a3aa7",
    "Ahmedabad": "#e34948",
}
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
BAND = "#f1f0ec"
# Short category names for the narrow right-hand margin of the panels.
CATEGORY_SHORT = {"Unhealthy for Sensitive Groups": "USG", "Very Unhealthy": "V. Unhealthy"}
MIN_WINDOW_DAYS = 7  # a zero-width date axis renders garbage ticks
# Years of daily lines for 8 cities are unreadable; older history lives in
# the monthly reports.
MAX_WINDOW_DAYS = 365
MAX_MARKER_POINTS = 60  # beyond this, markers just clutter the lines
# A dust storm can push one city's daily mean past 600 and squash every other
# line into the bottom of the chart. Cap the axis instead, and label peaks.
MIN_Y_CAP = 300  # top of "Very Unhealthy"; never clip below this
Y_CAP_PERCENTILE = 0.95
Y_CAP_HEADROOM = 1.15


def y_limit(values: list[float]) -> tuple[float, bool]:
    """Axis top and whether anything is clipped above it."""
    ymax = max(values)
    ordered = sorted(values)
    p95 = ordered[round(Y_CAP_PERCENTILE * (len(ordered) - 1))]
    cap = max(MIN_Y_CAP, p95 * Y_CAP_HEADROOM)
    if ymax * 1.1 <= cap:
        return max(100, ymax * 1.1), False
    return cap, True


def rolling_mean(points: list[tuple[date, float]], days: int = 7) -> list[tuple[date, float]]:
    """Trailing mean over the last `days` calendar days (gaps shorten the window)."""
    out = []
    for i, (d, _) in enumerate(points):
        window = [v for dd, v in points[: i + 1] if (d - dd).days < days]
        out.append((d, sum(window) / len(window)))
    return out


def load_series(csv_path: Path, column: str = "us_aqi") -> dict[str, list[tuple[date, float]]]:
    series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in read_rows(csv_path):
        if not row.get(column):
            continue
        series[row["city"]].append(
            (date.fromisoformat(row["date"]), float(row[column]))
        )
    for points in series.values():
        points.sort()
    return series


def recent(
    series: dict[str, list[tuple[date, float]]], days: int = MAX_WINDOW_DAYS
) -> dict[str, list[tuple[date, float]]]:
    """Keep only the last `days` days (relative to the newest point)."""
    if not series:
        return series
    last = max(d for pts in series.values() for d, _ in pts)
    cutoff = last - timedelta(days=days - 1)
    trimmed = {city: [(d, v) for d, v in pts if d >= cutoff] for city, pts in series.items()}
    return {city: pts for city, pts in trimmed.items() if pts}


def render(
    csv_path: Path = CSV_PATH,
    out_path: Path = CHART_PATH,
    daily_csv_path: Path = DAILY_CSV_PATH,
) -> Path:
    """Small multiples: one panel per city, shared axes, daily + 7-day mean.

    A single 8-line chart of a year of daily values was unreadable, and
    per-run peak labels overlapped into garbage once dust-storm spikes
    were frequent. Panels make each city legible and directly comparable.
    """
    series = load_series(daily_csv_path, "us_aqi_mean")
    if series:
        title = "Daily mean US AQI — Indian cities"
        note = "24-hour mean of hourly model values; bold line = 7-day mean"
    else:
        series = load_series(csv_path)
        title = "Daily US AQI snapshot — Indian cities"
        note = "one model reading per day"
    series = recent(series)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not series:
        fig, ax = plt.subplots(figsize=(10, 5), dpi=120)
        fig.patch.set_facecolor(SURFACE)
        ax.text(0.5, 0.5, "No data collected yet", ha="center", va="center",
                color=TEXT_SECONDARY, fontsize=14, transform=ax.transAxes)
        ax.set_axis_off()
        fig.savefig(out_path, facecolor=SURFACE)
        plt.close(fig)
        return out_path

    cities = [c for c, _, _ in CITIES if series.get(c)]
    # Two columns: time series want width, and the README shows images at
    # ~850 px, so a 4-wide grid would shrink every label to illegibility.
    ncols = min(2, len(cities))
    nrows = math.ceil(len(cities) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(9.5, 2.1 * nrows + 1.0),
                             dpi=120, sharex=True, sharey=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)

    top, clipped = y_limit([v for c in cities for _, v in series[c]])
    first = min(d for c in cities for d, _ in series[c])
    last = max(d for c in cities for d, _ in series[c])
    first = min(first, last - timedelta(days=MIN_WINDOW_DAYS - 1))
    bands = AQI_CATEGORIES + [(10_000, "Hazardous")]

    for i, ax in enumerate(axes.flat):
        if i >= len(cities):
            ax.set_axis_off()
            continue
        city = cities[i]
        pts = series[city]
        color = CITY_COLORS[city]
        ax.set_facecolor(SURFACE)
        lower = 0
        for j, (upper, label) in enumerate(bands):
            if lower >= top:
                break
            if j % 2 == 1:
                ax.axhspan(lower, min(upper, top), color=BAND, zorder=0, lw=0)
            if i % ncols == ncols - 1:  # category names on the right-hand column only
                ax.text(1.02, (lower + min(upper, top)) / 2, CATEGORY_SHORT.get(label, label),
                        transform=ax.get_yaxis_transform(), fontsize=8,
                        color=TEXT_SECONDARY, va="center")
            lower = upper

        xs, ys = zip(*pts)
        if len(pts) <= MAX_MARKER_POINTS:
            ax.plot(xs, ys, color=color, lw=2, marker="o", markersize=5,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
        else:
            ax.plot(xs, ys, color=color, lw=0.8, alpha=0.35, zorder=2)
            mx, my = zip(*rolling_mean(pts))
            ax.plot(mx, my, color=color, lw=2, zorder=3)

        peak_day, peak = max(pts, key=lambda p: (p[1], p[0]))
        if peak > top:  # one note per panel, never overlapping labels
            ax.text(0.98, 0.96, f"peak {peak:.0f} · {peak_day:%d %b}", transform=ax.transAxes,
                    ha="right", va="top", fontsize=8.5, color=TEXT_SECONDARY, zorder=5,
                    bbox={"boxstyle": "square,pad=0.2", "fc": SURFACE, "ec": "none"})

        ax.set_title(city, loc="left", fontsize=11, color=TEXT_PRIMARY, pad=4)
        ax.set_xlim(mdates.date2num(first) - 0.5, mdates.date2num(last) + 0.5)
        ax.set_ylim(0, top)
        ax.grid(axis="y", color=GRID, lw=0.6, zorder=1)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=TEXT_SECONDARY, length=0, labelsize=9)
        locator = mdates.AutoDateLocator(minticks=3, maxticks=5)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    if clipped:
        note += f" · axis capped at {top:.0f}, higher peaks noted per city"
    fig.suptitle(title, x=0.01, ha="left", color=TEXT_PRIMARY, fontsize=14)
    fig.text(0.01, 0.005, f"Source: CAMS via Open-Meteo (CC BY 4.0) · {note}",
             color=TEXT_SECONDARY, fontsize=8, wrap=True)
    fig.tight_layout(rect=(0, 0.025, 1, 0.975))
    fig.savefig(out_path, facecolor=SURFACE)
    plt.close(fig)
    return out_path


def main() -> int:
    path = render()
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
