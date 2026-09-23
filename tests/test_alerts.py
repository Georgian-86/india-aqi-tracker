import json

import pytest
import requests

import alerts
import fetch
from alerts import ALERT_AQI, CLEAR_AQI, MIN_STREAK, CityDay


class FakeGitHub:
    """In-memory stand-in for the GitHub REST endpoints alerts.py uses."""

    def __init__(self, fail_on=None):
        self.issues = {}  # number -> {"number", "title", "body", "state", "labels"}
        self.comments = {}  # number -> [body]
        self.calls = []
        self.fail_on = fail_on

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        path = url.split("/repos/owner/repo", 1)[1]
        self.calls.append((method, path))
        assert headers["Authorization"] == "Bearer t0ken"
        if self.fail_on == (method, path):
            return self._resp(500, {"message": "boom"})
        if method == "GET" and path == "/issues":
            assert params["labels"] == alerts.LABEL and params["state"] == "all"
            return self._resp(200, list(self.issues.values()))
        if method == "POST" and path == "/issues":
            n = len(self.issues) + 1
            self.issues[n] = {"number": n, "state": "open", **json}
            self.comments[n] = []
            return self._resp(201, self.issues[n])
        number = int(path.split("/")[2])
        if method == "PATCH":
            self.issues[number].update(json)
            return self._resp(200, self.issues[number])
        if method == "POST" and path.endswith("/comments"):
            self.comments[number].append(json["body"])
            return self._resp(201, {})
        raise AssertionError(f"unexpected call {method} {path}")

    @staticmethod
    def _resp(status, body):
        r = requests.Response()
        r.status_code = status
        r._content = json.dumps(body).encode()
        return r


ENV = {"GITHUB_TOKEN": "t0ken", "GITHUB_REPOSITORY": "owner/repo"}


def row(day, city, mean, peak="250"):
    return {"date": day, "city": city, "hours": "24", "us_aqi_mean": str(mean),
            "us_aqi_max": peak, "pm2_5_mean": "", "pm10_mean": "", "fetched_at_utc": "x"}


def write_daily(path, rows):
    fetch.append_rows(path, rows, fetch.DAILY_COLUMNS)


def run(tmp_path, gh, rows, name="d.csv"):
    path = tmp_path / name
    path.unlink(missing_ok=True)
    write_daily(path, rows)
    return alerts.main(path, env=ENV, session=gh)


# Levels defined relative to the thresholds, so re-tuning them doesn't break tests.
HIGH = ALERT_AQI + 20  # opens an alert (given MIN_STREAK days)
BAND = (CLEAR_AQI + ALERT_AQI) // 2  # between thresholds: an open alert stays open
LOW = CLEAR_AQI - 20  # closes an alert
CLEAN = 60


def days_from(start_day, values, city="Delhi"):
    """Rows for consecutive September days starting at start_day."""
    return [row(f"2026-09-{start_day + i:02d}", city, v) for i, v in enumerate(values)]


# --- pure logic ------------------------------------------------------------

def test_thresholds_are_ordered():
    assert CLEAR_AQI < ALERT_AQI and MIN_STREAK >= 1


def test_latest_days_streak_and_order():
    rows = [row("2026-09-20", "Delhi", HIGH), row("2026-09-22", "Delhi", HIGH + 5),
            row("2026-09-21", "Delhi", HIGH + 1), row("2026-09-19", "Delhi", BAND),
            row("2026-09-22", "Mumbai", CLEAN)]
    days = {d.city: d for d in alerts.latest_days(rows)}
    assert days["Delhi"] == CityDay("Delhi", "2026-09-22", float(HIGH + 5), "250", 3)
    assert days["Mumbai"].streak == 0
    assert "Chennai" not in days


@pytest.mark.parametrize("mean, streak, opens", [
    (ALERT_AQI - 1, MIN_STREAK, False),  # not high enough
    (ALERT_AQI, MIN_STREAK - 1, MIN_STREAK <= 1),  # high, but not for long enough
    (ALERT_AQI, MIN_STREAK, True),
    (620, MIN_STREAK + 5, True),
])
def test_plan_opens_only_after_streak_at_threshold(mean, streak, opens):
    actions = alerts.plan([CityDay("Delhi", "2026-09-22", mean, "700", streak)], {})
    assert [a.kind for a in actions] == (["open"] if opens else [])


def test_plan_open_issue_body_carries_markers():
    [a] = alerts.plan([CityDay("Delhi", "2026-09-22", 320, "410", MIN_STREAK)], {})
    assert a.title == "AQI alert: Delhi is Hazardous (2026-09-22)"
    assert f"for {MIN_STREAK} days running" in a.body
    assert alerts.city_marker("Delhi") in a.body
    assert alerts.dates_in([a.body]) == {"2026-09-22"}
    assert "CAMS via Open-Meteo" in a.body


def test_plan_hysteresis_keeps_issue_open_between_thresholds():
    body = alerts.city_marker("Delhi") + alerts.date_marker("2026-09-21")
    [a] = alerts.plan([CityDay("Delhi", "2026-09-22", BAND, "190", 0)], {"Delhi": (7, body)})
    assert a.kind == "comment" and a.issue == 7
    assert alerts.dates_in([a.new_issue_body]) == {"2026-09-21", "2026-09-22"}


