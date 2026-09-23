import calendar

import report
import update_readme
from common import CITIES


def daily(day, city, mean, pm25="20.0", pm10="30.0"):
    return {"date": day, "city": city, "hours": "24", "us_aqi_mean": str(mean),
            "us_aqi_max": str(mean), "pm2_5_mean": pm25, "pm10_mean": pm10,
            "fetched_at_utc": "x"}


def month_rows(month, days, city="Delhi", mean=100.0, **kw):
    return [daily(f"{month}-{d:02d}", city, mean, **kw) for d in days]


def test_complete_months_needs_last_day_and_min_days():
    rows = (month_rows("2026-06", range(23, 31))  # 8 days: too few
            + month_rows("2026-07", range(1, 32))  # complete
            + month_rows("2026-08", range(1, 31)))  # missing Aug 31: not complete
    assert report.complete_months(rows) == ["2026-07"]


def test_complete_months_min_days_boundary():
    enough = month_rows("2026-07", range(32 - report.MIN_DAYS, 32))
    too_few = month_rows("2026-08", range(33 - report.MIN_DAYS, 32))
    assert report.complete_months(enough + too_few) == ["2026-07"]


def test_render_month_ranking_and_categories():
    rows = (month_rows("2026-07", range(1, 32), "Delhi", 180.0, pm25="100.0")  # India Poor
            + month_rows("2026-07", range(1, 32), "Chennai", 40.0, pm25="10.0"))  # Good
    rows[5] = daily("2026-07-06", "Delhi", 420.0, pm25="100.0")  # worst day
    gases = [{"date": "2026-07-01", "city": "Chennai", "no2_mean": "200.0",
              "o3_max8h": "999", "fetched_at_utc": "x"}]  # NO₂ counts, O₃ must not
    md = report.render_month("2026-07", rows, gases)
    assert md.startswith("# Air quality report: July 2026")
    assert "Full-day means for 31 days of July 2026" in md
    ranking = md[md.index("## Ranking"):md.index("## Days")]
    assert ranking.index("Chennai") < ranking.index("Delhi")  # cleanest first
    assert "| 2 | Delhi | 188 | Unhealthy | 31 | 420 on 2026-07-06 |" in ranking
    # Chennai: 30 Good days (PM10 30 → 30 beats PM2.5 10 → 17) + 1 NO₂-driven Poor
    # day (NO₂ 200 → 220); O₃ 999 ignored.
    assert "| Chennai | 30 | · | · | 1 | · | · | PM10 30 · NO₂ 1 |" in md
    assert "| Delhi | · | · | · | 31 | · | · | PM2.5 31 |" in md


def test_render_month_marks_partial_city():
    rows = (month_rows("2026-07", range(1, 32), "Delhi")
            + month_rows("2026-07", range(10, 32), "Pune"))  # added mid-month
    md = report.render_month("2026-07", rows, [])
    assert "| Pune (22 days) |" in md
    assert "| Delhi |" in md


def test_write_reports_is_immutable(tmp_path):
    rows = month_rows("2026-07", range(1, 32))
    [path] = report.write_reports(rows, [], tmp_path)
    assert path.name == "2026-07.md"
    path.write_text("edited by hand")
    assert report.write_reports(rows, [], tmp_path) == []  # not rewritten
    assert path.read_text() == "edited by hand"


def test_main_no_complete_month(tmp_path, capsys):
    assert report.main(tmp_path / "none.csv", tmp_path / "none2.csv", tmp_path / "r") == 0
    assert "No new monthly reports." in capsys.readouterr().out
    assert not (tmp_path / "r").exists()


def test_readme_links_reports_newest_first():
    rows = [{"date": "2026-09-23", "city": CITIES[0][0], "us_aqi": "100", "pm2_5": "",
             "pm10": "", "no2": "", "o3": "", "fetched_at_utc": "2026-09-23T03:17:00Z"}]
    section = update_readme.render_section(rows, report_months=["2026-07", "2026-08"])
    assert (f"**Monthly reports:** [{calendar.month_abbr[8]} 2026](reports/2026-08.md) · "
            f"[{calendar.month_abbr[7]} 2026](reports/2026-07.md)") in section
    assert "Monthly reports" not in update_readme.render_section(rows)
