import calendar

import pytest

import drift
import report
from common import CITIES

CITY_NAMES = [c for c, _, _ in CITIES]
N = len(CITY_NAMES)


def month_rows(month, city, pm25=40.0, pm10=80.0, aqi=100.0, days=None):
    year, mon = map(int, month.split("-"))
    days = days or calendar.monthrange(year, mon)[1]
    return [{"date": f"{month}-{d:02d}", "city": city, "hours": "24",
             "us_aqi_mean": str(aqi), "us_aqi_max": str(aqi), "pm2_5_mean": str(pm25),
             "pm10_mean": str(pm10), "fetched_at_utc": "x"} for d in range(1, days + 1)]


def gas_rows(month, city, no2, days=30):
    return [{"date": f"{month}-{d:02d}", "city": city, "no2_mean": str(no2),
             "o3_max8h": "", "fetched_at_utc": "x"} for d in range(1, days + 1)]


def two_years(this_year=None, gases_this=None, cities=CITY_NAMES):
    """September 2025 as baseline, September 2026 with per-city overrides."""
    daily, gases = [], []
    for city in cities:
        daily += month_rows("2025-09", city)
        daily += month_rows("2026-09", city, **(this_year or {}).get(city, {}))
        gases += gas_rows("2025-09", city, 20.0)
        gases += gas_rows("2026-09", city, (gases_this or {}).get(city, 20.0))
    return daily, gases


def findings(daily, gases, month="2026-09"):
    return drift.check_month(drift.monthly_means(daily, gases), month)


def test_steady_data_has_no_findings():
    assert findings(*two_years()) == []


def test_all_cities_step_is_one_finding():
    # NO₂ halves everywhere (like mid-2023): one all-cities finding, no per-city noise.
    daily, gases = two_years(gases_this={c: 10.0 for c in CITY_NAMES})
    [f] = findings(daily, gases)
    assert (f.pollutant, f.kind) == ("no2_mean", "all-cities")
    assert f.median_ratio == pytest.approx(0.5)
    assert len(f.cities) == N
    assert "model change" in f.describe() and "2025-09" in f.describe()


def test_single_city_step():
    # Delhi's PM10 ×4 (like the 2025 dust season), everyone else steady.
    daily, gases = two_years({"Delhi": {"pm10": 320.0}})
    [f] = findings(daily, gases)
    assert (f.pollutant, f.kind, f.cities) == ("pm10_mean", "city", {"Delhi": 4.0})
    assert f.median_ratio == pytest.approx(1.0)


def test_ordinary_variation_is_not_flagged():
    # A cleaner year everywhere by 30% and one city 2.5× dirtier: plausible, no flag.
    this = {c: {"pm25": 28.0} for c in CITY_NAMES}
    this["Kolkata"] = {"pm25": 100.0}
    assert findings(*two_years(this)) == []


def test_needs_min_days_and_min_cities():
    few_days = [r for r in month_rows("2026-09", "Delhi", pm10=900.0)][: drift.MIN_DAYS - 1]
    daily, gases = two_years()
    daily = [r for r in daily if not (r["city"] == "Delhi" and r["date"] >= "2026")] + few_days
    assert findings(daily, gases) == []  # Delhi's short month is ignored
    too_few = CITY_NAMES[: drift.MIN_CITIES - 1]
    daily, gases = two_years(gases_this={c: 5.0 for c in too_few}, cities=too_few)
    assert findings(daily, gases) == []


def test_report_consistency_section():
    daily, gases = two_years(gases_this={c: 10.0 for c in CITY_NAMES})
    flagged = report.render_month("2026-09", daily, gases)
    assert "## Data consistency" in flagged
    assert "Possible CAMS model change** compared with 2025-09" in flagged
    clean = report.render_month("2026-09", *two_years())
    assert "No sign of a model change against 2025-09" in clean
    first_year = report.render_month("2025-09", *two_years())
    assert "No data for 2024-09 to compare against." in first_year


def test_main_scans_history(tmp_path, capsys):
    import fetch
    from common import DAILY_COLUMNS, GAS_COLUMNS
    daily, gases = two_years(gases_this={c: 10.0 for c in CITY_NAMES})
    fetch.append_rows(tmp_path / "d.csv", daily, DAILY_COLUMNS)
    fetch.append_rows(tmp_path / "g.csv", gases, GAS_COLUMNS)
    assert drift.main(tmp_path / "d.csv", tmp_path / "g.csv") == 0
    out = capsys.readouterr().out
    assert "2026-09  NO₂" in out
    assert "Checked 1 month(s) against the year before; 1 finding(s)." in out
