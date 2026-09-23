import csv
from datetime import datetime, timezone

import pytest
import requests

import fetch
from common import CITIES, COLUMNS, DAILY_COLUMNS
from conftest import FakeSession, make_response

FETCHED_AT = "2026-09-23T03:17:00Z"
# 03:17 UTC = 08:47 IST, two minutes after the fixture's current.time.
NOW = datetime(2026, 9, 23, 3, 17, tzinfo=timezone.utc)


def run_main(path, outcomes, now=NOW, daily_path=None):
    session = FakeSession(outcomes)
    daily_path = daily_path or path.with_name("aqi_daily.csv")
    return fetch.main(
        csv_path=path,
        daily_csv_path=daily_path,
        session=session,
        sleep=lambda s: None,
        now=now,
    )


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_build_params_single_request_for_all_cities():
    params = fetch.build_params()
    assert params["latitude"].split(",") == [str(lat) for _, lat, _ in CITIES]
    assert params["longitude"].split(",") == [str(lon) for _, _, lon in CITIES]
    assert params["current"] == "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone"
    assert params["hourly"] == "us_aqi,pm2_5,pm10"
    assert (params["past_days"], params["forecast_days"]) == ("1", "1")
    assert params["timezone"] == "Asia/Kolkata"


def test_parse_payload_maps_fields_in_city_order(payload):
    rows = fetch.parse_payload(payload, FETCHED_AT)
    assert [r["city"] for r in rows] == [c for c, _, _ in CITIES]
    delhi = rows[0]
    assert delhi == {
        "date": "2026-09-23",
        "city": "Delhi",
        "us_aqi": "168",
        "pm2_5": "88.4",
        "pm10": "142.1",
        "no2": "41.3",
        "o3": "52.0",
        "fetched_at_utc": FETCHED_AT,
    }


def test_parse_payload_missing_value_becomes_blank(payload):
    payload[2]["current"]["us_aqi"] = None
    rows = fetch.parse_payload(payload, FETCHED_AT)
    assert rows[2]["us_aqi"] == ""


def test_parse_payload_rejects_wrong_location_count(payload):
    with pytest.raises(fetch.FetchError, match="Expected 5"):
        fetch.parse_payload(payload[:4], FETCHED_AT)


def test_append_creates_file_with_header(tmp_path, payload):
    path = tmp_path / "data" / "aqi.csv"
    written = fetch.append_rows(path, fetch.parse_payload(payload, FETCHED_AT))
    assert written == 5
    lines = read_csv(path)
    assert lines[0] == COLUMNS
    assert len(lines) == 6


