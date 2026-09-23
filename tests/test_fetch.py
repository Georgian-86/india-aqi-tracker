import csv

import pytest
import requests

import fetch
from common import CITIES, COLUMNS
from conftest import FakeSession, make_response

FETCHED_AT = "2026-09-23T03:17:00Z"


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_build_params_single_request_for_all_cities():
    params = fetch.build_params()
    assert params["latitude"].split(",") == [str(lat) for _, lat, _ in CITIES]
    assert params["longitude"].split(",") == [str(lon) for _, _, lon in CITIES]
    assert params["current"] == "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone"
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


def test_main_success_writes_csv(tmp_path, payload, capsys):
    path = tmp_path / "aqi.csv"
    session = FakeSession([make_response(200, payload), make_response(200, payload)])
    assert fetch.main(csv_path=path, session=session, sleep=lambda s: None) == 0
    assert fetch.main(csv_path=path, session=session, sleep=lambda s: None) == 0
    assert len(read_csv(path)) == 6  # second run deduped
    assert "Wrote 0 new row(s)" in capsys.readouterr().out


def test_main_exits_nonzero_on_failure(tmp_path):
    path = tmp_path / "aqi.csv"
    session = FakeSession([requests.ConnectionError("down")] * fetch.MAX_ATTEMPTS)
    assert fetch.main(csv_path=path, session=session, sleep=lambda s: None) == 1
    assert not path.exists()


def test_main_exits_nonzero_on_malformed_payload(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    session = FakeSession([make_response(200, payload[:3])])
    assert fetch.main(csv_path=path, session=session, sleep=lambda s: None) == 1
    assert not path.exists()
