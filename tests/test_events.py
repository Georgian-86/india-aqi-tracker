import csv
from datetime import datetime, timezone

import pytest

import events
from common import CITIES, EVENT_COLUMNS
from conftest import FakeSession, make_response

N = len(CITIES)
DELHI, MUMBAI = CITIES[0][0], CITIES[1][0]
M = events.MARGIN
# The fixture's current.time is 2026-09-23T08:45 IST = 03:15 UTC.
NOW = datetime(2026, 9, 23, 3, 20, tzinfo=timezone.utc)


def reading(city, aqi, time_ist="2026-09-24T15:45"):
    return {"time_ist": time_ist, "city": city, "us_aqi": str(aqi), "pm2_5": "40",
            "pm10": "60", "no2": "", "o3": "", "fetched_at_utc": "2026-09-24T10:20:00Z"}


@pytest.mark.parametrize("previous, aqi, expected", [
    (None, 42, True),  # first reading establishes the state
    ("Moderate", 100 + M - 1, False),  # just into USG, but within the margin
    ("Moderate", 100 + M, True),  # clearly USG
    ("Unhealthy for Sensitive Groups", 100 - M + 1, False),  # barely back to Moderate
    ("Unhealthy for Sensitive Groups", 100 - M, True),
    ("Moderate", 60, False),  # same category
    ("Good", 250, True),  # several categories at once
    ("Hazardous", 900, False),  # nothing above Hazardous
    ("Hazardous", 300 - M, True),
    ("Good", 0, False),  # nothing below Good
])
def test_changed_uses_margin_past_the_edge(previous, aqi, expected):
    assert events.changed(previous, aqi) is expected


def test_detect_logs_only_changes():
    state = {DELHI: "Unhealthy", MUMBAI: "Moderate"}
    readings = [reading(DELHI, 215), reading(MUMBAI, 70), reading(CITIES[2][0], 33)]
    found, skipped = events.detect(readings, state)
    # Delhi 215 is 15 past Unhealthy's edge; Mumbai stays; Bengaluru is new.
    assert [(e["city"], e["from_category"], e["to_category"]) for e in found] == [
        (DELHI, "Unhealthy", "Very Unhealthy"),
        (CITIES[2][0], "", "Good"),
    ]
    assert skipped == [] and found[0]["time_ist"] == "2026-09-24T15:45"


def test_detect_skips_missing_values():
    found, skipped = events.detect([reading(DELHI, "")], {})
    assert found == [] and skipped == [DELHI]


def test_last_categories_uses_latest_time_not_file_order():
    rows = [{"time_ist": "2026-09-24T12:45", "city": DELHI, "to_category": "Unhealthy"},
            {"time_ist": "2026-09-24T09:45", "city": DELHI, "to_category": "Moderate"}]
    assert events.last_categories(rows) == {DELHI: "Unhealthy"}


def test_summary():
    found, _ = events.detect([reading(DELHI, 215), reading(MUMBAI, 70)],
                             {DELHI: "Unhealthy"})
    assert events.summary(found) == (
        f"data: AQI change 2026-09-24 15:45 IST: {DELHI} → Very Unhealthy, {MUMBAI} Moderate")


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(tmp_path, payload, now=NOW):
    session = FakeSession([make_response(200, payload)])
    code = events.main(tmp_path / "events.csv", tmp_path / "msg.txt", session=session,
                       sleep=lambda s: None, now=now)
    return code, session


def test_main_first_run_then_steady_then_change(tmp_path, payload):
    code, session = run(tmp_path, payload)
    assert code == 0
    params = session.calls[0]["params"]
    assert "hourly" not in params and params["current"]  # small request
    first = read_csv(tmp_path / "events.csv")
    assert len(first) == N and all(r["from_category"] == "" for r in first)
    assert list(first[0]) == EVENT_COLUMNS
    assert (tmp_path / "msg.txt").read_text().startswith("data: AQI change 2026-09-23 08:45 IST")

    # Next run, same values: nothing logged, no commit message.
    (tmp_path / "msg.txt").unlink()
    for loc in payload:
        loc["current"]["time"] = "2026-09-23T11:45"
    assert run(tmp_path, payload, now=NOW.replace(hour=6, minute=20))[0] == 0
    assert len(read_csv(tmp_path / "events.csv")) == N
    assert not (tmp_path / "msg.txt").exists()

    # Delhi jumps well into Hazardous: one row, one message.
    payload[0]["current"]["time"] = "2026-09-23T14:45"
    payload[0]["current"]["us_aqi"] = 420
    for loc in payload[1:]:
        loc["current"]["time"] = "2026-09-23T14:45"
    assert run(tmp_path, payload, now=NOW.replace(hour=9, minute=20))[0] == 0
    rows = read_csv(tmp_path / "events.csv")
    assert len(rows) == N + 1 and rows[-1]["to_category"] == "Hazardous"
    assert "Delhi → Hazardous" in (tmp_path / "msg.txt").read_text()


def test_main_rerun_same_time_adds_nothing(tmp_path, payload):
    run(tmp_path, payload)
    before = (tmp_path / "events.csv").read_text()
    run(tmp_path, payload)
    assert (tmp_path / "events.csv").read_text() == before


def test_main_fails_on_stale_data(tmp_path, payload, capsys):
    code, _ = run(tmp_path, payload, now=NOW.replace(day=24))
    assert code == 1 and "Stale data" in capsys.readouterr().err
    assert not (tmp_path / "events.csv").exists()


def test_main_fails_on_network_error(tmp_path):
    import requests
    import fetch
    session = FakeSession([requests.ConnectionError("down")] * fetch.MAX_ATTEMPTS)
    assert events.main(tmp_path / "e.csv", session=session, sleep=lambda s: None,
                       now=NOW) == 1