def test_append_same_day_is_idempotent(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    rows = fetch.parse_payload(payload, FETCHED_AT)
    assert fetch.append_rows(path, rows) == 5
    before = path.read_text()

    # Later fetch on the same IST day, with different values — still skipped.
    payload[0]["current"]["us_aqi"] = 999
    rerun = fetch.parse_payload(payload, "2026-09-23T09:00:00Z")
    assert fetch.append_rows(path, rerun) == 0
    assert path.read_text() == before


def test_append_only_missing_cities(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    rows = fetch.parse_payload(payload, FETCHED_AT)
    fetch.append_rows(path, rows[:2])  # Delhi, Mumbai already stored
    assert fetch.append_rows(path, rows) == 3
    lines = read_csv(path)
    assert [line[1] for line in lines[1:]] == [c for c, _, _ in CITIES]
    assert sum(1 for line in lines if line == COLUMNS) == 1  # header once


def test_append_next_day_adds_rows(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    fetch.append_rows(path, fetch.parse_payload(payload, FETCHED_AT))
    for loc in payload:
        loc["current"]["time"] = "2026-09-24T08:45"
    assert fetch.append_rows(path, fetch.parse_payload(payload, FETCHED_AT)) == 5
    assert len(read_csv(path)) == 11


def test_fetch_retries_then_succeeds(payload):
    session = FakeSession([
        requests.ConnectionError("boom"),
        make_response(503, {"error": True}),
        make_response(200, payload),
    ])
    sleeps = []
    result = fetch.fetch_payload(session=session, sleep=sleeps.append)
    assert result == payload
    assert len(session.calls) == 3
    assert sleeps == [2, 4]  # exponential backoff
    assert session.calls[0]["url"] == fetch.API_URL


def test_fetch_gives_up_after_max_attempts():
    session = FakeSession([requests.Timeout("slow")] * fetch.MAX_ATTEMPTS)
    sleeps = []
    with pytest.raises(fetch.FetchError, match="Giving up"):
        fetch.fetch_payload(session=session, sleep=sleeps.append)
    assert len(session.calls) == fetch.MAX_ATTEMPTS
    assert sleeps == [2, 4, 8]


def test_fetch_does_not_retry_client_error():
    session = FakeSession([make_response(400, {"reason": "bad param"})])
    with pytest.raises(requests.HTTPError):
        fetch.fetch_payload(session=session, sleep=lambda s: None)
    assert len(session.calls) == 1


def test_parse_payload_rejects_misordered_locations(payload):
    payload[0], payload[1] = payload[1], payload[0]  # Mumbai where Delhi should be
    with pytest.raises(fetch.FetchError, match="order changed"):
        fetch.parse_payload(payload, FETCHED_AT)


def test_main_success_writes_csv(tmp_path, payload, capsys):
    path = tmp_path / "aqi.csv"
    assert run_main(path, [make_response(200, payload)]) == 0
    assert run_main(path, [make_response(200, payload)]) == 0
    lines = read_csv(path)
    assert len(lines) == 6  # second run deduped
    assert lines[1][-1] == "2026-09-23T03:17:00Z"
    assert "Wrote 0 new row(s)" in capsys.readouterr().out


def test_main_exits_nonzero_on_failure(tmp_path):
    path = tmp_path / "aqi.csv"
    assert run_main(path, [requests.ConnectionError("down")] * fetch.MAX_ATTEMPTS) == 1
    assert not path.exists()


def test_main_exits_nonzero_on_malformed_payload(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    assert run_main(path, [make_response(200, payload[:3])]) == 1
    assert not path.exists()


def test_main_rejects_stale_data(tmp_path, payload, capsys):
    # API still serving yesterday's reading: must fail, not silently dedupe.
    path = tmp_path / "aqi.csv"
    now = datetime(2026, 9, 24, 3, 17, tzinfo=timezone.utc)
    assert run_main(path, [make_response(200, payload)], now=now) == 1
    assert not path.exists()
    assert "Stale data" in capsys.readouterr().err


def test_main_accepts_data_within_max_age(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    now = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)  # 13:30 IST, 4h45m old
    assert run_main(path, [make_response(200, payload)], now=now) == 0


def test_main_missing_aqi_stores_others_then_backfills(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    payload[3]["current"]["us_aqi"] = None  # Kolkata
    assert run_main(path, [make_response(200, payload)]) == 1  # loud failure
    assert [line[1] for line in read_csv(path)[1:]] == [
        "Delhi", "Mumbai", "Bengaluru", "Chennai"
    ]

    # Backup run later the same day gets Kolkata; only that row is added.
    payload[3]["current"]["us_aqi"] = 121
    assert run_main(path, [make_response(200, payload)]) == 0
    rows = read_csv(path)[1:]
    assert len(rows) == 5
    assert rows[-1][:3] == ["2026-09-23", "Kolkata", "121"]


def test_parse_daily_uses_previous_ist_day_only(payload):
    rows, skipped = fetch.parse_daily(payload, FETCHED_AT)
    assert skipped == []
    assert [r["city"] for r in rows] == [c for c, _, _ in CITIES]
    delhi = rows[0]
    hourly = payload[0]["hourly"]
    yesterday = hourly["us_aqi"][:24]  # fixture hours 0-23 are 2026-09-22
    assert delhi["date"] == "2026-09-22"
    assert delhi["hours"] == "24"
    assert delhi["us_aqi_mean"] == f"{sum(yesterday) / 24:.1f}"
    assert delhi["us_aqi_max"] == str(max(yesterday))
    assert delhi["pm2_5_mean"] == f"{sum(hourly['pm2_5'][:24]) / 24:.1f}"
    # Today's (partly forecast) hours must not leak into yesterday's stats.
    hourly["us_aqi"][30] = 9999
    assert fetch.parse_daily(payload, FETCHED_AT)[0][0]["us_aqi_max"] == str(max(yesterday))


def test_parse_daily_tolerates_a_few_missing_hours(payload):
    for i in (1, 2, 3):
        payload[1]["hourly"]["us_aqi"][i] = None
    rows, skipped = fetch.parse_daily(payload, FETCHED_AT)
    assert skipped == []
    assert rows[1]["hours"] == "21"


def test_parse_daily_skips_city_with_too_few_hours(payload):
    for i in range(24 - fetch.MIN_DAILY_HOURS + 1):
        payload[4]["hourly"]["us_aqi"][i] = None
    rows, skipped = fetch.parse_daily(payload, FETCHED_AT)
    assert skipped == ["Chennai"]
    assert len(rows) == 4


def test_parse_daily_without_hourly_block_skips_all(payload):
    for loc in payload:
        del loc["hourly"]
    rows, skipped = fetch.parse_daily(payload, FETCHED_AT)
    assert rows == [] and len(skipped) == 5


def test_main_writes_daily_csv_and_dedupes(tmp_path, payload):
    path, daily = tmp_path / "aqi.csv", tmp_path / "aqi_daily.csv"
    assert run_main(path, [make_response(200, payload)], daily_path=daily) == 0
    assert run_main(path, [make_response(200, payload)], daily_path=daily) == 0
    lines = read_csv(daily)
    assert lines[0] == DAILY_COLUMNS
    assert len(lines) == 6
    assert {line[0] for line in lines[1:]} == {"2026-09-22"}


def test_main_fails_but_keeps_snapshot_when_hourly_missing(tmp_path, payload):
    path, daily = tmp_path / "aqi.csv", tmp_path / "aqi_daily.csv"
    del payload[2]["hourly"]  # Bengaluru
    assert run_main(path, [make_response(200, payload)], daily_path=daily) == 1
    assert len(read_csv(path)) == 6  # snapshot fully stored
    assert "Bengaluru" not in [line[1] for line in read_csv(daily)]
