"""Tests for the README updater and chart renderer."""

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
    assert "![US AQI trend by city](charts/aqi_trend.png)" in out


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
