import csv
from datetime import datetime, timezone

import pytest
import requests

import fetch
from common import CITIES, COLUMNS, DAILY_COLUMNS, FORECAST_COLUMNS, HOURLY_COLUMNS
from conftest import FakeSession, make_response

FETCHED_AT = "2026-09-23T03:17:00Z"
N = len(CITIES)  # derive counts from CITIES so adding a city doesn't break tests
NAMES = [c for c, _, _ in CITIES]
# 03:17 UTC = 08:47 IST, two minutes after the fixture's current.time.
NOW = datetime(2026, 9, 23, 3, 17, tzinfo=timezone.utc)


def run_main(path, outcomes, now=NOW, daily_path=None):
    session = FakeSession(outcomes)
    daily_path = daily_path or path.with_name("aqi_daily.csv")
    return fetch.main(
        csv_path=path,
        daily_csv_path=daily_path,
        gases_csv_path=path.with_name("aqi_daily_gases.csv"),
        forecast_csv_path=path.with_name("aqi_forecast.csv"),
        hourly_csv_path=path.with_name("aqi_hourly.csv"),
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
    assert params["hourly"] == "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone"
    assert (params["past_days"], params["forecast_days"]) == ("1", "2")
    assert fetch.build_params(past_days=92)["past_days"] == "92"
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
    with pytest.raises(fetch.FetchError, match=f"Expected {N}"):
        fetch.parse_payload(payload[:-1], FETCHED_AT)


def test_append_creates_file_with_header(tmp_path, payload):
    path = tmp_path / "data" / "aqi.csv"
    written = fetch.append_rows(path, fetch.parse_payload(payload, FETCHED_AT))
    assert written == N
    lines = read_csv(path)
    assert lines[0] == COLUMNS
    assert len(lines) == N + 1


def test_append_same_day_is_idempotent(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    rows = fetch.parse_payload(payload, FETCHED_AT)
    assert fetch.append_rows(path, rows) == N
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
    assert fetch.append_rows(path, rows) == N - 2
    lines = read_csv(path)
    assert [line[1] for line in lines[1:]] == [c for c, _, _ in CITIES]
    assert sum(1 for line in lines if line == COLUMNS) == 1  # header once


def test_append_next_day_adds_rows(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    fetch.append_rows(path, fetch.parse_payload(payload, FETCHED_AT))
    for loc in payload:
        loc["current"]["time"] = "2026-09-24T08:45"
    assert fetch.append_rows(path, fetch.parse_payload(payload, FETCHED_AT)) == N
    assert len(read_csv(path)) == 2 * N + 1


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
    assert len(lines) == N + 1  # second run deduped
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
    assert [line[1] for line in read_csv(path)[1:]] == [c for c in NAMES if c != "Kolkata"]

    # Backup run later the same day gets Kolkata; only that row is added.
    payload[3]["current"]["us_aqi"] = 121
    assert run_main(path, [make_response(200, payload)]) == 0
    rows = read_csv(path)[1:]
    assert len(rows) == N
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
    assert skipped == ["Chennai 2026-09-22"]
    assert len(rows) == N - 1


def test_parse_daily_without_hourly_block_skips_all(payload):
    for loc in payload:
        del loc["hourly"]
    rows, skipped = fetch.parse_daily(payload, FETCHED_AT)
    assert rows == [] and len(skipped) == N


def test_main_writes_daily_csv_and_dedupes(tmp_path, payload):
    path, daily = tmp_path / "aqi.csv", tmp_path / "aqi_daily.csv"
    assert run_main(path, [make_response(200, payload)], daily_path=daily) == 0
    assert run_main(path, [make_response(200, payload)], daily_path=daily) == 0
    lines = read_csv(daily)
    assert lines[0] == DAILY_COLUMNS
    assert len(lines) == N + 1
    assert {line[0] for line in lines[1:]} == {"2026-09-22"}


def test_main_fails_but_keeps_snapshot_when_hourly_missing(tmp_path, payload):
    path, daily = tmp_path / "aqi.csv", tmp_path / "aqi_daily.csv"
    del payload[2]["hourly"]  # Bengaluru
    assert run_main(path, [make_response(200, payload)], daily_path=daily) == 1
    assert len(read_csv(path)) == N + 1  # snapshot fully stored
    assert "Bengaluru" not in [line[1] for line in read_csv(daily)]


def with_history(payload, days):
    """Rewrite each location's hourly block to cover `days` past days + today."""
    from datetime import timedelta

    start = datetime(2026, 9, 23) - timedelta(days=days)
    hours = (days + 1) * 24
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    for n, loc in enumerate(payload):
        # Day k (0 = oldest) has AQI 100 + 10*k + city index, flat all day.
        loc["hourly"] = {
            "time": times,
            "us_aqi": [100 + 10 * (h // 24) + n for h in range(hours)],
            "pm2_5": [50.0] * hours,
            "pm10": [80.0] * hours,
        }
    return payload


def test_parse_daily_backfill_covers_every_past_day(payload):
    rows, skipped = fetch.parse_daily(with_history(payload, 3), FETCHED_AT, days=3)
    assert skipped == []
    # Ordered by date, then in CITIES order.
    assert [(r["date"], r["city"]) for r in rows][:N + 1] == (
        [("2026-09-20", c) for c in NAMES] + [("2026-09-21", NAMES[0])]
    )
    assert len(rows) == 3 * N
    assert {r["date"] for r in rows} == {"2026-09-20", "2026-09-21", "2026-09-22"}
    by_key = {(r["date"], r["city"]): r for r in rows}
    assert by_key[("2026-09-22", "Mumbai")]["us_aqi_mean"] == "121.0"  # 100 + 10*2 + 1


def test_parse_daily_backfill_reports_gaps_per_day(payload):
    payload = with_history(payload, 3)
    for i in range(24, 48):  # wipe 2026-09-21 for Delhi
        payload[0]["hourly"]["us_aqi"][i] = None
    rows, skipped = fetch.parse_daily(payload, FETCHED_AT, days=3)
    assert skipped == ["Delhi 2026-09-21"]
    assert len(rows) == 3 * N - 1


def test_main_backfill_then_daily_run_dedupes(tmp_path, payload):
    path, daily = tmp_path / "aqi.csv", tmp_path / "aqi_daily.csv"
    session = FakeSession([make_response(200, with_history(payload, 5))])
    assert fetch.main(csv_path=path, daily_csv_path=daily, session=session,
                      gases_csv_path=tmp_path / "gases.csv",
                      forecast_csv_path=tmp_path / "forecast.csv",
                      hourly_csv_path=tmp_path / "hourly.csv",
                      sleep=lambda s: None, now=NOW, past_days=5) == 0
    assert session.calls[0]["params"]["past_days"] == "5"
    assert len(read_csv(daily)) == 1 + 5 * N
    # The normal daily run afterwards adds nothing new for yesterday.
    assert run_main(path, [make_response(200, with_history(payload, 1))], daily_path=daily) == 0
    assert len(read_csv(daily)) == 1 + 5 * N


@pytest.mark.parametrize("bad", ["0", "93", "-1"])
def test_cli_rejects_out_of_range_past_days(bad):
    with pytest.raises(SystemExit):
        fetch.cli(["--past-days", bad])


def test_cli_passes_past_days(monkeypatch):
    seen = {}
    monkeypatch.setattr(fetch, "main", lambda **kw: seen.update(kw) or 0)
    assert fetch.cli(["--past-days", "92"]) == 0
    assert seen == {"past_days": 92}
    assert fetch.cli([]) == 0
    assert seen == {"past_days": 1}


def test_parse_daily_gas_stats(payload):
    rows, _ = fetch.parse_daily(payload, FETCHED_AT)
    delhi = rows[0]
    hourly = payload[0]["hourly"]
    no2 = hourly["nitrogen_dioxide"][:24]
    o3 = hourly["ozone"][:24]
    assert delhi["no2_mean"] == f"{sum(no2) / 24:.1f}"
    best = max(sum(o3[i:i + 8]) / 8 for i in range(17))
    assert delhi["o3_max8h"] == f"{best:.1f}"


def test_o3_window_needs_complete_hours(payload):
    for i in range(0, 24, 7):  # a gap every 7 hours: no complete 8 h window
        payload[0]["hourly"]["ozone"][i] = None
    rows, _ = fetch.parse_daily(payload, FETCHED_AT)
    assert rows[0]["o3_max8h"] == ""


def test_main_writes_gases_csv_separately(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    assert run_main(path, [make_response(200, payload)]) == 0
    daily = read_csv(tmp_path / "aqi_daily.csv")
    gases = read_csv(tmp_path / "aqi_daily_gases.csv")
    assert daily[0] == DAILY_COLUMNS  # unchanged schema, gas fields not leaked
    assert gases[0] == ["date", "city", "no2_mean", "o3_max8h", "fetched_at_utc"]
    assert len(gases) == N + 1 and gases[1][:2] == ["2026-09-22", "Delhi"]


def test_backfill_fills_gases_for_days_already_in_daily_csv(tmp_path, payload):
    # Mirrors production: aqi_daily.csv already has the day, gases file doesn't.
    path, daily = tmp_path / "aqi.csv", tmp_path / "aqi_daily.csv"
    rows, _ = fetch.parse_daily(payload, FETCHED_AT)
    fetch.append_rows(daily, rows, DAILY_COLUMNS)
    assert run_main(path, [make_response(200, payload)], daily_path=daily) == 0
    assert len(read_csv(daily)) == N + 1  # nothing duplicated
    assert len(read_csv(tmp_path / "aqi_daily_gases.csv")) == N + 1  # gases filled in


# --- forecast ---------------------------------------------------------------

def test_parse_forecast_is_tomorrows_full_day(payload):
    rows, missing = fetch.parse_forecast(payload, FETCHED_AT)
    assert missing == []
    assert [r["city"] for r in rows] == [c for c, _, _ in CITIES]
    delhi = rows[0]
    assert (delhi["date"], delhi["issued"]) == ("2026-09-24", "2026-09-23")
    tomorrow = [v for v in payload[0]["hourly"]["us_aqi"][48:72] if v is not None]
    assert delhi["us_aqi_mean"] == f"{sum(tomorrow) / len(tomorrow):.1f}"
    assert delhi["us_aqi_max"] == str(max(tomorrow))


def test_parse_forecast_missing_hours(payload):
    for i in range(48, 72):
        payload[1]["hourly"]["us_aqi"][i] = None
    rows, missing = fetch.parse_forecast(payload, FETCHED_AT)
    assert missing == [CITIES[1][0]] and len(rows) == N - 1


def test_main_stores_forecast_first_issue_wins(tmp_path, payload, capsys):
    path = tmp_path / "aqi.csv"
    forecast = tmp_path / "aqi_forecast.csv"
    assert run_main(path, [make_response(200, payload)]) == 0
    rows = read_csv(forecast)
    assert rows[0] == FORECAST_COLUMNS and len(rows) == 1 + N
    # A later run (e.g. the backup cron) with a different forecast changes nothing.
    for loc in payload:
        loc["hourly"]["us_aqi"][48:72] = [999] * 24
    assert run_main(path, [make_response(200, payload)]) == 0
    assert read_csv(forecast) == rows


def test_missing_forecast_is_not_fatal(tmp_path, payload, capsys):
    for loc in payload:
        loc["hourly"]["us_aqi"][48:72] = [None] * 24
    assert run_main(tmp_path / "aqi.csv", [make_response(200, payload)]) == 0
    assert "WARNING: no forecast for" in capsys.readouterr().err


# --- hourly ------------------------------------------------------------------

def test_parse_hourly_keeps_only_completed_days(payload):
    rows = fetch.parse_hourly(payload, days=1)
    assert {r["date"] for r in rows} == {"2026-09-22"}  # not today, not tomorrow
    assert len(rows) == sum(
        v is not None for loc in payload for v in loc["hourly"]["us_aqi"][:24])
    first = rows[0]
    assert (first["hour"], first["city"]) == ("00", CITIES[0][0])
    assert first["us_aqi"] == str(payload[0]["hourly"]["us_aqi"][0])


def test_parse_hourly_skips_missing_hours(payload):
    payload[0]["hourly"]["us_aqi"][5] = None
    rows = fetch.parse_hourly(payload)
    assert not any(r["city"] == CITIES[0][0] and r["hour"] == "05" for r in rows)


def test_main_stores_hourly_and_dedupes(tmp_path, payload):
    path = tmp_path / "aqi.csv"
    assert run_main(path, [make_response(200, payload)]) == 0
    hourly = read_csv(tmp_path / "aqi_hourly.csv")
    assert hourly[0] == HOURLY_COLUMNS
    n = len(hourly)
    assert run_main(path, [make_response(200, payload)]) == 0
    assert len(read_csv(tmp_path / "aqi_hourly.csv")) == n
