"""Render charts/aqi_trend.png: US AQI per city over every collected day.

Plots the full-day mean (data/aqi_daily.csv) once any exists, since it's
comparable across days. Until then it falls back to the single daily
snapshot (data/aqi.csv).
"""

from __future__ import annotations

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
}
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
BAND = "#f1f0ec"
MIN_WINDOW_DAYS = 7  # a zero-width date axis renders garbage ticks
MAX_MARKER_POINTS = 60  # beyond this, markers just clutter the lines


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


def render(
    csv_path: Path = CSV_PATH,
    out_path: Path = CHART_PATH,
    daily_csv_path: Path = DAILY_CSV_PATH,
) -> Path:
    series = load_series(daily_csv_path, "us_aqi_mean")
    if series:
        title = "Daily mean US AQI — Indian metros"
        note = "24-hour mean of hourly model values"
    else:
        series = load_series(csv_path)
        title = "Daily US AQI snapshot — Indian metros"
        note = "one model reading per day"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    if not series:
        ax.text(0.5, 0.5, "No data collected yet", ha="center", va="center",
                color=TEXT_SECONDARY, fontsize=14, transform=ax.transAxes)
        ax.set_axis_off()
    else:
        ymax = max(v for pts in series.values() for _, v in pts)
        top = max(100, ymax * 1.1)

        # Alternating neutral bands for EPA categories, labelled on the right.
        lower = 0
        for i, (upper, label) in enumerate(AQI_CATEGORIES + [(10_000, "Hazardous")]):
            if lower >= top:
                break
            if i % 2 == 1:
                ax.axhspan(lower, min(upper, top), color=BAND, zorder=0, lw=0)
            mid = (lower + min(upper, top)) / 2
            ax.text(1.005, mid, label, transform=ax.get_yaxis_transform(),
                    fontsize=7.5, color=TEXT_SECONDARY, va="center")
            lower = upper

        for city, _, _ in CITIES:
            pts = series.get(city)
            if not pts:
                continue
            xs, ys = zip(*pts)
            marker = "o" if len(pts) <= MAX_MARKER_POINTS else None
            ax.plot(xs, ys, label=city, color=CITY_COLORS[city], lw=2,
                    marker=marker, markersize=6, markeredgecolor=SURFACE,
                    markeredgewidth=1.5, zorder=3)

        first = min(d for pts in series.values() for d, _ in pts)
        last = max(d for pts in series.values() for d, _ in pts)
        first = min(first, last - timedelta(days=MIN_WINDOW_DAYS - 1))
        # Half a day of padding each side (date objects can't hold hours).
        ax.set_xlim(mdates.date2num(first) - 0.5, mdates.date2num(last) + 0.5)
        ax.set_ylim(0, top)
        ax.grid(axis="y", color=GRID, lw=0.8, zorder=1)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=TEXT_SECONDARY, length=0, labelsize=9)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=10))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.set_ylabel("US AQI", color=TEXT_SECONDARY)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=len(CITIES),
                  frameon=False, fontsize=9, labelcolor=TEXT_PRIMARY,
                  borderaxespad=0, handlelength=1.5)

    ax.set_title(title, loc="left", color=TEXT_PRIMARY, fontsize=13, pad=26)
    fig.text(0.01, 0.01, f"Source: CAMS via Open-Meteo (CC BY 4.0) · {note}",
             color=TEXT_SECONDARY, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(out_path, facecolor=SURFACE)
    plt.close(fig)
    return out_path


def main() -> int:
    path = render()
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