def test_plan_closes_below_clear_threshold():
    body = alerts.city_marker("Delhi") + alerts.date_marker("2026-09-21")
    [a] = alerts.plan([CityDay("Delhi", "2026-09-22", CLEAR_AQI - 1, "160", 0)],
                      {"Delhi": (7, body)})
    assert a.kind == "close"
    assert f"Back below {alerts.aqi_category(CLEAR_AQI)} ({CLEAR_AQI})" in a.body


def test_plan_skips_day_already_reported():
    body = alerts.city_marker("Delhi") + alerts.date_marker("2026-09-22")
    day = CityDay("Delhi", "2026-09-22", HIGH, "310", MIN_STREAK)
    assert alerts.plan([day], {"Delhi": (7, body)}) == []


def test_plan_never_reopens_for_a_day_on_a_closed_issue():
    day = CityDay("Delhi", "2026-09-22", HIGH, "310", MIN_STREAK)
    assert alerts.plan([day], {}, {"Delhi": {"2026-09-22"}}) == []
    # ...but the next bad day opens a fresh alert.
    nxt = CityDay("Delhi", "2026-09-23", HIGH, "310", MIN_STREAK + 1)
    assert [a.kind for a in alerts.plan([nxt], {}, {"Delhi": {"2026-09-22"}})] == ["open"]


# --- end to end against the fake API ---------------------------------------

def test_episode_lifecycle(tmp_path):
    gh = FakeGitHub()
    history = [row("2026-09-01", "Mumbai", CLEAN)]
    delhi = [CLEAN] + [HIGH] * MIN_STREAK  # Sep 1 clean, then MIN_STREAK high days

    # Not yet a long enough streak: no issue.
    for n in range(2, len(delhi)):
        assert run(tmp_path, gh, history + days_from(1, delhi[:n])) == 0
        assert gh.issues == {}
    # Streak reached: issue opened, Mumbai untouched.
    history += days_from(1, delhi)
    assert run(tmp_path, gh, history) == 0
    assert len(gh.issues) == 1 and gh.issues[1]["state"] == "open"
    assert gh.issues[1]["labels"] == [alerts.LABEL]

    # Backup run the same day: nothing new.
    calls = len(gh.calls)
    assert run(tmp_path, gh, history) == 0
    assert gh.calls[calls:] == [("GET", "/issues")]

    # Next day between thresholds: one comment, still open.
    next_day = 1 + len(delhi)
    history += days_from(next_day, [BAND])
    assert run(tmp_path, gh, history) == 0
    assert gh.issues[1]["state"] == "open" and len(gh.comments[1]) == 1

    # Then below the clear threshold: closing comment and closed.
    history += days_from(next_day + 1, [LOW])
    assert run(tmp_path, gh, history) == 0
    assert gh.issues[1]["state"] == "closed"
    assert gh.issues[1]["state_reason"] == "completed"
    assert "closing" in gh.comments[1][-1]
    assert len(alerts.dates_in([gh.issues[1]["body"]])) == 3  # open day + 2 reported days

    # Re-run after closing: no reopen, no new issue.
    assert run(tmp_path, gh, history) == 0
    assert len(gh.issues) == 1


def test_manual_close_mid_episode_does_not_reopen_same_day(tmp_path):
    gh = FakeGitHub()
    history = days_from(1, [HIGH] * MIN_STREAK)
    run(tmp_path, gh, history)  # opens
    history += days_from(1 + MIN_STREAK, [HIGH])
    run(tmp_path, gh, history)  # that day recorded on the issue
    gh.issues[1]["state"] = "closed"  # someone closes it by hand
    assert run(tmp_path, gh, history) == 0
    assert len(gh.issues) == 1  # not reopened for the same day
    history += days_from(2 + MIN_STREAK, [HIGH])
    run(tmp_path, gh, history)
    assert len(gh.issues) == 2  # a new bad day does open a fresh alert


def test_one_issue_per_city(tmp_path):
    gh = FakeGitHub()
    rows = days_from(1, [HIGH] * MIN_STREAK) + days_from(1, [HIGH] * MIN_STREAK, "Kolkata")
    assert run(tmp_path, gh, rows) == 0
    assert sorted(i["title"].split()[2] for i in gh.issues.values()) == ["Delhi", "Kolkata"]


def test_api_error_exits_nonzero(tmp_path, capsys):
    gh = FakeGitHub(fail_on=("POST", "/issues"))
    assert run(tmp_path, gh, days_from(1, [HIGH] * MIN_STREAK)) == 1
    assert "HTTP 500" in capsys.readouterr().err


def test_dry_run_without_token(tmp_path, capsys):
    path = tmp_path / "d.csv"
    write_daily(path, days_from(1, [HIGH] * MIN_STREAK))
    assert alerts.main(path, env={}) == 0
    assert "would open: AQI alert: Delhi" in capsys.readouterr().out
