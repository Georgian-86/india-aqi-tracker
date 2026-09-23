"""Tests for the README updater and chart renderer."""

from datetime import date

import pytest

import fetch
import make_chart
import update_readme
from common import read_rows

README = """# Title

intro

<!-- AQI:START -->
old content
<!-- AQI:END -->

## Footer
"""


@pytest.fixture
def csv_path(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    for loc in payload:
        loc["current"]["time"] = "2026-09-22T08:45"
    fetch.append_rows(path, fetch.parse_payload(payload, "2026-09-22T03:17:00Z"))
    for loc in payload:
        loc["current"]["time"] = "2026-09-23T08:45"
        loc["current"]["us_aqi"] += 10
    fetch.append_rows(path, fetch.parse_payload(payload, "2026-09-23T03:17:00Z"))
    return path


def test_update_readme_replaces_only_marked_section(csv_path):
    out = update_readme.update_readme(README, read_rows(csv_path))
    assert "old content" not in out
    assert out.startswith("# Title\n\nintro\n\n<!-- AQI:START -->\n")
    assert out.endswith("<!-- AQI:END -->\n\n## Footer\n")
    assert "**Latest snapshot: 2026-09-23**" in out
    # fetched_at_utc 03:17Z is 08:47 IST; derived from data, not hard-coded.
    assert "(fetched 08:47 IST · 2 days collected)" in out
    assert "| Delhi | 178 | 🔴 Unhealthy |" in out
    assert "| Chennai | 48 | 🟢 Good |" in out
    assert f"![US AQI trend by city]({update_readme.CHART_URL})" in out
    assert "/charts/aqi_trend.png" in update_readme.CHART_URL


def test_update_readme_is_stable_on_rerun(csv_path):
    rows = read_rows(csv_path)
    once = update_readme.update_readme(README, rows)
    assert update_readme.update_readme(once, rows) == once


def test_update_readme_singular_day(payload, tmp_path):
    path = tmp_path / "aqi.csv"
    fetch.append_rows(path, fetch.parse_payload(payload, "2026-09-23T16:30:40Z"))
    out = update_readme.update_readme(README, read_rows(path))
    assert "(fetched 22:00 IST · 1 day collected)" in out


def test_update_readme_without_data():
    out = update_readme.update_readme(README, [])
    assert "No data collected yet" in out


def test_update_readme_requires_markers():
    with pytest.raises(ValueError, match="markers"):
        update_readme.update_readme("# no markers here\n", [])


def test_chart_is_written(csv_path, tmp_path):
    out = make_chart.render(csv_path, tmp_path / "charts" / "aqi.png", tmp_path / "none.csv")
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_chart_placeholder_when_no_data(tmp_path):
    out = make_chart.render(
        tmp_path / "missing.csv", tmp_path / "chart.png", tmp_path / "missing_daily.csv"
    )
    assert out.exists() and out.stat().st_size > 0


def test_chart_prefers_daily_means(csv_path, tmp_path, payload, monkeypatch):
    daily = tmp_path / "daily.csv"
    rows, _ = fetch.parse_daily(payload, "x")
    fetch.append_rows(daily, rows, fetch.DAILY_COLUMNS)
    seen = []
    real = make_chart.load_series
    monkeypatch.setattr(
        make_chart, "load_series", lambda p, col="us_aqi": seen.append(col) or real(p, col)
    )
    make_chart.render(csv_path, tmp_path / "c.png", daily)
    assert seen == ["us_aqi_mean"]  # snapshot CSV not needed


def test_chart_falls_back_to_snapshots(csv_path, tmp_path, monkeypatch):
    seen = []
    real = make_chart.load_series
    monkeypatch.setattr(
        make_chart, "load_series", lambda p, col="us_aqi": seen.append(col) or real(p, col)
    )
    make_chart.render(csv_path, tmp_path / "c.png", tmp_path / "no_daily.csv")
    assert seen == ["us_aqi_mean", "us_aqi"]


def test_change_since_previous_reading(csv_path):
    out = update_readme.update_readme(README, read_rows(csv_path))
    # Fixture: every city is +10 on 2026-09-23 vs 2026-09-22.
    assert "| Delhi | 178 | 🔴 Unhealthy | ▲ 10 |" in out


def test_change_is_dash_on_first_day(payload, tmp_path):
    path = tmp_path / "aqi.csv"
    fetch.append_rows(path, fetch.parse_payload(payload, "2026-09-23T03:17:00Z"))
    out = update_readme.update_readme(README, read_rows(path))
    assert "| Delhi | 168 | 🔴 Unhealthy | – |" in out


def daily_row(day, city, mean, peak="200", pm25="80.0"):
    return {"date": day, "city": city, "hours": "24", "us_aqi_mean": mean,
            "us_aqi_max": peak, "pm2_5_mean": pm25, "pm10_mean": "",
            "fetched_at_utc": "x"}


def test_daily_table_with_partial_week(csv_path):
    daily = [
        daily_row("2026-09-21", "Delhi", "150.0"),
        daily_row("2026-09-22", "Delhi", "171.4", peak="205"),
        daily_row("2026-09-22", "Chennai", "42.0", peak="55", pm25="10.2"),
    ]
    out = update_readme.update_readme(README, read_rows(csv_path), daily)
    assert "**Full day 2026-09-22**" in out
    # (150 + 171.4) / 2 = 160.7 → "161 (2d)"
    assert "| Delhi | 171 | 🔴 Unhealthy | 205 | 161 (2d) | 80 |" in out
    assert "| Chennai | 42 | 🟢 Good | 55 | 42 (1d) | 10.2 |" in out
    # Chart comes after both tables.
    assert out.index("Full day") < out.index("![US AQI trend")


def test_daily_week_mean_ignores_older_days(csv_path):
    daily = [daily_row(f"2026-09-{d:02d}", "Delhi", "100.0") for d in range(10, 16)]
    daily += [daily_row(f"2026-09-{d:02d}", "Delhi", "200.0") for d in range(16, 23)]
    out = update_readme.update_readme(README, read_rows(csv_path), daily)
    assert "| Delhi | 200 | 🔴 Unhealthy | 200 | 200 | 80 |" in out  # full week, no "(Nd)"


def test_no_daily_table_without_daily_data(csv_path):
    out = update_readme.update_readme(README, read_rows(csv_path), [])
    assert "Full day" not in out


def test_main_reads_both_csvs(tmp_path, payload):
    readme, snap, daily = tmp_path / "README.md", tmp_path / "a.csv", tmp_path / "d.csv"
    readme.write_text(README)
    fetch.append_rows(snap, fetch.parse_payload(payload, "2026-09-23T03:17:00Z"))
    rows, _ = fetch.parse_daily(payload, "2026-09-23T03:17:00Z")
    fetch.append_rows(daily, rows, fetch.DAILY_COLUMNS)
    assert update_readme.main(readme, snap, daily) == 0
    text = readme.read_text()
    assert "**Full day 2026-09-22**" in text and "| Mumbai | 74 |" in text


def test_change_hidden_when_times_of_day_differ(payload, tmp_path):
    # 22:00 IST yesterday vs 08:47 IST today: diurnal cycle, not a trend.
    path = tmp_path / "aqi.csv"
    for loc in payload:
        loc["current"]["time"] = "2026-09-22T22:00"
    fetch.append_rows(path, fetch.parse_payload(payload, "2026-09-22T16:30:00Z"))
    for loc in payload:
        loc["current"]["time"] = "2026-09-23T08:45"
    fetch.append_rows(path, fetch.parse_payload(payload, "2026-09-23T03:17:00Z"))
    out = update_readme.update_readme(README, read_rows(path))
    assert "| Delhi | 168 | 🔴 Unhealthy | – |" in out


def test_change_shown_across_midnight_within_window():
    prev = {"us_aqi": "100", "fetched_at_utc": "2026-09-22T18:00:00Z"}  # 23:30 IST
    cur = {"us_aqi": "90", "fetched_at_utc": "2026-09-23T19:00:00Z"}  # 00:30 IST
    assert update_readme._change(cur, prev) == "▼ 10"


def test_summary_counts_days_per_category(csv_path):
    means = ["45.0", "60.0", "120.0", "160.0", "160.0", "250.0", "320.0"]
    daily = [daily_row(f"2026-09-{16 + i}", "Delhi", m) for i, m in enumerate(means)]
    daily.append(daily_row("2026-09-22", "Chennai", "30.0"))
    out = update_readme.update_readme(README, read_rows(csv_path), daily)
    assert "**Last 30 days** (2026-08-24 to 2026-09-22, full-day means · 7 days of data)" in out
    #        Good Mod USG Unh VU Haz | mean = 1115/7 = 159.3 | worst
    assert "| Delhi | 1 | 1 | 1 | 2 | 1 | 1 | 159 | 320 on 2026-09-22 |" in out
    assert "| Chennai | 1 | · | · | · | · | · | 30 | 30 on 2026-09-22 |" in out
    assert out.index("Last 30 days") < out.index("![US AQI trend")


def test_summary_window_is_30_days(csv_path):
    daily = [daily_row("2026-08-23", "Delhi", "400.0")]  # 31 days before the end: excluded
    daily += [daily_row("2026-08-24", "Delhi", "100.0"), daily_row("2026-09-22", "Delhi", "50.0")]
    out = update_readme.update_readme(README, read_rows(csv_path), daily)
    assert "| Delhi | 1 | 1 | · | · | · | · | 75 | 100 on 2026-08-24 |" in out


def test_summary_omitted_with_single_day(csv_path):
    out = update_readme.update_readme(
        README, read_rows(csv_path), [daily_row("2026-09-22", "Delhi", "100.0")]
    )
    assert "Last 30 days" not in out


def test_y_limit_no_clipping_for_normal_range():
    top, clipped = make_chart.y_limit([40.0, 90.0, 180.0])
    assert not clipped and top == pytest.approx(198.0)


def test_y_limit_small_values_floor_at_100():
    assert make_chart.y_limit([20.0, 30.0]) == (100, False)


def test_y_limit_clips_rare_extremes():
    values = [100.0] * 95 + [620.0] * 5  # 5% dust-storm days
    top, clipped = make_chart.y_limit(values)
    assert clipped and top == make_chart.MIN_Y_CAP


def test_y_limit_follows_sustained_high_levels():
    # A Delhi winter: most days 300-450, so the cap rises instead of clipping it all.
    values = [300.0 + i for i in range(150)]
    top, clipped = make_chart.y_limit(values)
    assert not clipped and top == pytest.approx(449 * 1.1)


def test_peaks_above_one_label_per_run():
    d = [date(2026, 7, i) for i in range(1, 9)]
    pts = list(zip(d, [100, 400, 610, 500, 100, 350, 90, 320]))
    assert make_chart.peaks_above(pts, 300) == [(d[2], 610), (d[5], 350), (d[7], 320)]


def test_chart_with_outliers_renders(tmp_path):
    daily = tmp_path / "d.csv"
    rows = [daily_row(f"2026-07-{i:02d}", c, str(v)) for i in range(1, 31)
            for c, v in [("Delhi", 620.0 if i in (10, 11) else 150.0), ("Mumbai", 60.0)]]
    fetch.append_rows(daily, rows, fetch.DAILY_COLUMNS)
    out = make_chart.render(tmp_path / "none.csv", tmp_path / "c.png", daily)
    assert out.stat().st_size > 0


def test_daily_table_shows_india_aqi(csv_path):
    daily = [
        {**daily_row("2026-09-22", "Delhi", "172.2", peak="206", pm25="68.8"), "pm10_mean": "129.9"},
        {**daily_row("2026-09-22", "Kolkata", "300.0", pm25="300.0")},  # Severe via PM2.5
        {**daily_row("2026-09-22", "Chennai", "70.0", pm25="")},  # no PM data
    ]
    out = update_readme.update_readme(README, read_rows(csv_path), daily)
    assert "| India AQI (PM)¹ |" in out
    assert "| Delhi | 172 | 🔴 Unhealthy | 206 | 172 (1d) | 68.8 | 129 Moderate |" in out
    assert "| Severe (401+) |" in out
    assert "| Chennai | 70 | 🟡 Moderate | 200 | 70 (1d) | – | – |" in out
    assert "PM-only approximation" in out
