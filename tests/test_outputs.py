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
    out = make_chart.render(csv_path, tmp_path / "charts" / "aqi.png")
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_chart_placeholder_when_no_data(tmp_path):
    out = make_chart.render(tmp_path / "missing.csv", tmp_path / "chart.png")
    assert out.exists() and out.stat().st_size > 0
