import json

import fetch
import latest_json
from common import CITIES, COLUMNS, DAILY_COLUMNS

DELHI, MUMBAI = CITIES[0][0], CITIES[1][0]


def snap(day, city, aqi, o3="80"):
    return {"date": day, "city": city, "us_aqi": aqi, "pm2_5": "55.5", "pm10": "",
            "no2": "20", "o3": o3, "fetched_at_utc": f"{day}T03:17:00Z"}


def daily(day, city, mean, pm25="100.0", pm10="150.0"):
    return {"date": day, "city": city, "hours": "24", "us_aqi_mean": str(mean),
            "us_aqi_max": str(mean + 30), "pm2_5_mean": pm25, "pm10_mean": pm10,
            "fetched_at_utc": "x"}


def test_build_uses_latest_day_only_and_keeps_city_order():
    rows = [snap("2026-09-22", DELHI, "300"), snap("2026-09-23", MUMBAI, "90"),
            snap("2026-09-23", DELHI, "180")]
    data = latest_json.build(rows, [], [])
    assert data["snapshot"]["date"] == "2026-09-23"
    delhi, mumbai = data["snapshot"]["cities"]
    assert (delhi["city"], mumbai["city"]) == (DELHI, MUMBAI)  # CITIES order
    assert delhi["us_aqi"] == 180.0 and delhi["us_category"] == "Unhealthy"
    assert delhi["pm10"] is None  # missing values are null, not ""
    assert (delhi["lat"], delhi["lon"]) == CITIES[0][1:]
    assert data["full_day"] is None


def test_full_day_india_aqi_excludes_ozone_and_nulls_severe():
    daily_rows = [daily("2026-09-22", DELHI, 172), daily("2026-09-22", MUMBAI, 40,
                                                            pm25="600.0", pm10="30.0")]
    gases = [{"date": "2026-09-22", "city": DELHI, "no2_mean": "40.0", "o3_max8h": "900",
              "fetched_at_utc": "x"}]
    data = latest_json.build([], daily_rows, gases)
    delhi, mumbai = data["full_day"]["cities"]
    assert delhi["no2_mean"] == 40.0
    assert delhi["india_aqi"]["prominent"] == "PM2.5"  # O₃ 900 ignored
    assert delhi["india_aqi"]["pollutants"] == 3
    assert mumbai["india_aqi"]["index"] is None  # Severe: no number
    assert mumbai["india_aqi"]["category"] == "Severe"
    assert mumbai["no2_mean"] is None


def test_main_writes_stable_json(tmp_path):
    csv, daily_csv, gas_csv = (tmp_path / n for n in ("a.csv", "d.csv", "g.csv"))
    fetch.append_rows(csv, [snap("2026-09-23", DELHI, "180")], COLUMNS)
    fetch.append_rows(daily_csv, [daily("2026-09-22", DELHI, 172)], DAILY_COLUMNS)
    out = tmp_path / "out" / "latest.json"
    assert latest_json.main(out, csv, daily_csv, gas_csv) == 0
    first = out.read_text(encoding="utf-8")
    data = json.loads(first)
    assert data["schema_version"] == latest_json.SCHEMA_VERSION
    assert "CC BY 4.0" in data["attribution"]
    # No timestamps of its own: rerunning on the same data changes nothing.
    assert latest_json.main(out, csv, daily_csv, gas_csv) == 0
    assert out.read_text(encoding="utf-8") == first


def test_main_with_no_data(tmp_path):
    out = tmp_path / "latest.json"
    assert latest_json.main(out, tmp_path / "a", tmp_path / "b", tmp_path / "c") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["snapshot"] is None and data["full_day"] is None
