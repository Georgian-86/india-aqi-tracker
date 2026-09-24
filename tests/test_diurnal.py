from datetime import date, timedelta

import pytest

import diurnal
import update_readme
from common import CITIES

DELHI, MUMBAI = CITIES[0][0], CITIES[1][0]
D = diurnal.MIN_DAYS


def curve(hour):
    """Clean mid-afternoon, dirty late evening."""
    return {13: 60, 14: 50, 15: 55, 21: 190, 22: 200, 23: 195}.get(hour, 120)


def rows(city, days, fn=curve, skip_hour=None):
    out = []
    for d in range(days):
        day = (date(2026, 9, 1) + timedelta(days=d)).isoformat()
        for h in range(24):
            if h != skip_hour:
                out.append({"date": day, "hour": f"{h:02d}", "city": city,
                            "us_aqi": str(fn(h)), "pm2_5": "", "pm10": ""})
    return out


def test_profile_finds_cleanest_and_worst_stretch():
    start, end, [p] = diurnal.profiles(rows(DELHI, D))
    assert (p.city, p.days) == (DELHI, D)
    assert (p.best_start, p.worst_start) == (13, 21)
    assert p.best_mean == pytest.approx(55) and p.worst_mean == pytest.approx(195)
    assert diurnal.Profile.span(22) == "22:00–01:00"  # wraps past midnight


def test_window_wraps_past_midnight():
    [p] = diurnal.profiles(rows(DELHI, D, fn=lambda h: 300 if h in (23, 0, 1) else 100))[2]
    assert p.worst_start == 23


def test_needs_min_days_for_every_hour():
    assert diurnal.profiles(rows(DELHI, D - 1)) is None
    assert diurnal.profiles(rows(DELHI, D + 5, skip_hour=4)) is None  # an hour never seen


def test_only_last_window_days_count():
    old = rows(DELHI, diurnal.WINDOW_DAYS, fn=lambda h: 500 if h == 14 else 100)
    for r in old:  # shift these to before the window
        r["date"] = (date.fromisoformat(r["date"]) - timedelta(days=60)).isoformat()
    _, _, [p] = diurnal.profiles(old + rows(DELHI, D))
    assert p.best_start == 13  # the old 500s at 14:00 are outside the window


def test_readme_table():
    snaps = [{"date": "2026-09-20", "city": c, "us_aqi": "100", "pm2_5": "", "pm10": "",
              "no2": "", "o3": "", "fetched_at_utc": "2026-09-20T03:17:00Z"}
             for c in (DELHI, MUMBAI)]
    section = update_readme.render_section(snaps, hourly_rows=rows(DELHI, D) + rows(MUMBAI, 3))
    assert f"| {DELHI} | 13:00–16:00 (55) | 21:00–00:00 (195) | 140 |" in section
    assert f"| {MUMBAI} |" not in section.split("**Time of day**")[1]
    assert "Time of day" not in update_readme.render_section(snaps, hourly_rows=[])
