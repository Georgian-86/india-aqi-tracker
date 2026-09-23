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


def peaks_above(points: list[tuple[date, float]], cap: float) -> list[tuple[date, float]]:
    """The highest point of each consecutive run of points above cap."""
    peaks: list[tuple[date, float]] = []
    in_run = False
    for d, v in points:
        if v > cap:
            if in_run and v > peaks[-1][1]:
                peaks[-1] = (d, v)
            elif not in_run:
                peaks.append((d, v))
            in_run = True
        else:
            in_run = False
    return peaks


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
    series = load_series(daily_csv_path, "us_aqi_mean")
    if series:
        title = "Daily mean US AQI — Indian metros"
        note = "24-hour mean of hourly model values"
    else:
        series = load_series(csv_path)
        title = "Daily US AQI snapshot — Indian metros"
        note = "one model reading per day"
    series = recent(series)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    if not series:
        ax.text(0.5, 0.5, "No data collected yet", ha="center", va="center",
                color=TEXT_SECONDARY, fontsize=14, transform=ax.transAxes)
        ax.set_axis_off()
    else:
        top, clipped = y_limit([v for pts in series.values() for _, v in pts])
        if clipped:
            note += f" · values above {top:.0f} run off the top (peaks labelled)"

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
            for d, v in peaks_above(pts, top) if clipped else []:
                ax.plot([d], [top], marker="^", markersize=7, color=CITY_COLORS[city],
                        markeredgecolor=SURFACE, clip_on=False, zorder=4)
                ax.annotate(f"{v:.0f}", xy=(d, top), xytext=(5, -2),
                            textcoords="offset points", ha="left", va="top",
                            fontsize=7.5, color=TEXT_SECONDARY, zorder=5,
                            bbox={"boxstyle": "square,pad=0.15", "fc": SURFACE, "ec": "none"})

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
        # Up to 5 entries fit in one row across the plot; beyond that, wrap to two rows.
        ncol = len(CITIES) if len(CITIES) <= 5 else math.ceil(len(CITIES) / 2)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=ncol,
                  frameon=False, fontsize=9, labelcolor=TEXT_PRIMARY,
                  borderaxespad=0, handlelength=1.5)

    # Leave room above the axes for the legend: ~18 pt per legend row.
    legend_rows = 1 if len(CITIES) <= 5 else 2
    ax.set_title(title, loc="left", color=TEXT_PRIMARY, fontsize=13, pad=8 + 18 * legend_rows)
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
